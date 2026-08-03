from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "support_saas",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Ingestion tasks touch the filesystem and an external embeddings API,
    # so keep them out of memory-fast-path defaults: retry-friendly, and
    # don't let one huge document hog a worker forever.
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=15 * 60,
    task_soft_time_limit=12 * 60,
)
