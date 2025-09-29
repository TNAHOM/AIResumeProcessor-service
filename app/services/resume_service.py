import uuid
import boto3
from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session
from botocore.exceptions import ClientError
from app.db import models
from app.core.config import settings
from app.schemas.resume import ResumeUploadForm
from app.services.job_queue import job_queue
from app.workers.async_resume_processor import process_resume_async


def upload_to_s3(file: UploadFile, s3_path: str):
    """Upload file to S3 synchronously."""
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
    Create upload job using Redis queue instead of BackgroundTasks.
    
    This replaces the previous BackgroundTasks implementation with Redis-based job queue.
    """
    # Create application record
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

    # Upload to S3
    s3_path = f"resumes/{uuid.uuid4()}_{file.filename}"
    upload_to_s3(file, s3_path)

    # Update application with S3 path and set status to QUEUED
    application.s3_path = s3_path
    application.status = models.ApplicationStatus.QUEUED
    db.commit()

    # Enqueue job to Redis queue instead of using BackgroundTasks
    try:
        # Ensure application.id is a UUID when passing to process_resume
        application_id = application.id
        if isinstance(application_id, str):
            application_id = uuid.UUID(application_id)
            
        # Enqueue the async job
        job = job_queue.enqueue_job(
            process_resume_async,
            application_id,
            form_data.job_post_id,
            job_id=str(application_id)  # Use application ID as job ID for tracking
        )
        
        print(f"✅ Enqueued resume processing job {job.id} for application {application_id}")
        
    except Exception as e:
        print(f"❌ Failed to enqueue job: {e}")
        # Set application status to failed if job enqueue fails
        application.status = models.ApplicationStatus.FAILED
        application.failed_reason = f"Failed to enqueue processing job: {str(e)}"
        db.commit()
        raise HTTPException(status_code=500, detail="Failed to enqueue processing job.")

    return application
