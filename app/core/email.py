"""Small server-side boundary for account-token email delivery.

Token values are handed only to the configured mail transport. They are never
written to logs, audit metadata, database columns, or API responses in
production.
"""

import smtplib
from email.message import EmailMessage
from typing import Protocol

from app.core.config import Settings
from app.core.errors import AppError


class AccountEmailSender(Protocol):
    def send_verification(self, *, recipient: str, token: str) -> None: ...

    def send_password_reset(self, *, recipient: str, token: str) -> None: ...

    def health(self) -> bool: ...


class UnconfiguredEmailSender:
    def send_verification(self, *, recipient: str, token: str) -> None:
        del recipient, token
        raise AppError(
            "email_delivery_unavailable",
            "Account email delivery is not configured.",
            503,
        )

    def send_password_reset(self, *, recipient: str, token: str) -> None:
        self.send_verification(recipient=recipient, token=token)

    def health(self) -> bool:
        return False


class SmtpEmailSender:
    def __init__(self, settings: Settings) -> None:
        self.host = settings.email_smtp_host
        self.port = settings.email_smtp_port
        self.username = settings.email_smtp_username
        self.password = (
            settings.email_smtp_password.get_secret_value()
            if settings.email_smtp_password
            else None
        )
        self.sender = settings.email_from
        self.starttls = settings.email_smtp_starttls

    def send_verification(self, *, recipient: str, token: str) -> None:
        self._send(
            recipient,
            "Verify your Scholarship AI email address",
            "Use this one-time verification token:\n\n"
            f"{token}\n\n"
            "If you did not request this, you can ignore this message.",
        )

    def send_password_reset(self, *, recipient: str, token: str) -> None:
        self._send(
            recipient,
            "Reset your Scholarship AI password",
            "Use this one-time password-reset token:\n\n"
            f"{token}\n\n"
            "If you did not request this, you can ignore this message.",
        )

    def health(self) -> bool:
        try:
            with self._connection():
                return True
        except (OSError, smtplib.SMTPException):
            return False

    def _send(self, recipient: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)
        try:
            with self._connection() as connection:
                connection.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            raise AppError(
                "email_delivery_unavailable",
                "We could not send account email. Try again shortly.",
                503,
            ) from exc

    def _connection(self) -> smtplib.SMTP:
        assert self.host and self.username and self.password
        connection = smtplib.SMTP(self.host, self.port, timeout=10)
        connection.ehlo()
        if self.starttls:
            connection.starttls()
            connection.ehlo()
        connection.login(self.username, self.password)
        return connection


def get_account_email_sender(settings: Settings) -> AccountEmailSender:
    if settings.email_provider == "smtp":
        return SmtpEmailSender(settings)
    return UnconfiguredEmailSender()
