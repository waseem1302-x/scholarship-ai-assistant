"""Transactional, version-aware materialization of rich catalogue claim proposals."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalogue_ingestion.claim_schemas import (
    ClaimEntityType,
    ClaimResolution,
    ClaimScope,
    ResolvedClaim,
)
from app.modules.catalogue_ingestion.models import CatalogueSourceArtifact
from app.modules.catalogue_ingestion.normalization_utils import (
    disambiguate_currency,
    parse_flexible_datetime,
)
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
from app.modules.opportunities.materialization_models import (
    CatalogueMaterializedClaimLink,
    OpportunityEvent,
    OpportunityResource,
    ScholarshipEligibilityRule,
    ScholarshipProgramme,
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

CATALOGUE_GRAPH_MATERIALIZER_VERSION = "catalogue-rich-graph.v1"

_GroupKey = tuple[ClaimEntityType, str, str]
_FieldEntityKey = tuple[_GroupKey, str]
_FieldEntityTarget = tuple[object, str]


class CatalogueGraphMaterializer:
    """Create a complete draft operational graph from one approved claim proposal.

    The caller owns the transaction. This class flushes as needed for foreign keys and evidence
    identities but never commits or publishes.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.opportunities = OpportunityService(session)

    def materialize(
        self,
        *,
        candidate_id: uuid.UUID,
        review_id: uuid.UUID,
        proposal_hash: str,
        resolution: ClaimResolution,
    ) -> Opportunity:
        if not resolution.is_materializable:
            raise ValueError("Only complete, conflict-free claim resolutions can be materialized")
        if not resolution.resolved:
            raise ValueError("Claim resolution contains no materializable claims")
        if not re.fullmatch(r"[0-9a-f]{64}", proposal_hash):
            raise ValueError("proposal_hash must be a lowercase SHA-256 digest")

        artifacts = self._artifacts(resolution)
        primary_claim = min(
            resolution.resolved,
            key=lambda item: (item.trust_tier, item.artifact_id, item.claim.entity_type.value),
        )
        primary_artifact = artifacts[primary_claim.artifact_id]
        name = str(_required_value(resolution, ClaimEntityType.SCHOLARSHIP, "name"))
        provider = str(_required_value(resolution, ClaimEntityType.SCHOLARSHIP, "provider_name"))
        country_code = str(
            _required_value(resolution, ClaimEntityType.SCHOLARSHIP, "country_code")
        ).upper()
        intake_year = int(_required_value(resolution, ClaimEntityType.CYCLE, "intake_year"))

        # Degree Levels: Top-level scholarship field or aggregated from programmes/tracks
        raw_degree = _optional_value(resolution, ClaimEntityType.SCHOLARSHIP, "degree_levels")
        if raw_degree is None:
            prog_degrees = [
                item.claim.value.primitive()
                for item in resolution.resolved
                if item.claim.entity_type in (ClaimEntityType.PROGRAMME, ClaimEntityType.TRACK)
                and item.claim.field_path in ("degree_levels", "degree_level")
            ]
            if prog_degrees:
                flattened = []
                for entry in prog_degrees:
                    if isinstance(entry, list):
                        flattened.extend(entry)
                    else:
                        flattened.append(entry)
                raw_degree = flattened or ["masters"]
            else:
                raw_degree = ["masters"]
        degree_levels = _degree_levels(raw_degree)
        primary_degree = _primary_degree_level(degree_levels)
        source_excerpt = _source_excerpt(primary_artifact)

        payload = OpportunityCreate(
            name=name,
            provider_name=provider,
            provider_canonical_id=_slug(provider, max_length=120),
            programme_family_id=_slug(name, max_length=120),
            cycle_id=str(intake_year),
            country=country_code,
            degree_level=primary_degree,
            intake_year=intake_year,
            funding_type=FundingType.UNKNOWN,
            status=OpportunityStatus.DRAFT,
            data_confidence=DataConfidence.LOW,
            notes=(
                "Catalogue claim graph staged from validated official-source evidence; "
                "human approval and a separate publication action are required."
            ),
            source=SourceCreate(
                url=primary_artifact.final_url,
                source_type=SourceType.OFFICIAL,
                title=_source_title(primary_artifact.final_url),
                content_hash=primary_artifact.content_hash,
                relevant_excerpt=source_excerpt,
                verification_status=VerificationStatus.NEEDS_REVIEW,
            ),
        )
        response = self.opportunities.stage_opportunity_for_review(payload, commit=False)
        opportunity = self.session.scalar(select(Opportunity).where(Opportunity.id == response.id))
        if opportunity is None:
            raise RuntimeError("Draft opportunity disappeared during graph materialization")
        opportunity.degree_levels = degree_levels

        source_by_artifact, snapshot_by_artifact = self._materialize_sources(
            opportunity,
            primary_artifact=primary_artifact,
            artifacts=artifacts,
        )
        primary_source = source_by_artifact[str(primary_artifact.id)]
        cycle = OpportunityCycle(
            opportunity_id=opportunity.id,
            label=str(intake_year),
            intake_year=intake_year,
            timezone="UTC",
            is_current=True,
            source_id=primary_source.id,
        )
        self.session.add(cycle)
        self.session.flush()

        groups = _claim_groups(resolution.resolved)
        group_entity: dict[_GroupKey, object] = {}
        field_entity: dict[_FieldEntityKey, _FieldEntityTarget] = {}
        for key in groups:
            if key[0] is ClaimEntityType.SCHOLARSHIP:
                group_entity[key] = opportunity
            elif key[0] is ClaimEntityType.CYCLE:
                group_entity[key] = cycle

        track_by_key = self._materialize_tracks(opportunity, cycle, groups, group_entity)
        institution_by_key = self._materialize_institutions(groups, group_entity)
        self._materialize_institution_participation(
            opportunity,
            cycle,
            groups,
            track_by_key=track_by_key,
            institution_by_key=institution_by_key,
            source_by_artifact=source_by_artifact,
            field_entity=field_entity,
        )
        programmes_by_key = self._materialize_programmes(
            candidate_id,
            proposal_hash,
            opportunity,
            cycle,
            groups,
            group_entity,
            track_by_key=track_by_key,
            institution_by_key=institution_by_key,
        )
        self._materialize_scoped_entities(
            candidate_id,
            proposal_hash,
            opportunity,
            cycle,
            groups,
            group_entity,
            track_by_key=track_by_key,
            institution_by_key=institution_by_key,
            programmes_by_key=programmes_by_key,
        )
        self._materialize_aliases(opportunity, resolution.resolved)
        self.session.flush()
        self._materialize_evidence(
            candidate_id=candidate_id,
            review_id=review_id,
            proposal_hash=proposal_hash,
            resolution=resolution,
            group_entity=group_entity,
            field_entity=field_entity,
            snapshot_by_artifact=snapshot_by_artifact,
        )

        # Dynamically infer FundingType from materialized funding components
        funding_components = [
            item for item in group_entity.values() if isinstance(item, FundingComponent)
        ]
        if funding_components:
            has_tuition = any(
                "tuition" in (fc.component_type or "").lower()
                or "fee" in (fc.component_type or "").lower()
                for fc in funding_components
            )
            has_stipend = any(
                "stipend" in (fc.component_type or "").lower()
                or "allowance" in (fc.component_type or "").lower()
                or "living" in (fc.component_type or "").lower()
                for fc in funding_components
            )
            if has_tuition and has_stipend:
                opportunity.funding_type = FundingType.FULL
            elif has_tuition:
                opportunity.funding_type = FundingType.TUITION_ONLY
            elif has_stipend:
                opportunity.funding_type = FundingType.STIPEND_ONLY
            else:
                opportunity.funding_type = FundingType.PARTIAL

        # Auto-publish high confidence clean official opportunities if enabled
        if (
            getattr(self.opportunities.settings, "catalogue_auto_publish_high_confidence", False)
            and not resolution.conflicts
            and not resolution.rejected
        ):
            opportunity.status = OpportunityStatus.PUBLISHED
            opportunity.data_confidence = DataConfidence.HIGH

        self.session.flush()
        return opportunity

    def _materialize_sources(
        self,
        opportunity: Opportunity,
        *,
        primary_artifact: CatalogueSourceArtifact,
        artifacts: dict[str, CatalogueSourceArtifact],
    ) -> tuple[dict[str, Source], dict[str, SourceSnapshot]]:
        if not opportunity.sources:
            raise RuntimeError("Staged opportunity has no primary source")
        primary_source = opportunity.sources[0]
        self._apply_source_metadata(
            primary_source,
            primary_artifact,
            officiality=OfficialityStatus.OFFICIAL,
        )
        source_by_candidate_source: dict[uuid.UUID, Source] = {
            primary_artifact.source_id: primary_source
        }
        source_by_artifact: dict[str, Source] = {}
        snapshot_by_artifact: dict[str, SourceSnapshot] = {}

        ordered_artifacts = sorted(
            artifacts.values(),
            key=lambda item: (
                item.source_id != primary_artifact.source_id,
                str(item.source_id),
                str(item.id),
            ),
        )
        for artifact in ordered_artifacts:
            source = source_by_candidate_source.get(artifact.source_id)
            if source is None:
                canonical_url = self.opportunities.repository.canonicalize_url(artifact.final_url)
                source = Source(
                    opportunity_id=opportunity.id,
                    url=artifact.final_url,
                    canonical_url=canonical_url,
                    normalized_url=canonical_url,
                    domain=urlsplit(artifact.final_url).hostname,
                    source_owner_type=SourceOwnerType.UNKNOWN,
                    officiality_status=OfficialityStatus.SUPPORTING_OFFICIAL,
                    officiality_reason="Accepted by catalogue ingestion official-source policy",
                    content_type=artifact.content_type,
                    source_type=SourceType.OFFICIAL,
                    title=_source_title(artifact.final_url),
                    content_hash=artifact.content_hash,
                    relevant_excerpt=_source_excerpt(artifact),
                    verification_status=VerificationStatus.NEEDS_REVIEW,
                )
                opportunity.sources.append(source)
                self.session.flush()
                source_by_candidate_source[artifact.source_id] = source
            source_by_artifact[str(artifact.id)] = source

            snapshot = self.session.scalar(
                select(SourceSnapshot).where(
                    SourceSnapshot.source_id == source.id,
                    SourceSnapshot.content_hash == artifact.content_hash,
                )
            )
            if snapshot is None:
                snapshot = SourceSnapshot(
                    source_id=source.id,
                    http_status=200,
                    content_hash=artifact.content_hash,
                    normalized_text=artifact.normalized_text,
                    extraction_method=artifact.extraction_method,
                    byte_count=artifact.byte_count,
                    character_count=artifact.character_count,
                    fetch_metadata={
                        **(artifact.fetch_metadata or {}),
                        "catalogue_source_artifact_id": str(artifact.id),
                        "catalogue_candidate_source_id": str(artifact.source_id),
                    },
                )
                self.session.add(snapshot)
                self.session.flush()
            snapshot_by_artifact[str(artifact.id)] = snapshot
        return source_by_artifact, snapshot_by_artifact

    def _materialize_tracks(
        self,
        opportunity: Opportunity,
        cycle: OpportunityCycle,
        groups: dict[_GroupKey, list[ResolvedClaim]],
        group_entity: dict[_GroupKey, object],
    ) -> dict[str, ApplicationTrack]:
        grouped: dict[str, list[ResolvedClaim]] = defaultdict(list)
        group_keys: dict[str, list[_GroupKey]] = defaultdict(list)
        for key, items in groups.items():
            if key[0] is ClaimEntityType.TRACK:
                grouped[key[1]].extend(items)
                group_keys[key[1]].append(key)

        track_by_key: dict[str, ApplicationTrack] = {}
        fields_by_key: dict[str, dict[str, list[ResolvedClaim]]] = {}
        for entity_key in sorted(grouped):
            fields = _fields(grouped[entity_key])
            fields_by_key[entity_key] = fields
            track = ApplicationTrack(
                scholarship_id=opportunity.id,
                cycle_id=cycle.id,
                code=entity_key,
                name=_required_text(fields, "name"),
                track_type=_required_text(fields, "track_type"),
                application_method=_joined_text(fields, "application_method"),
                application_url=_optional_single_text(fields, "application_url"),
                status="needs_review",
                display_order=_optional_int(fields, "display_order") or 0,
            )
            self.session.add(track)
            self.session.flush()
            track_by_key[entity_key] = track
            for group_key in group_keys[entity_key]:
                group_entity[group_key] = track

        for entity_key, fields in fields_by_key.items():
            parent_key = _optional_single_text(fields, "parent_track_key")
            if parent_key:
                parent = track_by_key.get(parent_key)
                if parent is None:
                    raise ValueError(
                        f"Track {entity_key} references missing parent track {parent_key}"
                    )
                track_by_key[entity_key].parent_track_id = parent.id
        return track_by_key

    def _materialize_institutions(
        self,
        groups: dict[_GroupKey, list[ResolvedClaim]],
        group_entity: dict[_GroupKey, object],
    ) -> dict[str, Institution]:
        grouped: dict[str, list[ResolvedClaim]] = defaultdict(list)
        group_keys: dict[str, list[_GroupKey]] = defaultdict(list)
        for key, items in groups.items():
            if key[0] is ClaimEntityType.INSTITUTION:
                grouped[key[1]].extend(items)
                group_keys[key[1]].append(key)

        result: dict[str, Institution] = {}
        for entity_key in sorted(grouped):
            fields = _fields(grouped[entity_key])
            canonical_name = _required_text(fields, "canonical_name")
            slug = _slug(canonical_name)
            institution = self.session.scalar(select(Institution).where(Institution.slug == slug))
            country_code = _optional_single_text(fields, "country_code")
            if institution is None:
                institution = Institution(
                    canonical_name=canonical_name,
                    slug=slug,
                    institution_type=_optional_single_text(fields, "institution_type") or "unknown",
                    country_code=country_code.upper() if country_code else None,
                    official_website=_optional_single_text(fields, "official_website"),
                    official_domain=_domain(_optional_single_text(fields, "official_website")),
                    identity_status="needs_review",
                )
                self.session.add(institution)
                self.session.flush()
            else:
                if institution.canonical_name.casefold() != canonical_name.casefold():
                    raise ValueError(
                        f"Institution slug collision for {canonical_name}: "
                        "existing identity differs"
                    )
                if (
                    country_code
                    and institution.country_code
                    and institution.country_code.casefold() != country_code.casefold()
                ):
                    raise ValueError(
                        f"Institution {canonical_name} conflicts with existing country identity"
                    )
            result[entity_key] = institution
            for group_key in group_keys[entity_key]:
                group_entity[group_key] = institution
        return result

    def _materialize_institution_participation(
        self,
        opportunity: Opportunity,
        cycle: OpportunityCycle,
        groups: dict[_GroupKey, list[ResolvedClaim]],
        *,
        track_by_key: dict[str, ApplicationTrack],
        institution_by_key: dict[str, Institution],
        source_by_artifact: dict[str, Source],
        field_entity: dict[_FieldEntityKey, _FieldEntityTarget],
    ) -> None:
        seen: dict[tuple[uuid.UUID, uuid.UUID, str], InstitutionParticipation] = {}
        for key, items in sorted(
            groups.items(),
            key=lambda value: (value[0][0].value, value[0][1], value[0][2]),
        ):
            if key[0] is not ClaimEntityType.INSTITUTION:
                continue
            scope = items[0].claim.scope
            if not scope.track_key:
                continue
            track = track_by_key.get(scope.track_key)
            institution = institution_by_key.get(key[1])
            if track is None or institution is None:
                raise ValueError(f"Institution {key[1]} references unresolved track scope")
            fields = _fields(items)
            role = _optional_single_text(fields, "role") or "participating"
            identity = (track.id, institution.id, role)
            participation = seen.get(identity)
            if participation is None:
                support = min(items, key=lambda item: (item.trust_tier, item.artifact_id))
                participation = InstitutionParticipation(
                    scholarship_id=opportunity.id,
                    cycle_id=cycle.id,
                    track_id=track.id,
                    institution_id=institution.id,
                    role=role,
                    participation_status="needs_review",
                    application_url=_optional_single_text(fields, "application_url"),
                    source_id=source_by_artifact[support.artifact_id].id,
                )
                self.session.add(participation)
                self.session.flush()
                seen[identity] = participation
            for relationship_field in ("role", "application_url"):
                if fields.get(relationship_field):
                    field_entity[(key, relationship_field)] = (
                        participation,
                        "institution_participation",
                    )

    def _materialize_programmes(
        self,
        candidate_id: uuid.UUID,
        proposal_hash: str,
        opportunity: Opportunity,
        cycle: OpportunityCycle,
        groups: dict[_GroupKey, list[ResolvedClaim]],
        group_entity: dict[_GroupKey, object],
        *,
        track_by_key: dict[str, ApplicationTrack],
        institution_by_key: dict[str, Institution],
    ) -> dict[str, list[tuple[ClaimScope, ScholarshipProgramme]]]:
        programmes_by_key: dict[str, list[tuple[ClaimScope, ScholarshipProgramme]]] = defaultdict(
            list
        )
        for key, items in sorted(
            groups.items(),
            key=lambda value: (value[0][0].value, value[0][1], value[0][2]),
        ):
            if key[0] is not ClaimEntityType.PROGRAMME:
                continue
            fields = _fields(items)
            scope = items[0].claim.scope
            route_keys = _string_list(fields, "application_route_keys")
            track = _resolve_track(scope.track_key, track_by_key)
            if track is None and len(route_keys) == 1:
                track = _resolve_track(route_keys[0], track_by_key)
            institution = _resolve_institution(scope.institution_key, institution_by_key)
            identity_key = _entity_identity_key(
                candidate_id,
                proposal_hash,
                ClaimEntityType.PROGRAMME,
                key[1],
                scope,
            )
            programme = ScholarshipProgramme(
                scholarship_id=opportunity.id,
                cycle_id=cycle.id,
                track_id=track.id if track else None,
                institution_id=institution.id if institution else None,
                identity_key=identity_key,
                programme_key=scope.programme_key or key[1],
                name=_required_text(fields, "name"),
                programme_type=_optional_single_text(fields, "programme_type"),
                degree_levels=_string_list(fields, "degree_levels"),
                fields_of_study=_string_list(fields, "fields_of_study"),
                duration=_joined_text(fields, "duration"),
                description=_joined_text(fields, "description"),
                application_route_keys=route_keys,
                display_order=_optional_int(fields, "display_order") or 0,
            )
            self.session.add(programme)
            self.session.flush()
            group_entity[key] = programme
            lookup_keys = {key[1]}
            if scope.programme_key:
                lookup_keys.add(scope.programme_key)
            for lookup_key in lookup_keys:
                programmes_by_key[lookup_key].append((scope, programme))
        return programmes_by_key

    def _materialize_scoped_entities(
        self,
        candidate_id: uuid.UUID,
        proposal_hash: str,
        opportunity: Opportunity,
        cycle: OpportunityCycle,
        groups: dict[_GroupKey, list[ResolvedClaim]],
        group_entity: dict[_GroupKey, object],
        *,
        track_by_key: dict[str, ApplicationTrack],
        institution_by_key: dict[str, Institution],
        programmes_by_key: dict[str, list[tuple[ClaimScope, ScholarshipProgramme]]],
    ) -> None:
        supported = {
            ClaimEntityType.ELIGIBILITY,
            ClaimEntityType.DEADLINE,
            ClaimEntityType.EVENT,
            ClaimEntityType.FUNDING,
            ClaimEntityType.DOCUMENT,
            ClaimEntityType.STEP,
            ClaimEntityType.RESOURCE,
        }
        for key, items in sorted(
            groups.items(),
            key=lambda value: (value[0][0].value, value[0][1], value[0][2]),
        ):
            entity_type, entity_key, _scope_json = key
            if entity_type not in supported:
                continue
            fields = _fields(items)
            scope = items[0].claim.scope
            track = _resolve_track(scope.track_key, track_by_key)
            institution = _resolve_institution(scope.institution_key, institution_by_key)
            programme = _resolve_programme(
                scope,
                programmes_by_key,
                track_by_key=track_by_key,
                institution_by_key=institution_by_key,
            )
            common = {
                "scholarship_id": opportunity.id,
                "cycle_id": cycle.id,
                "track_id": track.id if track else None,
                "institution_id": institution.id if institution else None,
            }
            entity: object
            if entity_type is ClaimEntityType.ELIGIBILITY:
                entity = ScholarshipEligibilityRule(
                    **common,
                    programme_id=programme.id if programme else None,
                    identity_key=_entity_identity_key(
                        candidate_id, proposal_hash, entity_type, entity_key, scope
                    ),
                    rule_key=entity_key,
                    rule_type=_required_text(fields, "rule_type"),
                    operator=_required_text(fields, "operator"),
                    value_json={"value": _required_primitive(fields, "value")},
                    unit=_optional_single_text(fields, "unit"),
                    required=_optional_bool(fields, "required", default=True),
                    condition=_joined_text(fields, "condition"),
                    is_exclusion=_optional_bool(fields, "is_exclusion", default=False),
                    notes=_joined_text(fields, "notes"),
                    display_order=_optional_int(fields, "display_order") or 0,
                )
            elif entity_type is ClaimEntityType.DEADLINE:
                deadline_at = _optional_datetime(fields, "deadline_at")
                deadline_text = _optional_single_text(fields, "deadline_text")
                tz_text = _optional_single_text(fields, "timezone")
                if deadline_at is None and deadline_text:
                    deadline_at = parse_flexible_datetime(deadline_text, default_tz=tz_text)
                if deadline_at is None and deadline_text is None:
                    raise ValueError(
                        f"Deadline {entity_key} has neither deadline_at nor deadline_text"
                    )
                precision = _optional_single_text(fields, "precision") or (
                    "datetime" if deadline_at is not None else "text"
                )
                entity = ScopedDeadline(
                    **common,
                    programme_id=None,
                    scholarship_programme_id=programme.id if programme else None,
                    deadline_type=_required_text(fields, "deadline_type"),
                    deadline_at=deadline_at,
                    deadline_text=deadline_text,
                    local_date=deadline_at.date() if deadline_at else None,
                    deadline_precision=precision,
                    timezone=_optional_single_text(fields, "timezone") or "UTC",
                    varies_by=_optional_single_text(fields, "varies_by"),
                    label=_optional_single_text(fields, "label"),
                    notes=_joined_text(fields, "notes"),
                )
            elif entity_type is ClaimEntityType.EVENT:
                entity = OpportunityEvent(
                    **common,
                    programme_id=programme.id if programme else None,
                    identity_key=_entity_identity_key(
                        candidate_id, proposal_hash, entity_type, entity_key, scope
                    ),
                    event_key=entity_key,
                    event_type=_required_text(fields, "event_type"),
                    starts_at=_optional_datetime(fields, "starts_at"),
                    ends_at=_optional_datetime(fields, "ends_at"),
                    date_text=_optional_single_text(fields, "date_text"),
                    precision=_optional_single_text(fields, "precision"),
                    timezone=_optional_single_text(fields, "timezone"),
                    label=_optional_single_text(fields, "label"),
                    notes=_joined_text(fields, "notes"),
                    display_order=_optional_int(fields, "display_order") or 0,
                )
            elif entity_type is ClaimEntityType.FUNDING:
                entity = FundingComponent(
                    **common,
                    programme_id=None,
                    scholarship_programme_id=programme.id if programme else None,
                    component_type=_required_text(fields, "component_type"),
                    coverage_status=_required_text(fields, "coverage_status"),
                    amount=_optional_decimal(fields, "amount"),
                    currency=disambiguate_currency(
                        _optional_single_text(fields, "currency"), opportunity.country
                    ),
                    frequency=_optional_single_text(fields, "frequency"),
                    description=_joined_text(fields, "description"),
                )
            elif entity_type is ClaimEntityType.DOCUMENT:
                entity = RequiredDocument(
                    **common,
                    programme_id=None,
                    scholarship_programme_id=programme.id if programme else None,
                    document_key=entity_key,
                    name=_required_text(fields, "name"),
                    required=_optional_bool(fields, "required", default=True),
                    condition=_joined_text(fields, "condition"),
                    submission_stage=_optional_single_text(fields, "submission_stage"),
                    original_count=_optional_int(fields, "original_count"),
                    copy_count=_optional_int(fields, "copy_count"),
                    translation_requirement=_joined_text(fields, "translation_requirement"),
                    certification_requirement=_joined_text(fields, "certification_requirement"),
                    form_year=_optional_int(fields, "form_year"),
                    notes=_joined_text(fields, "notes"),
                    display_order=_optional_int(fields, "display_order") or 0,
                )
            elif entity_type is ClaimEntityType.STEP:
                entity = ApplicationStep(
                    **common,
                    programme_id=None,
                    scholarship_programme_id=programme.id if programme else None,
                    step_code=entity_key,
                    title=_required_text(fields, "title"),
                    description=_joined_text(fields, "description"),
                    application_url=_optional_single_text(fields, "application_url"),
                    display_order=_optional_int(fields, "display_order") or 0,
                )
            else:
                entity = OpportunityResource(
                    **common,
                    programme_id=programme.id if programme else None,
                    identity_key=_entity_identity_key(
                        candidate_id, proposal_hash, entity_type, entity_key, scope
                    ),
                    resource_key=entity_key,
                    title=_required_text(fields, "title"),
                    resource_type=_required_text(fields, "resource_type"),
                    url=_required_text(fields, "url"),
                    required=_optional_bool(fields, "required", default=False),
                    notes=_joined_text(fields, "notes"),
                    display_order=_optional_int(fields, "display_order") or 0,
                )
            self.session.add(entity)
            self.session.flush()
            group_entity[key] = entity

    def _materialize_aliases(
        self,
        opportunity: Opportunity,
        claims: list[ResolvedClaim],
    ) -> None:
        aliases = sorted(
            {
                str(item.claim.value.primitive()).strip()
                for item in claims
                if item.claim.entity_type is ClaimEntityType.SCHOLARSHIP
                and item.claim.field_path == "alias"
                and str(item.claim.value.primitive()).strip()
            }
        )
        for alias in aliases:
            normalized = _slug(alias)
            existing = self.session.scalar(
                select(ScholarshipAlias).where(
                    ScholarshipAlias.scholarship_id == opportunity.id,
                    ScholarshipAlias.normalized_alias == normalized,
                )
            )
            if existing is None:
                self.session.add(
                    ScholarshipAlias(
                        scholarship_id=opportunity.id,
                        alias=alias,
                        normalized_alias=normalized,
                    )
                )

    def _materialize_evidence(
        self,
        *,
        candidate_id: uuid.UUID,
        review_id: uuid.UUID,
        proposal_hash: str,
        resolution: ClaimResolution,
        group_entity: dict[_GroupKey, object],
        field_entity: dict[_FieldEntityKey, _FieldEntityTarget],
        snapshot_by_artifact: dict[str, SourceSnapshot],
    ) -> None:
        for item in resolution.resolved:
            key = _group_key(item)
            override = field_entity.get((key, item.claim.field_path))
            if override is not None:
                entity, evidence_entity_type = override
            else:
                entity = group_entity.get(key)
                evidence_entity_type = item.claim.entity_type.value
            if entity is None:
                raise ValueError(
                    f"No operational entity for claim {item.claim.entity_type.value}:"
                    f"{item.claim.entity_key}:{item.claim.field_path}"
                )
            entity_id = getattr(entity, "id", None)
            if not isinstance(entity_id, uuid.UUID):
                raise RuntimeError("Materialized entity has no persisted UUID")
            snapshot = snapshot_by_artifact.get(item.artifact_id)
            if snapshot is None:
                raise ValueError(f"Claim references unmapped source artifact {item.artifact_id}")
            evidence = self.session.scalar(
                select(FieldEvidence).where(
                    FieldEvidence.entity_type == evidence_entity_type,
                    FieldEvidence.entity_id == entity_id,
                    FieldEvidence.field_path == item.claim.field_path,
                    FieldEvidence.source_snapshot_id == snapshot.id,
                    FieldEvidence.excerpt_start == item.claim.excerpt_start,
                    FieldEvidence.excerpt_end == item.claim.excerpt_end,
                    FieldEvidence.support_type == EvidenceSupportType.EXPLICIT,
                )
            )
            if evidence is None:
                evidence = FieldEvidence(
                    entity_type=evidence_entity_type,
                    entity_id=entity_id,
                    field_path=item.claim.field_path,
                    source_snapshot_id=snapshot.id,
                    excerpt=item.claim.excerpt,
                    excerpt_start=item.claim.excerpt_start,
                    excerpt_end=item.claim.excerpt_end,
                    support_type=EvidenceSupportType.EXPLICIT,
                    validator_status=EvidenceValidatorStatus.PASSED,
                )
                self.session.add(evidence)
                self.session.flush()
            claim_id = item.claim_id or _resolved_claim_id(item)
            existing_link = self.session.scalar(
                select(CatalogueMaterializedClaimLink).where(
                    CatalogueMaterializedClaimLink.proposal_hash == proposal_hash,
                    CatalogueMaterializedClaimLink.claim_id == claim_id,
                    CatalogueMaterializedClaimLink.entity_id == entity_id,
                    CatalogueMaterializedClaimLink.field_path == item.claim.field_path,
                )
            )
            if existing_link is None:
                self.session.add(
                    CatalogueMaterializedClaimLink(
                        candidate_id=candidate_id,
                        review_id=review_id,
                        proposal_hash=proposal_hash,
                        claim_id=claim_id,
                        entity_type=evidence_entity_type,
                        entity_id=entity_id,
                        field_path=item.claim.field_path,
                        field_evidence_id=evidence.id,
                        provenance_json={
                            "claim_entity_type": item.claim.entity_type.value,
                            "claim_entity_key": item.claim.entity_key,
                            "artifact_id": item.artifact_id,
                            "source_id": item.source_id,
                            "source_url": item.source_url,
                            "content_hash": item.content_hash,
                            "trust_tier": item.trust_tier,
                            "objectives": [objective.value for objective in item.objectives],
                            "scope": item.claim.scope.model_dump(mode="json"),
                            "basis": item.claim.basis,
                            "source_snapshot_id": str(snapshot.id),
                        },
                    )
                )

    def _artifacts(self, resolution: ClaimResolution) -> dict[str, CatalogueSourceArtifact]:
        ids = {uuid.UUID(item.artifact_id) for item in resolution.resolved}
        artifacts = list(
            self.session.scalars(
                select(CatalogueSourceArtifact).where(CatalogueSourceArtifact.id.in_(ids))
            )
        )
        result = {str(item.id): item for item in artifacts}
        if set(result) != {str(item) for item in ids}:
            raise ValueError("Resolved claims reference missing source artifacts")
        return result

    @staticmethod
    def _apply_source_metadata(
        source: Source,
        artifact: CatalogueSourceArtifact,
        *,
        officiality: OfficialityStatus,
    ) -> None:
        source.normalized_url = source.canonical_url
        source.domain = urlsplit(artifact.final_url).hostname
        source.source_owner_type = SourceOwnerType.UNKNOWN
        source.officiality_status = officiality
        source.officiality_reason = "Accepted by catalogue ingestion official-source policy"
        source.content_type = artifact.content_type


def _claim_groups(claims: list[ResolvedClaim]) -> dict[_GroupKey, list[ResolvedClaim]]:
    groups: dict[_GroupKey, list[ResolvedClaim]] = defaultdict(list)
    for item in claims:
        groups[_group_key(item)].append(item)
    return dict(groups)


def _group_key(item: ResolvedClaim) -> _GroupKey:
    scope_json = json.dumps(
        item.claim.scope.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return item.claim.entity_type, item.claim.entity_key, scope_json


def _fields(items: list[ResolvedClaim]) -> dict[str, list[ResolvedClaim]]:
    result: dict[str, list[ResolvedClaim]] = defaultdict(list)
    for item in sorted(
        items,
        key=lambda value: (
            value.claim.field_path,
            value.trust_tier,
            value.artifact_id,
            value.claim.excerpt_start,
        ),
    ):
        result[item.claim.field_path].append(item)
    return dict(result)


def _required_value(
    resolution: ClaimResolution,
    entity_type: ClaimEntityType,
    field_path: str,
) -> object:
    values = [
        item.claim.value.primitive()
        for item in resolution.resolved
        if item.claim.entity_type is entity_type and item.claim.field_path == field_path
    ]
    if not values:
        raise ValueError(f"Missing required claim {entity_type.value}.{field_path}")
    normalized = {_stable_value(value) for value in values}
    if len(normalized) != 1:
        raise ValueError(f"Required claim {entity_type.value}.{field_path} is ambiguous")
    return values[0]


def _required_primitive(fields: dict[str, list[ResolvedClaim]], name: str) -> object:
    items = fields.get(name) or []
    if not items:
        raise ValueError(f"Missing required field {name}")
    values = [item.claim.value.primitive() for item in items]
    if len({_stable_value(value) for value in values}) != 1:
        raise ValueError(f"Required field {name} has multiple resolved values")
    return values[0]


def _required_text(fields: dict[str, list[ResolvedClaim]], name: str) -> str:
    value = _required_primitive(fields, name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Required field {name} must be non-empty text")
    return value.strip()


def _optional_single_text(fields: dict[str, list[ResolvedClaim]], name: str) -> str | None:
    items = fields.get(name) or []
    if not items:
        return None
    values = [str(item.claim.value.primitive()).strip() for item in items]
    values = [value for value in values if value]
    unique = list(dict.fromkeys(values))
    if len(unique) > 1:
        raise ValueError(f"Field {name} has multiple values but requires one operational value")
    return unique[0] if unique else None


def _joined_text(fields: dict[str, list[ResolvedClaim]], name: str) -> str | None:
    items = fields.get(name) or []
    if not items:
        return None
    values = [str(item.claim.value.primitive()).strip() for item in items]
    values = list(dict.fromkeys(value for value in values if value))
    return "\n\n".join(values) if values else None


def _string_list(fields: dict[str, list[ResolvedClaim]], name: str) -> list[str]:
    values: list[str] = []
    for item in fields.get(name) or []:
        primitive = item.claim.value.primitive()
        if isinstance(primitive, list):
            values.extend(str(value).strip() for value in primitive)
        else:
            values.append(str(primitive).strip())
    return list(dict.fromkeys(value for value in values if value))


def _optional_int(fields: dict[str, list[ResolvedClaim]], name: str) -> int | None:
    items = fields.get(name) or []
    if not items:
        return None
    values = [item.claim.value.primitive() for item in items]
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise ValueError(f"Field {name} must be an integer")
    unique = list(dict.fromkeys(values))
    if len(unique) > 1:
        raise ValueError(f"Field {name} has multiple integer values")
    return int(unique[0])


def _optional_bool(
    fields: dict[str, list[ResolvedClaim]],
    name: str,
    *,
    default: bool,
) -> bool:
    items = fields.get(name) or []
    if not items:
        return default
    values = [item.claim.value.primitive() for item in items]
    if any(not isinstance(value, bool) for value in values):
        raise ValueError(f"Field {name} must be a boolean")
    unique = list(dict.fromkeys(values))
    if len(unique) > 1:
        raise ValueError(f"Field {name} has multiple boolean values")
    return bool(unique[0])


def _optional_decimal(fields: dict[str, list[ResolvedClaim]], name: str) -> Decimal | None:
    items = fields.get(name) or []
    if not items:
        return None
    values = [Decimal(str(item.claim.value.primitive())) for item in items]
    unique = list(dict.fromkeys(values))
    if len(unique) > 1:
        raise ValueError(f"Field {name} has multiple numeric values")
    return unique[0]


def _optional_value(
    resolution: ClaimResolution,
    entity_type: ClaimEntityType,
    field_path: str,
) -> object | None:
    values = [
        item.claim.value.primitive()
        for item in resolution.resolved
        if item.claim.entity_type is entity_type and item.claim.field_path == field_path
    ]
    if not values:
        return None
    normalized = {_stable_value(value) for value in values}
    if len(normalized) != 1:
        return values[0]
    return values[0]


def _optional_datetime(fields: dict[str, list[ResolvedClaim]], name: str) -> datetime | None:
    raw = _optional_single_text(fields, name)
    if raw is None:
        return None
    tz_val = _optional_single_text(fields, "timezone")
    parsed = parse_flexible_datetime(raw, default_tz=tz_val)
    if parsed is not None:
        return parsed
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed
    except ValueError as exc:
        raise ValueError(f"Field {name} is not a supported ISO date/datetime: {raw}") from exc


def _degree_levels(value: object) -> list[str]:
    values = value if isinstance(value, list) else [value]
    normalized: list[str] = []
    for item in values:
        text = str(item)
        try:
            normalized.append(DegreeLevel(text).value)
        except ValueError as exc:
            raise ValueError(f"Unsupported degree level {text}") from exc
    result = list(dict.fromkeys(normalized))
    if not result:
        raise ValueError("At least one explicit degree level is required")
    return result


def _primary_degree_level(values: list[str]) -> DegreeLevel:
    return DegreeLevel(values[0])


def _resolve_track(
    key: str | None,
    tracks: dict[str, ApplicationTrack],
) -> ApplicationTrack | None:
    if not key:
        return None
    track = tracks.get(key)
    if track is None:
        raise ValueError(f"Scope references unknown track {key}")
    return track


def _resolve_institution(
    key: str | None,
    institutions: dict[str, Institution],
) -> Institution | None:
    if not key:
        return None
    institution = institutions.get(key)
    if institution is None:
        raise ValueError(f"Scope references unknown institution {key}")
    return institution


def _resolve_programme(
    scope: ClaimScope,
    programmes: dict[str, list[tuple[ClaimScope, ScholarshipProgramme]]],
    *,
    track_by_key: dict[str, ApplicationTrack],
    institution_by_key: dict[str, Institution],
) -> ScholarshipProgramme | None:
    if not scope.programme_key:
        return None
    candidates = list(programmes.get(scope.programme_key, []))
    if not candidates:
        raise ValueError(f"Scope references unknown scholarship programme {scope.programme_key}")
    if scope.track_key:
        track = _resolve_track(scope.track_key, track_by_key)
        candidates = [item for item in candidates if item[1].track_id == track.id]
    if scope.institution_key:
        institution = _resolve_institution(scope.institution_key, institution_by_key)
        candidates = [item for item in candidates if item[1].institution_id == institution.id]
    if len(candidates) != 1:
        raise ValueError(
            f"Scholarship programme scope {scope.programme_key} is ambiguous for the supplied scope"
        )
    return candidates[0][1]


def _entity_identity_key(
    candidate_id: uuid.UUID,
    proposal_hash: str,
    entity_type: ClaimEntityType,
    entity_key: str,
    scope: ClaimScope,
) -> str:
    payload = {
        "candidate_id": str(candidate_id),
        "proposal_hash": proposal_hash,
        "entity_type": entity_type.value,
        "entity_key": entity_key,
        "scope": scope.model_dump(mode="json"),
        "materializer": CATALOGUE_GRAPH_MATERIALIZER_VERSION,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _resolved_claim_id(item: ResolvedClaim) -> str:
    payload = {
        "artifact_id": item.artifact_id,
        "entity_type": item.claim.entity_type.value,
        "entity_key": item.claim.entity_key,
        "field_path": item.claim.field_path,
        "scope": item.claim.scope.model_dump(mode="json"),
        "value": item.claim.value.model_dump(mode="json"),
        "excerpt_start": item.claim.excerpt_start,
        "excerpt_end": item.claim.excerpt_end,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _source_excerpt(artifact: CatalogueSourceArtifact) -> str:
    excerpt = artifact.normalized_text[:12_000].strip()
    if len(excerpt) < 20:
        raise ValueError(
            "Official source artifact is too short for the operational source boundary"
        )
    return excerpt


def _source_title(url: str) -> str:
    return f"Official source - {urlsplit(url).hostname or 'source'}"[:255]


def _slug(value: str, *, max_length: int = 255) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")[:max_length]
    if len(slug) < 2:
        raise ValueError("Canonical identity cannot be reduced to a usable slug")
    return slug


def _domain(url: str | None) -> str | None:
    return urlsplit(url).hostname if url else None


def _stable_value(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


__all__ = ["CATALOGUE_GRAPH_MATERIALIZER_VERSION", "CatalogueGraphMaterializer"]
