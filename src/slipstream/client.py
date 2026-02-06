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

import logging
import time
from typing import Any, Callable, Dict, List, Optional

from .config import get_http_endpoint, get_ws_endpoint
from .errors import SlipstreamError
from .http_transport import HttpTransport
from .types import (
    Balance,
    ConnectionInfo,
    ConnectionState,
    ConnectionStatus,
    DepositEntry,
    LeaderHint,
    PaginationOptions,
    PendingDeposit,
    PerformanceMetrics,
    PriorityFee,
    RoutingRecommendation,
    SlipstreamConfig,
    SubmitOptions,
    TipInstruction,
    TopUpInfo,
    TransactionResult,
    UsageEntry,
)
from .ws_transport import WebSocketTransport

logger = logging.getLogger("slipstream.client")

Callback = Callable[..., Any]


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
        )
        self._connection_info: Optional[ConnectionInfo] = None
        self._connected = False
        self._latest_tip: Optional[TipInstruction] = None
        self._listeners: Dict[str, List[Callback]] = {}

        # Metrics
        self._tx_submitted = 0
        self._tx_confirmed = 0
        self._total_latency_ms = 0.0
        self._last_latency_ms = 0.0

        # Forward WS events
        self._ws.on("leader_hint", lambda h: self._emit("leader_hint", h))
        self._ws.on("tip_instruction", self._on_tip)
        self._ws.on("priority_fee", lambda f: self._emit("priority_fee", f))
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

        Establishes a WebSocket connection for streaming and prepares
        the HTTP transport for REST API calls.
        """
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

        except Exception:
            # WebSocket failed — fall back to HTTP-only
            logger.debug("WebSocket connection failed, using HTTP-only mode")
            client._connection_info = ConnectionInfo(
                protocol="http",
                region=config.region,
                server_time=int(time.time() * 1000),
            )
            client._connected = True

        return client

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

    # =========================================================================
    # Tip Caching
    # =========================================================================

    def get_latest_tip(self) -> Optional[TipInstruction]:
        """Get the most recently received tip instruction (cached)."""
        return self._latest_tip

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
