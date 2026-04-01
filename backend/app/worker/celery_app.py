from celery import Celery
from loguru import logger

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "helpdesk",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Sao_Paulo",
    enable_utc=True,
    task_soft_time_limit=settings.celery_task_soft_time_limit,
    task_time_limit=settings.celery_task_time_limit,
    task_max_retries=settings.celery_default_max_retries,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)


@celery_app.on_after_configure.connect
def log_celery_ready(sender, **kwargs):
    logger.info("Celery configured — broker: {}", settings.celery_broker_url)
