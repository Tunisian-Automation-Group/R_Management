from __future__ import annotations

from cappy_common.settings import CommonSettings


class Settings(CommonSettings):
    service_name: str = "gateway"
    upstream_timeout_seconds: float = 15.0
    # How long a checked session token is trusted before the accounts service
    # is asked again. Signing out through the gateway drops it at once.
    session_cache_seconds: float = 60.0
    # A built copy of the web app (``cappy/cappy/dist``). When set and it holds
    # an index.html, the gateway serves it at ``/`` with a single-page fallback,
    # so the website, the installed PWA and the API share one origin and the
    # browser never needs CORS. Empty: the gateway is API-only and the app is
    # hosted elsewhere (a CDN, or a native shell) and calls ``/api`` cross-origin.
    static_dir: str = ""
