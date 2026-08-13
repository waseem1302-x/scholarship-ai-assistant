"""Run one or more private Document Lab preparation jobs.

The worker accepts no document contents on the command line and intentionally
does not log file names, extracted text, or provider payloads.
"""

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.modules.document_lab.service import DocumentLabService
from app.modules.operations.service import OperationalJobService


def main() -> None:
    settings = get_settings()
    if not settings.document_lab_enabled:
        return
    with SessionLocal() as session:
        service = DocumentLabService(session, settings)
        health = OperationalJobService(session)
        health.started("document_jobs")
        processed = 0
        try:
            while service.process_next_job():
                processed += 1
            health.completed("document_jobs", processed)
        except Exception as exc:
            health.failed("document_jobs", exc)
            raise


if __name__ == "__main__":
    main()
