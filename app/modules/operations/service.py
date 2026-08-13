import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.modules.operations.models import OperationalJobHealth, OperationalJobRun


class OperationalJobService:
    """Persist only safe job liveness/counter data for operators."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self._active_runs: dict[str, uuid.UUID] = {}

    def started(self, job_name: str) -> None:
        record = self._record(job_name)
        started_at = datetime.now(UTC)
        record.last_started_at = started_at
        run = OperationalJobRun(job_name=job_name, started_at=started_at)
        self.session.add(run)
        self.session.flush()
        self._active_runs[job_name] = run.id
        self.session.commit()

    def completed(self, job_name: str, processed: int = 0) -> None:
        record = self._record(job_name)
        completed_at = datetime.now(UTC)
        record.last_completed_at = completed_at
        record.processed_count += max(0, processed)
        record.last_error_code = None
        run = self._active_run(job_name, completed_at)
        run.completed_at = completed_at
        run.duration_ms = self._duration_ms(run.started_at, completed_at)
        run.processed_count = max(0, processed)
        run.failed_count = 0
        run.error_code = None
        self.session.commit()

    def failed(self, job_name: str, error: BaseException) -> None:
        record = self._record(job_name)
        record.failed_count += 1
        # Error classes provide a safe operational category; messages can carry
        # private file, provider, account, or document information.
        record.last_error_code = type(error).__name__[:100]
        completed_at = datetime.now(UTC)
        run = self._active_run(job_name, completed_at)
        run.completed_at = completed_at
        run.duration_ms = self._duration_ms(run.started_at, completed_at)
        run.processed_count = 0
        run.failed_count = 1
        run.error_code = record.last_error_code
        self.session.commit()

    def _record(self, job_name: str) -> OperationalJobHealth:
        record = self.session.get(OperationalJobHealth, job_name)
        if record is None:
            record = OperationalJobHealth(job_name=job_name)
            self.session.add(record)
            self.session.flush()
        return record

    def _active_run(self, job_name: str, fallback_started_at: datetime) -> OperationalJobRun:
        run_id = self._active_runs.get(job_name)
        run = self.session.get(OperationalJobRun, run_id) if run_id else None
        if run is None or run.completed_at is not None:
            run = OperationalJobRun(job_name=job_name, started_at=fallback_started_at)
            self.session.add(run)
            self.session.flush()
            self._active_runs[job_name] = run.id
        return run

    @staticmethod
    def _duration_ms(started_at: datetime, completed_at: datetime) -> int:
        started = started_at.replace(tzinfo=UTC) if started_at.tzinfo is None else started_at
        return max(0, int((completed_at - started).total_seconds() * 1000))
