"""Service-to-service HTTP.

One client per upstream. Every call carries the internal token (``/internal/*``
routes require it) and the current request id, so a request is traceable across
services. Idempotent calls (GET) and calls that never reached the server are
retried with jittered backoff; anything else is not, because retrying a POST
that did land would do it twice.
"""

from __future__ import annotations

import asyncio
import random
from typing import Any

import httpx

from .errors import ApiError, Unavailable, Upstream
from .observability import request_id

_RETRYABLE_STATUS = {502, 503, 504}


class ServiceClient:
    def __init__(
        self,
        base_url: str,
        *,
        internal_token: str = "",
        timeout: float = 5.0,
        retries: int = 2,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout, connect=2.0),
            transport=transport,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
        self._token = internal_token
        self._retries = retries

    @property
    def base_url(self) -> str:
        return str(self._client.base_url)

    async def aclose(self) -> None:
        await self._client.aclose()

    def _headers(self, extra: dict | None) -> dict:
        h = {"x-request-id": request_id.get()} if request_id.get() != "-" else {}
        if self._token:
            h["x-internal-token"] = self._token
        if extra:
            h.update(extra)
        return h

    async def request(self, method: str, path: str, *, headers: dict | None = None, **kwargs: Any) -> Any:
        idempotent = method in ("GET", "HEAD")
        attempt = 0
        while True:
            try:
                r = await self._client.request(method, path, headers=self._headers(headers), **kwargs)
            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                # Never reached the server, so a retry cannot duplicate anything.
                if attempt < self._retries:
                    attempt += 1
                    await asyncio.sleep(_backoff(attempt))
                    continue
                raise Unavailable(f"{self.base_url} is unreachable") from e
            except httpx.HTTPError as e:
                raise Upstream(f"{self.base_url}{path}: {type(e).__name__}") from e
            if idempotent and r.status_code in _RETRYABLE_STATUS and attempt < self._retries:
                attempt += 1
                await asyncio.sleep(_backoff(attempt))
                continue
            break
        if r.status_code >= 400:
            # Pass a well-formed upstream error through with its own status, so a
            # 404 from the catalog stays a 404 for the caller.
            try:
                err = r.json()["error"]
                code, message = err["code"], err["message"]
            except (ValueError, KeyError, TypeError):
                raise Upstream(f"{path} returned {r.status_code}") from None
            raise ApiError(message, status=r.status_code, code=code)
        if r.status_code == 204 or not r.content:
            return None
        return r.json()

    async def get(self, path: str, **kwargs: Any) -> Any:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> Any:
        return await self.request("POST", path, **kwargs)

    async def put(self, path: str, **kwargs: Any) -> Any:
        return await self.request("PUT", path, **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> Any:
        return await self.request("DELETE", path, **kwargs)


def _backoff(attempt: int) -> float:
    return min(1.0, 0.1 * 2**attempt) * (0.5 + random.random())
