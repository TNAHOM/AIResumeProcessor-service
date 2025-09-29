import uuid
import boto3
from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session
from botocore.exceptions import ClientError
from app.db import models
from app.core.config import settings
from app.schemas.resume import ResumeUploadForm
from app.services.queue_service import QueueService


def upload_to_s3(file: UploadFile, s3_path: str):
    s3_client = boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_DEFAULT_REGION,
    )
    try:
        s3_client.upload_fileobj(file.file, settings.AWS_S3_BUCKET_NAME, s3_path)
        print(
            f"✅ Uploaded {file.filename} -> s3://{settings.AWS_S3_BUCKET_NAME}/{s3_path}"
        )
    except ClientError as e:
        print(f"❌ S3 Upload failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload file to S3.")


def create_upload_job(
    db: Session,
    file: UploadFile,
    form_data: ResumeUploadForm,
) -> models.Application:
    """
    Create a new resume upload job using Redis queue instead of BackgroundTasks
    """
    application = models.Application(
        original_filename=file.filename,
        job_post_id=form_data.job_post_id,
        name=form_data.candidate_name,
        email=form_data.candidate_email,
        seniority_level=form_data.seniority_level,
    )
    db.add(application)
    db.commit()
    db.refresh(application)

    s3_path = f"resumes/{uuid.uuid4()}_{file.filename}"
    upload_to_s3(file, s3_path)

    application.s3_path = s3_path
    application.status = models.ApplicationStatus.QUEUED
    db.commit()

    # Ensure application.id is a UUID when passing to queue service
    application_id = application.id
    if isinstance(application_id, str):
        application_id = uuid.UUID(application_id)
    
    # Enqueue the processing job using Redis/Celery
    try:
        task_id = QueueService.enqueue_resume_processing(
            application_id, form_data.job_post_id
        )
        print(f"✅ Enqueued resume processing task {task_id} for application {application_id}")
    except Exception as e:
        print(f"❌ Failed to enqueue resume processing: {e}")
        # Update application status to failed if queue enqueue fails
        application.status = models.ApplicationStatus.FAILED
        application.failed_reason = f"Failed to enqueue processing: {str(e)}"
        db.commit()
        raise HTTPException(
            status_code=500, 
            detail="Failed to enqueue resume processing job."
        )
    
    return application
