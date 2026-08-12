"""Run one or more private Document Lab preparation jobs.

The worker accepts no document contents on the command line and intentionally
does not log file names, extracted text, or provider payloads.
"""

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.modules.document_lab.service import DocumentLabService


def main() -> None:
    settings = get_settings()
    if not settings.document_lab_enabled:
        return
    with SessionLocal() as session:
        service = DocumentLabService(session, settings)
        while service.process_next_job():
            pass


if __name__ == "__main__":
    main()
