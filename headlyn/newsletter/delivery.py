from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any, Protocol

try:
    from mailjet_rest import Client
except ImportError:  # pragma: no cover - exercised only in an incomplete environment
    Client = None  # type: ignore[assignment]

from .render import DEFAULT_LOGO_PATH, render_html
from ..tls import configure_ca_bundle


LOGO_FILENAME = "headlyn-logo.png"


@dataclass(frozen=True)
class MailjetSettings:
    api_key: str
    api_secret: str
    sender: str
    sender_name: str
    reply_to: str
    recipients: tuple[str, ...]

    @classmethod
    def from_environment(cls) -> "MailjetSettings":
        recipients = tuple(
            address.strip()
            for address in os.environ.get("HEADLYN_RECIPIENTS", "").split(",")
            if address.strip()
        )
        return cls(
            api_key=os.environ.get("MJ_APIKEY_PUBLIC", "").strip(),
            api_secret=os.environ.get("MJ_APIKEY_PRIVATE", "").strip(),
            sender=os.environ.get("HEADLYN_MAILJET_FROM", "").strip(),
            sender_name=os.environ.get("HEADLYN_MAILJET_FROM_NAME", "Headlyn").strip(),
            reply_to=os.environ.get("HEADLYN_MAILJET_REPLY_TO", "").strip(),
            recipients=recipients,
        )

    def validate(self) -> None:
        missing = [
            name
            for name, value in (
                ("MJ_APIKEY_PUBLIC", self.api_key),
                ("MJ_APIKEY_PRIVATE", self.api_secret),
                ("HEADLYN_MAILJET_FROM", self.sender),
            )
            if not value
        ]
        if not self.recipients:
            missing.append("HEADLYN_RECIPIENTS")
        if missing:
            raise ValueError("missing Mailjet configuration: " + ", ".join(missing))


class MailSender(Protocol):
    def send(self, edition: dict[str, object], html_body: str, text_body: str) -> int:
        ...


class MailjetMailSender:
    """Deliver a rendered newsletter through Mailjet Send API v3.1."""

    def __init__(
        self,
        settings: MailjetSettings | None = None,
        *,
        client: Any | None = None,
    ) -> None:
        self.settings = settings or MailjetSettings.from_environment()
        self._client = client

    def send(self, edition: dict[str, object], html_body: str, text_body: str) -> int:
        configure_ca_bundle()
        self.settings.validate()
        email_html = html_body
        inline_attachments: list[dict[str, str]] = []
        try:
            logo_bytes = DEFAULT_LOGO_PATH.read_bytes()
        except OSError:
            logo_bytes = None
        if logo_bytes is not None:
            email_html = render_html(edition, logo_src=f"cid:{LOGO_FILENAME}")
            inline_attachments.append(
                {
                    "ContentType": "image/png",
                    "Filename": LOGO_FILENAME,
                    "ContentID": LOGO_FILENAME,
                    "Base64Content": base64.b64encode(logo_bytes).decode("ascii"),
                }
            )

        message: dict[str, object] = {
            "From": {"Email": self.settings.sender, "Name": self.settings.sender_name},
            "To": [{"Email": recipient} for recipient in self.settings.recipients],
            "Subject": f"Headlyn Daily Briefing — {edition['edition_date']}",
            "TextPart": text_body,
            "HTMLPart": email_html,
            "CustomID": f"headlyn-{edition['edition_date']}",
        }
        if self.settings.reply_to:
            message["ReplyTo"] = {"Email": self.settings.reply_to}
        if inline_attachments:
            message["InlinedAttachments"] = inline_attachments

        data = {"Messages": [message]}
        response = self._send_request(data)
        if response.status_code != 200:
            try:
                details = response.json()
            except (TypeError, ValueError):
                details = getattr(response, "text", "unknown Mailjet error")
            raise RuntimeError(f"Mailjet send failed ({response.status_code}): {details}")
        return len(self.settings.recipients)

    def _send_request(self, data: dict[str, object]) -> Any:
        if self._client is not None:
            return self._client.send.create(data=data)
        if Client is None:
            raise RuntimeError(
                "mailjet-rest is not installed; install dependencies from requirements.txt"
            )
        with Client(
            auth=(self.settings.api_key, self.settings.api_secret),
            version="v3.1",
        ) as mailjet:
            return mailjet.send.create(data=data)
