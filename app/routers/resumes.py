from fastapi import (
    APIRouter,
    Depends,
    UploadFile,
    File,
    HTTPException,
)
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.resume import (
    ResumeCreateResponse,
    ResumeStatusResponse,
    ResumeUploadForm,
)
from app.services import resume_service
from app.db.models import Application

router = APIRouter(prefix="/resumes", tags=["Resumes"])


@router.post("/upload", response_model=ResumeCreateResponse, status_code=202)
def upload_resume(
    file: UploadFile = File(...),
    form_data: ResumeUploadForm = Depends(ResumeUploadForm.as_form),
    db: Session = Depends(get_db),
):
    application = resume_service.create_upload_job(
        db, file, form_data
    )
    return {
        "application_id": application.id,
        "status": application.status,
        "message": "Resume accepted and is being processed in the background.",
    }


@router.get("/{application_id}", response_model=ResumeStatusResponse)
def get_application_status(application_id: str, db: Session = Depends(get_db)):
    print("Fetching application with ID:", application_id)
    application = db.query(Application).filter(Application.id == application_id).first()  # type: ignore
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    return application
