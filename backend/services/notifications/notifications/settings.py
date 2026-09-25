from __future__ import annotations

from typing import ClassVar, Literal

from cappy_common.settings import CommonSettings


class Settings(CommonSettings):
    # A worker: no endpoint acts for a person, so it verifies no tokens.
    verifies_tokens: ClassVar[bool] = False

    service_name: str = "notifications"
    database_url: str = "sqlite+aiosqlite:///./notifications.db"
    # "log" writes emails to the log instead of sending them.
    mailer: Literal["log", "ses"] = "log"
    mail_from: str = "Cappy <no-reply@cappy.local>"
    # Where people are. The pool holds their email; we never copy it.
    user_pool_id: str = ""
    # cognito-local in local development. Empty: the AWS endpoint.
    cognito_endpoint_url: str = ""
    web_base_url: str = "http://localhost:5173"

    def unsafe_reasons(self) -> list[str]:
        problems = super().unsafe_reasons()
        if not self.database_url.startswith("postgresql"):
            problems.append("DATABASE_URL must be Postgres")
        if self.mailer != "ses":
            problems.append("MAILER must be ses")
        if not self.user_pool_id:
            problems.append("USER_POOL_ID is required")
        return problems
