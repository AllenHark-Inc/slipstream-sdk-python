"""
AllenHarkSlipstream — SlipstreamClient

Main SDK entry point. Connects via WebSocket for streaming and HTTP for REST.

Example::

    from slipstream import SlipstreamClient, config_builder

    config = (
        config_builder()
        .api_key("sk_test_12345678")
        .region("us-east")
        .build()
    )

    client = await SlipstreamClient.connect(config)

    # Subscribe to leader hints
    client.on("leader_hint", lambda hint: print(f"Leader in {hint.preferred_region}"))
    await client.subscribe_leader_hints()

    # Submit a transaction
    result = await client.submit_transaction(tx_bytes)
    print(f"TX: {result.transaction_id}")

    # Check token balance
    balance = await client.get_balance()
    print(f"Balance: {balance.balance_sol} SOL ({balance.balance_tokens} tokens)")
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from .config import get_http_endpoint, get_ws_endpoint
from .discovery import discover, best_region, workers_for_region, workers_to_endpoints
from .errors import SlipstreamError
from .worker_selector import WorkerSelector
from .http_transport import HttpTransport
from .types import (
    Balance,
    ConnectionInfo,
    ConnectionState,
    ConnectionStatus,
    DepositEntry,
    FreeTierUsage,
    LandingRateStats,
    LatestBlockhash,
    LatestSlot,
    LeaderHint,
    PaginationOptions,
    PendingDeposit,
    PerformanceMetrics,
    PingResult,
    PriorityFee,
    RegionInfo,
    RoutingRecommendation,
    SlipstreamConfig,
    SubmitOptions,
    TipInstruction,
    TopUpInfo,
    TransactionResult,
    RpcError,
    RpcResponse,
    SimulationResult,
    UsageEntry,
    WebhookConfig,
)
from .ws_transport import WebSocketTransport

logger = logging.getLogger("slipstream.client")

Callback = Callable[..., Any]


class TimeSyncManager:
    """Tracks ping results for latency and clock synchronization."""

    def __init__(self, max_samples: int = 10) -> None:
        self._samples: List[PingResult] = []
        self._max_samples = max_samples
        self._task: Optional[asyncio.Task[None]] = None

    def record(self, result: PingResult) -> None:
        self._samples.append(result)
        if len(self._samples) > self._max_samples:
            self._samples.pop(0)

    def median_rtt_ms(self) -> Optional[int]:
        if not self._samples:
            return None
        rtts = sorted(s.rtt_ms for s in self._samples)
        return rtts[len(rtts) // 2]

    def median_clock_offset_ms(self) -> Optional[int]:
        if not self._samples:
            return None
        offsets = sorted(s.clock_offset_ms for s in self._samples)
        return offsets[len(offsets) // 2]

    def start(self, ping_fn: Callable[..., Any], interval: float, on_result: Optional[Callable[[PingResult], Any]] = None) -> None:
        self.stop()

        async def loop() -> None:
            while True:
                await asyncio.sleep(interval)
                try:
                    result = await ping_fn()
                    self.record(result)
                    if on_result:
                        on_result(result)
                except Exception:
                    logger.debug("Time sync ping failed", exc_info=True)

        self._task = asyncio.create_task(loop())

    def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None


class SlipstreamClient:
    """Slipstream client for transaction submission and streaming.

    Use :meth:`connect` to create a connected instance::

        client = await SlipstreamClient.connect(config)
    """

    def __init__(self, config: SlipstreamConfig) -> None:
        self._config = config
        self._http = HttpTransport(
            get_http_endpoint(config),
            config.api_key,
            config.protocol_timeouts.http,
        )
        self._ws = WebSocketTransport(
            get_ws_endpoint(config),
            config.api_key,
            config.region,
            config.tier.value if hasattr(config.tier, 'value') else str(config.tier),
        )
        self._connection_info: Optional[ConnectionInfo] = None
        self._connected = False
        self._latest_tip: Optional[TipInstruction] = None
        self._listeners: Dict[str, List[Callback]] = {}
        self._time_sync = TimeSyncManager(10)

        # Metrics
        self._tx_submitted = 0
        self._tx_confirmed = 0
        self._total_latency_ms = 0.0
        self._last_latency_ms = 0.0

        # Forward WS events
        self._ws.on("leader_hint", lambda h: self._emit("leader_hint", h))
        self._ws.on("tip_instruction", self._on_tip)
        self._ws.on("priority_fee", lambda f: self._emit("priority_fee", f))
        self._ws.on("latest_blockhash", lambda b: self._emit("latest_blockhash", b))
        self._ws.on("latest_slot", lambda s: self._emit("latest_slot", s))
        self._ws.on("transaction_update", lambda r: self._emit("transaction_update", r))
        self._ws.on("connected", lambda *_: self._set_connected(True))
        self._ws.on("disconnected", lambda *_: self._set_connected(False))
        self._ws.on("error", lambda e: self._emit("error", e))

    def _on_tip(self, tip: TipInstruction) -> None:
        self._latest_tip = tip
        self._emit("tip_instruction", tip)

    def _set_connected(self, val: bool) -> None:
        self._connected = val
        self._emit("connected" if val else "disconnected")

    # =========================================================================
    # Event emitter
    # =========================================================================

    def on(self, event: str, callback: Callback) -> None:
        """Register an event listener.

        Events: ``leader_hint``, ``tip_instruction``, ``priority_fee``,
        ``latest_blockhash``, ``latest_slot``,
        ``transaction_update``, ``connected``, ``disconnected``, ``error``
        """
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)

    def off(self, event: str, callback: Callback) -> None:
        """Remove an event listener."""
        if event in self._listeners:
            self._listeners[event] = [
                cb for cb in self._listeners[event] if cb is not callback
            ]

    def _emit(self, event: str, *args: Any) -> None:
        import asyncio

        for cb in self._listeners.get(event, []):
            try:
                result = cb(*args)
                if asyncio.iscoroutine(result):
                    asyncio.ensure_future(result)
            except Exception:
                logger.exception("Error in event listener for %s", event)

    # =========================================================================
    # Connection
    # =========================================================================

    @staticmethod
    async def connect(config: SlipstreamConfig) -> SlipstreamClient:
        """Connect to Slipstream.

        If no explicit endpoint is set, the SDK automatically discovers
        available workers via the discovery service, selects the best
        worker by latency, and connects directly to its IP address.
        Falls through to the next-best worker if connection fails.
        """
        # If no explicit endpoint, use discovery to find a worker
        if not config.endpoint:
            response = await discover(config.discovery_url)
            region = best_region(response, config.region)
            if not region:
                raise SlipstreamError.connection(
                    "No healthy workers found via discovery"
                )

            workers = workers_for_region(response, region)
            if not workers:
                raise SlipstreamError.connection(
                    f"No healthy workers in region '{region}'"
                )

            # Convert to endpoints and rank by latency
            endpoints = workers_to_endpoints(workers)
            selector = WorkerSelector(endpoints)
            rtts = await selector.measure_all()

            # Sort by RTT (lowest first), unreachable at end
            ranked = sorted(
                endpoints,
                key=lambda w: rtts.get(w.id, float("inf")),
            )

            logger.info(
                "Ranked %d workers by latency in region %s (best: %s)",
                len(ranked), region, ranked[0].id,
            )

            # Try workers in latency order — fall to next on complete failure
            last_error: Optional[Exception] = None
            for i, worker in enumerate(ranked):
                logger.info(
                    "Trying worker %s (%d/%d)", worker.id, i + 1, len(ranked)
                )
                worker_config = SlipstreamConfig(
                    api_key=config.api_key,
                    region=region,
                    endpoint=worker.http,
                    ws_endpoint=worker.websocket,
                    discovery_url=config.discovery_url,
                    tier=config.tier,
                    connection_timeout=config.connection_timeout,
                    max_retries=config.max_retries,
                    leader_hints=config.leader_hints,
                    stream_tip_instructions=config.stream_tip_instructions,
                    stream_priority_fees=config.stream_priority_fees,
                    stream_latest_blockhash=config.stream_latest_blockhash,
                    stream_latest_slot=config.stream_latest_slot,
                    protocol_timeouts=config.protocol_timeouts,
                    priority_fee=config.priority_fee,
                    retry_backoff=config.retry_backoff,
                    min_confidence=config.min_confidence,
                    idle_timeout=config.idle_timeout,
                    webhook_url=config.webhook_url,
                    webhook_events=config.webhook_events,
                    webhook_notification_level=config.webhook_notification_level,
                )
                try:
                    return await SlipstreamClient._try_connect(worker_config)
                except Exception as e:
                    logger.warning(
                        "Worker %s connection failed: %s, trying next", worker.id, e
                    )
                    last_error = e

            raise last_error or SlipstreamError.connection(
                f"All workers in region '{region}' rejected connection"
            )

        # Explicit endpoint set — connect directly
        return await SlipstreamClient._try_connect(config)

    @staticmethod
    async def _try_connect(config: SlipstreamConfig) -> SlipstreamClient:
        """Attempt connection to a single worker endpoint using WS → HTTP fallback."""
        client = SlipstreamClient(config)

        try:
            conn_info = await client._ws.connect()
            client._connection_info = conn_info
            client._connected = True

            if config.leader_hints:
                await client._ws.subscribe_leader_hints()
            if config.stream_tip_instructions:
                await client._ws.subscribe_tip_instructions()
            if config.stream_priority_fees:
                await client._ws.subscribe_priority_fees()
            if config.stream_latest_blockhash:
                await client._ws.subscribe_latest_blockhash()
            if config.stream_latest_slot:
                await client._ws.subscribe_latest_slot()

        except Exception:
            # WebSocket failed — fall back to HTTP-only
            logger.debug("WebSocket connection failed, using HTTP-only mode")
            client._connection_info = ConnectionInfo(
                protocol="http",
                region=config.region,
                server_time=int(time.time() * 1000),
            )
            client._connected = True

        # Auto-register webhook and fetch initial tip concurrently
        tasks = [client._fetch_initial_tip()]
        if config.webhook_url:
            tasks.append(client._auto_register_webhook())
        await asyncio.gather(*tasks, return_exceptions=True)

        return client

    async def _auto_register_webhook(self) -> None:
        try:
            await self.register_webhook(
                self._config.webhook_url,
                self._config.webhook_events,
                self._config.webhook_notification_level,
            )
            logger.info("Webhook auto-registered at %s", self._config.webhook_url)
        except Exception:
            logger.debug("Failed to auto-register webhook", exc_info=True)

    async def _fetch_initial_tip(self) -> None:
        """Eagerly fetch tip instructions so get_latest_tip() works after connect()."""
        try:
            tips = await self._http.get_tip_instructions()
            if tips:
                self._latest_tip = tips[-1]
        except Exception:
            pass  # Non-fatal — tip will be populated by streaming later

    def connection_info(self) -> ConnectionInfo:
        if not self._connection_info:
            raise SlipstreamError.not_connected()
        return self._connection_info

    def config(self) -> SlipstreamConfig:
        return self._config

    def is_connected(self) -> bool:
        return self._connected

    async def disconnect(self) -> None:
        """Disconnect from the server."""
        await self._ws.disconnect()
        await self._http.close()
        self._connected = False

    # =========================================================================
    # Transaction Submission
    # =========================================================================

    async def submit_transaction(self, transaction: bytes) -> TransactionResult:
        """Submit a signed transaction."""
        return await self.submit_transaction_with_options(transaction, SubmitOptions())

    async def submit_transaction_with_options(
        self, transaction: bytes, options: SubmitOptions
    ) -> TransactionResult:
        """Submit a transaction with custom options."""
        start = time.time()

        try:
            if self._ws.is_connected():
                result = await self._ws.submit_transaction(transaction, options)
            else:
                result = await self._http.submit_transaction(transaction, options)
        except Exception:
            self._tx_submitted += 1
            raise

        elapsed = (time.time() - start) * 1000
        self._last_latency_ms = elapsed
        self._tx_submitted += 1
        self._total_latency_ms += elapsed

        if result.status in ("confirmed", "sent"):
            self._tx_confirmed += 1

        return result

    # =========================================================================
    # Streaming Subscriptions
    # =========================================================================

    async def subscribe_leader_hints(self) -> None:
        """Subscribe to leader hint updates.

        Listen via ``client.on("leader_hint", callback)``.
        """
        await self._ws.subscribe_leader_hints()

    async def subscribe_tip_instructions(self) -> None:
        """Subscribe to tip instruction updates.

        Listen via ``client.on("tip_instruction", callback)``.
        """
        await self._ws.subscribe_tip_instructions()

    async def subscribe_priority_fees(self) -> None:
        """Subscribe to priority fee updates.

        Listen via ``client.on("priority_fee", callback)``.
        """
        await self._ws.subscribe_priority_fees()

    async def subscribe_latest_blockhash(self) -> None:
        """Subscribe to latest blockhash updates.

        Listen via ``client.on("latest_blockhash", callback)``.
        """
        await self._ws.subscribe_latest_blockhash()

    async def subscribe_latest_slot(self) -> None:
        """Subscribe to latest slot updates.

        Listen via ``client.on("latest_slot", callback)``.
        """
        await self._ws.subscribe_latest_slot()

    # =========================================================================
    # Tip Caching
    # =========================================================================

    def get_latest_tip(self) -> Optional[TipInstruction]:
        """Get the most recently received tip instruction (cached)."""
        return self._latest_tip

    # =========================================================================
    # Ping / Time Sync
    # =========================================================================

    async def ping(self) -> PingResult:
        """Send a ping and measure round-trip time and clock offset.

        Uses WebSocket if connected, otherwise raises.
        """
        if self._ws.is_connected():
            return await self._ws.ping()
        raise SlipstreamError.not_connected()

    # =========================================================================
    # Connection Status
    # =========================================================================

    def connection_status(self) -> ConnectionStatus:
        return ConnectionStatus(
            state=(
                ConnectionState.CONNECTED
                if self._connected
                else ConnectionState.DISCONNECTED
            ),
            protocol=self._connection_info.protocol if self._connection_info else "http",
            latency_ms=int(self._last_latency_ms),
            region=self._connection_info.region if self._connection_info else None,
        )

    # =========================================================================
    # Multi-Region Routing
    # =========================================================================

    async def get_routing_recommendation(self) -> RoutingRecommendation:
        return await self._http.get_routing_recommendation()

    async def get_regions(self) -> "List[RegionInfo]":
        """Get all configured regions.

        Returns a list of regions with their IDs, display names, endpoints,
        and geolocation coordinates. This endpoint does not require authentication.
        """
        return await self._http.get_regions()

    # =========================================================================
    # Token Billing
    # =========================================================================

    async def get_balance(self) -> Balance:
        return await self._http.get_balance()

    async def get_deposit_address(self) -> TopUpInfo:
        return await self._http.get_deposit_address()

    async def get_usage_history(
        self, options: Optional[PaginationOptions] = None
    ) -> List[UsageEntry]:
        return await self._http.get_usage_history(options)

    async def get_deposit_history(
        self, options: Optional[PaginationOptions] = None
    ) -> List[DepositEntry]:
        return await self._http.get_deposit_history(options)

    async def get_pending_deposit(self) -> PendingDeposit:
        return await self._http.get_pending_deposit()

    async def get_free_tier_usage(self) -> FreeTierUsage:
        """Get free tier daily usage statistics.

        Returns the number of transactions used today, remaining quota,
        and when the counter resets (UTC midnight).
        Only meaningful for keys on the 'free' tier.
        """
        return await self._http.get_free_tier_usage()

    @staticmethod
    def get_minimum_deposit_usd() -> float:
        """Minimum deposit in USD before tokens are credited ($10)."""
        return 10.0

    # =========================================================================
    # Metrics
    # =========================================================================

    def metrics(self) -> PerformanceMetrics:
        return PerformanceMetrics(
            transactions_submitted=self._tx_submitted,
            transactions_confirmed=self._tx_confirmed,
            average_latency_ms=(
                self._total_latency_ms / self._tx_submitted
                if self._tx_submitted > 0
                else 0.0
            ),
            success_rate=(
                self._tx_confirmed / self._tx_submitted
                if self._tx_submitted > 0
                else 0.0
            ),
        )

    # =========================================================================
    # Webhooks
    # =========================================================================

    async def register_webhook(
        self,
        url: str,
        events: Optional[list] = None,
        notification_level: Optional[str] = None,
    ) -> WebhookConfig:
        """Register or update a webhook for this API key.

        Returns the webhook configuration including the secret
        (only visible on register/update).
        """
        return await self._http.register_webhook(url, events, notification_level)

    async def get_webhook(self) -> Optional[WebhookConfig]:
        """Get current webhook configuration for this API key.

        Returns the webhook config with the secret masked, or None if none configured.
        """
        return await self._http.get_webhook()

    async def delete_webhook(self) -> None:
        """Delete (disable) the webhook for this API key."""
        await self._http.delete_webhook()

    # =========================================================================
    # Landing Rates
    # =========================================================================

    async def get_landing_rates(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> "LandingRateStats":
        """Get transaction landing rate statistics for this API key.

        Returns overall landing rate plus per-sender and per-region breakdowns.
        Defaults to the last 24 hours if no time range is specified.
        """
        return await self._http.get_landing_rates(start=start, end=end)

    # =========================================================================
    # Bundle Submission
    # =========================================================================

    async def submit_bundle(
        self,
        transactions: "List[bytes]",
        tip_lamports: "Optional[int]" = None,
    ) -> "BundleResult":
        """Submit a bundle of transactions for atomic execution.

        Bundles contain 2-5 transactions that are executed atomically — either
        all succeed or none. The sender must support bundle submission.

        Args:
            transactions: 2 to 5 signed transactions (raw bytes).
            tip_lamports: Optional tip amount in lamports.

        Returns:
            Bundle result with bundle ID, acceptance status, and signatures.

        Billing:
            5 tokens (0.00025 SOL) per bundle regardless of transaction count.
        """
        if len(transactions) < 2 or len(transactions) > 5:
            raise ValueError("Bundle must contain 2-5 transactions")
        return await self._http.submit_bundle(transactions, tip_lamports)

    # === Solana RPC Proxy ===

    async def rpc(
        self,
        method: str,
        params: "Optional[list]" = None,
    ) -> "RpcResponse":
        """Execute a Solana JSON-RPC call via the Slipstream proxy.

        Costs 1 token (0.00005 SOL) per call. Only methods from the
        allowlist are supported (simulateTransaction, getTransaction, etc.).

        Args:
            method: JSON-RPC method name (e.g. "getLatestBlockhash").
            params: RPC parameters array.

        Returns:
            Raw JSON-RPC 2.0 response.
        """
        return await self._http.rpc(method, params or [])

    async def simulate_transaction(self, transaction: bytes) -> "SimulationResult":
        """Simulate a transaction without submitting it to the network.

        Costs 1 token. Returns simulation result with logs and compute units.

        Args:
            transaction: Signed transaction bytes.

        Returns:
            SimulationResult with err, logs, units_consumed, return_data.
        """
        import base64
        tx_b64 = base64.b64encode(transaction).decode("ascii")
        response = await self.rpc("simulateTransaction", [
            tx_b64,
            {"encoding": "base64", "commitment": "confirmed", "replaceRecentBlockhash": True},
        ])
        if response.error:
            raise Exception(f"RPC error {response.error.code}: {response.error.message}")
        result = response.result
        value = result.get("value", result) if isinstance(result, dict) else result
        if isinstance(value, dict):
            return SimulationResult(
                err=value.get("err"),
                logs=value.get("logs", []),
                units_consumed=value.get("unitsConsumed", 0),
                return_data=value.get("returnData"),
            )
        return SimulationResult()

    async def simulate_bundle(
        self,
        transactions: "List[bytes]",
    ) -> "List[SimulationResult]":
        """Simulate each transaction in a bundle sequentially.

        Costs 1 token per transaction simulated. Stops on first failure.

        Args:
            transactions: List of signed transaction bytes.

        Returns:
            List of SimulationResult (one per transaction attempted).
        """
        results: list = []
        for tx in transactions:
            sim = await self.simulate_transaction(tx)
            results.append(sim)
            if sim.err is not None:
                break
        return results
