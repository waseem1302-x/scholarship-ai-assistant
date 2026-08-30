"""Production catalogue ingestion composition for evidence-routed extraction."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.modules.catalogue_ingestion.claim_bundle_provider import (
    CatalogueBundleClaimProvider,
    bundle_claim_prompt_hash,
    get_bundle_claim_provider,
)
from app.modules.catalogue_ingestion.claim_bundle_schemas import (
    CLAIM_BUNDLE_SCHEMA_VERSION,
    ClaimBundleExtractionOutput,
    EvidenceBlockSpan,
    ExpandedClaimBundle,
    expand_claim_bundle,
)
from app.modules.catalogue_ingestion.claim_provider import (
    OBJECTIVE_ENTITY_TYPES,
    OBJECTIVE_FIELD_PATHS,
    ClaimOutputTruncated,
)
from app.modules.catalogue_ingestion.claim_resolution import resolve_claims
from app.modules.catalogue_ingestion.claim_schemas import (
    ClaimExtractionOutput,
    ClaimObjective,
    ObjectiveCoverageState,
)
from app.modules.catalogue_ingestion.evidence_block_models import (
    CatalogueEvidenceBlock,
    CatalogueEvidenceRoute,
)
from app.modules.catalogue_ingestion.evidence_blocks import CatalogueEvidenceBlockBuilder
from app.modules.catalogue_ingestion.evidence_routing import CatalogueEvidenceRouter
from app.modules.catalogue_ingestion.extraction_cache import CatalogueExtractionCache
from app.modules.catalogue_ingestion.extraction_cache_models import ExtractionCacheDecision
from app.modules.catalogue_ingestion.extraction_planner import (
    EXTRACTION_JOB_PLANNER_VERSION,
    CatalogueExtractionPlanner,
    ExtractionJobPlan,
    split_extraction_job,
)
from app.modules.catalogue_ingestion.graph_materializer import MextGraphMaterializer
from app.modules.catalogue_ingestion.hardened_service import HardenedCatalogueIngestionService
from app.modules.catalogue_ingestion.models import (
    CandidateSourceRole,
    CandidateSourceStatus,
    CandidateStatus,
    CatalogueCandidate,
    CatalogueCandidateSource,
    CatalogueExtractionAttempt,
    CatalogueIngestionRun,
    CatalogueJobState,
    CatalogueSourceArtifact,
    ExtractionAttemptStatus,
    IngestionMode,
)
from app.modules.catalogue_ingestion.pipeline_versions import (
    BUNDLE_NORMALIZER_VERSION,
    BUNDLE_PROVIDER_PARSER_VERSION,
    BUNDLE_RESOLVER_VERSION,
    BUNDLE_VALIDATOR_VERSION,
)
from app.modules.catalogue_ingestion.provider import (
    ExtractionProviderError,
    ExtractionSchemaError,
)
from app.modules.catalogue_ingestion.provider_execution import ProviderExecutionBudgetExhausted
from app.modules.opportunities.source_monitor import FetchedSource


@dataclass(slots=True)
class _BundleGroupAccumulator:
    source: CatalogueCandidateSource
    artifact: CatalogueSourceArtifact
    objectives: tuple[ClaimObjective, ...]
    chunk_outputs: list[dict[str, Any]] = field(default_factory=list)
    cache_keys: list[str] = field(default_factory=list)
    provider_attempt_ids: list[uuid.UUID] = field(default_factory=list)
    outputs: dict[ClaimObjective, list[ClaimExtractionOutput]] = field(default_factory=dict)

    def add(
        self,
        *,
        raw_output: ClaimBundleExtractionOutput,
        expanded: ExpandedClaimBundle,
        cache_key: str,
        provider_attempt_id: uuid.UUID | None,
    ) -> None:
        self.chunk_outputs.append(raw_output.model_dump(mode="json"))
        self.cache_keys.append(cache_key)
        if provider_attempt_id is not None:
            self.provider_attempt_ids.append(provider_attempt_id)
        for objective, output in expanded.outputs.items():
            self.outputs.setdefault(objective, []).append(output)


class ProductionCatalogueIngestionService(HardenedCatalogueIngestionService):
    """Hardened acquisition plus deterministic evidence routing, cache, and bundled extraction."""

    def __init__(
        self,
        session,
        settings,
        *,
        bundle_claim_extractor: CatalogueBundleClaimProvider | None = None,
        **kwargs,
    ) -> None:
        super().__init__(session, settings, **kwargs)
        self.evidence_block_builder = CatalogueEvidenceBlockBuilder(session)
        self.evidence_router = CatalogueEvidenceRouter(session)
        self.extraction_planner = CatalogueExtractionPlanner(session)
        self.extraction_cache = CatalogueExtractionCache(session)
        self.bundle_claim_extractor = bundle_claim_extractor or get_bundle_claim_provider(settings)

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
            (item for item in source.artifacts if item.content_hash == content_hash),
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
        """Execute only routed evidence jobs, reusing validated cache entries whenever possible."""

        self._heartbeat_candidate(run, candidate, run_lease_token)
        self.evidence_router.persist_candidate(candidate.id)
        self.session.flush()
        self._heartbeat_candidate(run, candidate, run_lease_token)

        sources = self._current_official_sources(candidate.id)
        if not sources:
            self._manual_review(run, candidate, "official_source_artifact_missing", run_lease_token)
            return
        source_by_id = {source.id: source for source in sources}
        artifact_by_id: dict[uuid.UUID, CatalogueSourceArtifact] = {}
        for source in sources:
            artifact = next(
                (item for item in source.artifacts if item.content_hash == source.content_hash),
                None,
            )
            if artifact is None:
                self._manual_review(
                    run,
                    candidate,
                    "current_source_artifact_missing",
                    run_lease_token,
                )
                return
            artifact_by_id[artifact.id] = artifact

        blocks = list(
            self.session.scalars(
                select(CatalogueEvidenceBlock).where(
                    CatalogueEvidenceBlock.candidate_id == candidate.id,
                    CatalogueEvidenceBlock.source_artifact_id.in_(artifact_by_id),
                )
            )
        )
        blocks_by_id = {block.id: block for block in blocks}
        all_routes = list(
            self.session.scalars(
                select(CatalogueEvidenceRoute).where(
                    CatalogueEvidenceRoute.candidate_id == candidate.id,
                    CatalogueEvidenceRoute.selected.is_(True),
                )
            )
        )

        plan = self.extraction_planner.plan_candidate(
            candidate.id,
            max_input_characters=run.max_input_characters,
            run_max_output_tokens=run.max_output_tokens,
            input_cost_per_million=self.settings.catalogue_ai_input_cost_per_million,
            output_cost_per_million=self.settings.catalogue_ai_output_cost_per_million,
        )
        self.repository.refresh_provider_accounting(run)
        maximum_calls, maximum_cost = self._maximum_execution_envelope(
            plan.jobs,
            blocks_by_id=blocks_by_id,
            routes=all_routes,
            run=run,
        )
        remaining_calls = max(0, run.max_model_calls - run.model_calls)
        remaining_cost = max(Decimal("0"), run.max_estimated_cost - run.estimated_cost)
        self._persist_plan_checkpoint(
            run,
            candidate,
            run_lease_token,
            plan_jobs=plan.jobs,
            refusal_reasons=plan.refusal_reasons,
            estimated_calls=plan.estimated_calls,
            estimated_cost=plan.estimated_cost_upper,
            maximum_calls=min(maximum_calls, remaining_calls),
            maximum_cost=min(maximum_cost, remaining_cost),
        )
        if plan.refusal_reasons:
            self._manual_review(run, candidate, plan.refusal_reasons[0], run_lease_token)
            return
        if plan.estimated_calls > remaining_calls or plan.estimated_cost_upper > remaining_cost:
            raise ProviderExecutionBudgetExhausted("planned_bundle_extraction_exceeds_remaining_budget")

        groups: dict[tuple[uuid.UUID, tuple[str, ...]], _BundleGroupAccumulator] = {}
        pending_jobs = list(plan.jobs)
        while pending_jobs:
            self._heartbeat_candidate(run, candidate, run_lease_token)
            job = pending_jobs.pop(0)
            source = source_by_id.get(job.source_id)
            artifact = artifact_by_id.get(job.source_artifact_id)
            if source is None or artifact is None:
                self._manual_review(run, candidate, "planned_source_revision_missing", run_lease_token)
                return
            job_blocks = [blocks_by_id[item.block_id] for item in job.evidence]
            job_routes = self._job_routes(job, all_routes)
            prompt_hash = bundle_claim_prompt_hash(job.objectives)
            identity = self.extraction_cache.build_identity(
                source=source,
                artifact=artifact,
                blocks=job_blocks,
                routes=job_routes,
                objectives=[objective.value for objective in job.objectives],
                prompt_hash=prompt_hash,
                schema_version=CLAIM_BUNDLE_SCHEMA_VERSION,
                parser_version=BUNDLE_PROVIDER_PARSER_VERSION,
                normalizer_version=BUNDLE_NORMALIZER_VERSION,
                resolver_version=BUNDLE_RESOLVER_VERSION,
                validator_version=BUNDLE_VALIDATOR_VERSION,
                provider=self.bundle_claim_extractor.name,
                model=self.bundle_claim_extractor.model,
                capability_identity=self.bundle_claim_extractor.capability_identity,
            )
            cached = self.extraction_cache.lookup(
                identity,
                run_id=run.id,
                candidate_id=candidate.id,
                source_artifact_id=artifact.id,
                validator=lambda payload, job=job, blocks=job_blocks: self._cache_payload_valid(
                    payload,
                    job=job,
                    blocks=blocks,
                ),
            )
            if cached is not None:
                raw_output = ClaimBundleExtractionOutput.model_validate(cached.output_json)
                expanded = self._expand_bundle(raw_output, job=job, blocks=job_blocks)
                self._accumulate_bundle_group(
                    groups,
                    source=source,
                    artifact=artifact,
                    job=job,
                    raw_output=raw_output,
                    expanded=expanded,
                    cache_key=identity.cache_key,
                    provider_attempt_id=None,
                )
                continue

            resumable = self.repository.start_or_resume_job(
                run_id=run.id,
                candidate_id=candidate.id,
                stage="claim_bundle_extraction",
                job_key=self._resume_job_key(candidate.id, identity.cache_key),
                worker_id=candidate.claimed_by or "",
                run_lease_token=run_lease_token,
                candidate_lease_token=candidate.lease_token or "",
                checkpoint={
                    "cache_key": identity.cache_key,
                    "planner_job_key": job.job_key,
                    "objectives": [item.value for item in job.objectives],
                    "evidence_block_keys": [item.block_key for item in job.evidence],
                    "outcome": "pending",
                },
            )
            if resumable.state is CatalogueJobState.SUCCEEDED:
                outcome = str((resumable.checkpoint or {}).get("outcome") or "")
                if outcome == "split":
                    children = self._split_job(
                        job,
                        blocks_by_id=blocks_by_id,
                        routes=job_routes,
                        run=run,
                    )
                    expected = list((resumable.checkpoint or {}).get("child_job_keys") or [])
                    actual = [child.job_key for child in children]
                    if expected and expected != actual:
                        self._manual_review(
                            run,
                            candidate,
                            "resumable_split_plan_changed",
                            run_lease_token,
                        )
                        return
                    pending_jobs = [*children, *pending_jobs]
                    continue
                self._manual_review(
                    run,
                    candidate,
                    "resumable_job_cache_missing",
                    run_lease_token,
                )
                return

            source_links = artifact.fetch_metadata.get("links", [])
            if not isinstance(source_links, list):
                source_links = []
            try:
                execution = self.provider_executor.execute(
                    run=run,
                    run_lease_token=run_lease_token,
                    candidate=candidate,
                    source=source,
                    artifact=artifact,
                    provider=self.bundle_claim_extractor,
                    schema_version=CLAIM_BUNDLE_SCHEMA_VERSION,
                    prompt_hash=prompt_hash,
                    content_hash=artifact.content_hash,
                    source_text=job.evidence_text,
                    objective=None,
                    objective_bundle=[item.value for item in job.objectives],
                    evidence_block_keys=[item.block_key for item in job.evidence],
                    logical_job_key=self._provider_job_key(candidate.id, identity.cache_key),
                    max_output_tokens=job.max_output_tokens,
                    parser_version=BUNDLE_PROVIDER_PARSER_VERSION,
                    normalizer_version=BUNDLE_NORMALIZER_VERSION,
                    invoke=lambda job=job, source_links=source_links: self.bundle_claim_extractor.extract_bundle(
                        source_url=artifact.final_url,
                        evidence_text=job.evidence_text,
                        objectives=job.objectives,
                        scope_targets=[
                            {
                                "objective": target.objective.value,
                                "scope_type": target.scope_type,
                                "scope_key": target.scope_key,
                                "coverage_input_fingerprint": target.coverage_input_fingerprint,
                            }
                            for target in job.scopes
                        ],
                        source_links=source_links,
                        max_output_tokens=job.max_output_tokens,
                    ),
                    heartbeat=lambda: self._heartbeat_candidate(
                        run, candidate, run_lease_token
                    ),
                )
            except ClaimOutputTruncated as exc:
                self.metrics.add("ai_schema_failures")
                self._observe_provider_usage(exc.usage)
                children = self._split_job(
                    job,
                    blocks_by_id=blocks_by_id,
                    routes=job_routes,
                    run=run,
                )
                if children:
                    self.repository.complete_job(
                        resumable.id,
                        worker_id=candidate.claimed_by or "",
                        run_lease_token=run_lease_token,
                        candidate_lease_token=candidate.lease_token or "",
                        checkpoint={
                            "cache_key": identity.cache_key,
                            "planner_job_key": job.job_key,
                            "outcome": "split",
                            "error_code": exc.code,
                            "provider_attempt_id": str(
                                getattr(exc, "provider_attempt_id", "") or ""
                            ),
                            "child_job_keys": [child.job_key for child in children],
                        },
                    )
                    pending_jobs = [*children, *pending_jobs]
                    continue
                self.repository.complete_job(
                    resumable.id,
                    worker_id=candidate.claimed_by or "",
                    run_lease_token=run_lease_token,
                    candidate_lease_token=candidate.lease_token or "",
                    checkpoint={
                        "cache_key": identity.cache_key,
                        "planner_job_key": job.job_key,
                        "outcome": "terminal_truncation",
                        "error_code": exc.code,
                        "provider_attempt_id": str(
                            getattr(exc, "provider_attempt_id", "") or ""
                        ),
                    },
                )
                self._manual_review(run, candidate, exc.code, run_lease_token)
                return
            except ExtractionSchemaError as exc:
                self.metrics.add("ai_schema_failures")
                self._observe_provider_usage(exc.usage)
                self.repository.checkpoint_job(
                    resumable.id,
                    worker_id=candidate.claimed_by or "",
                    run_lease_token=run_lease_token,
                    candidate_lease_token=candidate.lease_token or "",
                    checkpoint={
                        "cache_key": identity.cache_key,
                        "planner_job_key": job.job_key,
                        "outcome": "schema_failed",
                        "error_code": exc.code,
                        "provider_attempt_id": str(
                            getattr(exc, "provider_attempt_id", "") or ""
                        ),
                    },
                )
                self._manual_review(run, candidate, exc.code, run_lease_token)
                return
            except ExtractionProviderError as exc:
                self.metrics.add("ai_extraction_failures")
                self._observe_provider_usage(exc.usage)
                self.repository.checkpoint_job(
                    resumable.id,
                    worker_id=candidate.claimed_by or "",
                    run_lease_token=run_lease_token,
                    candidate_lease_token=candidate.lease_token or "",
                    checkpoint={
                        "cache_key": identity.cache_key,
                        "planner_job_key": job.job_key,
                        "outcome": "provider_failed",
                        "error_code": exc.code,
                        "provider_attempt_id": str(
                            getattr(exc, "provider_attempt_id", "") or ""
                        ),
                    },
                )
                self._manual_review(run, candidate, exc.code, run_lease_token)
                return

            result = execution.result
            self._observe_provider_usage(result.usage)
            raw_output = result.output
            try:
                expanded = self._expand_bundle(raw_output, job=job, blocks=job_blocks)
            except ExtractionSchemaError:
                self.extraction_cache.record_event(
                    identity.cache_key,
                    decision=ExtractionCacheDecision.QUARANTINED,
                    reason="bundle_validation_boundary_rejected",
                    run_id=run.id,
                    candidate_id=candidate.id,
                    source_artifact_id=artifact.id,
                    detail={"provider_attempt_id": str(execution.provider_attempt_id)},
                )
                self.repository.checkpoint_job(
                    resumable.id,
                    worker_id=candidate.claimed_by or "",
                    run_lease_token=run_lease_token,
                    candidate_lease_token=candidate.lease_token or "",
                    checkpoint={
                        "cache_key": identity.cache_key,
                        "planner_job_key": job.job_key,
                        "outcome": "validation_failed",
                        "provider_attempt_id": str(execution.provider_attempt_id),
                    },
                )
                self._manual_review(
                    run,
                    candidate,
                    "bundle_validation_failed",
                    run_lease_token,
                )
                return

            cache_entry = self.extraction_cache.store_success(
                identity,
                output_json=raw_output.model_dump(mode="json"),
                origin_candidate_id=candidate.id,
                origin_source_id=source.id,
                source_artifact_id=artifact.id,
                evidence_block_keys=[item.block_key for item in job.evidence],
            )
            self.repository.complete_job(
                resumable.id,
                worker_id=candidate.claimed_by or "",
                run_lease_token=run_lease_token,
                candidate_lease_token=candidate.lease_token or "",
                checkpoint={
                    "cache_key": identity.cache_key,
                    "cache_entry_id": str(cache_entry.id),
                    "planner_job_key": job.job_key,
                    "outcome": "cached",
                    "provider_attempt_id": str(execution.provider_attempt_id),
                },
            )
            self._accumulate_bundle_group(
                groups,
                source=source,
                artifact=artifact,
                job=job,
                raw_output=raw_output,
                expanded=expanded,
                cache_key=identity.cache_key,
                provider_attempt_id=execution.provider_attempt_id,
            )

        self._finalize_bundle_resolution(
            run,
            candidate,
            run_lease_token,
            sources=sources,
            groups=groups,
        )

    def _current_official_sources(self, candidate_id: uuid.UUID) -> list[CatalogueCandidateSource]:
        persisted = list(
            self.session.scalars(
                select(CatalogueCandidateSource)
                .where(CatalogueCandidateSource.candidate_id == candidate_id)
                .options(selectinload(CatalogueCandidateSource.artifacts))
            )
        )
        role_order = self._source_role_order()
        sources = [
            source
            for source in persisted
            if source.is_official
            and source.status is CandidateSourceStatus.FETCHED
            and source.content_hash
            and source.artifacts
        ]
        sources.sort(
            key=lambda item: (
                role_order[item.source_role],
                item.trust_tier or 999,
                item.canonical_url,
            )
        )
        return sources

    def _job_routes(
        self,
        job: ExtractionJobPlan,
        routes: list[CatalogueEvidenceRoute],
    ) -> list[CatalogueEvidenceRoute]:
        block_ids = {item.block_id for item in job.evidence}
        scope_keys = {
            (
                target.objective,
                target.scope_type,
                target.scope_key,
                target.coverage_input_fingerprint,
            )
            for target in job.scopes
        }
        return [
            route
            for route in routes
            if route.selected
            and route.evidence_block_id in block_ids
            and (
                route.objective,
                route.scope_type,
                route.scope_key,
                route.coverage_input_fingerprint,
            )
            in scope_keys
        ]

    def _cache_payload_valid(
        self,
        payload: dict[str, Any],
        *,
        job: ExtractionJobPlan,
        blocks: list[CatalogueEvidenceBlock],
    ) -> bool:
        try:
            raw = ClaimBundleExtractionOutput.model_validate(payload)
            self._expand_bundle(raw, job=job, blocks=blocks)
        except (ValueError, ExtractionSchemaError):
            return False
        return True

    def _expand_bundle(
        self,
        raw_output: ClaimBundleExtractionOutput,
        *,
        job: ExtractionJobPlan,
        blocks: list[CatalogueEvidenceBlock],
    ) -> ExpandedClaimBundle:
        expanded = expand_claim_bundle(
            raw_output,
            requested_objectives=job.objectives,
            blocks_by_key={
                block.block_key: EvidenceBlockSpan(
                    block_key=block.block_key,
                    start_offset=block.start_offset,
                    end_offset=block.end_offset,
                    block_text=block.block_text,
                )
                for block in blocks
            },
            allowed_entity_types=OBJECTIVE_ENTITY_TYPES,
            allowed_field_paths=OBJECTIVE_FIELD_PATHS,
        )
        severe_prefixes = (
            "unknown_evidence_block:",
            "invalid_evidence_span:",
            "unrequested_objective_claim:",
            "objective_entity_mismatch:",
            "invalid_atomic_claim:",
            "objective_field_mismatch:",
            "provider_invalid_claims_dropped:",
        )
        warnings = [
            warning
            for output in expanded.outputs.values()
            for warning in output.warnings
        ]
        if any(warning.startswith(severe_prefixes) for warning in warnings):
            raise ExtractionSchemaError(
                "Bundled claim output failed deterministic evidence validation",
                failure_class="schema_validation_failure",
            )
        return expanded

    def _accumulate_bundle_group(
        self,
        groups: dict[tuple[uuid.UUID, tuple[str, ...]], _BundleGroupAccumulator],
        *,
        source: CatalogueCandidateSource,
        artifact: CatalogueSourceArtifact,
        job: ExtractionJobPlan,
        raw_output: ClaimBundleExtractionOutput,
        expanded: ExpandedClaimBundle,
        cache_key: str,
        provider_attempt_id: uuid.UUID | None,
    ) -> None:
        key = (source.id, tuple(item.value for item in job.objectives))
        group = groups.get(key)
        if group is None:
            group = _BundleGroupAccumulator(
                source=source,
                artifact=artifact,
                objectives=job.objectives,
            )
            groups[key] = group
        group.add(
            raw_output=raw_output,
            expanded=expanded,
            cache_key=cache_key,
            provider_attempt_id=provider_attempt_id,
        )

    def _finalize_bundle_resolution(
        self,
        run: CatalogueIngestionRun,
        candidate: CatalogueCandidate,
        run_lease_token: str,
        *,
        sources: list[CatalogueCandidateSource],
        groups: dict[tuple[uuid.UUID, tuple[str, ...]], _BundleGroupAccumulator],
    ) -> None:
        self._heartbeat_candidate(run, candidate, run_lease_token)
        extracted: list[tuple[CatalogueSourceArtifact, int, list[Any]]] = []
        unknown_objectives: set[str] = set()
        warnings: set[str] = set()
        coverage_by_objective: dict[ClaimObjective, list[ObjectiveCoverageState]] = {
            objective: [] for objective in ClaimObjective
        }
        role_order = self._source_role_order()

        for group in groups.values():
            self._persist_bundle_group_attempt(run, candidate, run_lease_token, group)
            effective_trust_tier = (
                (group.source.trust_tier or 99) * 10 + role_order[group.source.source_role]
            )
            for objective in group.objectives:
                outputs = group.outputs.get(objective, [])
                if not outputs:
                    continue
                merged = self._merge_objective_outputs(objective, outputs)
                if merged.conflicts:
                    candidate.conflicts.extend(merged.conflicts)
                unknown_objectives.update(
                    f"{group.artifact.id}:{objective.value}:{item}"
                    for item in merged.unknown_objectives
                )
                warnings.update(
                    f"{group.artifact.id}:{objective.value}:{item}"
                    for item in merged.warnings
                )
                coverage_by_objective[objective].append(merged.coverage_state)
                extracted.append((group.artifact, effective_trust_tier, merged.claims))

        if not extracted:
            self._manual_review(run, candidate, "insufficient_routed_evidence", run_lease_token)
            return

        candidate.status = CandidateStatus.EXTRACTED
        aggregate_coverage = {
            objective.value: self._aggregate_coverage(states).value
            for objective, states in coverage_by_objective.items()
        }
        resolution = resolve_claims(
            extracted,
            require_detail=True,
            objective_coverage=aggregate_coverage,
        ).model_copy(
            update={
                "unknown_objectives": sorted(unknown_objectives),
                "warnings": sorted(warnings),
            }
        )
        self._heartbeat_candidate(run, candidate, run_lease_token)
        candidate.proposed_payload = resolution.model_dump(mode="json")
        candidate.validation_errors = resolution.rejected + resolution.completeness_errors
        candidate.conflicts = sorted(set(candidate.conflicts + resolution.conflicts))
        if candidate.conflicts:
            candidate.status = CandidateStatus.CONFLICT_DETECTED
        elif candidate.validation_errors:
            candidate.status = CandidateStatus.VALIDATION_FAILED
        else:
            duplicate_ids = {
                str(item.id)
                for source in sources
                for item in self.opportunities.find_opportunities_by_canonical_url(
                    source.canonical_url
                )
            }
            if duplicate_ids:
                candidate.status = CandidateStatus.DUPLICATE_CANDIDATE
                candidate.duplicate_opportunity_ids = sorted(duplicate_ids)
            else:
                candidate.status = CandidateStatus.READY_FOR_REVIEW
                self.metrics.add("candidates_ready_for_review")
                if (
                    run.mode is IngestionMode.REVIEW_QUEUE
                    and not run.dry_run
                    and self._legacy_graph_compatible(resolution)
                ):
                    self._heartbeat_candidate(run, candidate, run_lease_token)
                    created = MextGraphMaterializer(self.session).materialize(resolution)
                    self._heartbeat_candidate(run, candidate, run_lease_token)
                    candidate.opportunity_id = created.id
                    candidate.status = CandidateStatus.SUBMITTED_FOR_REVIEW
        self.repository.release_candidate(candidate)
        self.session.commit()

    def _persist_bundle_group_attempt(
        self,
        run: CatalogueIngestionRun,
        candidate: CatalogueCandidate,
        run_lease_token: str,
        group: _BundleGroupAccumulator,
    ) -> None:
        self._heartbeat_candidate(run, candidate, run_lease_token)
        prompt_hash = bundle_claim_prompt_hash(group.objectives)
        extraction_job_key = self._bundle_group_job_key(candidate.id, group)
        attempt = self.session.scalar(
            select(CatalogueExtractionAttempt).where(
                CatalogueExtractionAttempt.candidate_id == candidate.id,
                CatalogueExtractionAttempt.source_id == group.source.id,
                CatalogueExtractionAttempt.content_hash == group.artifact.content_hash,
                CatalogueExtractionAttempt.schema_version == CLAIM_BUNDLE_SCHEMA_VERSION,
                CatalogueExtractionAttempt.prompt_hash == prompt_hash,
                CatalogueExtractionAttempt.provider == self.bundle_claim_extractor.name,
                CatalogueExtractionAttempt.model == self.bundle_claim_extractor.model,
                CatalogueExtractionAttempt.extraction_job_key == extraction_job_key,
            )
        )
        if attempt is None:
            attempt = CatalogueExtractionAttempt(
                candidate_id=candidate.id,
                source_id=group.source.id,
                provider=self.bundle_claim_extractor.name,
                model=self.bundle_claim_extractor.model,
                schema_version=CLAIM_BUNDLE_SCHEMA_VERSION,
                content_hash=group.artifact.content_hash,
                prompt_hash=prompt_hash,
                extraction_job_key=extraction_job_key,
                status=(
                    ExtractionAttemptStatus.SUCCEEDED
                    if group.provider_attempt_ids
                    else ExtractionAttemptStatus.REUSED
                ),
                output_json={
                    "schema_version": CLAIM_BUNDLE_SCHEMA_VERSION,
                    "objectives": [item.value for item in group.objectives],
                    "cache_keys": sorted(set(group.cache_keys)),
                    "chunks": group.chunk_outputs,
                },
                error_code=None,
                input_tokens=0,
                output_tokens=0,
                estimated_cost=Decimal("0"),
                latency_ms=0,
            )
            self.session.add(attempt)
            self.session.flush()

        worker_id = candidate.claimed_by
        candidate_lease_token = candidate.lease_token
        if worker_id is None or candidate_lease_token is None:
            raise RuntimeError("candidate lease disappeared before bundle attempt linking")
        for provider_attempt_id in dict.fromkeys(group.provider_attempt_ids):
            self.repository.link_provider_attempt(
                provider_attempt_id,
                attempt.id,
                worker_id=worker_id,
                run_lease_token=run_lease_token,
                candidate_lease_token=candidate_lease_token,
            )

    def _persist_plan_checkpoint(
        self,
        run: CatalogueIngestionRun,
        candidate: CatalogueCandidate,
        run_lease_token: str,
        *,
        plan_jobs: tuple[ExtractionJobPlan, ...],
        refusal_reasons: tuple[str, ...],
        estimated_calls: int,
        estimated_cost: Decimal,
        maximum_calls: int,
        maximum_cost: Decimal,
    ) -> None:
        key_payload = "|".join(
            (
                str(candidate.id),
                EXTRACTION_JOB_PLANNER_VERSION,
                *(job.job_key for job in plan_jobs),
                str(run.max_input_characters),
                str(run.max_output_tokens),
            )
        )
        job = self.repository.start_or_resume_job(
            run_id=run.id,
            candidate_id=candidate.id,
            stage="claim_bundle_plan",
            job_key=hashlib.sha256(key_payload.encode("utf-8")).hexdigest(),
            worker_id=candidate.claimed_by or "",
            run_lease_token=run_lease_token,
            candidate_lease_token=candidate.lease_token or "",
            checkpoint={"outcome": "planning"},
        )
        if job.state is CatalogueJobState.SUCCEEDED:
            return
        self.repository.complete_job(
            job.id,
            worker_id=candidate.claimed_by or "",
            run_lease_token=run_lease_token,
            candidate_lease_token=candidate.lease_token or "",
            checkpoint={
                "outcome": "planned" if not refusal_reasons else "refused",
                "planner_version": EXTRACTION_JOB_PLANNER_VERSION,
                "job_count": len(plan_jobs),
                "estimated_calls": estimated_calls,
                "estimated_cost_upper": str(estimated_cost),
                "maximum_physical_calls_with_split_and_retry": maximum_calls,
                "maximum_cost_upper_with_split_and_retry": str(maximum_cost),
                "refusal_reasons": list(refusal_reasons),
                "job_keys": [job.job_key for job in plan_jobs],
            },
        )

    def _maximum_execution_envelope(
        self,
        jobs: tuple[ExtractionJobPlan, ...],
        *,
        blocks_by_id: dict[uuid.UUID, CatalogueEvidenceBlock],
        routes: list[CatalogueEvidenceRoute],
        run: CatalogueIngestionRun,
    ) -> tuple[int, Decimal]:
        retry_multiplier = (
            self.settings.catalogue_ai_max_retries + 1
            if self.bundle_claim_extractor.name == "azure_openai"
            else 1
        )
        node_calls = 0
        node_cost = Decimal("0")
        stack = list(jobs)
        while stack:
            job = stack.pop()
            node_calls += 1
            node_cost += job.estimated_cost_upper
            stack.extend(
                self._split_job(
                    job,
                    blocks_by_id=blocks_by_id,
                    routes=self._job_routes(job, routes),
                    run=run,
                )
            )
        return node_calls * retry_multiplier, node_cost * retry_multiplier

    def _split_job(
        self,
        job: ExtractionJobPlan,
        *,
        blocks_by_id: dict[uuid.UUID, CatalogueEvidenceBlock],
        routes: list[CatalogueEvidenceRoute],
        run: CatalogueIngestionRun,
    ) -> tuple[ExtractionJobPlan, ...]:
        return split_extraction_job(
            job,
            blocks_by_id=blocks_by_id,
            routes=routes,
            run_max_output_tokens=run.max_output_tokens,
            input_cost_per_million=self.settings.catalogue_ai_input_cost_per_million,
            output_cost_per_million=self.settings.catalogue_ai_output_cost_per_million,
        )

    @staticmethod
    def _merge_objective_outputs(
        objective: ClaimObjective,
        outputs: list[ClaimExtractionOutput],
    ) -> ClaimExtractionOutput:
        return ClaimExtractionOutput(
            objective=objective,
            coverage_state=ProductionCatalogueIngestionService._aggregate_coverage(
                [item.coverage_state for item in outputs]
            ),
            claims=[claim for item in outputs for claim in item.claims],
            unknown_objectives=list(
                dict.fromkeys(
                    value for item in outputs for value in item.unknown_objectives
                )
            ),
            conflicts=list(
                dict.fromkeys(value for item in outputs for value in item.conflicts)
            ),
            warnings=list(
                dict.fromkeys(value for item in outputs for value in item.warnings)
            ),
        )

    @staticmethod
    def _aggregate_coverage(states: list[ObjectiveCoverageState]) -> ObjectiveCoverageState:
        if not states:
            return ObjectiveCoverageState.NOT_STATED
        if ObjectiveCoverageState.PARTIAL in states:
            return ObjectiveCoverageState.PARTIAL
        if ObjectiveCoverageState.COMPLETE in states:
            return ObjectiveCoverageState.COMPLETE
        if ObjectiveCoverageState.NOT_STATED in states:
            return ObjectiveCoverageState.NOT_STATED
        return ObjectiveCoverageState.NOT_APPLICABLE

    @staticmethod
    def _source_role_order() -> dict[CandidateSourceRole, int]:
        return {
            CandidateSourceRole.PRIMARY: 0,
            CandidateSourceRole.SUPPORTING: 1,
            CandidateSourceRole.CRAWLED: 2,
            CandidateSourceRole.DISCOVERED: 3,
        }

    @staticmethod
    def _resume_job_key(candidate_id: uuid.UUID, cache_key: str) -> str:
        return hashlib.sha256(
            f"claim-bundle-resume|{candidate_id}|{cache_key}".encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _provider_job_key(candidate_id: uuid.UUID, cache_key: str) -> str:
        return hashlib.sha256(
            f"claim-bundle-provider|{candidate_id}|{cache_key}".encode("utf-8")
        ).hexdigest()

    def _bundle_group_job_key(
        self,
        candidate_id: uuid.UUID,
        group: _BundleGroupAccumulator,
    ) -> str:
        payload = "|".join(
            (
                "claim-bundle-attempt-v1",
                str(candidate_id),
                str(group.source.id),
                group.artifact.content_hash,
                CLAIM_BUNDLE_SCHEMA_VERSION,
                bundle_claim_prompt_hash(group.objectives),
                BUNDLE_PROVIDER_PARSER_VERSION,
                BUNDLE_NORMALIZER_VERSION,
                BUNDLE_RESOLVER_VERSION,
                BUNDLE_VALIDATOR_VERSION,
                *(item.value for item in group.objectives),
                *sorted(set(group.cache_keys)),
            )
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _legacy_graph_compatible(resolution) -> bool:
        from app.modules.catalogue_ingestion.claim_schemas import ClaimEntityType

        expanded_entities = {
            ClaimEntityType.PROGRAMME,
            ClaimEntityType.ELIGIBILITY,
            ClaimEntityType.EVENT,
            ClaimEntityType.RESOURCE,
        }
        return not any(item.claim.entity_type in expanded_entities for item in resolution.resolved)


__all__ = [
    "ProductionCatalogueIngestionService",
]
