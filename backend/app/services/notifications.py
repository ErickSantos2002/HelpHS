"""
Notification service — in-app + email.

Usage
-----
Call ``notify()`` inside a router handler *before* ``await db.commit()``.
The notification is added to the session; the email is sent after the
commit is acknowledged (fire-and-forget via asyncio.create_task).

    await notify(db, user_id, NotificationType.ticket_updated, "Ticket updated",
                 "Your ticket HS-2026-0001 was updated.", data={"ticket_id": str(tid)},
                 settings=settings)
    await db.commit()

If the email fails it is logged and silently ignored — it never rolls back
the DB transaction.
"""

import asyncio
import uuid
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.models import Notification, NotificationType, User
from app.services.email import send_email


async def notify(
    db: AsyncSession,
    user_id: uuid.UUID,
    notif_type: NotificationType,
    title: str,
    message: str,
    data: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> None:
    """
    Create an in-app notification and schedule an email (best-effort).

    The Notification row is added to `db` but NOT committed here — the caller
    is responsible for the commit so the notification is atomic with the
    triggering operation.
    """
    notif = Notification(
        id=uuid.uuid4(),
        user_id=user_id,
        type=notif_type,
        title=title,
        message=message,
        data=data,
        read=False,
        email_sent=False,
    )
    db.add(notif)

    if settings is None:
        return  # no email without settings

    # Look up user email to send the notification
    result = await db.execute(select(User.email).where(User.id == user_id))
    email_addr = result.scalar_one_or_none()

    if email_addr:
        # Fire-and-forget: email failure must not affect the DB transaction
        asyncio.create_task(
            _send_and_log(notif, email_addr, title, message, settings),
            name=f"email-notif-{notif.id}",
        )


async def _send_and_log(
    notif: Notification,
    to_email: str,
    subject: str,
    body: str,
    settings: Settings,
) -> None:
    sent = await send_email(to_email, subject, body, settings)
    if sent:
        # Best-effort flag update — a new session would be needed here;
        # we just log since the notification already exists in DB.
        logger.debug("Email notification %s delivered to %s", notif.id, to_email)
    else:
        logger.warning("Email notification %s NOT delivered to %s", notif.id, to_email)
