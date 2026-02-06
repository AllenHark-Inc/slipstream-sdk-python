"""
AllenHarkSlipstream — MultiRegionClient

Manages connections to workers across multiple regions and auto-routes
transactions based on leader hints for optimal latency.

Example::

    from slipstream import MultiRegionClient, config_builder
    from slipstream.types import WorkerEndpoint, MultiRegionConfig

    config = config_builder().api_key("sk_test_12345678").build()

    workers = [
        WorkerEndpoint(id="w1", region="us-east", http="https://us-east.example.com"),
        WorkerEndpoint(id="w2", region="eu-central", http="https://eu-central.example.com"),
    ]

    multi = await MultiRegionClient.create(
        config, workers,
        MultiRegionConfig(auto_follow_leader=True),
    )

    result = await multi.submit_transaction(tx_bytes)
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from .client import SlipstreamClient
from .errors import SlipstreamError
from .types import (
    FallbackStrategy,
    LeaderHint,
    MultiRegionConfig,
    RoutingRecommendation,
    SlipstreamConfig,
    SubmitOptions,
    TransactionResult,
    WorkerEndpoint,
)

logger = logging.getLogger("slipstream.multi_region")

Callback = Callable[..., Any]


class MultiRegionClient:
    """Multi-region client with leader-aware transaction routing."""

    def __init__(
        self, config: SlipstreamConfig, multi_config: MultiRegionConfig
    ) -> None:
        self._config = config
        self._multi_config = multi_config
        self._clients: Dict[str, SlipstreamClient] = {}
        self._workers_by_region: Dict[str, List[WorkerEndpoint]] = {}
        self._current_routing: Optional[RoutingRecommendation] = None
        self._last_switch_time = 0.0
        self._listeners: Dict[str, List[Callback]] = {}

    def on(self, event: str, callback: Callback) -> None:
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)

    def _emit(self, event: str, *args: Any) -> None:
        for cb in self._listeners.get(event, []):
            try:
                result = cb(*args)
                if asyncio.iscoroutine(result):
                    asyncio.ensure_future(result)
            except Exception:
                logger.exception("Error in event listener for %s", event)

    @staticmethod
    async def create(
        config: SlipstreamConfig,
        workers: List[WorkerEndpoint],
        multi_config: MultiRegionConfig,
    ) -> MultiRegionClient:
        multi = MultiRegionClient(config, multi_config)

        for worker in workers:
            region_list = multi._workers_by_region.setdefault(worker.region, [])
            region_list.append(worker)

        # Connect to primary region
        primary_region = config.region or (workers[0].region if workers else None)
        if primary_region:
            await multi._ensure_region_connected(primary_region)

        # Auto-follow leader hints
        if multi_config.auto_follow_leader and primary_region:
            client = multi._clients.get(primary_region)
            if client:
                client.on("leader_hint", lambda h: multi._update_routing(h))

        return multi

    # =========================================================================
    # Transaction Submission
    # =========================================================================

    async def submit_transaction(self, transaction: bytes) -> TransactionResult:
        return await self.submit_transaction_with_options(transaction, SubmitOptions())

    async def submit_transaction_with_options(
        self, transaction: bytes, options: SubmitOptions
    ) -> TransactionResult:
        if options.broadcast_mode:
            return await self._broadcast(transaction, options)

        region = (
            self._current_routing.best_region
            if self._current_routing
            else self._default_region()
        )

        try:
            return await self._submit_to_region(region, transaction, options)
        except Exception as first_err:
            fallbacks = (
                self._current_routing.fallback_regions
                if self._current_routing
                else []
            )
            for fb in fallbacks:
                try:
                    return await self._submit_to_region(fb, transaction, options)
                except Exception:
                    continue
            raise first_err

    # =========================================================================
    # Routing
    # =========================================================================

    def get_current_routing(self) -> Optional[RoutingRecommendation]:
        return self._current_routing

    def connected_regions(self) -> List[str]:
        return list(self._clients.keys())

    async def disconnect_all(self) -> None:
        tasks = [c.disconnect() for c in self._clients.values()]
        await asyncio.gather(*tasks, return_exceptions=True)
        self._clients.clear()

    # =========================================================================
    # Internal
    # =========================================================================

    async def _submit_to_region(
        self, region: str, transaction: bytes, options: SubmitOptions
    ) -> TransactionResult:
        await self._ensure_region_connected(region)
        client = self._clients.get(region)
        if not client:
            raise SlipstreamError.connection(f"No client for region: {region}")
        return await client.submit_transaction_with_options(transaction, options)

    async def _broadcast(
        self, transaction: bytes, options: SubmitOptions
    ) -> TransactionResult:
        regions = list(self._workers_by_region.keys())[
            : self._multi_config.max_broadcast_regions
        ]

        results = await asyncio.gather(
            *(self._submit_to_region(r, transaction, options) for r in regions),
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, TransactionResult):
                return result

        for result in results:
            if isinstance(result, Exception):
                raise result

        raise SlipstreamError.transaction("All broadcast regions failed")

    async def _ensure_region_connected(self, region: str) -> None:
        if region in self._clients:
            return

        workers = self._workers_by_region.get(region, [])
        if not workers:
            raise SlipstreamError.config(f"No workers in region: {region}")

        worker = workers[0]
        region_config = SlipstreamConfig(
            api_key=self._config.api_key,
            region=region,
            endpoint=worker.http,
            connection_timeout=self._config.connection_timeout,
            max_retries=self._config.max_retries,
            leader_hints=self._config.leader_hints,
            stream_tip_instructions=self._config.stream_tip_instructions,
            stream_priority_fees=self._config.stream_priority_fees,
            protocol_timeouts=self._config.protocol_timeouts,
            priority_fee=self._config.priority_fee,
            retry_backoff=self._config.retry_backoff,
            min_confidence=self._config.min_confidence,
            idle_timeout=self._config.idle_timeout,
        )

        client = await SlipstreamClient.connect(region_config)
        self._clients[region] = client

        if self._multi_config.auto_follow_leader:
            client.on("leader_hint", lambda h: self._update_routing(h))

    def _update_routing(self, hint: LeaderHint) -> None:
        now = time.time() * 1000
        if now - self._last_switch_time < self._multi_config.switch_cooldown_ms:
            return

        if hint.confidence < self._multi_config.min_switch_confidence:
            return

        self._current_routing = RoutingRecommendation(
            best_region=hint.preferred_region,
            leader_pubkey=hint.leader_pubkey,
            slot=hint.slot,
            confidence=hint.confidence,
            expected_rtt_ms=hint.metadata.tpu_rtt_ms,
            fallback_regions=hint.backup_regions,
            fallback_strategy=FallbackStrategy.SEQUENTIAL,
            valid_for_ms=1000,
        )

        self._last_switch_time = now
        self._emit("routing_update", self._current_routing)

    def _default_region(self) -> str:
        return (
            self._config.region
            or (list(self._clients.keys())[0] if self._clients else "us-east")
        )
