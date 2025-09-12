from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Dict, Any

import uuid
from app.db.models import ApplicationStatus


class ResumeCreateResponse(BaseModel):
    application_id: uuid.UUID
    status: ApplicationStatus
    message: str


class ResumeStatusResponse(BaseModel):
    id: uuid.UUID
    original_filename: str
    status: ApplicationStatus
    s3_path: Optional[str] = None
    extracted_data: Optional[Dict[str, Any]] = None
    # embedded_value: list[float] | None = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
