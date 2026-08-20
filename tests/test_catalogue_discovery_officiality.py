import inspect
import uuid

import pytest

from app.modules.catalogue_ingestion.discovery import (
    DiscoveryObjectiveKind,
    DiscoveryScopeSnapshot,
    DiscoveryTargetIdentitySnapshot,
)
from app.modules.catalogue_ingestion.discovery_models import DiscoveryOfficialityStatus
from app.modules.catalogue_ingestion.discovery_officiality import (
    ContextualOfficialityClassifier,
    ReviewedOwnerDomain,
    SourceAuthorityClass,
)
from app.modules.opportunities.evidence_models import SourceOwnerType


def _provider_registration(
    *,
    provider_id: uuid.UUID | None = None,
    domain: str = "csc.edu.cn",
    owner_name: str = "China Scholarship Council",
) -> ReviewedOwnerDomain:
    return ReviewedOwnerDomain(
        domain=domain,
        owner_type=SourceOwnerType.PROVIDER,
        owner_name_snapshot=owner_name,
        authority_class=SourceAuthorityClass.CANONICAL_OWNER,
        review_reason="Operator verified the provider website.",
        provider_id=provider_id or uuid.uuid4(),
    )


def _institution_registration(
    institution_id: uuid.UUID,
    *,
    owner_name: str = "Tsinghua University",
) -> ReviewedOwnerDomain:
    return ReviewedOwnerDomain(
        domain="tsinghua.edu.cn",
        owner_type=SourceOwnerType.INSTITUTION,
        owner_name_snapshot=owner_name,
        authority_class=SourceAuthorityClass.SUPPORTING_INSTITUTION,
        review_reason="Operator verified the institution website.",
        institution_id=institution_id,
    )


def _target(**overrides) -> DiscoveryTargetIdentitySnapshot:
    values = {
        "scholarship_name": "Chinese Government Scholarship",
        "provider_name": "China Scholarship Council",
        "country": "China",
    }
    values.update(overrides)
    return DiscoveryTargetIdentitySnapshot(**values)


def _assess(
    url: str,
    *,
    registrations: tuple[ReviewedOwnerDomain, ...] = (),
    objective_kind: DiscoveryObjectiveKind = DiscoveryObjectiveKind.RESOLVE_CANONICAL_SOURCE,
    scope: DiscoveryScopeSnapshot | None = None,
    target: DiscoveryTargetIdentitySnapshot | None = None,
):
    return ContextualOfficialityClassifier().assess(
        url,
        objective_kind=objective_kind,
        scope=scope or DiscoveryScopeSnapshot(),
        target=target or _target(),
        reviewed_owner_domains=registrations,
    )


def test_reviewed_provider_root_and_subdomain_are_official() -> None:
    registration = _provider_registration()

    root = _assess("https://csc.edu.cn/scholarships", registrations=(registration,))
    subdomain = _assess("https://apply.csc.edu.cn/csc", registrations=(registration,))

    assert root.officiality_status is DiscoveryOfficialityStatus.OFFICIAL
    assert subdomain.officiality_status is DiscoveryOfficialityStatus.OFFICIAL
    assert root.owner_id == registration.provider_id
    assert root.canonical_domain == "csc.edu.cn"
    assert root.trust_tier == 1


def test_reviewed_institution_is_supporting_official_for_local_objective() -> None:
    institution_id = uuid.uuid4()
    registration = _institution_registration(institution_id)

    assessment = _assess(
        "https://admission.tsinghua.edu.cn/csc/deadline",
        registrations=(registration,),
        objective_kind=DiscoveryObjectiveKind.INSTITUTION_LOCAL_DEADLINE,
        scope=DiscoveryScopeSnapshot(institution_id=institution_id),
        target=_target(institution_name="Tsinghua University"),
    )

    assert assessment.officiality_status is DiscoveryOfficialityStatus.SUPPORTING_OFFICIAL
    assert assessment.owner_type is SourceOwnerType.INSTITUTION
    assert assessment.context_institution_id == institution_id
    assert assessment.trust_tier == 3


def test_known_third_party_directory_is_never_promoted_by_context() -> None:
    registration = _provider_registration(domain="scholarshipportal.com")

    assessment = _assess(
        "https://scholarshipportal.com/csc",
        registrations=(registration,),
    )

    assert assessment.officiality_status is DiscoveryOfficialityStatus.THIRD_PARTY
    assert assessment.owner_type is SourceOwnerType.UNKNOWN
    assert assessment.trust_tier is None


@pytest.mark.parametrize(
    "url",
    (
        "https://csc.edu.cn.evil.example/csc",
        "https://evil.example/csc.edu.cn/scholarship",
        "https://not-csc.edu.cn/csc",
    ),
)
def test_deceptive_host_and_path_text_do_not_prove_ownership(url: str) -> None:
    assessment = _assess(url, registrations=(_provider_registration(),))

    assert assessment.officiality_status is DiscoveryOfficialityStatus.UNRESOLVED
    assert assessment.reason_code == "NO_REVIEWED_OWNER_DOMAIN_MATCH"


def test_unreviewed_government_syntax_is_only_a_hint() -> None:
    assessment = _assess("https://unknown.gov.cn/csc")

    assert assessment.officiality_status is DiscoveryOfficialityStatus.UNRESOLVED


def test_specific_delegated_subdomain_does_not_inherit_parent_global_authority() -> None:
    provider_id = uuid.uuid4()
    canonical = _provider_registration(provider_id=provider_id)
    portal = ReviewedOwnerDomain(
        domain="apply.csc.edu.cn",
        owner_type=SourceOwnerType.PROVIDER,
        owner_name_snapshot="China Scholarship Council",
        authority_class=SourceAuthorityClass.APPLICATION_PORTAL,
        review_reason="Operator verified the scoped application portal.",
        provider_id=provider_id,
    )

    funding = _assess(
        "https://apply.csc.edu.cn/program",
        registrations=(canonical, portal),
        objective_kind=DiscoveryObjectiveKind.FUNDING_COVERAGE,
    )
    application = _assess(
        "https://apply.csc.edu.cn/program",
        registrations=(canonical, portal),
        objective_kind=DiscoveryObjectiveKind.APPLICATION_ROUTE,
    )

    assert funding.officiality_status is DiscoveryOfficialityStatus.UNRESOLVED
    assert funding.canonical_domain == "apply.csc.edu.cn"
    assert application.officiality_status is DiscoveryOfficialityStatus.SUPPORTING_OFFICIAL


def test_cross_owner_and_cross_domain_contexts_remain_unresolved() -> None:
    cross_owner = _assess(
        "https://csc.edu.cn/scholarships",
        registrations=(_provider_registration(),),
        target=_target(provider_name="MEXT"),
    )
    cross_domain = _assess(
        "https://studyinchina.example/csc",
        registrations=(_provider_registration(),),
    )

    assert cross_owner.officiality_status is DiscoveryOfficialityStatus.UNRESOLVED
    assert cross_owner.reason_code == "CROSS_PROVIDER_OWNER"
    assert cross_domain.officiality_status is DiscoveryOfficialityStatus.UNRESOLVED


def test_invalid_url_returns_explicit_policy_assessment() -> None:
    assessment = _assess("http://csc.edu.cn/scholarships")

    assert assessment.officiality_status is DiscoveryOfficialityStatus.REJECTED_URL_POLICY
    assert assessment.reason_code == "URL_POLICY_URL_SCHEME_NOT_ALLOWED"
    assert assessment.normalized_url is None


def test_context_hash_is_order_independent_and_changes_with_objective() -> None:
    provider = _provider_registration()
    institution_id = uuid.uuid4()
    institution = _institution_registration(institution_id)
    local_scope = DiscoveryScopeSnapshot(institution_id=institution_id)
    local_target = _target(institution_name="Tsinghua University")

    first = _assess(
        "https://tsinghua.edu.cn/csc",
        registrations=(provider, institution),
        objective_kind=DiscoveryObjectiveKind.INSTITUTION_LOCAL_REQUIREMENTS,
        scope=local_scope,
        target=local_target,
    )
    reordered = _assess(
        "https://tsinghua.edu.cn/csc",
        registrations=(institution, provider),
        objective_kind=DiscoveryObjectiveKind.INSTITUTION_LOCAL_REQUIREMENTS,
        scope=local_scope,
        target=local_target,
    )
    umbrella = _assess(
        "https://tsinghua.edu.cn/csc",
        registrations=(provider, institution),
    )

    assert first.assessment_context_hash == reordered.assessment_context_hash
    assert first.officiality_status is DiscoveryOfficialityStatus.SUPPORTING_OFFICIAL
    assert umbrella.officiality_status is DiscoveryOfficialityStatus.UNRESOLVED
    assert first.assessment_context_hash != umbrella.assessment_context_hash


def test_search_rank_and_title_are_not_classifier_inputs() -> None:
    parameters = inspect.signature(ContextualOfficialityClassifier.assess).parameters

    assert "provider_rank" not in parameters
    assert "minimal_title" not in parameters


@pytest.mark.parametrize("domain", ("https://csc.edu.cn", "csc.edu.cn/path", "csc.edu.cn?x=1"))
def test_reviewed_owner_domain_requires_a_bare_dns_name(domain: str) -> None:
    with pytest.raises(ValueError, match="bare public DNS name"):
        _provider_registration(domain=domain)
