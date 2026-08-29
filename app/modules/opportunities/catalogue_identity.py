"""Deterministic catalogue identity for scholarship families and scoped variants."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass

CATALOGUE_IDENTITY_POLICY_VERSION = "catalogue-identity.v1"

_GENERIC_SUFFIXES = frozenset(
    {
        "award",
        "awards",
        "program",
        "programme",
        "programs",
        "programmes",
        "scheme",
        "schemes",
        "scholarship",
        "scholarships",
    }
)


def normalize_catalogue_alias(value: str | None) -> str | None:
    """Normalize presentation variants without fuzzy-merging distinct names."""

    if value is None:
        return None
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    tokens = normalized.split()
    while tokens and tokens[-1] in _GENERIC_SUFFIXES:
        tokens.pop()
    return "-".join(tokens) or None


@dataclass(frozen=True, slots=True)
class CatalogueIdentity:
    policy_version: str
    family_key: str
    route_key: str
    identity_key: str
    components: dict[str, str | None]


def build_catalogue_identity(
    *,
    provider_canonical_id: str,
    programme_family_id: str,
    programme_route_id: str,
    host_institution: str | None,
    destination_country: str,
    degree_level: str,
    cycle_id: str | None,
) -> CatalogueIdentity:
    components = {
        "provider": normalize_catalogue_alias(provider_canonical_id),
        "programme_family": normalize_catalogue_alias(programme_family_id),
        "programme_route": normalize_catalogue_alias(programme_route_id),
        "host_institution": normalize_catalogue_alias(host_institution),
        "destination_country": normalize_catalogue_alias(destination_country),
        "degree_level": normalize_catalogue_alias(degree_level),
        "cycle": normalize_catalogue_alias(cycle_id),
    }
    if any(
        not components[key]
        for key in (
            "provider",
            "programme_family",
            "programme_route",
            "destination_country",
            "degree_level",
        )
    ):
        raise ValueError("Catalogue identity is missing a mandatory component")

    family_components = {
        key: components[key] for key in ("provider", "programme_family")
    }
    route_components = {key: value for key, value in components.items() if key != "cycle"}
    return CatalogueIdentity(
        policy_version=CATALOGUE_IDENTITY_POLICY_VERSION,
        family_key=_identity_digest("family", family_components),
        route_key=_identity_digest("route", route_components),
        identity_key=_identity_digest("cycle", components),
        components=components,
    )


def _identity_digest(kind: str, components: dict[str, str | None]) -> str:
    encoded = json.dumps(
        {"kind": kind, **components},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "CATALOGUE_IDENTITY_POLICY_VERSION",
    "CatalogueIdentity",
    "build_catalogue_identity",
    "normalize_catalogue_alias",
]
