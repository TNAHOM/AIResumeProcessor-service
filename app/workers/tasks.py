import uuid
import logging
from celery import Task
from app.core.celery_app import celery_app
from app.workers.async_resume_processor import process_resume_async

logger = logging.getLogger(__name__)


class CallbackTask(Task):
    """Task with callbacks for success/failure handling"""
    def on_success(self, retval, task_id, args, kwargs):
        logger.info(f"Task {task_id} succeeded with args: {args}")

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(f"Task {task_id} failed with args: {args}, error: {exc}")


@celery_app.task(base=CallbackTask, bind=True, name="process_resume_task")
def process_resume_task(self, application_id: str, job_post_id: str):
    """
    Celery task to process resume asynchronously
    
    Args:
        application_id: UUID string of the application
        job_post_id: UUID string of the job post
    """
    try:
        # Convert string UUIDs back to UUID objects
        app_uuid = uuid.UUID(application_id)
        job_uuid = uuid.UUID(job_post_id)
        
        logger.info(f"Starting resume processing task for application {application_id}")
        
        # Call the async processor
        import asyncio
        result = asyncio.run(process_resume_async(app_uuid, job_uuid))
        
        logger.info(f"Resume processing completed for application {application_id}")
        return {"status": "completed", "application_id": application_id}
        
    except Exception as exc:
        logger.exception(f"Resume processing failed for application {application_id}: {exc}")
        # Re-raise to let Celery handle the failure
        raise self.retry(exc=exc, countdown=60, max_retries=3)