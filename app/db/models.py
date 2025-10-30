import enum
import uuid
from typing import Optional
from sqlalchemy import String, DateTime, JSON, Enum, func
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
    
class ProgressStatus(str, enum.Enum):
    APPLIED = "APPLIED"
    SHORTLISTED = "SHORTLISTED"
    INTERVIEWING = "INTERVIEWING"
    REJECTED = "REJECTED"
    HIRED = "HIRED"


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, index=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)
    phone_number: Mapped[str] = mapped_column(String, nullable=False)

    job_post_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)

    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    s3_path: Mapped[Optional[str]] = mapped_column(String, unique=True, index=True)

    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus), default=ApplicationStatus.PENDING, nullable=False
    )
    seniority_level: Mapped[Optional[SeniorityLevel]] = mapped_column(
        Enum(SeniorityLevel), nullable=True
    )
    progress_status: Mapped[Optional[ProgressStatus]] = mapped_column(Enum(ProgressStatus), default=ProgressStatus.APPLIED, nullable=False)

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
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[Optional[DateTime]] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )

    extracted_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    embedded_value: Mapped[Optional[list[float]]] = mapped_column(Vector(3072))
