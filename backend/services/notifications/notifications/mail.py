"""Who someone is (Cognito) and how an email leaves (SES)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from cappy_common.events import aws_client

log = logging.getLogger(__name__)


@dataclass
class Email:
    to: str
    subject: str
    text: str


class Directory:
    """The email address behind a Cognito ``sub``, or None if they are gone."""

    async def email_of(self, sub: str) -> str | None: ...

    async def person_of(self, sub: str) -> tuple[str | None, str | None]:
        """(verified email, locale). Locale is Cognito's standard attribute."""
        return await self.email_of(sub), None

    async def sign_out_everywhere(self, sub: str) -> None:
        """Revoke every refresh token they hold."""


class Mailer:
    async def send(self, email: Email) -> None: ...


class CognitoDirectory(Directory):
    def __init__(self, settings) -> None:  # noqa: ANN001
        self._c = aws_client("cognito-idp", settings, settings.cognito_endpoint_url)
        self._pool = settings.user_pool_id
        self._local = bool(settings.cognito_endpoint_url)

    def _lookup(self, sub: str) -> tuple[str | None, str | None]:
        # With email as the sign-in attribute (our pools) Cognito's username is
        # the sub, so AdminGetUser, which has far more quota than ListUsers,
        # finds them directly. ListUsers is the fallback for other pools.
        try:
            user = self._c.admin_get_user(UserPoolId=self._pool, Username=sub)
            raw = user.get("UserAttributes", [])
        except self._c.exceptions.UserNotFoundException:
            users = self._c.list_users(UserPoolId=self._pool, Filter=f'sub = "{sub}"', Limit=1)["Users"]
            if not users:
                return None, None
            raw = users[0].get("Attributes", [])
        attrs = {a["Name"]: a["Value"] for a in raw}
        if attrs.get("email_verified") not in ("true", True):
            return None, attrs.get("locale")  # never mail an address nobody proved they own
        return attrs.get("email"), attrs.get("locale")

    async def email_of(self, sub: str) -> str | None:
        return (await self.person_of(sub))[0]

    def _username(self, sub: str) -> str:
        try:
            return self._c.admin_get_user(UserPoolId=self._pool, Username=sub)["Username"]
        except self._c.exceptions.UserNotFoundException:
            users = self._c.list_users(UserPoolId=self._pool, Filter=f'sub = "{sub}"', Limit=1)["Users"]
            if not users:
                raise
            return users[0]["Username"]

    def _sign_out(self, sub: str) -> None:
        if self._local:
            # cognito-local answers "Unsupported" (after four slow retries); locally only the devices go.
            log.warning("cognito-local cannot sign %s out everywhere; skipped", sub)
            return
        try:
            self._c.admin_user_global_sign_out(UserPoolId=self._pool, Username=self._username(sub))
        except self._c.exceptions.UserNotFoundException:
            return  # nothing left to sign out

    async def sign_out_everywhere(self, sub: str) -> None:
        if sub and '"' not in sub:
            await asyncio.to_thread(self._sign_out, sub)

    async def person_of(self, sub: str) -> tuple[str | None, str | None]:
        if not sub or '"' in sub:
            return None, None
        return await asyncio.to_thread(self._lookup, sub)


class SesMailer(Mailer):
    def __init__(self, settings) -> None:  # noqa: ANN001
        # SES v1's SendEmail: the same in AWS, and within every LocalStack tier.
        self._c = aws_client("ses", settings)
        self._from = settings.mail_from

    async def send(self, email: Email) -> None:
        await asyncio.to_thread(
            self._c.send_email,
            Source=self._from,
            Destination={"ToAddresses": [email.to]},
            Message={
                "Subject": {"Data": email.subject, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": email.text, "Charset": "UTF-8"}},
            },
        )


class LogMailer(Mailer):
    def __init__(self) -> None:
        self.sent: list[Email] = []

    async def send(self, email: Email) -> None:
        self.sent.append(email)
        log.info("email to %s: %s", email.to, email.subject)
