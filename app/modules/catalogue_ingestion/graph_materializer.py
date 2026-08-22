"""Transactional materialization of a resolved direct-URL proposal into one draft graph."""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalogue_ingestion.claim_schemas import (
    ClaimEntityType,
    ClaimResolution,
    ResolvedClaim,
)
from app.modules.catalogue_ingestion.models import CatalogueSourceArtifact
from app.modules.opportunities.evidence_models import (
    ApplicationStep,
    EvidenceSupportType,
    EvidenceValidatorStatus,
    FieldEvidence,
    FundingComponent,
    OfficialityStatus,
    RequiredDocument,
    ScopedDeadline,
    SourceOwnerType,
    SourceSnapshot,
)
from app.modules.opportunities.graph_models import (
    ApplicationTrack,
    Institution,
    InstitutionParticipation,
    ScholarshipAlias,
)
from app.modules.opportunities.models import (
    DataConfidence,
    DegreeLevel,
    FundingType,
    Opportunity,
    OpportunityCycle,
    OpportunityStatus,
    Source,
    SourceType,
    VerificationStatus,
)
from app.modules.opportunities.schemas import OpportunityCreate, SourceCreate
from app.modules.opportunities.service import OpportunityService


class MextGraphMaterializer:
    def __init__(self, session: Session) -> None:
        self.session = session

    def materialize(self, resolution: ClaimResolution) -> Opportunity:
        if not resolution.is_materializable:
            raise ValueError("Only complete, conflict-free claim resolutions can be materialized")
        artifacts = self._artifacts(resolution)
        first = artifacts[resolution.resolved[0].artifact_id]
        name = str(_required_value(resolution, ClaimEntityType.SCHOLARSHIP, "name"))
        provider = str(_required_value(resolution, ClaimEntityType.SCHOLARSHIP, "provider_name"))
        intake_year = int(_required_value(resolution, ClaimEntityType.CYCLE, "intake_year"))
        country_code = str(
            _required_value(resolution, ClaimEntityType.SCHOLARSHIP, "country_code")
        ).upper()
        country = "Japan" if country_code == "JP" else country_code
        degree_levels = [
            str(item)
            for item in _required_value(resolution, ClaimEntityType.SCHOLARSHIP, "degree_levels")
        ]
        payload = OpportunityCreate(
            name=name,
            provider_name=provider,
            provider_canonical_id=_slug(provider),
            programme_family_id="mext",
            cycle_id=str(intake_year),
            country=country,
            degree_level=_legacy_degree_level(degree_levels),
            intake_year=intake_year,
            funding_type=FundingType.UNKNOWN,
            status=OpportunityStatus.DRAFT,
            data_confidence=DataConfidence.LOW,
            notes="MEXT multi-route graph staged from official sources; human review required.",
            source=SourceCreate(
                url=first.final_url,
                source_type=SourceType.OFFICIAL,
                title=_source_title(first.final_url),
                content_hash=first.content_hash,
                relevant_excerpt=first.normalized_text[:12_000],
                verification_status=VerificationStatus.NEEDS_REVIEW,
            ),
        )
        response = OpportunityService(self.session).stage_opportunity_for_review(
            payload, commit=False
        )
        opportunity = self.session.scalar(select(Opportunity).where(Opportunity.id == response.id))
        assert opportunity is not None
        opportunity.degree_levels = degree_levels
        primary_source = opportunity.sources[0]
        self._apply_source_metadata(primary_source, first)
        source_by_artifact = {str(first.id): primary_source}
        for artifact_id, artifact in artifacts.items():
            if artifact_id == str(first.id):
                continue
            source = Source(
                opportunity_id=opportunity.id,
                url=artifact.final_url,
                canonical_url=OpportunityService(self.session).repository.canonicalize_url(
                    artifact.final_url
                ),
                normalized_url=OpportunityService(self.session).repository.canonicalize_url(
                    artifact.final_url
                ),
                domain=urlsplit(artifact.final_url).hostname,
                source_owner_type=SourceOwnerType.GOVERNMENT,
                officiality_status=OfficialityStatus.SUPPORTING_OFFICIAL,
                officiality_reason="Accepted by direct URL official-source policy",
                content_type=artifact.content_type,
                source_type=SourceType.OFFICIAL,
                title=_source_title(artifact.final_url),
                content_hash=artifact.content_hash,
                relevant_excerpt=artifact.normalized_text[:12_000],
                verification_status=VerificationStatus.NEEDS_REVIEW,
            )
            opportunity.sources.append(source)
            source_by_artifact[artifact_id] = source
        self.session.flush()

        snapshot_by_artifact: dict[str, SourceSnapshot] = {}
        for artifact_id, artifact in artifacts.items():
            source = source_by_artifact[artifact_id]
            snapshot = SourceSnapshot(
                source_id=source.id,
                http_status=200,
                content_hash=artifact.content_hash,
                normalized_text=artifact.normalized_text,
                extraction_method=artifact.extraction_method,
                byte_count=artifact.byte_count,
                character_count=artifact.character_count,
                fetch_metadata={
                    **artifact.fetch_metadata,
                    "catalogue_source_artifact_id": artifact_id,
                },
            )
            self.session.add(snapshot)
            snapshot_by_artifact[artifact_id] = snapshot
        self.session.flush()

        cycle = OpportunityCycle(
            opportunity_id=opportunity.id,
            intake_year=intake_year,
            timezone="Asia/Tokyo",
        )
        self.session.add(cycle)
        self.session.flush()
        entity_map: dict[tuple[ClaimEntityType, str], object] = {}
        for item in resolution.resolved:
            if item.claim.entity_type is ClaimEntityType.SCHOLARSHIP:
                entity_map[(item.claim.entity_type, item.claim.entity_key)] = opportunity
            elif item.claim.entity_type is ClaimEntityType.CYCLE:
                entity_map[(item.claim.entity_type, item.claim.entity_key)] = cycle

        groups = _claim_groups(resolution.resolved)
        for (entity_type, entity_key), fields in groups.items():
            if entity_type is ClaimEntityType.TRACK:
                track = ApplicationTrack(
                    scholarship_id=opportunity.id,
                    cycle_id=cycle.id,
                    code=entity_key,
                    name=str(_field(fields, "name", entity_key.replace("_", " ").title())),
                    track_type=str(_field(fields, "track_type", "recommendation_route")),
                    application_method=_optional_text(fields, "application_method"),
                    application_url=_optional_text(fields, "application_url"),
                    status="needs_review",
                    display_order=int(_field(fields, "display_order", 0)),
                )
                self.session.add(track)
                self.session.flush()
                entity_map[(entity_type, entity_key)] = track

        for (entity_type, entity_key), fields in groups.items():
            if entity_type is not ClaimEntityType.TRACK:
                continue
            parent_key = _optional_text(fields, "parent_track_key")
            if parent_key:
                track = entity_map[(entity_type, entity_key)]
                parent = entity_map.get((ClaimEntityType.TRACK, parent_key))
                if parent is None:
                    raise ValueError(f"Track {entity_key} references missing parent {parent_key}")
                track.parent_track_id = parent.id

        participation_evidence: list[tuple[InstitutionParticipation, ResolvedClaim]] = []
        for (entity_type, entity_key), fields in groups.items():
            if entity_type is ClaimEntityType.INSTITUTION:
                canonical_name = str(_field(fields, "canonical_name", entity_key))
                slug = _slug(canonical_name)
                institution = self.session.scalar(
                    select(Institution).where(Institution.slug == slug)
                )
                if institution is None:
                    institution = Institution(
                        canonical_name=canonical_name,
                        slug=slug,
                        institution_type=str(_field(fields, "institution_type", "unknown")),
                        country_code=_optional_text(fields, "country_code"),
                        official_website=_optional_text(fields, "official_website"),
                        official_domain=_domain(_optional_text(fields, "official_website")),
                        identity_status="needs_review",
                    )
                    self.session.add(institution)
                    self.session.flush()
                entity_map[(entity_type, entity_key)] = institution
                track_keys = {
                    item.claim.scope.track_key
                    for item in resolution.resolved
                    if item.claim.entity_type is ClaimEntityType.INSTITUTION
                    and item.claim.entity_key == entity_key
                    and item.claim.scope.track_key
                }
                for track_key in sorted(track_keys):
                    track = entity_map.get((ClaimEntityType.TRACK, track_key))
                    if track is None:
                        raise ValueError(
                            f"Institution {entity_key} references missing track {track_key}"
                        )
                    support = next(
                        item
                        for item in resolution.resolved
                        if item.claim.entity_type is ClaimEntityType.INSTITUTION
                        and item.claim.entity_key == entity_key
                        and item.claim.scope.track_key == track_key
                    )
                    participation = InstitutionParticipation(
                        scholarship_id=opportunity.id,
                        cycle_id=cycle.id,
                        track_id=track.id,
                        institution_id=institution.id,
                        role=str(_field(fields, "role", "participating")),
                        participation_status="needs_review",
                        application_url=_optional_text(fields, "application_url"),
                        source_id=source_by_artifact[support.artifact_id].id,
                    )
                    self.session.add(participation)
                    participation_evidence.append((participation, support))

        self._materialize_scoped_facts(opportunity, cycle, groups, entity_map, resolution.resolved)
        for item in resolution.resolved:
            if (
                item.claim.entity_type is ClaimEntityType.SCHOLARSHIP
                and item.claim.field_path == "alias"
            ):
                alias = str(item.claim.value.primitive())
                self.session.add(
                    ScholarshipAlias(
                        scholarship_id=opportunity.id,
                        alias=alias,
                        normalized_alias=_slug(alias),
                    )
                )
        self.session.flush()

        for item in resolution.resolved:
            entity = entity_map.get((item.claim.entity_type, item.claim.entity_key))
            if entity is None:
                continue
            snapshot = snapshot_by_artifact[item.artifact_id]
            self.session.add(
                FieldEvidence(
                    entity_type=item.claim.entity_type.value,
                    entity_id=entity.id,
                    field_path=item.claim.field_path,
                    source_snapshot_id=snapshot.id,
                    excerpt=item.claim.excerpt,
                    excerpt_start=item.claim.excerpt_start,
                    excerpt_end=item.claim.excerpt_end,
                    support_type=EvidenceSupportType.EXPLICIT,
                    validator_status=EvidenceValidatorStatus.PASSED,
                )
            )
        for participation, support in participation_evidence:
            snapshot = snapshot_by_artifact[support.artifact_id]
            self.session.add(
                FieldEvidence(
                    entity_type="institution_participation",
                    entity_id=participation.id,
                    field_path="scope.track_key",
                    source_snapshot_id=snapshot.id,
                    excerpt=support.claim.excerpt,
                    excerpt_start=support.claim.excerpt_start,
                    excerpt_end=support.claim.excerpt_end,
                    support_type=EvidenceSupportType.EXPLICIT,
                    validator_status=EvidenceValidatorStatus.PASSED,
                )
            )
        self.session.flush()
        return opportunity

    def _materialize_scoped_facts(
        self,
        opportunity: Opportunity,
        cycle: OpportunityCycle,
        groups: dict[tuple[ClaimEntityType, str], dict[str, ResolvedClaim]],
        entity_map: dict[tuple[ClaimEntityType, str], object],
        claims: list[ResolvedClaim],
    ) -> None:
        for (entity_type, entity_key), fields in groups.items():
            sample = next(iter(fields.values())).claim
            track = entity_map.get((ClaimEntityType.TRACK, sample.scope.track_key or ""))
            institution = entity_map.get(
                (ClaimEntityType.INSTITUTION, sample.scope.institution_key or "")
            )
            common = {
                "scholarship_id": opportunity.id,
                "cycle_id": cycle.id,
                "track_id": getattr(track, "id", None),
                "institution_id": getattr(institution, "id", None),
            }
            entity: object | None = None
            if entity_type is ClaimEntityType.DEADLINE:
                raw = str(_field(fields, "deadline_at"))
                parsed, local_date, precision = _deadline(raw)
                entity = ScopedDeadline(
                    **common,
                    deadline_type=str(_field(fields, "deadline_type", "application")),
                    deadline_at=parsed,
                    local_date=local_date,
                    deadline_precision=precision,
                    timezone=str(_field(fields, "timezone", "Asia/Tokyo")),
                    label=_optional_text(fields, "label"),
                    notes=_optional_text(fields, "notes"),
                )
            elif entity_type is ClaimEntityType.FUNDING:
                entity = FundingComponent(
                    **common,
                    component_type=str(_field(fields, "component_type", entity_key)),
                    coverage_status=str(_field(fields, "coverage_status", "unknown")),
                    amount=_optional_decimal(fields, "amount"),
                    currency=_optional_text(fields, "currency"),
                    frequency=_optional_text(fields, "frequency"),
                    description=_optional_text(fields, "description"),
                )
            elif entity_type is ClaimEntityType.DOCUMENT:
                entity = RequiredDocument(
                    **common,
                    document_key=entity_key,
                    name=str(_field(fields, "name", entity_key.replace("_", " ").title())),
                    required=bool(_field(fields, "required", True)),
                    notes=_optional_text(fields, "notes"),
                    display_order=int(_field(fields, "display_order", 0)),
                )
            elif entity_type is ClaimEntityType.STEP:
                entity = ApplicationStep(
                    **common,
                    step_code=entity_key,
                    title=str(_field(fields, "title", entity_key.replace("_", " ").title())),
                    description=_optional_text(fields, "description"),
                    application_url=_optional_text(fields, "application_url"),
                    display_order=int(_field(fields, "display_order", 0)),
                )
            if entity is not None:
                self.session.add(entity)
                self.session.flush()
                entity_map[(entity_type, entity_key)] = entity

    def _artifacts(self, resolution: ClaimResolution) -> dict[str, CatalogueSourceArtifact]:
        ids = {uuid.UUID(item.artifact_id) for item in resolution.resolved}
        artifacts = self.session.scalars(
            select(CatalogueSourceArtifact).where(CatalogueSourceArtifact.id.in_(ids))
        ).all()
        result = {str(item.id): item for item in artifacts}
        if result.keys() != {str(item) for item in ids}:
            raise ValueError("Resolved claims reference missing source artifacts")
        return result

    @staticmethod
    def _apply_source_metadata(source: Source, artifact: CatalogueSourceArtifact) -> None:
        source.normalized_url = source.canonical_url
        source.domain = urlsplit(artifact.final_url).hostname
        source.source_owner_type = SourceOwnerType.GOVERNMENT
        source.officiality_status = OfficialityStatus.OFFICIAL
        source.officiality_reason = "Accepted by direct URL official-source policy"
        source.content_type = artifact.content_type


def _claim_groups(
    claims: list[ResolvedClaim],
) -> dict[tuple[ClaimEntityType, str], dict[str, ResolvedClaim]]:
    groups: dict[tuple[ClaimEntityType, str], dict[str, ResolvedClaim]] = defaultdict(dict)
    for item in claims:
        groups[(item.claim.entity_type, item.claim.entity_key)].setdefault(
            item.claim.field_path, item
        )
    return groups


def _required_value(
    resolution: ClaimResolution, entity_type: ClaimEntityType, field_path: str
) -> object:
    for item in resolution.resolved:
        if item.claim.entity_type is entity_type and item.claim.field_path == field_path:
            return item.claim.value.primitive()
    raise ValueError(f"Missing required claim {entity_type.value}.{field_path}")


def _field(fields: dict[str, ResolvedClaim], name: str, default: object | None = None) -> object:
    item = fields.get(name)
    if item is None:
        if default is None:
            raise ValueError(f"Missing required field {name}")
        return default
    return item.claim.value.primitive()


def _optional_text(fields: dict[str, ResolvedClaim], name: str) -> str | None:
    item = fields.get(name)
    return str(item.claim.value.primitive()) if item else None


def _optional_decimal(fields: dict[str, ResolvedClaim], name: str) -> Decimal | None:
    item = fields.get(name)
    return Decimal(str(item.claim.value.primitive())) if item else None


def _deadline(value: str) -> tuple[datetime, date | None, str]:
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        local = date.fromisoformat(value)
        return datetime(local.year, local.month, local.day, tzinfo=UTC), local, "date"
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed, parsed.date(), "datetime"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:255]


def _domain(url: str | None) -> str | None:
    return urlsplit(url).hostname if url else None


def _source_title(url: str) -> str:
    return f"Official MEXT source - {urlsplit(url).hostname or 'source'}"[:255]


def _legacy_degree_level(values: list[str]) -> DegreeLevel:
    for value in values:
        try:
            return DegreeLevel(value)
        except ValueError:
            continue
    return DegreeLevel.SHORT_COURSE
