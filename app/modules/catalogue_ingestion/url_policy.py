"""Shared deterministic URL normalization policies for catalogue acquisition."""

from __future__ import annotations

import ipaddress
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

MAX_CATALOGUE_URL_LENGTH = 2048

_TRACKING_QUERY_KEYS = frozenset(
    {
        "_ga",
        "dclid",
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
        "msclkid",
    }
)
_AUTH_PATH_CUES = re.compile(
    r"(?:^|/)(?:account|auth|authenticate|captcha|idp|login|logout|session|signin|sign-in|sso)"
    r"(?:[.;/]|$)",
    re.IGNORECASE,
)
_AUTH_QUERY_KEYS = frozenset({"execution", "jsessionid", "samlrequest", "session", "sessionid"})
_AUTH_PATH_PARAMETER = re.compile(r";jsessionid(?:=|/|$)", re.IGNORECASE)
_DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_INTERNAL_HOST_SUFFIXES = (
    ".home",
    ".internal",
    ".lan",
    ".local",
    ".localdomain",
    ".localhost",
)
_PERCENT_ESCAPE = re.compile(r"%[0-9a-fA-F]{2}")


class URLRejectionCode(StrEnum):
    EMPTY = "url_empty"
    TOO_LONG = "url_too_long"
    MALFORMED = "url_malformed"
    UNSUPPORTED_SCHEME = "url_scheme_not_allowed"
    CREDENTIALS = "url_credentials_not_allowed"
    INVALID_HOST = "url_host_invalid"
    INTERNAL_HOST = "url_internal_host_not_allowed"
    PRIVATE_LITERAL = "url_private_literal_not_allowed"
    INVALID_PORT = "url_port_invalid"
    AUTHENTICATION_TARGET = "url_authentication_target_not_allowed"


@dataclass(frozen=True, slots=True)
class URLNormalizationPolicy:
    allowed_schemes: frozenset[str]
    reject_non_public_hosts: bool
    reject_authentication_targets: bool
    max_length: int = MAX_CATALOGUE_URL_LENGTH

    def __post_init__(self) -> None:
        if not self.allowed_schemes or any(
            scheme not in {"http", "https"} for scheme in self.allowed_schemes
        ):
            raise ValueError("URL policy schemes must be a non-empty HTTP/HTTPS subset")
        if not 1 <= self.max_length <= MAX_CATALOGUE_URL_LENGTH:
            raise ValueError(f"URL policy length must be between 1 and {MAX_CATALOGUE_URL_LENGTH}")


@dataclass(frozen=True, slots=True)
class NormalizedURL:
    value: str
    scheme: str
    host: str
    port: int | None


@dataclass(frozen=True, slots=True)
class URLNormalizationResult:
    normalized: NormalizedURL | None
    rejection_code: URLRejectionCode | None

    @property
    def accepted(self) -> bool:
        return self.normalized is not None


COMPARISON_URL_POLICY = URLNormalizationPolicy(
    allowed_schemes=frozenset({"http", "https"}),
    reject_non_public_hosts=False,
    reject_authentication_targets=False,
)

CRAWL_URL_POLICY = URLNormalizationPolicy(
    allowed_schemes=frozenset({"https"}),
    reject_non_public_hosts=True,
    reject_authentication_targets=False,
)

DISCOVERY_LEAD_URL_POLICY = URLNormalizationPolicy(
    allowed_schemes=frozenset({"https"}),
    reject_non_public_hosts=True,
    reject_authentication_targets=True,
)


def normalize_catalogue_url(
    value: str | None,
    *,
    policy: URLNormalizationPolicy,
) -> URLNormalizationResult:
    if value is None or not value.strip():
        return _rejected(URLRejectionCode.EMPTY)
    candidate = value.strip()
    if len(candidate) > policy.max_length:
        return _rejected(URLRejectionCode.TOO_LONG)
    if any(
        character.isspace() or unicodedata.category(character) == "Cc" for character in candidate
    ):
        return _rejected(URLRejectionCode.MALFORMED)

    try:
        parsed = urlsplit(candidate)
        scheme = parsed.scheme.casefold()
        raw_host = parsed.hostname
        username = parsed.username
        password = parsed.password
    except (UnicodeError, ValueError):
        return _rejected(URLRejectionCode.MALFORMED)
    if scheme not in policy.allowed_schemes:
        return _rejected(URLRejectionCode.UNSUPPORTED_SCHEME)
    if username is not None or password is not None:
        return _rejected(URLRejectionCode.CREDENTIALS)
    if not raw_host:
        return _rejected(URLRejectionCode.INVALID_HOST)

    host_result = _normalize_host(raw_host, reject_non_public=policy.reject_non_public_hosts)
    if isinstance(host_result, URLRejectionCode):
        return _rejected(host_result)
    host, is_ipv6 = host_result

    try:
        port = parsed.port
    except ValueError:
        return _rejected(URLRejectionCode.INVALID_PORT)
    if port is not None and port < 1:
        return _rejected(URLRejectionCode.INVALID_PORT)

    if not _valid_percent_escapes(parsed.path) or not _valid_percent_escapes(parsed.query):
        return _rejected(URLRejectionCode.MALFORMED)
    path = _normalize_path(parsed.path)
    try:
        query_pairs = parse_qsl(parsed.query, keep_blank_values=True, max_num_fields=100)
    except ValueError:
        return _rejected(URLRejectionCode.MALFORMED)
    if policy.reject_authentication_targets and _is_authentication_target(path, query_pairs):
        return _rejected(URLRejectionCode.AUTHENTICATION_TARGET)

    filtered_pairs = [
        (key, query_value) for key, query_value in query_pairs if not _is_tracking_key(key)
    ]
    filtered_pairs.sort(key=lambda pair: (pair[0].casefold(), pair[0], pair[1]))
    query = urlencode(filtered_pairs, doseq=True)

    default_port = (scheme == "https" and port == 443) or (scheme == "http" and port == 80)
    rendered_host = f"[{host}]" if is_ipv6 else host
    netloc = rendered_host if port is None or default_port else f"{rendered_host}:{port}"
    normalized_value = urlunsplit((scheme, netloc, path, query, ""))
    if len(normalized_value) > policy.max_length:
        return _rejected(URLRejectionCode.TOO_LONG)
    return URLNormalizationResult(
        normalized=NormalizedURL(
            value=normalized_value,
            scheme=scheme,
            host=host,
            port=None if default_port else port,
        ),
        rejection_code=None,
    )


def normalize_comparison_url(value: str | None) -> str | None:
    result = normalize_catalogue_url(value, policy=COMPARISON_URL_POLICY)
    return result.normalized.value if result.normalized is not None else None


def normalize_crawl_url_identity(value: str | None) -> str | None:
    result = normalize_catalogue_url(value, policy=CRAWL_URL_POLICY)
    return result.normalized.value if result.normalized is not None else None


def normalize_discovery_lead_url(value: str | None) -> URLNormalizationResult:
    return normalize_catalogue_url(value, policy=DISCOVERY_LEAD_URL_POLICY)


def is_authentication_or_session_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        query_pairs = parse_qsl(parsed.query, keep_blank_values=True, max_num_fields=100)
    except ValueError:
        return True
    return _is_authentication_target(parsed.path, query_pairs)


def _normalize_host(
    value: str,
    *,
    reject_non_public: bool,
) -> tuple[str, bool] | URLRejectionCode:
    host = unicodedata.normalize("NFKC", value).casefold().strip(".")
    if not host or "%" in host:
        return URLRejectionCode.INVALID_HOST
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if re.fullmatch(r"[0-9.]+", host):
            return URLRejectionCode.INVALID_HOST
        try:
            host = host.encode("idna").decode("ascii").casefold()
        except UnicodeError:
            return URLRejectionCode.INVALID_HOST
        labels = host.split(".")
        if len(host) > 253 or any(not _DNS_LABEL.fullmatch(label) for label in labels):
            return URLRejectionCode.INVALID_HOST
        if reject_non_public and (
            len(labels) < 2
            or host in {"localhost", "localhost.localdomain"}
            or host.endswith(_INTERNAL_HOST_SUFFIXES)
        ):
            return URLRejectionCode.INTERNAL_HOST
        return host, False

    if reject_non_public and not _is_public_address(address):
        return URLRejectionCode.PRIVATE_LITERAL
    return address.compressed, address.version == 6


def _is_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return not (
        not address.is_global
        or address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def _normalize_path(value: str) -> str:
    path = quote(value or "/", safe="/!$&'()*+,-.:;=@_~%")
    path = _PERCENT_ESCAPE.sub(lambda match: match.group(0).upper(), path)
    return path.rstrip("/") or "/"


def _valid_percent_escapes(value: str) -> bool:
    index = 0
    while True:
        index = value.find("%", index)
        if index < 0:
            return True
        if not _PERCENT_ESCAPE.match(value, index):
            return False
        index += 3


def _is_authentication_target(path: str, query_pairs: list[tuple[str, str]]) -> bool:
    decoded_path = unicodedata.normalize("NFKC", unquote(unquote(path)))
    if _AUTH_PATH_CUES.search(decoded_path) or _AUTH_PATH_PARAMETER.search(decoded_path):
        return True
    return any(unquote(unquote(key)).casefold() in _AUTH_QUERY_KEYS for key, _ in query_pairs)


def _is_tracking_key(value: str) -> bool:
    lowered = value.casefold()
    return lowered.startswith("utm_") or lowered in _TRACKING_QUERY_KEYS


def _rejected(code: URLRejectionCode) -> URLNormalizationResult:
    return URLNormalizationResult(normalized=None, rejection_code=code)


__all__ = [
    "COMPARISON_URL_POLICY",
    "CRAWL_URL_POLICY",
    "DISCOVERY_LEAD_URL_POLICY",
    "MAX_CATALOGUE_URL_LENGTH",
    "NormalizedURL",
    "URLNormalizationPolicy",
    "URLNormalizationResult",
    "URLRejectionCode",
    "is_authentication_or_session_url",
    "normalize_catalogue_url",
    "normalize_comparison_url",
    "normalize_crawl_url_identity",
    "normalize_discovery_lead_url",
]
