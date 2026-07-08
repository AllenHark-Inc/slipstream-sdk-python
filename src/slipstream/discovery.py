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

DEFAULT_DISCOVERY_URL = "https://discovery.allenhark.network"


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

    response = parse_discovery_response(data)

    logger.info(
        "Discovery complete: %d regions, %d workers, recommended=%s",
        len(response.regions),
        len(response.workers),
        response.recommended_region,
    )

    return response


def parse_discovery_response(data: dict) -> DiscoveryResponse:
    """Parse a raw discovery JSON payload (as returned by ``GET /v1/discovery``)
    into a :class:`DiscoveryResponse`.

    Pulled out of :func:`discover` so the parsing logic — in particular the
    backward-compatible handling of the optional ``legacy_*`` port fields —
    can be exercised directly against a plain dict, without a network call.
    """
    regions = [
        DiscoveryRegion(
            id=r.get("id", ""),
            name=r.get("name", ""),
            lat=r.get("lat"),
            lon=r.get("lon"),
            leader_rtt_ms=r.get("leader_rtt_ms"),
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
                grpc=w.get("ports", {}).get("grpc", 10000),
                # Legacy ports are only advertised during a port migration.
                # `.get(key, None)` keeps this backward-compatible: an old
                # control plane that omits these keys entirely yields None,
                # not a default port.
                legacy_quic=w.get("ports", {}).get("legacy_quic", None),
                legacy_grpc=w.get("ports", {}).get("legacy_grpc", None),
                legacy_ws=w.get("ports", {}).get("legacy_ws", None),
            ),
            healthy=w.get("healthy", False),
            version=w.get("version"),
        )
        for w in data.get("workers", [])
    ]

    return DiscoveryResponse(
        regions=regions,
        workers=workers,
        recommended_region=data.get("recommended_region"),
    )


def workers_to_endpoints(workers: List[DiscoveryWorker]) -> List[WorkerEndpoint]:
    """Convert discovery workers to SDK WorkerEndpoints. Only healthy workers."""
    endpoints = []
    for w in workers:
        if not w.healthy:
            continue

        # Legacy fallback endpoints — only present during a port migration.
        # Built with the same URL shape as their primary counterparts so the
        # connect path can dial them transparently.
        legacy_quic = (
            f"quic://{w.ip}:{w.ports.legacy_quic}"
            if w.ports.legacy_quic is not None
            else None
        )
        legacy_grpc = (
            f"http://{w.ip}:{w.ports.legacy_grpc}"
            if w.ports.legacy_grpc is not None
            else None
        )
        legacy_websocket = (
            f"ws://{w.ip}:{w.ports.legacy_ws}/ws"
            if w.ports.legacy_ws is not None
            else None
        )

        endpoints.append(
            WorkerEndpoint(
                id=w.id,
                region=w.region,
                websocket=f"ws://{w.ip}:{w.ports.ws}/ws",
                http=f"http://{w.ip}:{w.ports.http}",
                legacy_quic=legacy_quic,
                legacy_grpc=legacy_grpc,
                legacy_websocket=legacy_websocket,
            )
        )
    return endpoints


# Protocols whose worker endpoint carries both a primary and a legacy variant.
_LEGACY_CAPABLE_PROTOCOLS = ("websocket", "http", "quic", "grpc")


def connect_targets(endpoint: WorkerEndpoint, protocol: str) -> List[str]:
    """Build the ordered list of connect targets for a worker endpoint and
    protocol: the primary endpoint first, followed by the legacy endpoint
    (if the worker advertises one and it differs from the primary).

    Returns ``[primary]`` when there is no legacy endpoint (today's
    single-attempt behavior, unchanged for old control planes / workers that
    never had a port migration), or ``[]`` when the worker has no primary
    endpoint for the protocol at all.

    Supported protocols: ``"websocket"``, ``"http"``, ``"quic"``, ``"grpc"``.
    Note ``WorkerEndpoint`` only carries primary endpoints for
    ``"websocket"`` and ``"http"`` today, so ``"quic"``/``"grpc"`` always
    resolve to an empty list (no primary endpoint) even though their legacy
    fields are parsed for forward-compatibility.
    """
    if protocol not in _LEGACY_CAPABLE_PROTOCOLS:
        raise ValueError(f"Unknown protocol: {protocol}")

    if protocol == "websocket":
        primary, legacy = endpoint.websocket, endpoint.legacy_websocket
    elif protocol == "http":
        primary, legacy = endpoint.http, None
    elif protocol == "quic":
        primary, legacy = None, endpoint.legacy_quic
    else:  # grpc
        primary, legacy = None, endpoint.legacy_grpc

    if not primary:
        return []
    if not legacy or legacy == primary:
        return [primary]
    return [primary, legacy]


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
