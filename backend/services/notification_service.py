import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
from backend.database import settings

class NotificationService:
    def send_email(self, subject: str, body: str, to_email: str = None):
        if not settings.SMTP_USER or not settings.SMTP_PASS:
            print("SMTP not configured. Skipping email.")
            return

        to_email = to_email or settings.SMTP_USER
        msg = MIMEMultipart()
        msg['From'] = settings.SMTP_USER
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        try:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                server.starttls()
                server.login(settings.SMTP_USER, settings.SMTP_PASS)
                server.send_message(msg)
            print(f"Email sent: {subject}")
        except Exception as e:
            print(f"Email Error: {e}")

    def send_teams_notification(self, message: str):
        if not settings.TEAMS_WEBHOOK_URL:
            print("Teams Webhook not configured. Skipping.")
            return

        payload = {"text": message}
        try:
            requests.post(settings.TEAMS_WEBHOOK_URL, json=payload)
            print("Teams notification sent.")
        except Exception as e:
            print(f"Teams Error: {e}")

    def notify_event(self, event_name: str, book_title: str, details: str = ""):
        message = f"Event: {event_name}\nBook: {book_title}\n{details}"
        self.send_email(f"Book System: {event_name}", message)
        self.send_teams_notification(message)

notification_service = NotificationService()
