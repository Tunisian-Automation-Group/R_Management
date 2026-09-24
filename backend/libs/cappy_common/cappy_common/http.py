"""Service-to-service HTTP. Thin: one client per upstream, errors mapped to ``Upstream``."""

from __future__ import annotations

from typing import Any

import httpx

from .errors import ApiError, Upstream


class ServiceClient:
    def __init__(
        self, base_url: str, *, timeout: float = 10.0, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout, transport=transport)

    @property
    def base_url(self) -> str:
        return str(self._client.base_url)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            r = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as e:
            raise Upstream(f"{self.base_url}{path}: {e}") from e
        if r.status_code >= 400:
            # Pass a well-formed upstream error through with its own status so a
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

    async def delete(self, path: str, **kwargs: Any) -> Any:
        return await self.request("DELETE", path, **kwargs)
