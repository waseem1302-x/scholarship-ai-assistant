"""Safe content-addressed extraction caching with explicit decision reasons."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalogue_ingestion.evidence_block_models import (
    CatalogueEvidenceBlock,
    CatalogueEvidenceRoute,
)
from app.modules.catalogue_ingestion.extraction_cache_models import (
    EXTRACTION_CACHE_VERSION,
    CatalogueExtractionCacheEntry,
    CatalogueExtractionCacheEvent,
    ExtractionCacheDecision,
)
from app.modules.catalogue_ingestion.models import (
    CatalogueCandidateSource,
    CatalogueSourceArtifact,
)
from app.modules.catalogue_ingestion.topology_models import (
    CatalogueScopeNode,
    CatalogueSourceScopeLink,
)


@dataclass(frozen=True, slots=True)
class ExtractionCacheIdentity:
    normalized_content_hash: str
    authority_context_hash: str
    evidence_block_set_hash: str
    scope_fingerprint: str
    objective_bundle: tuple[str, ...]
    objective_bundle_hash: str
    prompt_hash: str
    schema_version: str
    parser_version: str
    normalizer_version: str
    resolver_version: str
    validator_version: str
    provider: str
    model: str
    capability_identity_hash: str
    cache_version: str = EXTRACTION_CACHE_VERSION

    @property
    def cache_key(self) -> str:
        payload = {
            "authority_context_hash": self.authority_context_hash,
            "cache_version": self.cache_version,
            "capability_identity_hash": self.capability_identity_hash,
            "evidence_block_set_hash": self.evidence_block_set_hash,
            "model": self.model,
            "normalized_content_hash": self.normalized_content_hash,
            "normalizer_version": self.normalizer_version,
            "objective_bundle": list(self.objective_bundle),
            "objective_bundle_hash": self.objective_bundle_hash,
            "parser_version": self.parser_version,
            "prompt_hash": self.prompt_hash,
            "provider": self.provider,
            "resolver_version": self.resolver_version,
            "schema_version": self.schema_version,
            "scope_fingerprint": self.scope_fingerprint,
            "validator_version": self.validator_version,
        }
        return _stable_hash(payload)


class CatalogueExtractionCache:
    """Read/write boundary for validated reusable extraction output."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def build_identity(
        self,
        *,
        source: CatalogueCandidateSource,
        artifact: CatalogueSourceArtifact,
        blocks: Sequence[CatalogueEvidenceBlock],
        routes: Sequence[CatalogueEvidenceRoute],
        objectives: Iterable[str],
        prompt_hash: str,
        schema_version: str,
        parser_version: str,
        normalizer_version: str,
        resolver_version: str,
        validator_version: str,
        provider: str,
        model: str,
        capability_identity: str,
        evidence_spans: Sequence[tuple[str, int, int]] | None = None,
    ) -> ExtractionCacheIdentity:
        if not source.is_official or source.trust_tier is None:
            raise ValueError("only verified official evidence may enter the extraction cache")
        if artifact.source_id != source.id:
            raise ValueError("cache artifact does not belong to source")
        if any(block.source_artifact_id != artifact.id for block in blocks):
            raise ValueError("cache evidence block does not belong to artifact")
        objective_bundle = tuple(
            sorted({str(value).strip() for value in objectives if str(value).strip()})
        )
        if not objective_bundle:
            raise ValueError("cache objective bundle cannot be empty")
        return ExtractionCacheIdentity(
            normalized_content_hash=artifact.content_hash,
            authority_context_hash=self._authority_context_hash(source, artifact),
            evidence_block_set_hash=_evidence_block_set_hash(
                blocks,
                evidence_spans=evidence_spans,
            ),
            scope_fingerprint=_scope_fingerprint(routes),
            objective_bundle=objective_bundle,
            objective_bundle_hash=_stable_hash(list(objective_bundle)),
            prompt_hash=_required_version(prompt_hash, "prompt_hash"),
            schema_version=_required_version(schema_version, "schema_version"),
            parser_version=_required_version(parser_version, "parser_version"),
            normalizer_version=_required_version(normalizer_version, "normalizer_version"),
            resolver_version=_required_version(resolver_version, "resolver_version"),
            validator_version=_required_version(validator_version, "validator_version"),
            provider=_required_version(provider, "provider"),
            model=_required_version(model, "model"),
            capability_identity_hash=hashlib.sha256(
                _required_version(capability_identity, "capability_identity").encode("utf-8")
            ).hexdigest(),
        )

    def lookup(
        self,
        identity: ExtractionCacheIdentity,
        *,
        run_id: uuid.UUID | None,
        candidate_id: uuid.UUID | None,
        source_artifact_id: uuid.UUID | None,
        validator: Callable[[dict[str, Any]], bool] | None = None,
    ) -> CatalogueExtractionCacheEntry | None:
        entry = self.session.scalar(
            select(CatalogueExtractionCacheEntry).where(
                CatalogueExtractionCacheEntry.cache_key == identity.cache_key
            )
        )
        hit_reason = "all_cache_identity_dimensions_match"
        if entry is None:
            entry = self._resolver_compatible_entry(identity)
            if entry is not None:
                hit_reason = "resolver_version_changed_revalidated"
        if entry is None:
            self.record_event(
                identity.cache_key,
                decision=ExtractionCacheDecision.MISS,
                reason="cache_key_not_found",
                run_id=run_id,
                candidate_id=candidate_id,
                source_artifact_id=source_artifact_id,
            )
            return None
        if validator is not None:
            try:
                accepted = bool(validator(dict(entry.output_json)))
            except Exception:
                accepted = False
            if not accepted:
                self.record_event(
                    identity.cache_key,
                    decision=ExtractionCacheDecision.INVALIDATED,
                    reason="current_validation_boundary_rejected",
                    run_id=run_id,
                    candidate_id=candidate_id,
                    source_artifact_id=source_artifact_id,
                    detail={
                        "entry_id": str(entry.id),
                        "entry_resolver_version": entry.resolver_version,
                        "requested_resolver_version": identity.resolver_version,
                    },
                )
                return None
        self.record_event(
            identity.cache_key,
            decision=ExtractionCacheDecision.HIT,
            reason=hit_reason,
            run_id=run_id,
            candidate_id=candidate_id,
            source_artifact_id=source_artifact_id,
            detail={
                "entry_id": str(entry.id),
                "entry_resolver_version": entry.resolver_version,
                "requested_resolver_version": identity.resolver_version,
            },
        )
        return entry

    def store_success(
        self,
        identity: ExtractionCacheIdentity,
        *,
        output_json: dict[str, Any],
        origin_candidate_id: uuid.UUID | None,
        origin_source_id: uuid.UUID | None,
        source_artifact_id: uuid.UUID | None,
        evidence_block_keys: Sequence[str],
    ) -> CatalogueExtractionCacheEntry:
        existing = self.session.scalar(
            select(CatalogueExtractionCacheEntry).where(
                CatalogueExtractionCacheEntry.cache_key == identity.cache_key
            )
        )
        if existing is not None:
            return existing
        entry = CatalogueExtractionCacheEntry(
            cache_key=identity.cache_key,
            origin_candidate_id=origin_candidate_id,
            origin_source_id=origin_source_id,
            source_artifact_id=source_artifact_id,
            normalized_content_hash=identity.normalized_content_hash,
            authority_context_hash=identity.authority_context_hash,
            evidence_block_set_hash=identity.evidence_block_set_hash,
            evidence_block_keys=list(evidence_block_keys),
            scope_fingerprint=identity.scope_fingerprint,
            objective_bundle=list(identity.objective_bundle),
            objective_bundle_hash=identity.objective_bundle_hash,
            prompt_hash=identity.prompt_hash,
            schema_version=identity.schema_version,
            parser_version=identity.parser_version,
            normalizer_version=identity.normalizer_version,
            resolver_version=identity.resolver_version,
            validator_version=identity.validator_version,
            provider=identity.provider,
            model=identity.model,
            capability_identity_hash=identity.capability_identity_hash,
            output_json=dict(output_json),
            cache_version=identity.cache_version,
        )
        self.session.add(entry)
        self.session.flush()
        return entry

    def record_event(
        self,
        cache_key: str,
        *,
        decision: ExtractionCacheDecision,
        reason: str,
        run_id: uuid.UUID | None,
        candidate_id: uuid.UUID | None,
        source_artifact_id: uuid.UUID | None,
        detail: dict[str, Any] | None = None,
    ) -> CatalogueExtractionCacheEvent:
        event = CatalogueExtractionCacheEvent(
            run_id=run_id,
            candidate_id=candidate_id,
            source_artifact_id=source_artifact_id,
            cache_key=cache_key,
            decision=decision.value,
            reason=reason.strip()[:100] or "unspecified",
            detail_json=dict(detail or {}),
        )
        self.session.add(event)
        self.session.flush()
        return event

    def _resolver_compatible_entry(
        self,
        identity: ExtractionCacheIdentity,
    ) -> CatalogueExtractionCacheEntry | None:
        """Reuse raw extraction when only downstream resolution rules changed."""

        return self.session.scalar(
            select(CatalogueExtractionCacheEntry)
            .where(
                CatalogueExtractionCacheEntry.normalized_content_hash
                == identity.normalized_content_hash,
                CatalogueExtractionCacheEntry.authority_context_hash
                == identity.authority_context_hash,
                CatalogueExtractionCacheEntry.evidence_block_set_hash
                == identity.evidence_block_set_hash,
                CatalogueExtractionCacheEntry.scope_fingerprint == identity.scope_fingerprint,
                CatalogueExtractionCacheEntry.objective_bundle_hash
                == identity.objective_bundle_hash,
                CatalogueExtractionCacheEntry.prompt_hash == identity.prompt_hash,
                CatalogueExtractionCacheEntry.schema_version == identity.schema_version,
                CatalogueExtractionCacheEntry.parser_version == identity.parser_version,
                CatalogueExtractionCacheEntry.normalizer_version == identity.normalizer_version,
                CatalogueExtractionCacheEntry.validator_version == identity.validator_version,
                CatalogueExtractionCacheEntry.provider == identity.provider,
                CatalogueExtractionCacheEntry.model == identity.model,
                CatalogueExtractionCacheEntry.capability_identity_hash
                == identity.capability_identity_hash,
                CatalogueExtractionCacheEntry.cache_version == identity.cache_version,
            )
            .order_by(CatalogueExtractionCacheEntry.created_at.desc())
        )

    def _authority_context_hash(
        self,
        source: CatalogueCandidateSource,
        artifact: CatalogueSourceArtifact,
    ) -> str:
        links = list(
            self.session.execute(
                select(CatalogueSourceScopeLink, CatalogueScopeNode)
                .join(
                    CatalogueScopeNode,
                    CatalogueScopeNode.id == CatalogueSourceScopeLink.scope_node_id,
                )
                .where(
                    CatalogueSourceScopeLink.source_id == source.id,
                    (
                        CatalogueSourceScopeLink.source_artifact_id.is_(None)
                        | (CatalogueSourceScopeLink.source_artifact_id == artifact.id)
                    ),
                )
            )
        )
        scope_context = sorted(
            (
                node.node_type.value,
                node.canonical_key,
                node.lifecycle_key,
                link.relationship_type.value,
                link.confidence.value,
                bool(link.applicability_is_explicit),
            )
            for link, node in links
        )
        host = urlsplit(artifact.final_url).hostname or ""
        payload = {
            "official": True,
            "official_host": host.casefold(),
            "source_role": source.source_role.value,
            "trust_tier": source.trust_tier,
            "scope_context": scope_context,
        }
        return _stable_hash(payload)


def _evidence_block_set_hash(
    blocks: Sequence[CatalogueEvidenceBlock],
    *,
    evidence_spans: Sequence[tuple[str, int, int]] | None = None,
) -> str:
    if evidence_spans is not None:
        block_by_key = {block.block_key: block for block in blocks}
        identities = []
        for block_key, start_offset, end_offset in evidence_spans:
            block = block_by_key.get(block_key)
            if block is None:
                raise ValueError("cache evidence span references an unknown block")
            if not (block.start_offset <= start_offset < end_offset <= block.end_offset):
                raise ValueError("cache evidence span falls outside its persisted block")
            identities.append(
                (
                    block.source_content_hash,
                    start_offset,
                    end_offset,
                    block.block_hash,
                    block.builder_version,
                )
            )
        return _stable_hash(sorted(identities))
    identities = sorted(
        (
            block.source_content_hash,
            block.start_offset,
            block.end_offset,
            block.block_hash,
            block.builder_version,
        )
        for block in blocks
    )
    return _stable_hash(identities)


def _scope_fingerprint(routes: Sequence[CatalogueEvidenceRoute]) -> str:
    scope_rows = sorted(
        {
            (
                route.scope_type,
                route.scope_key,
                route.objective.value,
                route.coverage_input_fingerprint,
            )
            for route in routes
            if route.selected
        }
    )
    return _stable_hash(scope_rows)


def _required_version(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized


def _stable_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "CatalogueExtractionCache",
    "ExtractionCacheIdentity",
]
