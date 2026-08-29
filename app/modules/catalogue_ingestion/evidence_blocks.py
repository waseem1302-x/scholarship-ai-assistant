"""Deterministic complete-document evidence blocks with exact artifact offsets."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalogue_ingestion.evidence_block_models import (
    EVIDENCE_BLOCK_BUILDER_VERSION,
    CatalogueEvidenceBlock,
)
from app.modules.catalogue_ingestion.models import CatalogueSourceArtifact

DEFAULT_EVIDENCE_BLOCK_TARGET_CHARS = 8_000
DEFAULT_EVIDENCE_BLOCK_MAX_CHARS = 12_000
_MIN_PREFERRED_CUT = 0.55


@dataclass(frozen=True, slots=True)
class EvidenceBlockSpec:
    block_index: int
    block_key: str
    block_hash: str
    source_content_hash: str
    start_offset: int
    end_offset: int
    block_text: str
    heading: str | None
    section_key: str | None
    coordinate_json: tuple[dict[str, Any], ...]
    topology_hints: tuple[str, ...]
    language_hints: tuple[str, ...]
    source_role: str
    builder_version: str = EVIDENCE_BLOCK_BUILDER_VERSION


def build_evidence_blocks(
    text: str,
    *,
    source_artifact_id: uuid.UUID,
    source_content_hash: str,
    source_role: str,
    fetch_metadata: dict[str, Any] | None = None,
    target_chars: int = DEFAULT_EVIDENCE_BLOCK_TARGET_CHARS,
    max_chars: int = DEFAULT_EVIDENCE_BLOCK_MAX_CHARS,
) -> tuple[EvidenceBlockSpec, ...]:
    """Cover the complete immutable artifact text without silent truncation.

    Offsets are exact positions in ``CatalogueSourceArtifact.normalized_text``. The builder performs
    no masking or normalization after those offsets are chosen. Acquisition coordinates are carried
    forward when the format adapter supplied them.
    """

    if target_chars < 256:
        raise ValueError("target_chars must be at least 256")
    if max_chars < target_chars:
        raise ValueError("max_chars must be greater than or equal to target_chars")
    if not source_content_hash or len(source_content_hash) > 128:
        raise ValueError("source_content_hash is required")
    if not source_role.strip():
        raise ValueError("source_role is required")
    if not text:
        return ()

    metadata = dict(fetch_metadata or {})
    heading_positions = _heading_positions(text)
    language_hints = _string_tuple(metadata.get("language_hints"))
    topology_hints = _topology_hints(metadata, source_role)
    blocks: list[EvidenceBlockSpec] = []
    start = 0
    index = 0
    text_length = len(text)
    while start < text_length:
        end = _preferred_cut(text, start=start, target_chars=target_chars, max_chars=max_chars)
        if end <= start:
            end = min(text_length, start + max_chars)
        block_text = text[start:end]
        heading = _active_heading(heading_positions, start, end)
        block_hash = hashlib.sha256(block_text.encode("utf-8")).hexdigest()
        section_key = _section_key(heading, index)
        block_key = _block_key(
            source_artifact_id=source_artifact_id,
            source_content_hash=source_content_hash,
            start=start,
            end=end,
            block_hash=block_hash,
        )
        coordinates = tuple(_coordinates_for_span(metadata.get("coordinates"), start, end))
        blocks.append(
            EvidenceBlockSpec(
                block_index=index,
                block_key=block_key,
                block_hash=block_hash,
                source_content_hash=source_content_hash,
                start_offset=start,
                end_offset=end,
                block_text=block_text,
                heading=heading,
                section_key=section_key,
                coordinate_json=coordinates,
                topology_hints=topology_hints,
                language_hints=language_hints,
                source_role=source_role.strip(),
            )
        )
        start = end
        index += 1

    if blocks[-1].end_offset != text_length:
        raise AssertionError("evidence block builder did not cover the complete artifact")
    for previous, current in zip(blocks, blocks[1:], strict=False):
        if previous.end_offset != current.start_offset:
            raise AssertionError("evidence block spans must be contiguous")
    return tuple(blocks)


class CatalogueEvidenceBlockBuilder:
    """Persist one immutable builder version per source artifact."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def persist_artifact(
        self,
        *,
        candidate_id: uuid.UUID,
        source_id: uuid.UUID,
        artifact: CatalogueSourceArtifact,
        source_role: str,
    ) -> list[CatalogueEvidenceBlock]:
        existing = list(
            self.session.scalars(
                select(CatalogueEvidenceBlock)
                .where(
                    CatalogueEvidenceBlock.source_artifact_id == artifact.id,
                    CatalogueEvidenceBlock.builder_version == EVIDENCE_BLOCK_BUILDER_VERSION,
                )
                .order_by(CatalogueEvidenceBlock.block_index)
            )
        )
        if existing:
            return existing

        specs = build_evidence_blocks(
            artifact.normalized_text,
            source_artifact_id=artifact.id,
            source_content_hash=artifact.content_hash,
            source_role=source_role,
            fetch_metadata=artifact.fetch_metadata,
        )
        records = [
            CatalogueEvidenceBlock(
                candidate_id=candidate_id,
                source_id=source_id,
                source_artifact_id=artifact.id,
                block_index=spec.block_index,
                block_key=spec.block_key,
                block_hash=spec.block_hash,
                source_content_hash=spec.source_content_hash,
                start_offset=spec.start_offset,
                end_offset=spec.end_offset,
                block_text=spec.block_text,
                heading=spec.heading,
                section_key=spec.section_key,
                coordinate_json=list(spec.coordinate_json),
                topology_hints=list(spec.topology_hints),
                language_hints=list(spec.language_hints),
                source_role=spec.source_role,
                builder_version=spec.builder_version,
            )
            for spec in specs
        ]
        self.session.add_all(records)
        self.session.flush()
        return records


def _preferred_cut(text: str, *, start: int, target_chars: int, max_chars: int) -> int:
    hard_end = min(len(text), start + max_chars)
    if hard_end == len(text):
        return hard_end
    preferred_start = min(hard_end, start + max(1, int(target_chars * _MIN_PREFERRED_CUT)))
    target_end = min(hard_end, start + target_chars)
    search_start = max(preferred_start, target_end - 1_500)

    for pattern in ("\n\n", "\n"):
        position = text.rfind(pattern, search_start, hard_end)
        if position >= preferred_start:
            return position + len(pattern)
    for match in reversed(list(re.finditer(r"[.!?。！？]\s+", text[search_start:hard_end]))):
        position = search_start + match.end()
        if position >= preferred_start:
            return position
    position = text.rfind(" ", search_start, hard_end)
    if position >= preferred_start:
        return position + 1
    return hard_end


def _heading_positions(text: str) -> tuple[tuple[int, str], ...]:
    positions: list[tuple[int, str]] = []
    offset = 0
    for raw_line in text.splitlines(keepends=True):
        stripped = raw_line.strip()
        if _looks_like_heading(stripped):
            positions.append((offset, stripped.lstrip("#").strip()[:500]))
        offset += len(raw_line)
    return tuple(positions)


def _looks_like_heading(value: str) -> bool:
    if not value or len(value) > 180:
        return False
    if value.startswith("#"):
        return True
    if re.match(r"^(?:\d+(?:\.\d+)*|[A-Z]|[IVXLC]+)[.)\-:]\s+\S", value):
        return True
    letters = [character for character in value if character.isalpha()]
    if len(letters) >= 4 and sum(character.isupper() for character in letters) / len(letters) >= 0.8:
        return True
    return value.endswith(":") and len(value.split()) <= 12


def _active_heading(
    positions: tuple[tuple[int, str], ...],
    start: int,
    end: int,
) -> str | None:
    active: str | None = None
    for position, heading in positions:
        if position > end:
            break
        if position <= start or (start <= position < end and active is None):
            active = heading
    return active


def _section_key(heading: str | None, block_index: int) -> str:
    if not heading:
        return f"block-{block_index:05d}"
    normalized = re.sub(r"[^\w]+", "-", heading.casefold(), flags=re.UNICODE).strip("-")
    return (normalized or f"block-{block_index:05d}")[:255]


def _block_key(
    *,
    source_artifact_id: uuid.UUID,
    source_content_hash: str,
    start: int,
    end: int,
    block_hash: str,
) -> str:
    payload = (
        f"{source_artifact_id}|{source_content_hash}|{EVIDENCE_BLOCK_BUILDER_VERSION}|"
        f"{start}|{end}|{block_hash}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple, set)):
        return ()
    return tuple(
        dict.fromkeys(
            item.strip()[:64]
            for item in (str(raw) for raw in value)
            if item.strip()
        )
    )


def _topology_hints(metadata: dict[str, Any], source_role: str) -> tuple[str, ...]:
    raw = metadata.get("topology_hints")
    hints = list(_string_tuple(raw))
    canonical_hint = metadata.get("canonical_url_hint")
    if isinstance(canonical_hint, str) and canonical_hint.strip():
        hints.append(f"canonical:{canonical_hint.strip()[:500]}")
    hints.append(f"source_role:{source_role.strip()[:64]}")
    return tuple(dict.fromkeys(hints))


def _coordinates_for_span(value: object, start: int, end: int) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for raw in value[:500]:
        if not isinstance(raw, dict):
            continue
        coordinate = dict(raw)
        raw_start = coordinate.get("start_offset")
        raw_end = coordinate.get("end_offset")
        if isinstance(raw_start, int) and isinstance(raw_end, int):
            if raw_end <= start or raw_start >= end:
                continue
        result.append(coordinate)
        if len(result) >= 100:
            break
    return result


__all__ = [
    "DEFAULT_EVIDENCE_BLOCK_MAX_CHARS",
    "DEFAULT_EVIDENCE_BLOCK_TARGET_CHARS",
    "CatalogueEvidenceBlockBuilder",
    "EvidenceBlockSpec",
    "build_evidence_blocks",
]
