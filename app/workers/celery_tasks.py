import asyncio
import uuid
from app.core.celery_app import celery_app
from app.workers.resume_processor import process_resume_async


@celery_app.task
def process_resume_task(application_id: str, job_post_id: str):
    """
    Celery task to process a resume asynchronously.
    
    Args:
        application_id: The UUID of the application as a string
        job_post_id: The UUID of the job post as a string
    """
    # Convert string UUIDs back to UUID objects
    app_uuid = uuid.UUID(application_id)
    job_uuid = uuid.UUID(job_post_id)
    
    # Run the async resume processing function
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(process_resume_async(app_uuid, job_uuid))
    finally:
        loop.close()


# Make the task available for import
__all__ = ["process_resume_task"]