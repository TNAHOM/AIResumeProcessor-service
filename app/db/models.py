import enum
import uuid
from typing import Optional
from sqlalchemy import String, DateTime, JSON, Enum, func, ForeignKey, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator
from pgvector.sqlalchemy import Vector


class Base(DeclarativeBase):
    pass


class GUID(TypeDecorator):
    """Platform-independent GUID type stored as string."""

    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return str(value)
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            return uuid.UUID(value)
        except Exception:
            return value


class ApplicationStatus(str, enum.Enum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class SeniorityLevel(str, enum.Enum):
    INTERN = "INTERN"
    JUNIOR = "JUNIOR"
    MID = "MID"
    SENIOR = "SENIOR"


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, index=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)

    job_post_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), nullable=True, index=True  # Added index for job post queries
    )

    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    s3_path: Mapped[Optional[str]] = mapped_column(String, unique=True, index=True)

    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus), 
        default=ApplicationStatus.PENDING, 
        nullable=False,
        index=True  # Added index for status queries - critical for performance
    )
    seniority_level: Mapped[Optional[SeniorityLevel]] = mapped_column(
        Enum(SeniorityLevel), nullable=True
    )

    # this is going to contain a json file {'weakness': [], 'strengths': [], 'score': 8.5}
    analysis: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        default={
            "weakness": [],
            "strengths": [],
            "score": None,
        },
    )

    failed_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True  # Added index for time-based queries
    )
    updated_at: Mapped[Optional[DateTime]] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), index=True  # Added index for time-based queries
    )

    extracted_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    embedded_value: Mapped[Optional[list[float]]] = mapped_column(
        Vector(3072), default=[]  # Fixed default for embedded_value to be list instead of dict
    )

    # Composite indexes for common query patterns
    __table_args__ = (
        # Index for filtering by status and created_at (common for dashboard queries)
        Index('ix_applications_status_created_at', 'status', 'created_at'),
        # Index for filtering by job_post_id and status (common for job-specific queries)
        Index('ix_applications_job_post_status', 'job_post_id', 'status'),
        # Index for filtering by email and status (user-specific queries)
        Index('ix_applications_email_status', 'email', 'status'),
    )
