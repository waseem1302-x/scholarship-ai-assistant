"""Deterministic evidence persistence for catalogue graph facts."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.modules.opportunities.evidence_models import (
    EvidenceIntegrityError,
    EvidenceSupportType,
    EvidenceValidatorStatus,
    FieldEvidence,
    SourceSnapshot,
)


class EvidenceStore:
    """Persist field evidence only when its excerpt matches an immutable snapshot."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add_field_evidence(
        self,
        *,
        entity_type: str,
        entity_id: uuid.UUID,
        field_path: str,
        source_snapshot_id: uuid.UUID,
        excerpt: str,
        excerpt_start: int,
        excerpt_end: int,
        support_type: EvidenceSupportType,
        validator_status: EvidenceValidatorStatus,
    ) -> FieldEvidence:
        if not entity_type.strip():
            raise EvidenceIntegrityError("entity_type is required")
        if not field_path.strip():
            raise EvidenceIntegrityError("field_path is required")
        if excerpt_start < 0 or excerpt_end < excerpt_start:
            raise EvidenceIntegrityError("invalid evidence excerpt offsets")

        snapshot = self.session.get(SourceSnapshot, source_snapshot_id)
        if snapshot is None:
            raise EvidenceIntegrityError("source snapshot does not exist")
        if excerpt_end > len(snapshot.normalized_text):
            raise EvidenceIntegrityError("evidence excerpt offsets exceed snapshot text")
        if snapshot.normalized_text[excerpt_start:excerpt_end] != excerpt:
            raise EvidenceIntegrityError("evidence excerpt does not match snapshot text")

        evidence = FieldEvidence(
            entity_type=entity_type.strip(),
            entity_id=entity_id,
            field_path=field_path.strip(),
            source_snapshot_id=source_snapshot_id,
            excerpt=excerpt,
            excerpt_start=excerpt_start,
            excerpt_end=excerpt_end,
            support_type=support_type,
            validator_status=validator_status,
        )
        self.session.add(evidence)
        return evidence


__all__ = ["EvidenceIntegrityError", "EvidenceStore"]
