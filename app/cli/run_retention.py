"""Run private-data retention jobs and record only safe aggregate health."""

from datetime import UTC, datetime

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.modules.assistant.service import AssistantService
from app.modules.auth.service import AuthService
from app.modules.document_lab.service import DocumentLabService
from app.modules.matching.repository import MatchEvaluationRepository
from app.modules.operations.service import OperationalJobService


def main() -> None:
    settings = get_settings()
    with SessionLocal() as session:
        health = OperationalJobService(session)
        health.started("retention")
        try:
            processed = AssistantService(session, settings).purge_expired_data()
            processed += AuthService(session, settings).purge_expired_auth_tokens()
            processed += MatchEvaluationRepository(session).purge_expired(before=datetime.now(UTC))
            session.commit()
            processed += DocumentLabService(session, settings).purge_expired()
            health.completed("retention", processed)
        except Exception as exc:
            health.failed("retention", exc)
            raise


if __name__ == "__main__":
    main()
