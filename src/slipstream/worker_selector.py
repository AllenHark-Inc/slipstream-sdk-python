"""
AllenHarkSlipstream — Worker Selector

Pings available workers and selects the lowest-latency endpoint.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import aiohttp

from .errors import SlipstreamError
from .types import WorkerEndpoint


@dataclass
class LatencyMeasurement:
    rtt_ms: float
    measured_at: float
    reachable: bool


class WorkerSelector:
    """Ping-based worker selection for lowest latency."""

    def __init__(
        self,
        workers: List[WorkerEndpoint],
        cache_ttl_ms: int = 30_000,
        ping_timeout_ms: int = 5_000,
    ) -> None:
        self._workers = workers
        self._latencies: Dict[str, LatencyMeasurement] = {}
        self._cache_ttl_ms = cache_ttl_ms
        self._ping_timeout_ms = ping_timeout_ms

    @property
    def worker_count(self) -> int:
        return len(self._workers)

    @property
    def workers(self) -> List[WorkerEndpoint]:
        return list(self._workers)

    async def select_best(self) -> WorkerEndpoint:
        if not self._workers:
            raise SlipstreamError.config("No workers available")

        if len(self._workers) == 1:
            return self._workers[0]

        await self._ensure_measurements()

        best: Optional[WorkerEndpoint] = None
        best_rtt = float("inf")

        for worker in self._workers:
            m = self._latencies.get(worker.id)
            if m and m.reachable and m.rtt_ms < best_rtt:
                best_rtt = m.rtt_ms
                best = worker

        return best or self._workers[0]

    async def select_best_in_region(self, region: str) -> WorkerEndpoint:
        region_workers = [w for w in self._workers if w.region == region]

        if not region_workers:
            raise SlipstreamError.config(f"No workers available in region: {region}")

        if len(region_workers) == 1:
            return region_workers[0]

        await self._ensure_measurements()

        best: Optional[WorkerEndpoint] = None
        best_rtt = float("inf")

        for worker in region_workers:
            m = self._latencies.get(worker.id)
            if m and m.reachable and m.rtt_ms < best_rtt:
                best_rtt = m.rtt_ms
                best = worker

        return best or region_workers[0]

    async def measure_all(self) -> Dict[str, float]:
        results: Dict[str, float] = {}

        async def measure_one(worker: WorkerEndpoint) -> None:
            m = await self._ping_worker(worker)
            self._latencies[worker.id] = m
            if m.reachable:
                results[worker.id] = m.rtt_ms

        await asyncio.gather(
            *(measure_one(w) for w in self._workers),
            return_exceptions=True,
        )
        return results

    def get_latency(self, worker_id: str) -> Optional[float]:
        m = self._latencies.get(worker_id)
        return m.rtt_ms if m and m.reachable else None

    async def _ensure_measurements(self) -> None:
        now = time.time() * 1000
        needs = any(
            worker.id not in self._latencies
            or (now - self._latencies[worker.id].measured_at * 1000) > self._cache_ttl_ms
            for worker in self._workers
        )
        if needs:
            await self.measure_all()

    async def _ping_worker(self, worker: WorkerEndpoint) -> LatencyMeasurement:
        endpoint = worker.http
        if not endpoint:
            return LatencyMeasurement(
                rtt_ms=float("inf"), measured_at=time.time(), reachable=False
            )

        timeout = aiohttp.ClientTimeout(total=self._ping_timeout_ms / 1000)
        start = time.time()

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.head(f"{endpoint}/management/health"):
                    rtt = (time.time() - start) * 1000
                    return LatencyMeasurement(
                        rtt_ms=rtt, measured_at=time.time(), reachable=True
                    )
        except Exception:
            return LatencyMeasurement(
                rtt_ms=float("inf"), measured_at=time.time(), reachable=False
            )
