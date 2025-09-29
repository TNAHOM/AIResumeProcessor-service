from celery import Celery
from app.core.config import settings

# Create Celery app
celery_app = Celery(
    "resume_processor",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.celery_tasks"]
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_max_tasks_per_child=1000,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)