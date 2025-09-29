import uuid
import boto3
from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session
from botocore.exceptions import ClientError
from app.db import models
from app.core.config import settings
from app.schemas.resume import ResumeUploadForm
from app.services.job_queue import job_queue


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

    # Ensure application.id is a UUID when passing to process_resume
    application_id = application.id
    if isinstance(application_id, str):
        application_id = uuid.UUID(application_id)
    
    # Enqueue job to Redis instead of using BackgroundTasks
    job_data = {
        "application_id": str(application_id),
        "job_post_id": str(form_data.job_post_id)
    }
    job_queue.enqueue_job("process_resume", job_data, queue_name="resume_processing")
    
    return application
