"""What accounts needs from the catalog: an owner record for each new person."""

from __future__ import annotations

from cappy_common.http import ServiceClient
from cappy_common.models import Owner


class CatalogClient:
    async def create_owner(self, owner: Owner) -> Owner:
        raise NotImplementedError

    async def owner_exists(self, owner_id: str) -> bool:
        raise NotImplementedError

    async def aclose(self) -> None:
        """Release resources."""


class HttpCatalogClient(CatalogClient):
    def __init__(self, base_url: str) -> None:
        self._client = ServiceClient(base_url)

    async def create_owner(self, owner: Owner) -> Owner:
        data = await self._client.post("/internal/owners", json=owner.model_dump(mode="json", by_alias=True))
        return Owner.model_validate(data)

    async def owner_exists(self, owner_id: str) -> bool:
        from cappy_common.errors import ApiError

        try:
            await self._client.get(f"/owners/{owner_id}")
            return True
        except ApiError as e:
            if e.status == 404:
                return False
            raise

    async def aclose(self) -> None:
        await self._client.aclose()
