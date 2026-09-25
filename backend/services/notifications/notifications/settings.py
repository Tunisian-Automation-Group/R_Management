from __future__ import annotations

from typing import Literal

from cappy_common.settings import CommonSettings


class Settings(CommonSettings):
    service_name: str = "notifications"
    database_url: str = "sqlite+aiosqlite:///./notifications.db"
    # "log" writes emails to the log instead of sending them.
    mailer: Literal["log", "ses"] = "log"
    mail_from: str = "Cappy <no-reply@cappy.local>"
    # Where people are (USER_POOL_ID, COGNITO_ENDPOINT_URL, in CommonSettings):
    # the pool holds their email; we never copy it.
    web_base_url: str = "http://localhost:5173"
    # SNS platform applications (APNs, FCM). Empty: pushes are logged only.
    push_ios_app_arn: str = ""
    push_android_app_arn: str = ""

    def unsafe_reasons(self) -> list[str]:
        problems = super().unsafe_reasons()
        if not self.database_url.startswith("postgresql"):
            problems.append("DATABASE_URL must be Postgres")
        if self.mailer != "ses":
            problems.append("MAILER must be ses")
        if not self.user_pool_id:
            problems.append("USER_POOL_ID is required")
        return problems
