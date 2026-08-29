from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from urllib.parse import urljoin

import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.core.errors import AppError
from app.modules.catalogue_ingestion.acquisition_bundle import (
    ACQUISITION_BUNDLE_POLICY_VERSION,
    AcquisitionSourceRole,
    build_acquisition_bundle_summary,
    classify_acquisition_source,
)
from app.modules.catalogue_ingestion.claim_provider import FakeClaimProvider
from app.modules.catalogue_ingestion.claim_schemas import (
    ClaimExtractionOutput,
    ClaimObjective,
    ClaimResolution,
)
from app.modules.catalogue_ingestion.models import (
    CandidateStatus,
    CatalogueCandidate,
    IngestionMode,
)
from app.modules.catalogue_ingestion.service import CatalogueIngestionService
from app.modules.opportunities.models import Provider
from app.modules.opportunities.source_monitor import FetchedLink, FetchedSource, SourceFetchError

FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "catalogue_acquisition"
    / "three_family_source_bundles.v1.json"
)


def test_comprehensive_official_source_can_cover_all_core_bundle_roles() -> None:
    decision = classify_acquisition_source(
        source_url="https://official.test/scholarship",
        source_text=(
            "Scholarship overview and funding benefits. Eligibility and academic requirements. "
            "Application deadline and intake dates. How to apply through the application process. "
            "Required documents and supporting document checklist."
        ),
        is_root=True,
    )
    summary = build_acquisition_bundle_summary(
        artifacts=[
            {
                "artifact_id": "artifact-1",
                "source_id": "source-1",
                "url": "https://official.test/scholarship",
                "content_hash": "a" * 64,
                "content_type": "text/html",
                "role": decision.role.value,
                "covered_roles": [role.value for role in decision.covered_roles],
            }
        ]
    )

    assert summary["complete"] is True
    assert summary["gaps"] == []
    assert set(summary["covered_roles"]) >= {
        role.value
        for role in (
            AcquisitionSourceRole.IDENTITY_OVERVIEW,
            AcquisitionSourceRole.FUNDING_BENEFITS,
            AcquisitionSourceRole.ELIGIBILITY,
            AcquisitionSourceRole.DATES_CYCLE,
            AcquisitionSourceRole.APPLICATION_PROCESS,
            AcquisitionSourceRole.REQUIRED_DOCUMENTS,
        )
    }


def test_degree_programme_document_is_classified_as_programme_annex() -> None:
    decision = classify_acquisition_source(
        source_url="https://programme.example/attachment/123/download",
        source_text=(
            "Bachelor's Track Program. List of degree programs. "
            "Applied Mathematics and Computer Science."
        ),
    )

    assert decision.role is AcquisitionSourceRole.PROGRAMME_COURSE_ANNEX


def test_large_official_bundle_allows_sixty_artifacts() -> None:
    settings = Settings(catalogue_ai_max_pages_per_candidate=60)
    artifacts = [
        {
            "artifact_id": f"artifact-{index}",
            "source_id": f"source-{index}",
            "url": f"https://programme.example/subject/{index}",
            "content_hash": f"{index:064x}",
            "content_type": "text/html",
            "role": AcquisitionSourceRole.PROGRAMME_COURSE_ANNEX.value,
            "covered_roles": [AcquisitionSourceRole.PROGRAMME_COURSE_ANNEX.value],
        }
        for index in range(settings.catalogue_ai_max_pages_per_candidate)
    ]

    summary = build_acquisition_bundle_summary(artifacts=artifacts)

    assert summary["accepted_artifact_count"] == 60


def _fixture() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _fetched(url: str, text: str, *, links: tuple[FetchedLink, ...] = ()) -> FetchedSource:
    digest = hashlib.sha256(text.encode()).hexdigest()
    return FetchedSource(
        url=url,
        final_url=url,
        content_hash=digest,
        excerpt_text=text,
        section_label="Scholarship",
        bytes_read=len(text.encode()),
        normalized_text=text,
        normalized_content_hash=digest,
        content_type="text/html",
        links=links,
    )


class _FixtureFetcher:
    def __init__(self, family: dict[str, object]) -> None:
        root_url = str(family["root_url"])
        pages = list(family["pages"])
        resolved: list[tuple[str, str]] = []
        for index, (location, text) in enumerate(pages):
            url = (
                root_url
                if index == 0
                else str(location)
                if str(location).startswith("https://")
                else urljoin(root_url, str(location))
            )
            resolved.append((url, str(text)))
        root = resolved[0]
        self.responses = {
            url: _fetched(
                url,
                text,
                links=(
                    tuple(
                        FetchedLink(url=child_url, text=child_text)
                        for child_url, child_text in resolved[1:]
                    )
                    if url == root[0]
                    else ()
                ),
            )
            for url, text in resolved
        }
        self.calls: list[str] = []

    def fetch(self, url: str) -> FetchedSource:
        return self.fetch_with_limit(url, max_bytes=10_000_000)

    def fetch_with_limit(self, url: str, *, max_bytes: int) -> FetchedSource:
        self.calls.append(url)
        result = self.responses[url]
        if result.bytes_read > max_bytes:
            raise SourceFetchError("crawl_byte_budget_exceeded")
        return result


def _settings(domains: set[str]) -> Settings:
    return Settings(
        env="test",
        database_url="sqlite+pysqlite:///:memory:",
        jwt_secret="test-secret-that-is-at-least-32-characters-long",
        catalogue_bounded_crawling_enabled=True,
        catalogue_ai_max_pages_per_candidate=10,
        catalogue_reviewed_official_domains=",".join(sorted(domains)),
        source_monitor_per_host_interval_seconds=0,
    )


def _typed_value(value: object) -> dict[str, object | None]:
    result: dict[str, object | None] = {
        "string_value": None,
        "decimal_value": None,
        "integer_value": None,
        "boolean_value": None,
        "string_list_value": None,
    }
    if isinstance(value, bool):
        result["boolean_value"] = value
    elif isinstance(value, int):
        result["integer_value"] = value
    elif isinstance(value, list):
        result["string_list_value"] = value
    else:
        result["string_value"] = value
    return result


def _claim(
    text: str,
    entity_type: str,
    entity_key: str,
    field_path: str,
    value: object,
    excerpt: str,
    *,
    programme_key: str | None = None,
    track_key: str | None = None,
) -> dict[str, object]:
    start = text.index(excerpt)
    return {
        "entity_type": entity_type,
        "entity_key": entity_key,
        "field_path": field_path,
        "value": _typed_value(value),
        "scope": {
            "cycle_key": "2027",
            "track_key": track_key,
            "institution_key": None,
            "programme_key": programme_key,
        },
        "excerpt": excerpt,
        "excerpt_start": start,
        "excerpt_end": start + len(excerpt),
        "basis": "explicit",
    }


def _claims_for_fixture(
    family: dict[str, object], source_url: str, text: str
) -> ClaimExtractionOutput:
    name = str(family["name"])
    provider = str(family["provider"])
    country = str(family["country_code"])
    programme = str(family["programme"])
    claims: list[dict[str, object]] = []
    if source_url.endswith("/overview"):
        claims = [
            _claim(text, "scholarship", "scholarship", "name", name, name),
            _claim(text, "scholarship", "scholarship", "provider_name", provider, provider),
            _claim(
                text,
                "scholarship",
                "scholarship",
                "country_code",
                country,
                f"study in {country}",
            ),
            _claim(
                text,
                "scholarship",
                "scholarship",
                "degree_levels",
                ["masters"],
                "masters level",
            ),
            _claim(text, "cycle", "2027", "intake_year", 2027, "2027 intake"),
            _claim(
                text,
                "programme",
                "course",
                "name",
                programme,
                programme,
                programme_key="course",
            ),
            _claim(
                text,
                "programme",
                "course",
                "degree_levels",
                ["masters"],
                "masters level",
                programme_key="course",
            ),
            _claim(
                text,
                "programme",
                "course",
                "description",
                f"{programme} at masters level",
                f"{programme} at masters level",
                programme_key="course",
            ),
        ]
    elif source_url.endswith("/funding"):
        claims = [
            _claim(
                text,
                "funding",
                "tuition",
                "component_type",
                "tuition",
                "tuition is fully covered",
            ),
            _claim(
                text,
                "funding",
                "tuition",
                "coverage_status",
                "confirmed",
                "tuition is fully covered",
            ),
        ]
    elif source_url.endswith("/eligibility"):
        excerpt = "applicants must hold a bachelor's degree"
        claims = [
            _claim(text, "eligibility", "degree", "rule_type", "academic_background", excerpt),
            _claim(text, "eligibility", "degree", "value", "bachelors", excerpt),
            _claim(text, "eligibility", "degree", "condition", "required", excerpt),
        ]
    elif source_url.endswith("/dates"):
        claims = [
            _claim(
                text,
                "deadline",
                "application",
                "deadline_type",
                "application_submission",
                "Application deadline 2027-05-15",
            ),
            _claim(
                text,
                "deadline",
                "application",
                "deadline_at",
                "2027-05-15",
                "Application deadline 2027-05-15",
            ),
            _claim(
                text,
                "step",
                "submit",
                "title",
                "Submit the application",
                "Submit the application",
            ),
        ]
    elif source_url.endswith("/apply"):
        claims = [
            _claim(
                text,
                "track",
                "online",
                "name",
                "Online Application",
                "Online Application",
                track_key="online",
            ),
            _claim(
                text,
                "track",
                "online",
                "application_method",
                "online",
                "Apply online",
                track_key="online",
            ),
            _claim(
                text,
                "track",
                "online",
                "application_url",
                source_url,
                source_url,
                track_key="online",
            ),
        ]
    elif source_url.endswith("/documents"):
        claims = [
            _claim(text, "document", "passport", "name", "Passport", "Passport"),
            _claim(text, "document", "passport", "required", True, "Passport is required"),
            _claim(text, "document", "passport", "copy_count", 1, "one certified copy"),
            _claim(
                text,
                "document",
                "passport",
                "certification_requirement",
                "certified",
                "certified copy",
            ),
        ]
    for claim in claims:
        scope = claim["scope"]
        assert isinstance(scope, dict)
        scope["country_code"] = country
        scope["programme_family_key"] = str(family["id"])
    return ClaimExtractionOutput.model_validate(
        {
            "claims": claims,
            "unknown_objectives": [],
            "conflicts": [],
            "warnings": [],
        }
    )


class _RecordingClaimProvider(FakeClaimProvider):
    def __init__(self, family: dict[str, object]) -> None:
        super().__init__(lambda url, text: _claims_for_fixture(family, url, text))
        self.invocations: list[tuple[str, ClaimObjective]] = []

    def extract_claims(
        self,
        *,
        source_url,
        source_text,
        objective=ClaimObjective.IDENTITY,
        source_links=None,
    ):
        self.invocations.append((source_url, objective))
        return super().extract_claims(
            source_url=source_url,
            source_text=source_text,
            objective=objective,
            source_links=source_links,
        )


def _phase3_settings(domains: set[str]) -> Settings:
    return Settings(
        env="test",
        database_url="sqlite+pysqlite:///:memory:",
        jwt_secret="test-secret-that-is-at-least-32-characters-long",
        catalogue_ai_ingestion_enabled=True,
        catalogue_ai_provider="azure_openai",
        catalogue_ai_endpoint="https://example.openai.azure.com",
        catalogue_ai_model="structured-output-deployment",
        catalogue_ai_input_cost_per_million=Decimal("1"),
        catalogue_ai_output_cost_per_million=Decimal("2"),
        catalogue_ai_max_calls_per_run=20,
        catalogue_bounded_crawling_enabled=True,
        catalogue_source_routing_enabled=True,
        catalogue_ai_max_pages_per_candidate=6,
        catalogue_reviewed_official_domains=",".join(sorted(domains)),
        source_monitor_per_host_interval_seconds=0,
    )


@pytest.mark.parametrize("family_index", [0, 1, 2])
def test_three_family_candidate_only_paths_build_reviewable_complete_bundles(
    db_session, tmp_path: Path, family_index: int
) -> None:
    family = _fixture()["families"][family_index]
    assert isinstance(family, dict)
    fetcher = _FixtureFetcher(family)
    domains = {"csc-fixture.test", "daad-fixture.test", "erasmus-fixture.test"}
    domains.add("consortium-fixture.test")
    service = CatalogueIngestionService(db_session, _settings(domains), fetcher=fetcher)

    if family_index == 2:
        provider_name = "Synthetic Erasmus Consortium"
        db_session.add(
            Provider(
                name=provider_name,
                website_url="https://consortium-fixture.test",
            )
        )
        db_session.commit()
        run = service.create_run_from_url(
            str(family["root_url"]),
            target_name=str(family["name"]),
            provider=provider_name,
            mode=IngestionMode.CANDIDATE_ONLY,
            dry_run=True,
        )
    else:
        seed_path = tmp_path / f"{family['id']}.json"
        seed_path.write_text(
            json.dumps(
                [
                    {
                        "name": family["name"],
                        "possible_official_url": family["root_url"],
                    }
                ]
            ),
            encoding="utf-8",
        )
        run = service.create_run_from_source(
            str(seed_path), mode=IngestionMode.CANDIDATE_ONLY, dry_run=True
        )

    completed = service.process_run(run.id, worker_id=f"phase2-{family['id']}")
    candidate = db_session.scalar(
        select(CatalogueCandidate).where(CatalogueCandidate.run_id == run.id)
    )
    assert candidate is not None
    bundle = candidate.acquisition_bundle
    assert completed.model_calls == 0
    assert len(fetcher.calls) == len(family["pages"])
    assert bundle["policy_version"] == ACQUISITION_BUNDLE_POLICY_VERSION
    assert bundle["accepted_artifact_count"] == len(family["pages"])
    assert bundle["reviewable"] is True
    assert bundle["complete"] is True
    assert bundle["gaps"] == []
    assert set(bundle["covered_roles"]) == {
        role.value
        for role in AcquisitionSourceRole
        if role not in {
            AcquisitionSourceRole.UNKNOWN,
            AcquisitionSourceRole.COUNTRY_ROUTE,
            AcquisitionSourceRole.PROGRAMME_COURSE_ANNEX,
        }
    }
    operator_status = service.run_status(run.id)
    operator_candidate = operator_status.candidates[0]
    assert operator_candidate.acquisition_bundle == bundle
    artifact_roles = {
        artifact.acquisition_role
        for source in operator_candidate.sources
        for artifact in source.artifacts
    }
    assert artifact_roles == set(bundle["covered_roles"])
    assert all(
        artifact.acquisition_role_classifier_version == ACQUISITION_BUNDLE_POLICY_VERSION
        for source in operator_candidate.sources
        for artifact in source.artifacts
    )


def test_bundle_reports_blocked_objective_and_budget_exhaustion() -> None:
    summary = build_acquisition_bundle_summary(
        artifacts=[
            {
                "artifact_id": "artifact-1",
                "source_id": "source-1",
                "url": "https://official.test/overview",
                "content_hash": "a" * 64,
                "content_type": "text/html",
                "role": AcquisitionSourceRole.IDENTITY_OVERVIEW.value,
            }
        ],
        blocked_urls=[("https://official.test/deadline", "source_access_denied")],
        budget_exhausted=True,
    )

    assert "deadline_source_blocked" in summary["gaps"]
    assert "funding_source_missing" in summary["gaps"]
    assert "acquisition_budget_exhausted" in summary["gaps"]
    assert summary["complete"] is False


@pytest.mark.parametrize("family_index", [0, 1, 2])
def test_three_family_seed_paths_extract_per_artifact_and_objective_from_fixtures(
    db_session, tmp_path: Path, family_index: int
) -> None:
    family = _fixture()["families"][family_index]
    assert isinstance(family, dict)
    domains = {"csc-fixture.test", "daad-fixture.test", "erasmus-fixture.test"}
    if family_index == 2:
        domains.add("consortium-fixture.test")
        db_session.add(
            Provider(
                name=str(family["provider"]),
                website_url="https://consortium-fixture.test",
            )
        )
        db_session.commit()
    provider = _RecordingClaimProvider(family)
    service = CatalogueIngestionService(
        db_session,
        _phase3_settings(domains),
        fetcher=_FixtureFetcher(family),
        claim_extractor=provider,
    )
    seed_path = tmp_path / f"phase3-{family['id']}.json"
    seed_path.write_text(
        json.dumps(
            [
                {
                    "name": family["name"],
                    "provider": family["provider"] if family_index == 2 else None,
                    "possible_official_url": family["root_url"],
                }
            ]
        ),
        encoding="utf-8",
    )
    run = service.create_run_from_source(
        str(seed_path), mode=IngestionMode.EXTRACTION, dry_run=True
    )

    completed = service.process_run(run.id, worker_id=f"phase3-{family['id']}")
    candidate = db_session.scalar(
        select(CatalogueCandidate).where(CatalogueCandidate.run_id == run.id)
    )
    assert candidate is not None
    assert candidate.status is CandidateStatus.READY_FOR_REVIEW, {
        "failure_code": candidate.failure_code,
        "failure_reason": candidate.failure_reason,
        "validation_errors": candidate.validation_errors,
        "conflicts": candidate.conflicts,
        "invocations": provider.invocations,
        "sources": [
            (
                source.id,
                source.url,
                [
                    (
                        decision.role,
                        decision.deterministic_signals,
                        decision.ambiguity_reason,
                    )
                    for artifact in source.artifacts
                    for decision in artifact.routing_decisions
                ],
            )
            for source in candidate.sources
        ],
    }
    assert completed.model_calls == len(ClaimObjective)
    assert len(provider.invocations) == len(ClaimObjective)
    assert len({url for url, _objective in provider.invocations}) == len(family["pages"])
    resolution = ClaimResolution.model_validate(candidate.proposed_payload)
    assert set(resolution.objective_coverage) == {item.value for item in ClaimObjective}
    assert set(resolution.objective_coverage.values()) == {"complete"}
    assert resolution.completeness_errors == []
    assert {
        item.extraction.objective for item in resolution.resolved if item.extraction is not None
    } == set(ClaimObjective)
    assert all(
        item.extraction is not None
        and item.extraction.schema_version.endswith(item.extraction.objective.value)
        and len(item.extraction.prompt_hash) == 64
        and item.extraction.provider == provider.name
        and item.extraction.model == provider.model
        for item in resolution.resolved
    )
    assert all(
        item.claim.scope.country_code == family["country_code"]
        and item.claim.scope.programme_family_key == family["id"]
        for item in resolution.resolved
    )
    resolved_values = {
        (item.claim.entity_type.value, item.claim.entity_key, item.claim.field_path): (
            item.claim.value.primitive()
        )
        for item in resolution.resolved
    }
    assert resolved_values == {
        ("cycle", "intake_2027", "intake_year"): 2027,
        ("deadline", "application", "deadline_at"): "2027-05-15",
        ("deadline", "application", "deadline_type"): "application_submission",
        ("document", "passport", "certification_requirement"): "certified",
        ("document", "passport", "copy_count"): 1,
        ("document", "passport", "name"): "Passport",
        ("document", "passport", "required"): True,
        ("eligibility", "degree", "condition"): "required",
        ("eligibility", "degree", "rule_type"): "academic_background",
        ("eligibility", "degree", "value"): "bachelors",
        ("funding", "tuition", "component_type"): "tuition",
        ("funding", "tuition", "coverage_status"): "confirmed",
        ("programme", "course", "degree_levels"): ["masters"],
        ("programme", "course", "description"): (
            f"{family['programme']} at masters level"
        ),
        ("programme", "course", "name"): family["programme"],
        ("scholarship", "scholarship", "country_code"): family["country_code"],
        ("scholarship", "scholarship", "degree_levels"): ["masters"],
        ("scholarship", "scholarship", "name"): family["name"],
        ("scholarship", "scholarship", "provider_name"): family["provider"],
        ("step", "submit", "title"): "Submit the application",
        ("track", "online", "application_method"): "online",
        ("track", "online", "application_url"): urljoin(
            str(family["root_url"]), "apply"
        ),
        ("track", "online", "name"): "Online Application",
    }
    artifact_text = {
        str(artifact.id): artifact.normalized_text
        for source in candidate.sources
        for artifact in source.artifacts
    }
    assert all(
        artifact_text[item.artifact_id][
            item.claim.excerpt_start : item.claim.excerpt_end
        ]
        == item.claim.excerpt
        for item in resolution.resolved
    )


def test_direct_source_bundle_rejects_urls_beyond_configured_page_budget(db_session) -> None:
    settings = _settings({"official.test"})
    service = CatalogueIngestionService(db_session, settings, fetcher=_FixtureFetcher({
        "root_url": "https://official.test/overview",
        "pages": [["overview", "Official scholarship overview text."]],
    }))

    with pytest.raises(AppError, match="page budget"):
        service.create_run_from_url(
            "https://official.test/overview",
            supporting_urls=[
                f"https://official.test/page-{index}"
                for index in range(settings.catalogue_ai_max_pages_per_candidate)
            ],
            mode=IngestionMode.CANDIDATE_ONLY,
            dry_run=True,
        )


def test_direct_bundle_deduplicates_identical_normalized_content(db_session) -> None:
    root = "https://official.test/overview"
    supporting = "https://official.test/funding"
    text = "Official scholarship funding and overview details with sufficient text."

    class DuplicateFetcher:
        def fetch(self, url: str) -> FetchedSource:
            return _fetched(url, text)

    service = CatalogueIngestionService(
        db_session,
        _settings({"official.test"}),
        fetcher=DuplicateFetcher(),
    )
    run = service.create_run_from_url(
        root,
        supporting_urls=[supporting],
        target_name="Synthetic duplicate content route",
        mode=IngestionMode.CANDIDATE_ONLY,
        dry_run=True,
    )

    service.process_run(run.id, worker_id="phase2-dedup")
    candidate = db_session.scalar(
        select(CatalogueCandidate).where(CatalogueCandidate.run_id == run.id)
    )
    assert candidate is not None
    duplicate_source = next(source for source in candidate.sources if source.url == supporting)
    assert duplicate_source.failure_code == "direct_source_content_duplicate"
    assert candidate.acquisition_bundle["accepted_artifact_count"] == 1
