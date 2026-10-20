"""Email (SMTP) and Microsoft Teams notifications for workflow events."""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import requests

from backend.config import settings

logger = logging.getLogger(__name__)


class NotificationService:
    def send_email(self, subject: str, body: str, to_email: Optional[str] = None) -> bool:
        if not settings.SMTP_USER or not settings.SMTP_PASS:
            logger.debug("SMTP not configured; skipping email '%s'", subject)
            return False

        msg = MIMEMultipart()
        msg["From"] = settings.SMTP_USER
        msg["To"] = to_email or settings.NOTIFY_EMAIL_TO or settings.SMTP_USER
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        try:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
                server.starttls()
                server.login(settings.SMTP_USER, settings.SMTP_PASS)
                server.send_message(msg)
            logger.info("Email sent: %s", subject)
            return True
        except Exception:
            logger.exception("Failed to send email '%s'", subject)
            return False

    def send_teams_notification(self, title: str, message: str) -> bool:
        if not settings.TEAMS_WEBHOOK_URL:
            logger.debug("Teams webhook not configured; skipping")
            return False

        payload = {"title": title, "text": message.replace("\n", "<br>")}
        try:
            response = requests.post(settings.TEAMS_WEBHOOK_URL, json=payload, timeout=10)
            response.raise_for_status()
            logger.info("Teams notification sent: %s", title)
            return True
        except Exception:
            logger.exception("Failed to send Teams notification '%s'", title)
            return False

    def notify_event(self, event_name: str, book_title: str, details: str = "") -> None:
        """Send an event to every configured channel. Never raises."""
        message = f"Event: {event_name}\nBook: {book_title}\n{details}".strip()
        self.send_email(f"Book System: {event_name}", message)
        self.send_teams_notification(f"{event_name} — {book_title}", message)


notification_service = NotificationService()
