"""Settings every service shares. Each service extends this with its own."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class CommonSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "cappy"
    log_level: str = "INFO"

    # memory:// for tests and single-process runs, redis://host:6379/0 in compose.
    event_bus_url: str = "memory://"

    # Where the other services live. The gateway and any service that composes
    # another one reads these; a service never talks to its own URL.
    catalog_url: str = "http://localhost:8001"
    matching_url: str = "http://localhost:8002"
    booking_url: str = "http://localhost:8003"

    # Until real accounts exist the frontend speaks for one seeded owner.
    # Requests may override it with an ``X-Cappy-User`` header.
    demo_user_id: str = "o1"

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Development convenience: any port on localhost, or a private LAN address
    # (a phone on the same Wi-Fi hitting Vite's network URL). Vite moves to
    # 5174 when 5173 is busy, and an exact list then blocks every call with
    # "Disallowed CORS origin". Set to "" in production and list origins instead.
    cors_origin_regex: str = (
        r"^https?://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+"
        r"|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)(:\d+)?$"
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]
