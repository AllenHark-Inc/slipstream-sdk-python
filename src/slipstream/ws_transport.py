"""
AllenHarkSlipstream — WebSocket Streaming Transport

Handles real-time streaming subscriptions with auto-reconnect.
Uses aiohttp WebSocket client.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Set

import aiohttp

from .errors import SlipstreamError
from .types import (
    AlternativeSender,
    ConnectionInfo,
    LatestBlockhash,
    LatestSlot,
    LeaderHint,
    LeaderHintMetadata,
    PingResult,
    PriorityFee,
    RateLimitInfo,
    RoutingInfo,
    SubmitOptions,
    TipInstruction,
    TransactionError,
    TransactionResult,
)

logger = logging.getLogger("slipstream.ws")

VERSION = "0.1.0"

# Callback type alias
Callback = Callable[..., Any]


class WebSocketTransport:
    """WebSocket transport with auto-reconnect and streaming subscriptions."""

    def __init__(
        self,
        url: str,
        api_key: str,
        region: Optional[str] = None,
        tier: str = "pro",
        keep_alive_interval: float = 5.0,
    ) -> None:
        self._url = url
        self._api_key = api_key
        self._region = region
        self._tier = tier
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._connected = False
        self._should_reconnect = True
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10
        self._subscribed_streams: Set[str] = set()
        self._request_id_counter = 0
        self._pending_requests: Dict[str, asyncio.Future[TransactionResult]] = {}
        self._listeners: Dict[str, List[Callback]] = {}
        self._recv_task: Optional[asyncio.Task[None]] = None
        self._heartbeat_task: Optional[asyncio.Task[None]] = None
        self._ping_seq: int = 0
        self._pending_ping: Optional[asyncio.Future[PingResult]] = None
        self._keep_alive_interval: float = keep_alive_interval

    def on(self, event: str, callback: Callback) -> None:
        """Register an event listener."""
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
        for cb in self._listeners.get(event, []):
            try:
                result = cb(*args)
                if asyncio.iscoroutine(result):
                    asyncio.ensure_future(result)
            except Exception:
                logger.exception("Error in event listener for %s", event)

    async def connect(self) -> ConnectionInfo:
        """Connect to the WebSocket server."""
        self._session = aiohttp.ClientSession()

        try:
            self._ws = await self._session.ws_connect(self._url)
        except Exception as e:
            await self._session.close()
            raise SlipstreamError.connection(
                f"WebSocket connection failed: {e}"
            ) from e

        # Send connect message
        await self._send(
            {
                "type": "connect",
                "version": VERSION,
                "apiKey": self._api_key,
                "features": ["leader_hints", "tip_instructions", "priority_fees"],
                "region": self._region,
                "tier": self._tier,
            }
        )

        # Wait for connected response
        try:
            msg = await asyncio.wait_for(self._ws.receive(), timeout=10)
        except asyncio.TimeoutError:
            await self._cleanup()
            raise SlipstreamError.timeout(10_000)

        if msg.type != aiohttp.WSMsgType.TEXT:
            await self._cleanup()
            raise SlipstreamError.connection("Unexpected WebSocket message type")

        data = json.loads(msg.data)
        if data.get("type") != "connected":
            await self._cleanup()
            raise SlipstreamError.connection(
                f"Expected 'connected', got '{data.get('type')}'"
            )

        self._connected = True
        self._reconnect_attempts = 0

        info = ConnectionInfo(
            session_id=data.get("session_id", ""),
            protocol="websocket",
            region=data.get("region"),
            server_time=data.get("server_time", 0),
            features=data.get("features", []),
            rate_limit=RateLimitInfo(
                rps=data.get("rate_limit", {}).get("rps", 100),
                burst=data.get("rate_limit", {}).get("burst", 200),
            ),
        )

        # Start receive loop and heartbeat
        self._recv_task = asyncio.create_task(self._receive_loop())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        # Re-subscribe on reconnect
        for stream in self._subscribed_streams:
            await self._send({"type": "subscribe", "stream": stream})

        self._emit("connected", info)
        return info

    async def disconnect(self) -> None:
        """Disconnect from the WebSocket server."""
        self._should_reconnect = False
        await self._cleanup()

    def is_connected(self) -> bool:
        return self._connected

    # =========================================================================
    # Subscriptions
    # =========================================================================

    async def subscribe_leader_hints(self) -> None:
        self._subscribed_streams.add("leader_hints")
        if self._connected:
            await self._send({"type": "subscribe", "stream": "leader_hints"})

    async def subscribe_tip_instructions(self) -> None:
        self._subscribed_streams.add("tip_instructions")
        if self._connected:
            await self._send({"type": "subscribe", "stream": "tip_instructions"})

    async def subscribe_priority_fees(self) -> None:
        self._subscribed_streams.add("priority_fees")
        if self._connected:
            await self._send({"type": "subscribe", "stream": "priority_fees"})

    async def subscribe_latest_blockhash(self) -> None:
        self._subscribed_streams.add("latest_blockhash")
        if self._connected:
            await self._send({"type": "subscribe", "stream": "latest_blockhash"})

    async def subscribe_latest_slot(self) -> None:
        self._subscribed_streams.add("latest_slot")
        if self._connected:
            await self._send({"type": "subscribe", "stream": "latest_slot"})

    async def unsubscribe(self, stream: str) -> None:
        self._subscribed_streams.discard(stream)
        if self._connected:
            await self._send({"type": "unsubscribe", "stream": stream})

    # =========================================================================
    # Ping / Keep-Alive
    # =========================================================================

    async def ping(self) -> PingResult:
        """Send a ping and measure RTT + clock offset."""
        if not self._connected:
            raise SlipstreamError.connection("Not connected")

        seq = self._ping_seq
        self._ping_seq += 1
        client_send_time = int(time.time() * 1000)

        loop = asyncio.get_event_loop()
        future: asyncio.Future[PingResult] = loop.create_future()
        self._pending_ping = future

        await self._send({"type": "ping", "seq": seq, "client_time": client_send_time})

        try:
            result = await asyncio.wait_for(future, timeout=5.0)
            return result
        except asyncio.TimeoutError:
            self._pending_ping = None
            raise SlipstreamError.connection("Ping timeout")

    # =========================================================================
    # Transaction Submission
    # =========================================================================

    async def submit_transaction(
        self, transaction: bytes, options: Optional[SubmitOptions] = None
    ) -> TransactionResult:
        if not self._connected:
            raise SlipstreamError.not_connected()

        import base64

        opts = options or SubmitOptions()
        self._request_id_counter += 1
        request_id = f"req_{self._request_id_counter}_{int(time.time() * 1000)}"

        base64_tx = base64.b64encode(transaction).decode("ascii")

        loop = asyncio.get_event_loop()
        future: asyncio.Future[TransactionResult] = loop.create_future()
        self._pending_requests[request_id] = future

        await self._send(
            {
                "type": "submit_transaction",
                "requestId": request_id,
                "transaction": base64_tx,
                "dedupId": opts.dedup_id,
                "options": {
                    "broadcastMode": opts.broadcast_mode,
                    "preferredSender": opts.preferred_sender,
                    "maxRetries": opts.max_retries,
                    "timeoutMs": opts.timeout_ms,
                },
            }
        )

        try:
            return await asyncio.wait_for(future, timeout=opts.timeout_ms / 1000)
        except asyncio.TimeoutError:
            self._pending_requests.pop(request_id, None)
            raise SlipstreamError.timeout(opts.timeout_ms)

    # =========================================================================
    # Internal
    # =========================================================================

    async def _send(self, msg: Dict[str, Any]) -> None:
        if self._ws and not self._ws.closed:
            await self._ws.send_json(msg)

    async def _receive_loop(self) -> None:
        if not self._ws:
            return

        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        self._handle_message(data)
                    except json.JSONDecodeError:
                        logger.warning("Received malformed JSON message from WebSocket")
                elif msg.type in (
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.ERROR,
                ):
                    break
        except Exception:
            logger.exception("WebSocket receive error")
        finally:
            self._connected = False
            self._emit("disconnected")

            # Reject pending requests
            for req_id, future in list(self._pending_requests.items()):
                if not future.done():
                    future.set_exception(
                        SlipstreamError.connection("WebSocket closed")
                    )
            self._pending_requests.clear()

            if self._should_reconnect:
                asyncio.create_task(self._schedule_reconnect())

    async def _heartbeat_loop(self) -> None:
        """Background loop for keep-alive pings."""
        while self._connected:
            await asyncio.sleep(self._keep_alive_interval)
            if self._connected:
                try:
                    await self.ping()
                except Exception:
                    logger.debug("Heartbeat ping failed", exc_info=True)

    def _handle_message(self, msg: Dict[str, Any]) -> None:
        msg_type = msg.get("type", "")

        if msg_type == "leader_hint":
            self._emit("leader_hint", _parse_leader_hint(msg))

        elif msg_type == "tip_instruction":
            self._emit("tip_instruction", _parse_tip_instruction(msg))

        elif msg_type == "priority_fee":
            self._emit("priority_fee", _parse_priority_fee(msg))

        elif msg_type == "latest_blockhash":
            self._emit("latest_blockhash", _parse_latest_blockhash(msg))

        elif msg_type == "latest_slot":
            self._emit("latest_slot", _parse_latest_slot(msg))

        elif msg_type in (
            "transaction_accepted",
            "transaction_update",
            "transaction_confirmed",
            "transaction_failed",
        ):
            result = _parse_transaction_result_ws(msg)
            request_id = msg.get("request_id", "")

            future = self._pending_requests.pop(request_id, None)
            if future and not future.done():
                if msg_type == "transaction_failed":
                    error_msg = (msg.get("error") or {}).get(
                        "message", "Transaction failed"
                    )
                    future.set_exception(SlipstreamError.transaction(error_msg))
                else:
                    future.set_result(result)

            self._emit("transaction_update", result)

        elif msg_type == "pong":
            if self._pending_ping and not self._pending_ping.done():
                now = int(time.time() * 1000)
                server_time = msg.get("server_time", now)
                client_time = msg.get("client_time", now)
                rtt_ms = now - client_time
                clock_offset_ms = server_time - (client_time + rtt_ms // 2)
                self._pending_ping.set_result(PingResult(
                    seq=msg.get("seq", 0),
                    rtt_ms=rtt_ms,
                    clock_offset_ms=clock_offset_ms,
                    server_time=server_time,
                ))
                self._pending_ping = None

        elif msg_type == "heartbeat":
            asyncio.ensure_future(
                self._send({"type": "pong", "timestamp": int(time.time() * 1000)})
            )

        elif msg_type == "error":
            self._emit(
                "error", SlipstreamError.protocol(msg.get("message", "Unknown error"))
            )

    async def _schedule_reconnect(self) -> None:
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            return

        delay = min(2**self._reconnect_attempts, 30)
        self._reconnect_attempts += 1

        await asyncio.sleep(delay)
        try:
            await self.connect()
        except Exception:
            logger.debug("Reconnect attempt %d failed", self._reconnect_attempts)

    async def _cleanup(self) -> None:
        self._connected = False

        if self._recv_task and not self._recv_task.done():
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass

        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        if self._ws and not self._ws.closed:
            await self._ws.close()

        if self._session and not self._session.closed:
            await self._session.close()


# =============================================================================
# Parsers
# =============================================================================


def _parse_leader_hint(msg: Dict[str, Any]) -> LeaderHint:
    metadata = msg.get("metadata") or {}
    return LeaderHint(
        timestamp=msg.get("timestamp", 0),
        slot=msg.get("slot", 0),
        expires_at_slot=msg.get("expires_at_slot", 0),
        preferred_region=msg.get("preferred_region", ""),
        backup_regions=msg.get("backup_regions", []),
        confidence=msg.get("confidence", 0),
        leader_pubkey=msg.get("leader_pubkey", ""),
        metadata=LeaderHintMetadata(
            tpu_rtt_ms=metadata.get("tpu_rtt_ms", 0),
            region_score=metadata.get("region_score", 0.0),
            leader_tpu_address=metadata.get("leader_tpu_address"),
            region_rtt_ms=metadata.get("region_rtt_ms"),
        ),
    )


def _parse_tip_instruction(msg: Dict[str, Any]) -> TipInstruction:
    alts = msg.get("alternative_senders", [])
    return TipInstruction(
        timestamp=msg.get("timestamp", 0),
        sender=msg.get("sender", ""),
        sender_name=msg.get("sender_name", ""),
        tip_wallet_address=msg.get("tip_wallet_address", ""),
        tip_amount_sol=msg.get("tip_amount_sol", 0.0),
        tip_tier=msg.get("tip_tier", ""),
        expected_latency_ms=msg.get("expected_latency_ms", 0),
        confidence=msg.get("confidence", 0),
        valid_until_slot=msg.get("valid_until_slot", 0),
        alternative_senders=[
            AlternativeSender(
                sender=a.get("sender", ""),
                tip_amount_sol=a.get("tip_amount_sol", 0.0),
                confidence=a.get("confidence", 0),
            )
            for a in alts
        ],
    )


def _parse_priority_fee(msg: Dict[str, Any]) -> PriorityFee:
    return PriorityFee(
        timestamp=msg.get("timestamp", 0),
        speed=msg.get("speed", ""),
        compute_unit_price=msg.get("compute_unit_price", 0),
        compute_unit_limit=msg.get("compute_unit_limit", 0),
        estimated_cost_sol=msg.get("estimated_cost_sol", 0.0),
        landing_probability=msg.get("landing_probability", 0),
        network_congestion=msg.get("network_congestion", ""),
        recent_success_rate=msg.get("recent_success_rate", 0.0),
    )


def _parse_transaction_result_ws(msg: Dict[str, Any]) -> TransactionResult:
    routing_data = msg.get("routing")
    error_data = msg.get("error")

    routing = None
    if routing_data:
        routing = RoutingInfo(
            region=routing_data.get("region", ""),
            sender=routing_data.get("sender", ""),
            routing_latency_ms=routing_data.get("routing_latency_ms", 0),
            sender_latency_ms=routing_data.get("sender_latency_ms", 0),
            total_latency_ms=routing_data.get("total_latency_ms", 0),
        )

    error = None
    if error_data:
        error = TransactionError(
            code=error_data.get("code", ""),
            message=error_data.get("message", ""),
            details=error_data.get("details"),
        )

    return TransactionResult(
        request_id=msg.get("request_id", ""),
        transaction_id=msg.get("transaction_id", ""),
        signature=msg.get("signature"),
        status=msg.get("status", "pending"),
        slot=msg.get("slot"),
        timestamp=msg.get("timestamp", 0),
        routing=routing,
        error=error,
    )


def _parse_latest_blockhash(msg: Dict[str, Any]) -> LatestBlockhash:
    return LatestBlockhash(
        blockhash=msg.get("blockhash", ""),
        last_valid_block_height=msg.get("last_valid_block_height", 0),
        timestamp=msg.get("timestamp", 0),
    )


def _parse_latest_slot(msg: Dict[str, Any]) -> LatestSlot:
    return LatestSlot(
        slot=msg.get("slot", 0),
        timestamp=msg.get("timestamp", 0),
    )
