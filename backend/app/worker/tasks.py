from loguru import logger

from app.worker.celery_app import celery_app


@celery_app.task(bind=True, name="tasks.send_notification_email", max_retries=3)
def send_notification_email(self, user_id: str, subject: str, body: str) -> dict:
    """Envia email de notificacao de forma assincrona."""
    try:
        logger.info(f"Sending notification email to user {user_id}: {subject}")
        # Implementacao real sera adicionada na task de email (Sprint 3)
        return {"status": "queued", "user_id": user_id, "subject": subject}
    except Exception as exc:
        logger.error(f"Email task failed: {exc}")
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(bind=True, name="tasks.classify_ticket", max_retries=2)
def classify_ticket(self, ticket_id: str, title: str, description: str) -> dict:
    """Classifica ticket via IA de forma assincrona."""
    try:
        logger.info(f"Classifying ticket {ticket_id}")
        # Implementacao real sera adicionada na task de IA (Sprint 6)
        return {"status": "queued", "ticket_id": ticket_id}
    except Exception as exc:
        logger.error(f"Classification task failed: {exc}")
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(name="tasks.health_check")
def health_check() -> dict:
    """Task de verificacao de saude do worker."""
    logger.info("Celery worker health check OK")
    return {"status": "ok"}
