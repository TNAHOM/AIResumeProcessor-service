from fastapi import (
    APIRouter,
    Depends,
    UploadFile,
    File,
    BackgroundTasks,
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
from app.core.security import validate_file_upload
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/resumes", tags=["Resumes"])


@router.post("/upload", response_model=ResumeCreateResponse, status_code=202)
def upload_resume(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    form_data: ResumeUploadForm = Depends(ResumeUploadForm.as_form),
    db: Session = Depends(get_db),
):
    """Upload a resume file for processing.
    
    The file will be uploaded to S3 and processed in the background using:
    1. AWS Textract for text extraction
    2. Text grouping and normalization 
    3. Gemini AI for structured data extraction
    4. Embedding generation for similarity matching
    5. Database storage of results
    """
    logger.info(f"Resume upload requested for candidate: {form_data.candidate_email}")
    
    # Validate the uploaded file
    validate_file_upload(file)
    
    try:
        application = resume_service.create_upload_job(
            db, file, background_tasks, form_data
        )
        
        logger.info(f"Resume upload job created with ID: {application.id}")
        
        return ResumeCreateResponse(
            application_id=application.id,
            job_post_id=form_data.job_post_id,
            seniority_level=form_data.seniority_level,
            status=application.status,
            message="Resume accepted and is being processed in the background.",
        )
    except Exception as e:
        logger.error(f"Failed to create upload job: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to process resume upload")


@router.get("/{application_id}", response_model=ResumeStatusResponse)
def get_application_status(application_id: str, db: Session = Depends(get_db)):
    """Get the processing status and results for a resume application."""
    logger.info(f"Fetching application status for ID: {application_id}")
    
    application = db.query(Application).filter(Application.id == application_id).first()  # type: ignore
    if not application:
        logger.warning(f"Application not found: {application_id}")
        raise HTTPException(status_code=404, detail="Application not found")
    
    logger.info(f"Application found with status: {application.status}")
    return application
