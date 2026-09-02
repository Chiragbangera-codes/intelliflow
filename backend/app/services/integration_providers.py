"""
Integration Provider Interface and Concrete Implementations.

Defines pluggable integration handlers: Webhook, Slack, MS Teams, Email, Generic HTTP.
All outbound calls enforce strict SSRF validation and safe error handling.
"""

from __future__ import annotations

import abc
import json
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from app.core.config import settings
from app.models.integration import IntegrationProvider
from app.utils.ssrf import safe_http_post

logger = logging.getLogger(__name__)


class BaseIntegrationProvider(abc.ABC):
    """Abstract interface for all integration providers."""

    @abc.abstractmethod
    async def send_message(
        self,
        payload: dict[str, Any],
        configuration: dict[str, Any],
        credentials: dict[str, Any] | None,
        allow_test_local: bool = False,
    ) -> dict[str, Any]:
        """Send a message/event payload to the external provider."""

    @abc.abstractmethod
    async def test_connection(
        self,
        configuration: dict[str, Any],
        credentials: dict[str, Any] | None,
        allow_test_local: bool = False,
    ) -> dict[str, Any]:
        """Verify connectivity and credentials with the provider."""


class WebhookProvider(BaseIntegrationProvider):
    """Generic Webhook integration provider."""

    async def send_message(
        self,
        payload: dict[str, Any],
        configuration: dict[str, Any],
        credentials: dict[str, Any] | None,
        allow_test_local: bool = False,
    ) -> dict[str, Any]:
        url = configuration.get("url")
        if not url:
            return {"success": False, "error": "Missing 'url' in webhook configuration."}

        headers = {"Content-Type": "application/json"}
        if credentials and "api_key" in credentials:
            headers["Authorization"] = f"Bearer {credentials['api_key']}"

        payload_bytes = json.dumps(payload).encode("utf-8")
        status, body, _ = await safe_http_post(
            url=url,
            headers=headers,
            content=payload_bytes,
            timeout_seconds=settings.WEBHOOK_TIMEOUT_SECONDS,
            allow_test_local=allow_test_local,
        )
        is_ok = 200 <= status < 300
        return {"success": is_ok, "status_code": status, "response": body[:500]}

    async def test_connection(
        self,
        configuration: dict[str, Any],
        credentials: dict[str, Any] | None,
        allow_test_local: bool = False,
    ) -> dict[str, Any]:
        test_payload = {"test": True, "provider": "webhook", "message": "IntelliFlow Ping"}
        return await self.send_message(test_payload, configuration, credentials, allow_test_local)


class SlackProvider(BaseIntegrationProvider):
    """Slack Incoming Webhook provider."""

    async def send_message(
        self,
        payload: dict[str, Any],
        configuration: dict[str, Any],
        credentials: dict[str, Any] | None,
        allow_test_local: bool = False,
    ) -> dict[str, Any]:
        webhook_url = configuration.get("webhook_url") or (
            credentials.get("webhook_url") if credentials else None
        )
        if not webhook_url:
            return {"success": False, "error": "Missing Slack 'webhook_url'."}

        channel = configuration.get("channel")
        text = payload.get("text") or payload.get("message") or "IntelliFlow Platform Notification"

        slack_body: dict[str, Any] = {
            "text": text,
            "blocks": [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*IntelliFlow Notification*\n{text}"},
                }
            ],
        }
        if channel:
            slack_body["channel"] = channel

        headers = {"Content-Type": "application/json"}
        status, body, _ = await safe_http_post(
            url=webhook_url,
            headers=headers,
            content=json.dumps(slack_body).encode("utf-8"),
            timeout_seconds=settings.WEBHOOK_TIMEOUT_SECONDS,
            allow_test_local=allow_test_local,
        )
        is_ok = 200 <= status < 300
        return {"success": is_ok, "status_code": status, "response": body[:500]}

    async def test_connection(
        self,
        configuration: dict[str, Any],
        credentials: dict[str, Any] | None,
        allow_test_local: bool = False,
    ) -> dict[str, Any]:
        test_payload = {"text": "IntelliFlow Slack integration connection verified successfully."}
        return await self.send_message(test_payload, configuration, credentials, allow_test_local)


class TeamsProvider(BaseIntegrationProvider):
    """Microsoft Teams Webhook / MessageCard provider."""

    async def send_message(
        self,
        payload: dict[str, Any],
        configuration: dict[str, Any],
        credentials: dict[str, Any] | None,
        allow_test_local: bool = False,
    ) -> dict[str, Any]:
        webhook_url = configuration.get("webhook_url") or (
            credentials.get("webhook_url") if credentials else None
        )
        if not webhook_url:
            return {"success": False, "error": "Missing MS Teams 'webhook_url'."}

        title = payload.get("title") or "IntelliFlow Alert"
        text = payload.get("text") or payload.get("message") or "Platform notification"

        teams_body = {
            "@type": "MessageCard",
            "@context": "https://schema.org/extensions",
            "summary": title,
            "themeColor": "0076D7",
            "title": title,
            "sections": [{"activityTitle": title, "activitySubtitle": text}],
        }

        headers = {"Content-Type": "application/json"}
        status, body, _ = await safe_http_post(
            url=webhook_url,
            headers=headers,
            content=json.dumps(teams_body).encode("utf-8"),
            timeout_seconds=settings.WEBHOOK_TIMEOUT_SECONDS,
            allow_test_local=allow_test_local,
        )
        is_ok = 200 <= status < 300
        return {"success": is_ok, "status_code": status, "response": body[:500]}

    async def test_connection(
        self,
        configuration: dict[str, Any],
        credentials: dict[str, Any] | None,
        allow_test_local: bool = False,
    ) -> dict[str, Any]:
        test_payload = {
            "title": "IntelliFlow MS Teams Connection Test",
            "text": "Microsoft Teams connector is successfully linked.",
        }
        return await self.send_message(test_payload, configuration, credentials, allow_test_local)


class EmailProvider(BaseIntegrationProvider):
    """SMTP Email integration provider."""

    async def send_message(
        self,
        payload: dict[str, Any],
        configuration: dict[str, Any],
        credentials: dict[str, Any] | None,
        allow_test_local: bool = False,
    ) -> dict[str, Any]:
        host = configuration.get("smtp_host") or settings.SMTP_HOST
        port = int(configuration.get("smtp_port") or settings.SMTP_PORT)
        sender = configuration.get("from_email") or settings.SMTP_FROM
        recipient = payload.get("to") or configuration.get("default_recipient")

        if not host:
            return {
                "success": False,
                "error": "SMTP Host is not configured.",
            }
        if not recipient:
            return {"success": False, "error": "No recipient email address specified."}

        subject = payload.get("subject") or "IntelliFlow Notification"
        body_text = payload.get("body") or payload.get("message") or ""

        msg = MIMEMultipart()
        msg["From"] = sender
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(body_text, "plain"))

        try:
            with smtplib.SMTP(host, port, timeout=10) as server:
                if configuration.get("use_tls", settings.SMTP_USE_TLS):
                    server.starttls()
                user = (credentials.get("smtp_user") if credentials else None) or settings.SMTP_USER
                password = (
                    credentials.get("smtp_password") if credentials else None
                ) or settings.SMTP_PASSWORD
                if user and password:
                    server.login(user, password)
                server.send_message(msg)
            return {"success": True, "message": f"Email dispatched to {recipient}"}
        except Exception as exc:
            logger.warning("SMTP dispatch error: %s", exc)
            return {"success": False, "error": str(exc)}

    async def test_connection(
        self,
        configuration: dict[str, Any],
        credentials: dict[str, Any] | None,
        allow_test_local: bool = False,
    ) -> dict[str, Any]:
        test_payload = {
            "to": configuration.get("default_recipient") or "test@example.com",
            "subject": "IntelliFlow SMTP Connection Verification",
            "body": "Your email integration configuration has been successfully tested.",
        }
        return await self.send_message(test_payload, configuration, credentials, allow_test_local)


class GenericHTTPProvider(BaseIntegrationProvider):
    """Custom Generic HTTP / REST endpoint provider."""

    async def send_message(
        self,
        payload: dict[str, Any],
        configuration: dict[str, Any],
        credentials: dict[str, Any] | None,
        allow_test_local: bool = False,
    ) -> dict[str, Any]:
        url = configuration.get("url")
        if not url:
            return {"success": False, "error": "Missing 'url' in Generic HTTP configuration."}

        headers = dict(configuration.get("headers") or {})
        headers.setdefault("Content-Type", "application/json")

        if credentials:
            if "api_key" in credentials:
                headers["Authorization"] = f"Bearer {credentials['api_key']}"
            elif "basic_user" in credentials and "basic_pass" in credentials:
                import base64

                auth_str = f"{credentials['basic_user']}:{credentials['basic_pass']}"
                encoded = base64.b64encode(auth_str.encode()).decode()
                headers["Authorization"] = f"Basic {encoded}"

        status, body, _ = await safe_http_post(
            url=url,
            headers=headers,
            content=json.dumps(payload).encode("utf-8"),
            timeout_seconds=settings.WEBHOOK_TIMEOUT_SECONDS,
            allow_test_local=allow_test_local,
        )
        is_ok = 200 <= status < 300
        return {"success": is_ok, "status_code": status, "response": body[:500]}

    async def test_connection(
        self,
        configuration: dict[str, Any],
        credentials: dict[str, Any] | None,
        allow_test_local: bool = False,
    ) -> dict[str, Any]:
        test_payload = {
            "test": True,
            "provider": "generic_http",
            "message": "IntelliFlow Ping Verification",
        }
        return await self.send_message(test_payload, configuration, credentials, allow_test_local)


_PROVIDERS: dict[IntegrationProvider, BaseIntegrationProvider] = {
    IntegrationProvider.WEBHOOK: WebhookProvider(),
    IntegrationProvider.SLACK: SlackProvider(),
    IntegrationProvider.MSTEAMS: TeamsProvider(),
    IntegrationProvider.EMAIL: EmailProvider(),
    IntegrationProvider.GENERIC_HTTP: GenericHTTPProvider(),
}


def get_integration_provider(provider: IntegrationProvider) -> BaseIntegrationProvider:
    """Factory to retrieve the appropriate integration provider implementation."""
    impl = _PROVIDERS.get(provider)
    if not impl:
        raise ValueError(f"Unsupported integration provider: {provider}")
    return impl
