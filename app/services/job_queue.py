import json
import logging
import uuid
from typing import Any, Dict, Optional
import asyncio

# Note: This is a simplified implementation for development
# In production, install: pip install redis rq aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)


class MockJobQueue:
    """Mock Redis-based job queue service for development when Redis isn't available."""
    
    def __init__(self):
        self.jobs = {}
        logger.warning("Using mock job queue - install redis, rq, aioredis for production")
    
    def enqueue_job(self, func, *args, job_id: Optional[str] = None, **kwargs) -> "MockJob":
        """Enqueue a job for background processing."""
        if job_id is None:
            job_id = str(uuid.uuid4())
        
        job = MockJob(job_id, func, args, kwargs)
        self.jobs[job_id] = job
        
        # Simulate async processing
        asyncio.create_task(self._process_job(job))
        
        logger.info(f"Enqueued mock job {job.id} for function {func.__name__}")
        return job
    
    async def _process_job(self, job):
        """Process job asynchronously."""
        try:
            job.status = "started"
            result = await job.func(*job.args, **job.kwargs)
            job.result = result
            job.status = "finished"
        except Exception as e:
            job.exception = str(e)
            job.status = "failed"
    
    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of a job by ID."""
        job = self.jobs.get(job_id)
        if not job:
            return None
        
        return {
            "id": job.id,
            "status": job.status,
            "result": job.result,
            "exception": job.exception,
            "created_at": job.created_at,
        }


class MockJob:
    """Mock job object."""
    
    def __init__(self, job_id: str, func, args, kwargs):
        self.id = job_id
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.status = "queued"
        self.result = None
        self.exception = None
        self.created_at = str(uuid.uuid4().hex)


class AsyncJobQueue:
    """Async job queue service - simplified version."""
    
    def __init__(self):
        self.jobs = {}
    
    async def enqueue_job_async(self, job_data: Dict[str, Any], job_id: Optional[str] = None) -> str:
        """Enqueue a job asynchronously."""
        if job_id is None:
            job_id = str(uuid.uuid4())
        
        self.jobs[job_id] = {
            "id": job_id,
            "status": "queued",
            "data": job_data,
            "created_at": str(uuid.uuid4().hex)
        }
        
        logger.info(f"Enqueued async job {job_id}")
        return job_id
    
    async def get_job_status_async(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job status asynchronously."""
        return self.jobs.get(job_id)
    
    async def update_job_status(self, job_id: str, status: str, **kwargs):
        """Update job status and additional fields."""
        if job_id in self.jobs:
            self.jobs[job_id]["status"] = status
            self.jobs[job_id].update(kwargs)
            logger.debug(f"Updated job {job_id} status to {status}")


# Global instances
job_queue = MockJobQueue()
async_job_queue = AsyncJobQueue()