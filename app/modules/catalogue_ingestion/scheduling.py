"""Rate-aware provider admission and persistent circuit-breaker control."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.catalogue_ingestion.provider_attempts import (
    CatalogueProviderAttempt,
    ProviderAttemptState,
    ProviderFailureClass,
)
from app.modules.catalogue_ingestion.scheduling_models import (
    CatalogueProviderCircuit,
    CatalogueProviderLane,
    CatalogueSchedulingDecision,
    ProviderCircuitState,
    SchedulingDecisionKind,
)


@dataclass(frozen=True)
class ProviderAdmission:
    allowed: bool
    reason: str
    decision_id: uuid.UUID


class CatalogueProviderScheduler:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def admit(
        self,
        *,
        provider: str,
        deployment: str | None,
        logical_job_key: str,
        run_id: uuid.UUID | None = None,
        candidate_id: uuid.UUID | None = None,
        observed_at: datetime | None = None,
        commit: bool = True,
    ) -> ProviderAdmission:
        now = observed_at or datetime.now(UTC)
        lane = self._lane_for_update(provider, deployment)
        open_circuits = list(
            self.session.scalars(
                select(CatalogueProviderCircuit)
                .where(
                    CatalogueProviderCircuit.lane_id == lane.id,
                    CatalogueProviderCircuit.state.in_(
                        {ProviderCircuitState.OPEN, ProviderCircuitState.HALF_OPEN}
                    ),
                )
                .with_for_update()
            )
        )
        blocking = False
        for circuit in open_circuits:
            if circuit.state is ProviderCircuitState.HALF_OPEN:
                blocking = True
                break
            if circuit.opened_until is None or _as_utc(circuit.opened_until) > _as_utc(now):
                blocking = True
                break
            circuit.state = ProviderCircuitState.HALF_OPEN

        active = (
            self.session.scalar(
                select(func.count())
                .select_from(CatalogueProviderAttempt)
                .where(
                    CatalogueProviderAttempt.provider == provider,
                    func.coalesce(CatalogueProviderAttempt.deployment, "") == lane.deployment,
                    CatalogueProviderAttempt.state.in_(
                        {
                            ProviderAttemptState.RESERVED,
                            ProviderAttemptState.DISPATCHING,
                            ProviderAttemptState.DISPATCHED,
                        }
                    ),
                )
            )
            or 0
        )
        concurrency_limit = self.settings.catalogue_provider_max_concurrency_per_deployment
        if blocking:
            kind = SchedulingDecisionKind.CIRCUIT_OPEN
            reason = "provider_circuit_open"
            allowed = False
        elif active >= concurrency_limit:
            kind = SchedulingDecisionKind.CONCURRENCY_LIMIT
            reason = "provider_concurrency_limit"
            allowed = False
        elif provider == "azure_openai" and not self.settings.catalogue_ai_ingestion_enabled:
            kind = SchedulingDecisionKind.KILL_SWITCH
            reason = "catalogue_ai_kill_switch_disabled"
            allowed = False
        else:
            kind = SchedulingDecisionKind.DISPATCH_ALLOWED
            reason = "dispatch_allowed"
            allowed = True
            lane.last_admitted_at = now
        decision = CatalogueSchedulingDecision(
            run_id=run_id,
            candidate_id=candidate_id,
            logical_job_key=logical_job_key[:128],
            provider=provider[:100],
            deployment=lane.deployment,
            decision=kind,
            reason=reason,
            active_attempts=int(active),
            concurrency_limit=concurrency_limit,
        )
        self.session.add(decision)
        self.session.flush()
        if commit:
            self.session.commit()
        return ProviderAdmission(allowed=allowed, reason=reason, decision_id=decision.id)

    def record_failure(
        self,
        *,
        provider: str,
        deployment: str | None,
        failure_class: ProviderFailureClass,
        retry_after_seconds: float | None = None,
        observed_at: datetime | None = None,
    ) -> None:
        now = observed_at or datetime.now(UTC)
        lane = self._lane_for_update(provider, deployment)
        circuit = self.session.scalar(
            select(CatalogueProviderCircuit)
            .where(
                CatalogueProviderCircuit.lane_id == lane.id,
                CatalogueProviderCircuit.failure_class == failure_class,
            )
            .with_for_update()
        )
        if circuit is None:
            circuit = CatalogueProviderCircuit(lane_id=lane.id, failure_class=failure_class)
            self.session.add(circuit)
            self.session.flush()
        circuit.consecutive_failures += 1
        circuit.last_failure_at = now
        immediate = failure_class is ProviderFailureClass.AUTHENTICATION_CONFIGURATION_ERROR
        if immediate or (
            circuit.consecutive_failures
            >= self.settings.catalogue_provider_circuit_failure_threshold
        ):
            duration = max(
                float(self.settings.catalogue_provider_circuit_open_seconds),
                float(retry_after_seconds or 0),
            )
            circuit.state = ProviderCircuitState.OPEN
            circuit.opened_until = now + timedelta(seconds=duration)
        self.session.commit()

    def record_success(
        self,
        *,
        provider: str,
        deployment: str | None,
        observed_at: datetime | None = None,
    ) -> None:
        now = observed_at or datetime.now(UTC)
        lane = self._lane_for_update(provider, deployment)
        circuits = list(
            self.session.scalars(
                select(CatalogueProviderCircuit)
                .where(CatalogueProviderCircuit.lane_id == lane.id)
                .with_for_update()
            )
        )
        for circuit in circuits:
            circuit.state = ProviderCircuitState.CLOSED
            circuit.consecutive_failures = 0
            circuit.opened_until = None
            circuit.last_success_at = now
        self.session.commit()

    def _lane_for_update(
        self,
        provider: str,
        deployment: str | None,
    ) -> CatalogueProviderLane:
        provider_key = provider.strip()
        deployment_key = (deployment or "").strip()
        if not provider_key or len(provider_key) > 100 or len(deployment_key) > 255:
            raise ValueError("provider lane identity is invalid")
        lane = self.session.scalar(
            select(CatalogueProviderLane)
            .where(
                CatalogueProviderLane.provider == provider_key,
                CatalogueProviderLane.deployment == deployment_key,
            )
            .with_for_update()
        )
        if lane is not None:
            return lane
        try:
            with self.session.begin_nested():
                lane = CatalogueProviderLane(provider=provider_key, deployment=deployment_key)
                self.session.add(lane)
                self.session.flush()
        except IntegrityError:
            lane = self.session.scalar(
                select(CatalogueProviderLane)
                .where(
                    CatalogueProviderLane.provider == provider_key,
                    CatalogueProviderLane.deployment == deployment_key,
                )
                .with_for_update()
            )
            if lane is None:
                raise
        return lane


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
