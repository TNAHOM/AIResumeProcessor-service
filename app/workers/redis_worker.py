"""
Redis-based background worker for processing resume jobs
"""
import json
import logging
import signal
import sys
import uuid
from typing import Dict, Any

from app.services.job_queue import job_queue
from app.workers.resume_processor import process_resume

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class RedisWorker:
    """Redis-based worker for processing background jobs"""
    
    def __init__(self, queue_name: str = "resume_processing"):
        self.queue_name = queue_name
        self.running = True
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
    
    def process_job(self, job_data: Dict[str, Any]) -> bool:
        """Process a single job"""
        try:
            job_name = job_data.get("name")
            data = job_data.get("data", {})
            
            if job_name == "process_resume":
                application_id = uuid.UUID(data["application_id"])
                job_post_id = uuid.UUID(data["job_post_id"])
                
                logger.info(f"Processing resume job for application {application_id}")
                process_resume(application_id, job_post_id)
                logger.info(f"Completed resume job for application {application_id}")
                return True
            else:
                logger.warning(f"Unknown job type: {job_name}")
                return False
                
        except Exception as e:
            logger.exception(f"Failed to process job {job_data.get('id', 'unknown')}: {e}")
            return False
    
    def start(self):
        """Start the worker loop"""
        logger.info(f"Starting Redis worker, listening on queue: {self.queue_name}")
        
        while self.running:
            try:
                # Poll for jobs with 5 second timeout
                job_data = job_queue.dequeue_job(self.queue_name, timeout=5)
                
                if job_data:
                    success = self.process_job(job_data)
                    if success:
                        logger.info(f"Successfully processed job {job_data.get('id')}")
                    else:
                        logger.error(f"Failed to process job {job_data.get('id')}")
                        # TODO: Implement retry logic or dead letter queue
                
            except Exception as e:
                logger.exception(f"Error in worker loop: {e}")
                # Continue running even if there's an error
        
        logger.info("Worker stopped")


def main():
    """Main entry point for the worker"""
    worker = RedisWorker()
    try:
        worker.start()
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
    except Exception as e:
        logger.exception(f"Worker failed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()