"""Read helpers for evidence-backed Scholarship Intelligence Graph facts."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.opportunities.evidence_models import (
    EvidenceSupportType,
    EvidenceValidatorStatus,
    FieldEvidence,
    ScopedDeadline,
)


@dataclass(frozen=True, slots=True)
class FactScope:
    """Requested graph scope for resolving inherited scholarship facts."""

    cycle_id: uuid.UUID | None = None
    track_id: uuid.UUID | None = None
    institution_id: uuid.UUID | None = None
    programme_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class ScopedDeadlineResolution:
    """Deterministic result of resolving one scoped deadline."""

    conflict: bool
    fact_id: uuid.UUID | None = None
    deadline_at: datetime | None = None
    timezone: str | None = None
    label: str | None = None
    scope_level: str | None = None
    conflicting_fact_ids: tuple[uuid.UUID, ...] = field(default_factory=tuple)


def _fact_matches_scope(fact: ScopedDeadline, scope: FactScope) -> bool:
    """Return whether a fact can be inherited by the requested scope."""

    dimensions = (
        (fact.cycle_id, scope.cycle_id),
        (fact.track_id, scope.track_id),
        (fact.institution_id, scope.institution_id),
        (fact.programme_id, scope.programme_id),
    )
    return all(fact_value is None or fact_value == requested_value for fact_value, requested_value in dimensions)


def _specificity(fact: ScopedDeadline) -> int:
    return sum(
        value is not None
        for value in (
            fact.cycle_id,
            fact.track_id,
            fact.institution_id,
            fact.programme_id,
        )
    )


def _scope_level(fact: ScopedDeadline) -> str:
    if fact.programme_id is not None and fact.track_id is not None:
        return "programme_track"
    if fact.programme_id is not None:
        return "programme"
    if fact.institution_id is not None and fact.track_id is not None:
        return "institution_track"
    if fact.track_id is not None:
        return "track"
    if fact.institution_id is not None:
        return "institution"
    if fact.cycle_id is not None:
        return "cycle"
    return "scholarship"


def _passed_evidence_by_fact(
    session: Session,
    fact_ids: list[uuid.UUID],
) -> dict[uuid.UUID, set[EvidenceSupportType]]:
    if not fact_ids:
        return {}

    evidence_rows = session.scalars(
        select(FieldEvidence).where(
            FieldEvidence.entity_type == "scoped_deadline",
            FieldEvidence.entity_id.in_(fact_ids),
            FieldEvidence.field_path == "deadline_at",
            FieldEvidence.validator_status == EvidenceValidatorStatus.PASSED,
        )
    ).all()

    supports: dict[uuid.UUID, set[EvidenceSupportType]] = {}
    for evidence in evidence_rows:
        supports.setdefault(evidence.entity_id, set()).add(evidence.support_type)
    return supports


def _conflict(facts: list[ScopedDeadline]) -> ScopedDeadlineResolution:
    return ScopedDeadlineResolution(
        conflict=True,
        conflicting_fact_ids=tuple(sorted((fact.id for fact in facts), key=str)),
    )


def _resolved(fact: ScopedDeadline) -> ScopedDeadlineResolution:
    return ScopedDeadlineResolution(
        conflict=False,
        fact_id=fact.id,
        deadline_at=fact.deadline_at,
        timezone=fact.timezone,
        label=fact.label,
        scope_level=_scope_level(fact),
    )


def resolve_scoped_deadline(
    session: Session,
    *,
    scholarship_id: uuid.UUID,
    deadline_type: str,
    scope: FactScope | None = None,
) -> ScopedDeadlineResolution:
    """Resolve a deadline without letting unsupported child facts override a parent.

    Scholarship-level facts are the inheritance fallback. A more-specific fact may
    override only when ``deadline_at`` has PASSED + EXPLICIT field evidence. Any
    matching PASSED + CONTRADICTS evidence is surfaced as a review conflict rather
    than silently selecting one deadline.
    """

    requested_scope = scope or FactScope()
    facts = list(
        session.scalars(
            select(ScopedDeadline).where(
                ScopedDeadline.scholarship_id == scholarship_id,
                ScopedDeadline.deadline_type == deadline_type,
            )
        ).all()
    )
    matching = [fact for fact in facts if _fact_matches_scope(fact, requested_scope)]
    if not matching:
        return ScopedDeadlineResolution(conflict=False)

    evidence = _passed_evidence_by_fact(session, [fact.id for fact in matching])

    contradicted = [
        fact
        for fact in matching
        if EvidenceSupportType.CONTRADICTS in evidence.get(fact.id, set())
    ]
    if contradicted:
        return _conflict(contradicted)

    child_specificities = sorted(
        {_specificity(fact) for fact in matching if _specificity(fact) > 0},
        reverse=True,
    )
    for specificity in child_specificities:
        supported = [
            fact
            for fact in matching
            if _specificity(fact) == specificity
            and EvidenceSupportType.EXPLICIT in evidence.get(fact.id, set())
        ]
        if not supported:
            continue

        distinct_deadlines = {
            (fact.deadline_at, fact.timezone)
            for fact in supported
        }
        if len(distinct_deadlines) > 1:
            return _conflict(supported)

        selected = min(supported, key=lambda fact: str(fact.id))
        return _resolved(selected)

    inherited = [fact for fact in matching if _specificity(fact) == 0]
    if not inherited:
        return ScopedDeadlineResolution(conflict=False)

    distinct_inherited = {(fact.deadline_at, fact.timezone) for fact in inherited}
    if len(distinct_inherited) > 1:
        return _conflict(inherited)

    selected = min(inherited, key=lambda fact: str(fact.id))
    return _resolved(selected)


__all__ = ["FactScope", "ScopedDeadlineResolution", "resolve_scoped_deadline"]
