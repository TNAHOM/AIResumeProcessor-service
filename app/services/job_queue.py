"""
Simple Redis-based job queue implementation
"""
import json
import uuid
from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)

# Try to import Redis, fallback to mock if not available
try:
    from redis import Redis
    REDIS_AVAILABLE = True
except ImportError:
    logger.warning("Redis not available, using mock Redis for development")
    REDIS_AVAILABLE = False
    Redis = None

from app.core.config import settings


class JobQueue:
    """Simple Redis-based job queue for background tasks"""
    
    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or settings.REDIS_URL
        self._redis = None
    
    @property
    def redis(self):
        """Lazy initialization of Redis connection"""
        if self._redis is None:
            if not REDIS_AVAILABLE:
                logger.info("Redis not available, using MockRedis for development")
                self._redis = MockRedis()
            else:
                try:
                    self._redis = Redis.from_url(self.redis_url, decode_responses=True)
                    # Test connection
                    self._redis.ping()
                    logger.info(f"Connected to Redis at {self.redis_url}")
                except Exception as e:
                    logger.error(f"Failed to connect to Redis at {self.redis_url}: {e}")
                    logger.info("Falling back to MockRedis for development")
                    self._redis = MockRedis()
        return self._redis
    
    def enqueue_job(self, job_name: str, job_data: Dict[str, Any], queue_name: str = "default") -> str:
        """Enqueue a job to the specified queue"""
        job_id = str(uuid.uuid4())
        job_payload = {
            "id": job_id,
            "name": job_name,
            "data": job_data,
            "created_at": json.dumps({"timestamp": str(uuid.uuid1().time)})
        }
        
        try:
            # Add job to queue (list)
            self.redis.lpush(f"queue:{queue_name}", json.dumps(job_payload))
            logger.info(f"Enqueued job {job_name} with ID {job_id} to queue {queue_name}")
            return job_id
        except Exception as e:
            logger.error(f"Failed to enqueue job {job_name}: {e}")
            raise
    
    def dequeue_job(self, queue_name: str = "default", timeout: int = 0) -> Optional[Dict[str, Any]]:
        """Dequeue a job from the specified queue"""
        try:
            result = self.redis.brpop(f"queue:{queue_name}", timeout=timeout)
            if result:
                _, job_data = result
                return json.loads(job_data)
            return None
        except Exception as e:
            logger.error(f"Failed to dequeue job from {queue_name}: {e}")
            return None


class MockRedis:
    """Mock Redis for development when Redis is not available"""
    
    def __init__(self):
        self._data = {}
    
    def ping(self):
        return True
    
    def lpush(self, key: str, value: str):
        if key not in self._data:
            self._data[key] = []
        self._data[key].insert(0, value)
        logger.info(f"[MockRedis] LPUSH {key}: {value[:100]}...")
        return len(self._data[key])
    
    def brpop(self, key: str, timeout: int = 0):
        if key in self._data and self._data[key]:
            value = self._data[key].pop()
            logger.info(f"[MockRedis] BRPOP {key}: {value[:100]}...")
            return (key, value)
        return None


# Global job queue instance
job_queue = JobQueue()