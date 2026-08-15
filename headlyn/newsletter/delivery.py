from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Protocol

from .render import DEFAULT_LOGO_PATH, render_html


@dataclass(frozen=True)
class SmtpSettings:
    host: str
    port: int
    username: str
    password: str
    sender: str
    reply_to: str
    recipients: tuple[str, ...]
    starttls: bool = True

    @classmethod
    def from_environment(cls) -> "SmtpSettings":
        recipients = tuple(
            address.strip()
            for address in os.environ.get("HEADLYN_RECIPIENTS", "").split(",")
            if address.strip()
        )
        return cls(
            host=os.environ.get("HEADLYN_SMTP_HOST", "").strip(),
            port=int(os.environ.get("HEADLYN_SMTP_PORT", "587")),
            username=os.environ.get("HEADLYN_SMTP_USERNAME", "").strip(),
            password=os.environ.get("HEADLYN_SMTP_PASSWORD", ""),
            sender=os.environ.get("HEADLYN_SMTP_FROM", "").strip(),
            reply_to=os.environ.get("HEADLYN_SMTP_REPLY_TO", "").strip(),
            recipients=recipients,
            starttls=os.environ.get("HEADLYN_SMTP_STARTTLS", "true").lower()
            not in {"0", "false", "no"},
        )

    def validate(self) -> None:
        missing = [
            name
            for name, value in (
                ("HEADLYN_SMTP_HOST", self.host),
                ("HEADLYN_SMTP_FROM", self.sender),
            )
            if not value
        ]
        if not self.recipients:
            missing.append("HEADLYN_RECIPIENTS")
        if missing:
            raise ValueError("missing SMTP configuration: " + ", ".join(missing))


class MailSender(Protocol):
    def send(self, edition: dict[str, object], html_body: str, text_body: str) -> int:
        ...


class SmtpMailSender:
    def __init__(self, settings: SmtpSettings | None = None) -> None:
        self.settings = settings or SmtpSettings.from_environment()

    def send(self, edition: dict[str, object], html_body: str, text_body: str) -> int:
        self.settings.validate()
        message = EmailMessage()
        message["Subject"] = f"Headlyn Daily Briefing — {edition['edition_date']}"
        message["From"] = self.settings.sender
        message["To"] = ", ".join(self.settings.recipients)
        if self.settings.reply_to:
            message["Reply-To"] = self.settings.reply_to
        message.set_content(text_body)
        email_html = html_body
        logo_bytes: bytes | None = None
        try:
            logo_bytes = DEFAULT_LOGO_PATH.read_bytes()
            email_html = render_html(edition, logo_src="cid:headlyn-logo")
        except OSError:
            pass
        message.add_alternative(email_html, subtype="html")
        if logo_bytes is not None:
            html_part = message.get_payload()[-1]
            html_part.add_related(
                logo_bytes,
                maintype="image",
                subtype="png",
                cid="<headlyn-logo>",
                filename=Path(DEFAULT_LOGO_PATH).name,
            )
        with smtplib.SMTP(self.settings.host, self.settings.port, timeout=30) as server:
            if self.settings.starttls:
                server.starttls()
            if self.settings.username:
                server.login(self.settings.username, self.settings.password)
            server.send_message(message)
        return len(self.settings.recipients)
