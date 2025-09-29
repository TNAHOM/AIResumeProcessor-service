import uuid
import logging
from app.workers.tasks import process_resume_task

logger = logging.getLogger(__name__)


class QueueService:
    """Service for managing background job queue operations"""
    
    @staticmethod
    def enqueue_resume_processing(application_id: uuid.UUID, job_post_id: uuid.UUID) -> str:
        """
        Enqueue a resume processing job
        
        Args:
            application_id: UUID of the application to process
            job_post_id: UUID of the job post
            
        Returns:
            Task ID string from Celery
        """
        try:
            # Convert UUIDs to strings for JSON serialization
            app_id_str = str(application_id)
            job_id_str = str(job_post_id)
            
            # Enqueue the task
            task = process_resume_task.delay(app_id_str, job_id_str)
            
            logger.info(
                f"Enqueued resume processing task {task.id} for application {app_id_str}"
            )
            
            return task.id
            
        except Exception as e:
            logger.exception(
                f"Failed to enqueue resume processing for application {application_id}: {e}"
            )
            raise
    
    @staticmethod
    def get_task_status(task_id: str) -> dict:
        """
        Get the status of a background task
        
        Args:
            task_id: Task ID returned from enqueue_resume_processing
            
        Returns:
            Dict with task status information
        """
        try:
            from app.core.celery_app import celery_app
            result = celery_app.AsyncResult(task_id)
            
            return {
                "task_id": task_id,
                "status": result.status,
                "result": result.result if result.ready() else None,
                "traceback": result.traceback if result.failed() else None,
            }
            
        except Exception as e:
            logger.exception(f"Failed to get task status for {task_id}: {e}")
            return {
                "task_id": task_id,
                "status": "UNKNOWN",
                "error": str(e)
            }