"""The CDN in front of public photos, behind one call (F-4): CloudFront today,
another CDN (Fastly, Cloudflare) is a class here and a setting."""

from __future__ import annotations

import asyncio
import logging
import time

log = logging.getLogger(__name__)


class Cdn:
    """No CDN (local runs, tests): nothing to purge."""

    async def purge(self, paths: list[str]) -> None:
        """Drop these paths from every edge now, not when their cache expires."""


class CloudFrontCdn(Cdn):
    def __init__(self, settings) -> None:  # noqa: ANN001
        self._settings = settings

    async def purge(self, paths: list[str]) -> None:
        from cappy_common.events import aws_client

        if not paths:
            return
        try:
            cf = aws_client("cloudfront", self._settings)
            await asyncio.to_thread(
                cf.create_invalidation,
                DistributionId=self._settings.cdn_distribution_id,
                InvalidationBatch={
                    "Paths": {"Quantity": len(paths), "Items": paths[:3000]},
                    "CallerReference": f"mod-{time.time_ns()}",
                },
            )
        except Exception as e:  # noqa: BLE001 - photos expire from the edge by themselves in the end
            log.warning("could not purge the CDN for %s: %s", paths[:5], e)


def make_cdn(settings) -> Cdn:  # noqa: ANN001
    return CloudFrontCdn(settings) if settings.cdn_distribution_id else Cdn()
