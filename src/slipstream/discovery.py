"""
AllenHarkSlipstream — Service Discovery

Automatically discovers available workers and regions from the
Slipstream discovery endpoint. SDKs call this before connecting
so no manual endpoint configuration is needed.
"""

from __future__ import annotations

import logging
from typing import List, Optional

import aiohttp

from .errors import SlipstreamError
from .types import (
    DiscoveryRegion,
    DiscoveryResponse,
    DiscoveryWorker,
    DiscoveryWorkerPorts,
    WorkerEndpoint,
)

logger = logging.getLogger("slipstream.discovery")

DEFAULT_DISCOVERY_URL = "https://discovery.slipstream.allenhark.com"


async def discover(discovery_url: str) -> DiscoveryResponse:
    """Fetch available workers and regions from the discovery service.

    Args:
        discovery_url: Base URL of the discovery service.

    Returns:
        DiscoveryResponse with regions and workers.
    """
    url = f"{discovery_url}/v1/discovery"
    logger.debug("Fetching worker discovery from %s", url)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise SlipstreamError.connection(
                        f"Discovery failed (HTTP {resp.status}): {body}"
                    )
                data = await resp.json()
    except aiohttp.ClientError as e:
        raise SlipstreamError.connection(f"Discovery request failed: {e}") from e

    regions = [
        DiscoveryRegion(
            id=r.get("id", ""),
            name=r.get("name", ""),
            lat=r.get("lat"),
            lon=r.get("lon"),
        )
        for r in data.get("regions", [])
    ]

    workers = [
        DiscoveryWorker(
            id=w.get("id", ""),
            region=w.get("region", ""),
            ip=w.get("ip", ""),
            ports=DiscoveryWorkerPorts(
                quic=w.get("ports", {}).get("quic", 4433),
                ws=w.get("ports", {}).get("ws", 9000),
                http=w.get("ports", {}).get("http", 9000),
            ),
            healthy=w.get("healthy", False),
            version=w.get("version"),
        )
        for w in data.get("workers", [])
    ]

    logger.info(
        "Discovery complete: %d regions, %d workers, recommended=%s",
        len(regions),
        len(workers),
        data.get("recommended_region"),
    )

    return DiscoveryResponse(
        regions=regions,
        workers=workers,
        recommended_region=data.get("recommended_region"),
    )


def workers_to_endpoints(workers: List[DiscoveryWorker]) -> List[WorkerEndpoint]:
    """Convert discovery workers to SDK WorkerEndpoints. Only healthy workers."""
    return [
        WorkerEndpoint(
            id=w.id,
            region=w.region,
            websocket=f"ws://{w.ip}:{w.ports.ws}/ws",
            http=f"http://{w.ip}:{w.ports.http}",
        )
        for w in workers
        if w.healthy
    ]


def best_region(
    response: DiscoveryResponse, preferred: Optional[str] = None
) -> Optional[str]:
    """Pick the best region from a discovery response.

    Args:
        response: Discovery response.
        preferred: User's preferred region (optional).

    Returns:
        Best region ID, or None if no healthy workers.
    """
    if preferred:
        has_workers = any(
            w.region == preferred and w.healthy for w in response.workers
        )
        if has_workers:
            return preferred
        logger.warning(
            "Preferred region '%s' has no healthy workers, falling back", preferred
        )

    return response.recommended_region


def workers_for_region(
    response: DiscoveryResponse, region: str
) -> List[DiscoveryWorker]:
    """Filter discovery workers by region."""
    return [w for w in response.workers if w.region == region and w.healthy]
