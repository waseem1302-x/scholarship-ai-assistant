"""Deterministic known-candidate source selection and binding."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import exists, select
from sqlalchemy.orm import Session, aliased

from app.modules.catalogue_ingestion.discovery import (
    DiscoveryObjectiveKind,
    DiscoveryScopeSnapshot,
    DiscoveryTargetIdentitySnapshot,
)
from app.modules.catalogue_ingestion.discovery_models import (
    CatalogueDiscoveryAssessment,
    CatalogueDiscoveryLead,
    CatalogueDiscoveryObservation,
    CatalogueDiscoveryQuery,
    CatalogueDiscoveryRun,
    DiscoveryOfficialityStatus,
)
from app.modules.catalogue_ingestion.discovery_officiality import (
    CONTEXTUAL_OFFICIALITY_CLASSIFIER_VERSION,
)
from app.modules.catalogue_ingestion.discovery_repository import (
    CatalogueDiscoveryRepository,
    DiscoverySourceBindingOutcome,
    DiscoveryStateError,
)
from app.modules.catalogue_ingestion.models import CatalogueCandidateSource
from app.modules.opportunities.evidence_models import SourceOwnerType

MAX_RANK = 2**31 - 1


@dataclass(frozen=True)
class DiscoveryRootSelection:
    lead_id: uuid.UUID
    assessment_id: uuid.UUID
    normalized_url: str
    selection_key: tuple[int, int, int, int, str, str]


@dataclass(frozen=True)
class DiscoveryBindingResult:
    source: CatalogueCandidateSource
    lead_id: uuid.UUID
    assessment_id: uuid.UUID
    created: bool
    candidate_resumed: bool


class CatalogueDiscoveryBindingService:
    """Select and bind one official root for an explicit target candidate."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = CatalogueDiscoveryRepository(session)

    def select_root(
        self,
        *,
        run_id: uuid.UUID,
        lead_id: uuid.UUID | None = None,
    ) -> DiscoveryRootSelection:
        run = self.session.get(CatalogueDiscoveryRun, run_id)
        if run is None:
            raise DiscoveryStateError("catalogue_discovery_run_not_found")
        if run.target_candidate_id is None:
            raise DiscoveryStateError("binding_requires_explicit_target_candidate")

        scope = DiscoveryScopeSnapshot.model_validate(run.objective_scope)
        target = DiscoveryTargetIdentitySnapshot.model_validate(run.target_identity_snapshot)
        objective_kind = DiscoveryObjectiveKind(run.objective_kind)
        superseding_assessment = aliased(CatalogueDiscoveryAssessment)
        rows = self.session.execute(
            select(
                CatalogueDiscoveryAssessment,
                CatalogueDiscoveryLead,
                CatalogueDiscoveryQuery,
                CatalogueDiscoveryObservation,
            )
            .join(
                CatalogueDiscoveryLead,
                CatalogueDiscoveryLead.id == CatalogueDiscoveryAssessment.lead_id,
            )
            .join(
                CatalogueDiscoveryObservation,
                CatalogueDiscoveryObservation.lead_id == CatalogueDiscoveryLead.id,
            )
            .join(
                CatalogueDiscoveryQuery,
                CatalogueDiscoveryQuery.id == CatalogueDiscoveryObservation.query_id,
            )
            .where(
                CatalogueDiscoveryQuery.run_id == run.id,
                CatalogueDiscoveryLead.active.is_(True),
                CatalogueDiscoveryAssessment.officiality_status
                == DiscoveryOfficialityStatus.OFFICIAL,
                ~exists().where(
                    superseding_assessment.supersedes_assessment_id
                    == CatalogueDiscoveryAssessment.id
                ),
            )
        ).all()

        selections: dict[tuple[uuid.UUID, uuid.UUID], DiscoveryRootSelection] = {}
        for assessment, lead, query, observation in rows:
            if lead_id is not None and lead.id != lead_id:
                continue
            if not _assessment_matches_root_context(
                assessment,
                objective_kind=objective_kind,
                scope=scope,
                target=target,
            ):
                continue
            selection = DiscoveryRootSelection(
                lead_id=lead.id,
                assessment_id=assessment.id,
                normalized_url=lead.normalized_url,
                selection_key=(
                    assessment.trust_tier or MAX_RANK,
                    query.ordinal,
                    _authority_rank(assessment),
                    observation.provider_rank or MAX_RANK,
                    lead.normalized_url,
                    str(assessment.id),
                ),
            )
            key = (lead.id, assessment.id)
            previous = selections.get(key)
            if previous is None or selection.selection_key < previous.selection_key:
                selections[key] = selection
        if not selections:
            raise DiscoveryStateError("binding_no_acceptable_official_root")
        return min(selections.values(), key=lambda item: item.selection_key)

    def bind_best_root(self, *, run_id: uuid.UUID) -> DiscoveryBindingResult:
        selection = self.select_root(run_id=run_id)
        outcome: DiscoverySourceBindingOutcome = self.repository.bind_candidate_source(
            run_id=run_id,
            lead_id=selection.lead_id,
            assessment_id=selection.assessment_id,
        )
        return DiscoveryBindingResult(
            source=outcome.source,
            lead_id=selection.lead_id,
            assessment_id=selection.assessment_id,
            created=outcome.created,
            candidate_resumed=outcome.candidate_resumed,
        )


def _assessment_matches_root_context(
    assessment: CatalogueDiscoveryAssessment,
    *,
    objective_kind: DiscoveryObjectiveKind,
    scope: DiscoveryScopeSnapshot,
    target: DiscoveryTargetIdentitySnapshot,
) -> bool:
    if any(
        (
            assessment.classifier_version != CONTEXTUAL_OFFICIALITY_CLASSIFIER_VERSION,
            assessment.context_type != f"discovery:{objective_kind.value}",
            assessment.context_scholarship_id != scope.scholarship_id,
            assessment.context_institution_id != scope.institution_id,
            assessment.context_cycle_id != scope.cycle_id,
            assessment.owner_id is None,
            assessment.canonical_domain is None,
            assessment.trust_tier is None,
        )
    ):
        return False

    if target.provider_name is not None:
        return bool(
            assessment.owner_type
            in {SourceOwnerType.PROVIDER.value, SourceOwnerType.GOVERNMENT.value}
            and assessment.context_provider_id is not None
            and assessment.owner_id == assessment.context_provider_id
            and assessment.reason_code == "REVIEWED_PROVIDER_AUTHORITY"
        )
    return bool(
        target.institution_name is not None
        and scope.institution_id is not None
        and assessment.owner_type == SourceOwnerType.INSTITUTION.value
        and assessment.owner_id == scope.institution_id
        and assessment.context_institution_id == scope.institution_id
        and assessment.reason_code == "REVIEWED_INSTITUTION_CANONICAL_OWNER"
    )


def _authority_rank(assessment: CatalogueDiscoveryAssessment) -> int:
    return (
        0
        if assessment.reason_code
        in {"REVIEWED_PROVIDER_AUTHORITY", "REVIEWED_INSTITUTION_CANONICAL_OWNER"}
        else 1
    )
