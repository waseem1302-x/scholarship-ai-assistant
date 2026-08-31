"""Named evidence trust domains layered over the existing deterministic source tiers."""

from __future__ import annotations

from enum import StrEnum


class EvidenceTrustDomain(StrEnum):
    """Purpose-specific evidence authority; separate from numeric source ranking."""

    OFFICIAL_FACTUAL = "official_factual"
    AUTHORITATIVE_PARTNER = "authoritative_partner"
    INSTITUTION_SPECIFIC_OFFICIAL = "institution_specific_official"
    EXPERIENTIAL_GUIDANCE = "experiential_guidance"
    UNSUPPORTED_UNVERIFIED = "unsupported_unverified"


OFFICIAL_FACTUAL_DOMAINS = frozenset(
    {
        EvidenceTrustDomain.OFFICIAL_FACTUAL,
        EvidenceTrustDomain.AUTHORITATIVE_PARTNER,
        EvidenceTrustDomain.INSTITUTION_SPECIFIC_OFFICIAL,
    }
)

_TRUST_DOMAIN_RANK = {
    EvidenceTrustDomain.OFFICIAL_FACTUAL: 1,
    EvidenceTrustDomain.AUTHORITATIVE_PARTNER: 2,
    EvidenceTrustDomain.INSTITUTION_SPECIFIC_OFFICIAL: 3,
    EvidenceTrustDomain.EXPERIENTIAL_GUIDANCE: 90,
    EvidenceTrustDomain.UNSUPPORTED_UNVERIFIED: 99,
}


def trust_domain_for_source_tier(
    *,
    is_official: bool,
    trust_tier: int | None,
) -> EvidenceTrustDomain:
    """Map the existing reviewed classifier tiers without rewriting historical source rows."""

    if not is_official:
        return EvidenceTrustDomain.UNSUPPORTED_UNVERIFIED
    if trust_tier == 1:
        return EvidenceTrustDomain.OFFICIAL_FACTUAL
    if trust_tier == 2:
        return EvidenceTrustDomain.AUTHORITATIVE_PARTNER
    if trust_tier == 3:
        return EvidenceTrustDomain.INSTITUTION_SPECIFIC_OFFICIAL
    return EvidenceTrustDomain.UNSUPPORTED_UNVERIFIED


def trust_domain_rank(domain: EvidenceTrustDomain | None) -> int:
    if domain is None:
        return 100
    return _TRUST_DOMAIN_RANK[domain]


__all__ = [
    "OFFICIAL_FACTUAL_DOMAINS",
    "EvidenceTrustDomain",
    "trust_domain_for_source_tier",
    "trust_domain_rank",
]
