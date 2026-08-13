from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.modules.operations.models import OperationalJobHealth


class OperationalJobService:
    """Persist only safe job liveness/counter data for operators."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def started(self, job_name: str) -> None:
        record = self._record(job_name)
        record.last_started_at = datetime.now(UTC)
        self.session.commit()

    def completed(self, job_name: str, processed: int = 0) -> None:
        record = self._record(job_name)
        record.last_completed_at = datetime.now(UTC)
        record.processed_count += max(0, processed)
        record.last_error_code = None
        self.session.commit()

    def failed(self, job_name: str, error: BaseException) -> None:
        record = self._record(job_name)
        record.failed_count += 1
        # Error classes provide a safe operational category; messages can carry
        # private file, provider, account, or document information.
        record.last_error_code = type(error).__name__[:100]
        self.session.commit()

    def _record(self, job_name: str) -> OperationalJobHealth:
        record = self.session.get(OperationalJobHealth, job_name)
        if record is None:
            record = OperationalJobHealth(job_name=job_name)
            self.session.add(record)
            self.session.flush()
        return record
