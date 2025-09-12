import enum
import uuid
from sqlalchemy import Column, String, DateTime, JSON, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.types import TypeDecorator

Base = declarative_base()


class GUID(TypeDecorator):
    """Platform-independent GUID type.
    Ensures uuid.UUID values are bound to the DB as strings (avoids character varying = uuid errors).
    """

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


class Application(Base):
    __tablename__ = "applications"

    id: str = Column(
        GUID(), primary_key=True, index=True, default=lambda: str(uuid.uuid4())
    )  # type: ignore
    original_filename: str = Column(String, nullable=False)  # type: ignore
    s3_path: str = Column(String, unique=True, index=True, nullable=True)  # type: ignore
    status: ApplicationStatus = Column(
        Enum(ApplicationStatus), default=ApplicationStatus.PENDING, nullable=False
    )  # type: ignore
    failed_reason: str | None = Column(String, nullable=True)  # type: ignore
    extracted_data: dict | None = Column(JSON, nullable=True)  # type: ignore
    embedded_value: list[float] | None = Column(JSON, nullable=True, default={})  # type: ignore
    created_at: DateTime = Column(DateTime(timezone=True), server_default=func.now())  # type: ignore
    updated_at: DateTime | None = Column(DateTime(timezone=True), onupdate=func.now())  # type: ignore
