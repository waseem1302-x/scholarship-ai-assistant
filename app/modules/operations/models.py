import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class OperationalJobHealth(Base):
    __tablename__ = "operational_job_health"

    job_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), onupdate=utc_now
    )

    recent_runs: Mapped[list["OperationalJobRun"]] = relationship(
        order_by="OperationalJobRun.started_at.desc()",
        cascade="all, delete-orphan",
    )


class OperationalJobRun(Base):
    __tablename__ = "operational_job_runs"
    __table_args__ = (Index("ix_operational_job_runs_job_started", "job_name", "started_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_name: Mapped[str] = mapped_column(
        ForeignKey("operational_job_health.job_name", ondelete="CASCADE"), index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    processed_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(100))
    release_version: Mapped[str] = mapped_column(String(100), default="unknown")
