"""Push notifications through SNS Mobile Push (APNs for iOS, FCM v1 for
Android): one platform endpoint per device token."""

from __future__ import annotations

import asyncio
import json
import logging

from cappy_common.events import aws_client

log = logging.getLogger(__name__)


class Pusher:
    async def register(self, platform: str, token: str) -> str | None:
        """The endpoint to push to, or None when push is not configured."""

    async def send(self, endpoint: str, title: str, body: str, link: str) -> bool:
        """False when the device is gone (uninstalled, token expired)."""


class LogPusher(Pusher):
    """Local development and tests: pushes are logged and kept."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def register(self, platform: str, token: str) -> str | None:
        return f"local:{platform}:{token[:12]}"

    async def send(self, endpoint: str, title: str, body: str, link: str) -> bool:
        self.sent.append((endpoint, title))
        log.info("push to %s: %s", endpoint, title)
        return not endpoint.endswith("gone")


class SnsPusher(Pusher):
    def __init__(self, settings) -> None:  # noqa: ANN001
        self._c = aws_client("sns", settings)
        self._apps = {"ios": settings.push_ios_app_arn, "android": settings.push_android_app_arn}

    async def register(self, platform: str, token: str) -> str | None:
        app = self._apps.get(platform)
        if not app:
            return None
        r = await asyncio.to_thread(self._c.create_platform_endpoint, PlatformApplicationArn=app, Token=token)
        return r["EndpointArn"]

    async def send(self, endpoint: str, title: str, body: str, link: str) -> bool:
        message = {
            "default": body,
            "APNS": json.dumps({"aps": {"alert": {"title": title, "body": body}, "sound": "default"}, "link": link}),
            "GCM": json.dumps(
                {
                    "fcmV1Message": {
                        "message": {
                            "notification": {"title": title, "body": body},
                            "data": {"link": link},
                        }
                    }
                }
            ),
        }
        try:
            await asyncio.to_thread(
                self._c.publish, TargetArn=endpoint, Message=json.dumps(message), MessageStructure="json"
            )
            return True
        except self._c.exceptions.EndpointDisabledException:
            return False
