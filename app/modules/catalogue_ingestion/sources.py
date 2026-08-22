"""Official-source classification and discovery-only provider boundaries."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from urllib.parse import urlparse

from app.modules.catalogue_ingestion.schemas import SeedCandidate

THIRD_PARTY_DIRECTORY_DOMAINS = {
    "scholarshipportal.com",
    "scholarships.com",
    "scholarshiproar.com",
    "opportunitiescorners.com",
    "wemakescholars.com",
}
GOVERNMENT_SUFFIXES = (".gov", ".gov.uk", ".gov.au", ".gc.ca", ".gov.cn", ".go.jp")
UNIVERSITY_HINT = re.compile(r"(?:^|\.)(?:edu|ac)\.[a-z]{2,}$|\.edu$")


class SourceClassificationReason(StrEnum):
    INVALID_HTTPS_URL = "invalid_https_url"
    THIRD_PARTY_DIRECTORY = "third_party_directory"
    REVIEWED_DOMAIN = "reviewed_domain"
    PROVIDER_WEBSITE = "provider_website"
    GOVERNMENT_SUFFIX = "government_suffix"
    UNIVERSITY_WEBSITE = "university_website"
    UNRESOLVED_EDUCATION_DOMAIN = "unresolved_education_domain"
    UNRESOLVED_OWNER = "unresolved_owner"


@dataclass(frozen=True)
class SourceClassification:
    is_official: bool
    trust_tier: int | None
    reason: str
    reason_code: SourceClassificationReason = SourceClassificationReason.UNRESOLVED_OWNER


@dataclass(frozen=True)
class DiscoveredUrl:
    url: str
    discovery_reason: str


class WebDiscoveryProvider(Protocol):
    def discover(self, seed: SeedCandidate, *, limit: int) -> list[DiscoveredUrl]: ...


class DisabledWebDiscoveryProvider:
    def discover(self, seed: SeedCandidate, *, limit: int) -> list[DiscoveredUrl]:
        del seed, limit
        return []


class SeedUrlDiscoveryProvider:
    """Use a URL supplied by seed material as a lead, never as truth."""

    def discover(self, seed: SeedCandidate, *, limit: int) -> list[DiscoveredUrl]:
        if limit < 1 or seed.possible_official_url is None:
            return []
        return [
            DiscoveredUrl(
                url=str(seed.possible_official_url),
                discovery_reason="operator seed supplied a possible official URL",
            )
        ]


class OfficialSourceClassifier:
    def classify(
        self,
        url: str,
        *,
        provider_website_url: str | None = None,
        university_website_url: str | None = None,
        reviewed_official_domains: set[str] | None = None,
    ) -> SourceClassification:
        host = _host(url)
        if not host:
            return SourceClassification(
                False,
                None,
                "URL has no valid HTTPS host",
                SourceClassificationReason.INVALID_HTTPS_URL,
            )
        if any(_same_or_subdomain(host, domain) for domain in THIRD_PARTY_DIRECTORY_DOMAINS):
            return SourceClassification(
                False,
                None,
                "known third-party scholarship directory",
                SourceClassificationReason.THIRD_PARTY_DIRECTORY,
            )

        reviewed = {domain.casefold().strip(".") for domain in reviewed_official_domains or set()}
        if any(_same_or_subdomain(host, domain) for domain in reviewed):
            return SourceClassification(
                True,
                1,
                "domain is on the reviewed provider allowlist",
                SourceClassificationReason.REVIEWED_DOMAIN,
            )

        provider_host = _host(provider_website_url)
        if provider_host and _same_registrable_family(host, provider_host):
            return SourceClassification(
                True,
                1,
                "domain matches the provider's canonical website",
                SourceClassificationReason.PROVIDER_WEBSITE,
            )

        if host.endswith(GOVERNMENT_SUFFIXES):
            return SourceClassification(
                True,
                2,
                "recognized government/ministry domain suffix",
                SourceClassificationReason.GOVERNMENT_SUFFIX,
            )

        university_host = _host(university_website_url)
        if university_host and _same_registrable_family(host, university_host):
            return SourceClassification(
                True,
                3,
                "domain matches the university's canonical website",
                SourceClassificationReason.UNIVERSITY_WEBSITE,
            )

        if UNIVERSITY_HINT.search(host):
            return SourceClassification(
                False,
                None,
                "education-domain syntax alone is insufficient without a resolved "
                "university identity",
                SourceClassificationReason.UNRESOLVED_EDUCATION_DOMAIN,
            )
        return SourceClassification(
            False,
            None,
            "domain is not deterministically tied to the provider",
            SourceClassificationReason.UNRESOLVED_OWNER,
        )


def _host(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return None
    return parsed.hostname.casefold().strip(".")


def _same_or_subdomain(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")


def _same_registrable_family(left: str, right: str) -> bool:
    return _same_or_subdomain(left, right) or _same_or_subdomain(right, left)
