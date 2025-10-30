from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Dict, Any

import uuid
from app.db.models import ApplicationStatus, ProgressStatus
from fastapi import Form


class ResumeCreateResponse(BaseModel):
    application_id: uuid.UUID
    job_post_id: uuid.UUID
    seniority_level: Optional[str]
    status: ApplicationStatus
    message: str


class ResumeStatusResponse(BaseModel):
    id: uuid.UUID
    original_filename: str
    status: ApplicationStatus
    progress_status: ProgressStatus
    seniority_level: Optional[str] = None
    phone_number: Optional[str] = None
    s3_path: Optional[str] = None
    extracted_data: Optional[Dict[str, Any]] = None
    # embedded_value: list[float] | None = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ResumeUploadForm(BaseModel):
    job_post_id: uuid.UUID
    seniority_level: Optional[str]
    candidate_name: str
    candidate_email: str
    candidate_phone: str

    @classmethod
    def as_form(
        cls,
        job_post_id: uuid.UUID = Form(...),
        seniority_level: Optional[str] = Form(...),
        candidate_name: str = Form(...),
        candidate_email: str = Form(...),
        candidate_phone: str = Form(...),
    ) -> "ResumeUploadForm":
        """
        Create a ResumeUploadForm from form fields so it can be used with Depends(ResumeUploadForm.as_form).

        FastAPI will coerce form values to the annotated types (e.g. uuid.UUID).
        """
        return cls(
            job_post_id=job_post_id,
            seniority_level=seniority_level,
            candidate_name=candidate_name,
            candidate_email=candidate_email,
            candidate_phone=candidate_phone,
        )
