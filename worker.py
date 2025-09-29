#!/usr/bin/env python3
"""
Redis worker script to process resume jobs asynchronously.

This script runs the worker that processes jobs from the Redis queue.
In production, you would run multiple instances of this worker for scalability.

Usage:
    python worker.py

Or with Redis/RQ (when properly installed):
    rq worker resume_processing --url redis://localhost:6379/0
"""

import asyncio
import logging
import signal
import sys
from typing import Any, Dict

from app.services.job_queue import job_queue, async_job_queue
from app.workers.async_resume_processor import process_resume_async

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s'
)
logger = logging.getLogger(__name__)


class AsyncWorker:
    """Async worker to process resume jobs."""
    
    def __init__(self):
        self.running = False
        self.tasks = set()
    
    async def start(self):
        """Start the worker to process jobs."""
        self.running = True
        logger.info("🚀 Starting async resume processor worker...")
        
        while self.running:
            try:
                # In production, this would poll Redis queue for jobs
                # For now, we'll just wait and process any jobs that come in
                await asyncio.sleep(5)
                
                # Process completed tasks
                done_tasks = [task for task in self.tasks if task.done()]
                for task in done_tasks:
                    self.tasks.remove(task)
                    try:
                        await task  # This will raise any exceptions that occurred
                        logger.info("✅ Task completed successfully")
                    except Exception as e:
                        logger.error(f"❌ Task failed: {e}")
                
            except KeyboardInterrupt:
                logger.info("🛑 Worker shutdown requested")
                break
            except Exception as e:
                logger.exception(f"Worker error: {e}")
                await asyncio.sleep(5)  # Brief pause before retrying
        
        # Wait for remaining tasks to complete
        if self.tasks:
            logger.info(f"Waiting for {len(self.tasks)} remaining tasks to complete...")
            await asyncio.gather(*self.tasks, return_exceptions=True)
        
        logger.info("👋 Worker stopped")
    
    def stop(self):
        """Stop the worker."""
        self.running = False
    
    async def process_job(self, job_data: Dict[str, Any]):
        """Process a single job."""
        try:
            application_id = job_data.get('application_id')
            job_post_id = job_data.get('job_post_id')
            
            if not application_id or not job_post_id:
                raise ValueError("Missing required job data: application_id or job_post_id")
            
            logger.info(f"🔄 Processing job: {application_id}")
            task = asyncio.create_task(process_resume_async(application_id, job_post_id))
            self.tasks.add(task)
            
        except Exception as e:
            logger.error(f"Failed to process job: {e}")
            raise


async def main():
    """Main worker function."""
    worker = AsyncWorker()
    
    # Set up signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        worker.stop()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await worker.start()
    except Exception as e:
        logger.exception(f"Worker failed: {e}")
        sys.exit(1)


def sync_worker():
    """Fallback synchronous worker using RQ (when Redis is available)."""
    try:
        # This would work when Redis and RQ are properly installed
        from rq import Worker
        import redis
        
        redis_conn = redis.from_url("redis://localhost:6379/0")
        worker = Worker(["resume_processing"], connection=redis_conn)
        
        logger.info("🚀 Starting RQ worker for resume processing...")
        worker.work()
        
    except ImportError:
        logger.error("RQ not available. Please install: pip install rq redis")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"RQ worker failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--rq":
        # Use RQ worker when Redis is available
        sync_worker()
    else:
        # Use async worker (default)
        asyncio.run(main())