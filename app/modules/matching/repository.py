import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.matching.models import MatchEvaluation


class MatchEvaluationRepository:
    """Persistence boundary for user-owned evaluation history."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def latest_for_user(self, user_id: uuid.UUID) -> MatchEvaluation | None:
        statement = (
            select(MatchEvaluation)
            .where(MatchEvaluation.user_id == user_id)
            .order_by(MatchEvaluation.evaluated_at.desc(), MatchEvaluation.id.desc())
            .limit(1)
        )
        return self.session.scalar(statement)

    def add(self, evaluation: MatchEvaluation) -> None:
        self.session.add(evaluation)

    def purge_expired(self, *, before: datetime) -> int:
        """Return the number of expired evaluations removed by a retention job."""
        evaluations = list(
            self.session.scalars(
                select(MatchEvaluation).where(MatchEvaluation.expires_at <= before)
            )
        )
        for evaluation in evaluations:
            self.session.delete(evaluation)
        return len(evaluations)
