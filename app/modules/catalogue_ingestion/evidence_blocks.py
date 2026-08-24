"""Deterministic, versioned citation blocks for immutable source artifacts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalogue_ingestion.models import CatalogueEvidenceBlock, CatalogueSourceArtifact

EVIDENCE_BLOCK_CANONICALIZATION_VERSION = "evidence-blocks.v1"
MAX_EVIDENCE_BLOCK_CHARACTERS = 1_200


@dataclass(frozen=True, slots=True)
class CanonicalEvidenceBlock:
    block_id: str
    block_index: int
    start_offset: int
    end_offset: int
    text: str
    locator: dict[str, int]


def canonical_evidence_blocks(text: str) -> tuple[CanonicalEvidenceBlock, ...]:
    """Split normalized source text deterministically without changing offsets."""

    if not text:
        return ()
    spans: list[tuple[int, int]] = []
    start = 0
    while start < len(text):
        upper = min(len(text), start + MAX_EVIDENCE_BLOCK_CHARACTERS)
        end = upper
        if upper < len(text):
            paragraph = text.rfind("\n\n", start + 1, upper + 1)
            line = text.rfind("\n", start + 1, upper + 1)
            space = text.rfind(" ", start + 1, upper + 1)
            end = max(paragraph, line, space)
            if end <= start:
                end = upper
        while end < len(text) and text[end].isspace():
            end += 1
        if end <= start:
            end = min(len(text), start + 1)
        spans.append((start, end))
        start = end

    blocks: list[CanonicalEvidenceBlock] = []
    for index, (start_offset, end_offset) in enumerate(spans):
        block_text = text[start_offset:end_offset]
        identity = "\x1f".join(
            (
                EVIDENCE_BLOCK_CANONICALIZATION_VERSION,
                str(index),
                str(start_offset),
                str(end_offset),
                block_text,
            )
        )
        blocks.append(
            CanonicalEvidenceBlock(
                block_id=hashlib.sha256(identity.encode("utf-8")).hexdigest(),
                block_index=index,
                start_offset=start_offset,
                end_offset=end_offset,
                text=block_text,
                locator={"start_offset": start_offset, "end_offset": end_offset},
            )
        )
    return tuple(blocks)


def ensure_evidence_blocks(
    session: Session, artifact: CatalogueSourceArtifact
) -> tuple[CatalogueEvidenceBlock, ...]:
    """Persist the canonical block set once for an immutable artifact."""

    existing = tuple(
        session.scalars(
            select(CatalogueEvidenceBlock)
            .where(CatalogueEvidenceBlock.artifact_id == artifact.id)
            .order_by(CatalogueEvidenceBlock.block_index)
        )
    )
    if existing:
        return existing
    blocks = canonical_evidence_blocks(artifact.normalized_text)
    persisted = tuple(
        CatalogueEvidenceBlock(
            artifact_id=artifact.id,
            block_id=block.block_id,
            canonicalization_version=EVIDENCE_BLOCK_CANONICALIZATION_VERSION,
            block_index=block.block_index,
            start_offset=block.start_offset,
            end_offset=block.end_offset,
            text=block.text,
            locator=block.locator,
        )
        for block in blocks
    )
    session.add_all(persisted)
    return persisted


__all__ = [
    "EVIDENCE_BLOCK_CANONICALIZATION_VERSION",
    "MAX_EVIDENCE_BLOCK_CHARACTERS",
    "CanonicalEvidenceBlock",
    "canonical_evidence_blocks",
    "ensure_evidence_blocks",
]
