"""Production catalogue ingestion composition for evidence-routed extraction."""

from __future__ import annotations

import uuid

from app.modules.catalogue_ingestion.evidence_blocks import CatalogueEvidenceBlockBuilder
from app.modules.catalogue_ingestion.evidence_routing import CatalogueEvidenceRouter
from app.modules.catalogue_ingestion.hardened_service import HardenedCatalogueIngestionService
from app.modules.catalogue_ingestion.models import (
    CatalogueCandidate,
    CatalogueCandidateSource,
    CatalogueIngestionRun,
)
from app.modules.opportunities.source_monitor import FetchedSource


class ProductionCatalogueIngestionService(HardenedCatalogueIngestionService):
    """Current production composition: hardened acquisition plus evidence-first routing."""

    def __init__(self, session, settings, **kwargs) -> None:
        super().__init__(session, settings, **kwargs)
        self.evidence_block_builder = CatalogueEvidenceBlockBuilder(session)
        self.evidence_router = CatalogueEvidenceRouter(session)

    def _persist_source_artifact(
        self,
        source: CatalogueCandidateSource,
        fetched: FetchedSource,
    ) -> None:
        """Persist the immutable artifact and its complete-document block representation."""

        super()._persist_source_artifact(source, fetched)
        self.session.flush()
        content_hash = fetched.normalized_content_hash or fetched.content_hash
        artifact = next(
            (
                item
                for item in source.artifacts
                if item.content_hash == content_hash
            ),
            None,
        )
        if artifact is None:
            return
        self.evidence_block_builder.persist_artifact(
            candidate_id=source.candidate_id,
            source_id=source.id,
            artifact=artifact,
            source_role=source.source_role.value,
        )

    def _process_direct_claims(
        self,
        run: CatalogueIngestionRun,
        candidate: CatalogueCandidate,
        run_lease_token: str,
    ) -> None:
        """Persist zero-model routing decisions before the compatibility extraction loop."""

        self._heartbeat_candidate(run, candidate, run_lease_token)
        self.evidence_router.persist_candidate(candidate.id)
        self._heartbeat_candidate(run, candidate, run_lease_token)
        super()._process_direct_claims(run, candidate, run_lease_token)


__all__ = ["ProductionCatalogueIngestionService"]
