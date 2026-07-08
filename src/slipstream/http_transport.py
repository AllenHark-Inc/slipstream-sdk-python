"""
AllenHarkSlipstream — HTTP REST Transport

Uses aiohttp for all REST API calls.
"""

from __future__ import annotations

import base64
from typing import Any, Awaitable, Callable, Dict, List, Optional, TypeVar

import aiohttp

from .errors import SlipstreamError
from .types import (
    Balance,
    DepositEntry,
    FallbackStrategy,
    FreeTierUsage,
    PaginationOptions,
    PendingDeposit,
    RegionInfo,
    RoutingRecommendation,
    SenderInfo,
    SubmitOptions,
    TipInstruction,
    TipTier,
    TopUpInfo,
    TransactionResult,
    UsageEntry,
    WebhookConfig,
)


class HttpTransport:
    """HTTP REST transport using aiohttp.

    Prefers ``base_url``; falls back ONCE to ``legacy_base_url`` (if given)
    when a request fails with a connect/transport error. A successful
    request against the primary URL never attempts the legacy URL. No
    legacy URL ⇒ single attempt, unchanged behavior.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout_ms: int = 10_000,
        legacy_base_url: Optional[str] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._legacy_base_url = (
            legacy_base_url.rstrip("/") if legacy_base_url else None
        )
        self._api_key = api_key
        self._timeout = aiohttp.ClientTimeout(total=timeout_ms / 1000)
        self._session: Optional[aiohttp.ClientSession] = None

    def _targets(self) -> List[str]:
        if self._legacy_base_url and self._legacy_base_url != self._base_url:
            return [self._base_url, self._legacy_base_url]
        return [self._base_url]

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=self._timeout,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> Any:
        session = await self._ensure_session()

        async def attempt(base_url: str) -> Any:
            url = f"{base_url}{path}"
            try:
                async with session.request(method, url, json=body, params=params) as resp:
                    if resp.status == 401:
                        raise SlipstreamError.auth("Invalid API key")
                    if resp.status == 429:
                        raise SlipstreamError.rate_limited()
                    if not (200 <= resp.status < 300):
                        error_text = await resp.text()
                        raise SlipstreamError.internal(
                            f"HTTP {resp.status}: {error_text or resp.reason}"
                        )
                    return await resp.json()
            except SlipstreamError:
                raise
            except aiohttp.ClientError as e:
                raise SlipstreamError.connection(f"HTTP request failed: {e}") from e
            except Exception as e:
                raise SlipstreamError.connection(f"HTTP request failed: {e}") from e

        return await _try_targets(self._targets(), attempt)

    # =========================================================================
    # Transaction
    # =========================================================================

    async def submit_transaction(
        self, transaction: bytes, options: Optional[SubmitOptions] = None
    ) -> TransactionResult:
        opts = options or SubmitOptions()
        base64_tx = base64.b64encode(transaction).decode("ascii")

        data = await self._request(
            "POST",
            "/v1/transactions/submit",
            body={
                "transaction": base64_tx,
                "dedup_id": opts.dedup_id,
                "options": {
                    "broadcast_mode": opts.broadcast_mode,
                    "preferred_sender": opts.preferred_sender,
                    "max_retries": opts.max_retries,
                    "timeout_ms": opts.timeout_ms,
                    "tpu_submission": opts.tpu_submission,
                },
            },
        )

        return _parse_transaction_result(data)

    async def get_transaction_status(self, transaction_id: str) -> TransactionResult:
        data = await self._request("GET", f"/v1/transactions/{transaction_id}/status")
        return _parse_transaction_result(data)

    # =========================================================================
    # Token Billing
    # =========================================================================

    async def get_balance(self) -> Balance:
        data = await self._request("GET", "/v1/balance")
        balance_lamports = data.get("balance_lamports", 0)
        cost_per_query = 50_000
        grace_limit = 1_000_000

        return Balance(
            balance_sol=balance_lamports / 1_000_000_000,
            balance_tokens=balance_lamports // cost_per_query,
            balance_lamports=balance_lamports,
            grace_remaining_tokens=(balance_lamports + grace_limit) // cost_per_query,
        )

    async def get_deposit_address(self) -> TopUpInfo:
        data = await self._request("GET", "/v1/deposit-address")
        return TopUpInfo(
            deposit_wallet=data.get("deposit_wallet", ""),
            min_amount_sol=data.get("min_amount_sol", 0.0),
            min_amount_lamports=data.get("min_amount_lamports", 0),
        )

    async def get_usage_history(
        self, opts: Optional[PaginationOptions] = None
    ) -> List[UsageEntry]:
        params: Dict[str, str] = {}
        if opts:
            if opts.limit is not None:
                params["limit"] = str(opts.limit)
            if opts.offset is not None:
                params["offset"] = str(opts.offset)

        data = await self._request("GET", "/v1/usage-history", params=params or None)
        entries = data.get("entries", [])

        return [
            UsageEntry(
                timestamp=_parse_timestamp(e.get("created_at")),
                tx_type=e.get("tx_type", ""),
                amount_lamports=e.get("amount_lamports", 0),
                balance_after_lamports=e.get("balance_after_lamports", 0),
                description=e.get("description"),
            )
            for e in entries
        ]

    async def get_deposit_history(
        self, opts: Optional[PaginationOptions] = None
    ) -> List[DepositEntry]:
        params: Dict[str, str] = {}
        if opts:
            if opts.limit is not None:
                params["limit"] = str(opts.limit)
            if opts.offset is not None:
                params["offset"] = str(opts.offset)

        data = await self._request("GET", "/v1/deposit-history", params=params or None)
        deposits = data.get("deposits", [])

        return [
            DepositEntry(
                signature=d.get("signature", ""),
                amount_lamports=d.get("amount_lamports", 0),
                amount_sol=d.get("amount_lamports", 0) / 1_000_000_000,
                usd_value=d.get("usd_value"),
                sol_usd_price=d.get("sol_usd_price"),
                credited=d.get("credited", False),
                credited_at=d.get("credited_at"),
                slot=d.get("slot", 0),
                detected_at=d.get("detected_at", ""),
                block_time=d.get("block_time"),
            )
            for d in deposits
        ]

    async def get_pending_deposit(self) -> PendingDeposit:
        data = await self._request("GET", "/v1/deposit-pending")
        return PendingDeposit(
            pending_lamports=data.get("pending_lamports", 0),
            pending_sol=data.get("pending_sol", 0.0),
            pending_count=data.get("pending_count", 0),
            minimum_deposit_usd=data.get("minimum_deposit_usd", 10.0),
        )

    async def get_free_tier_usage(self) -> FreeTierUsage:
        data = await self._request("GET", "/v1/free-tier-usage")
        return FreeTierUsage(
            used=data.get("used", 0),
            remaining=data.get("remaining", 0),
            limit=data.get("limit", 100),
            resets_at=data.get("resets_at", ""),
        )

    # =========================================================================
    # Routing
    # =========================================================================

    async def get_routing_recommendation(self) -> RoutingRecommendation:
        try:
            data = await self._request("GET", "/v1/routing/recommendation")
            return RoutingRecommendation(
                best_region=data.get("best_region", "unknown"),
                leader_pubkey=data.get("leader_pubkey"),
                slot=data.get("slot", 0),
                confidence=data.get("confidence", 0),
                expected_rtt_ms=data.get("expected_rtt_ms"),
                fallback_regions=data.get("fallback_regions", []),
                fallback_strategy=FallbackStrategy(
                    data.get("fallback_strategy", "retry")
                ),
                valid_for_ms=data.get("valid_for_ms", 1000),
            )
        except SlipstreamError as e:
            if "404" in str(e):
                return RoutingRecommendation(
                    best_region="unknown",
                    confidence=50,
                )
            raise

    # =========================================================================
    # Tip Instructions
    # =========================================================================

    async def get_tip_instructions(self) -> List[TipInstruction]:
        """Fetch current tip instructions from the worker."""
        try:
            raw = await self._request("GET", "/v1/tip-instructions")
        except Exception:
            return []
        if not isinstance(raw, list):
            return []
        tips = []
        for r in raw:
            tips.append(TipInstruction(
                timestamp=r.get("timestamp", 0),
                sender=r.get("sender_id", ""),
                sender_name=r.get("sender_id", ""),
                tip_wallet_address=r.get("tip_wallet", ""),
                tip_amount_sol=r.get("tip_amount_lamports", 0) / 1_000_000_000,
                tip_tier=r.get("tier", "standard"),
                expected_latency_ms=r.get("expected_latency_ms", 0),
                confidence=r.get("confidence", 0),
                valid_until_slot=r.get("valid_until_slot", 0),
                alternative_senders=[],
            ))
        return tips

    # =========================================================================
    # Config
    # =========================================================================

    async def get_regions(self) -> List[RegionInfo]:
        data = await self._request("GET", "/v1/config/regions")
        regions = data.get("regions", [])
        return [
            RegionInfo(
                region_id=r.get("region_id", ""),
                display_name=r.get("display_name", ""),
                endpoint=r.get("endpoint", ""),
                geolocation=r.get("geolocation"),
            )
            for r in regions
        ]

    async def get_senders(self) -> List[SenderInfo]:
        data = await self._request("GET", "/v1/config/senders")
        senders = data.get("senders", [])
        return [
            SenderInfo(
                sender_id=s.get("sender_id", ""),
                display_name=s.get("display_name", ""),
                tip_wallets=s.get("tip_wallets", []),
                tip_tiers=[
                    TipTier(
                        name=t.get("name", ""),
                        amount_sol=t.get("amount_sol", 0.0),
                        expected_latency_ms=t.get("expected_latency_ms", 0),
                    )
                    for t in s.get("tip_tiers", [])
                ],
            )
            for s in senders
        ]

    # =========================================================================
    # Webhooks
    # =========================================================================

    async def register_webhook(
        self,
        url: str,
        events: Optional[List[str]] = None,
        notification_level: Optional[str] = None,
    ) -> WebhookConfig:
        body: Dict[str, Any] = {"url": url}
        if events is not None:
            body["events"] = events
        if notification_level is not None:
            body["notification_level"] = notification_level

        data = await self._request("POST", "/v1/webhooks", body)
        return WebhookConfig(
            id=data.get("id", ""),
            url=data.get("url", ""),
            secret=data.get("secret"),
            events=data.get("events", []),
            notification_level=data.get("notification_level", "final"),
            is_active=data.get("is_active", True),
            created_at=data.get("created_at"),
        )

    async def get_webhook(self) -> Optional[WebhookConfig]:
        try:
            data = await self._request("GET", "/v1/webhooks")
            return WebhookConfig(
                id=data.get("id", ""),
                url=data.get("url", ""),
                secret=data.get("secret"),
                events=data.get("events", []),
                notification_level=data.get("notification_level", "final"),
                is_active=data.get("is_active", True),
                created_at=data.get("created_at"),
            )
        except SlipstreamError as e:
            if "404" in str(e):
                return None
            raise

    async def delete_webhook(self) -> None:
        await self._request("DELETE", "/v1/webhooks")

    # =========================================================================
    # Landing Rates
    # =========================================================================

    async def get_landing_rates(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> "LandingRateStats":
        params: Dict[str, str] = {}
        if start is not None:
            params["start"] = start
        if end is not None:
            params["end"] = end
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        path = f"/v1/metrics/landing-rates?{qs}" if qs else "/v1/metrics/landing-rates"
        data = await self._request("GET", path)
        from .types import (
            LandingRatePeriod,
            LandingRateStats,
            RegionLandingRate,
            SenderLandingRate,
        )
        return LandingRateStats(
            period=LandingRatePeriod(
                start=data.get("period", {}).get("start", ""),
                end=data.get("period", {}).get("end", ""),
            ),
            total_sent=data.get("total_sent", 0),
            total_landed=data.get("total_landed", 0),
            landing_rate=data.get("landing_rate", 0.0),
            by_sender=[
                SenderLandingRate(
                    sender=s.get("sender", ""),
                    total_sent=s.get("total_sent", 0),
                    total_landed=s.get("total_landed", 0),
                    landing_rate=s.get("landing_rate", 0.0),
                )
                for s in data.get("by_sender", [])
            ],
            by_region=[
                RegionLandingRate(
                    region=r.get("region", ""),
                    total_sent=r.get("total_sent", 0),
                    total_landed=r.get("total_landed", 0),
                    landing_rate=r.get("landing_rate", 0.0),
                )
                for r in data.get("by_region", [])
            ],
        )

    # =========================================================================
    # Bundle Submission
    # =========================================================================

    async def submit_bundle(
        self,
        transactions: "List[bytes]",
        tip_lamports: Optional[int] = None,
    ) -> "BundleResult":
        import base64 as b64
        txs_b64 = [b64.b64encode(tx).decode() for tx in transactions]
        body: Dict[str, Any] = {"transactions": txs_b64}
        if tip_lamports is not None:
            body["tip_lamports"] = tip_lamports
        data = await self._request("POST", "/v1/bundles/submit", body=body)
        from .types import BundleResult
        return BundleResult(
            bundle_id=data.get("bundle_id", ""),
            accepted=data.get("accepted", False),
            signatures=data.get("signatures", []),
            sender_id=data.get("sender_id"),
            error=data.get("error"),
        )

    async def rpc(self, method: str, params: list) -> "RpcResponse":
        """Execute a Solana JSON-RPC call via the Slipstream proxy."""
        from .types import RpcResponse, RpcError
        data = await self._request("POST", "/v1/rpc", body={
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        })
        error = None
        if data.get("error"):
            err = data["error"]
            error = RpcError(
                code=err.get("code", 0),
                message=err.get("message", ""),
                data=err.get("data"),
            )
        return RpcResponse(
            jsonrpc=data.get("jsonrpc", "2.0"),
            id=data.get("id", 1),
            result=data.get("result"),
            error=error,
        )


# =============================================================================
# Legacy-port connect fallback
# =============================================================================
#
# Shared "prefer-primary / single-legacy-fallback" connect semantics used by
# every transport that dials a worker endpoint (HTTP, WebSocket). Mirrors the
# Rust SDK's `client-sdk/rust/src/connection/mod.rs` and the TypeScript SDK's
# `client-sdk/typescript/src/transport/fallback.ts` behavior:
#
# - The PRIMARY target is tried first. On success, no other target is ever
#   attempted.
# - If (and only if) the primary attempt fails with a *connect/transport*
#   error — connection refused, DNS failure, transport-establishment error,
#   or a connect timeout — the LEGACY target (if one exists) is tried
#   exactly once.
# - Application errors (auth rejection, protocol/validation errors, rate
#   limiting, etc.) are surfaced immediately and never trigger a fallback,
#   since they would fail identically against the legacy port.
# - No legacy target present ⇒ single attempt, error surfaced unchanged
#   (today's behavior, byte-for-byte).

T = TypeVar("T")


def _is_connect_failure(err: BaseException) -> bool:
    """Classify whether an error is a connect/transport-establishment
    failure (worth retrying against a different endpoint) versus an
    application error, which must NOT trigger a legacy-port fallback.
    """
    return isinstance(err, SlipstreamError) and err.code in ("CONNECTION", "TIMEOUT")


async def _try_targets(
    targets: List[str], attempt: Callable[[str], Awaitable[T]]
) -> T:
    """Attempt ``attempt`` against each target in order, returning the first
    success. Only proceeds to the next target when the previous attempt
    failed with a connect/transport error (see :func:`_is_connect_failure`);
    any other error — or a failure on the final target — is raised
    immediately.

    A successful attempt on an earlier target means ``attempt`` is never
    invoked for any subsequent target.
    """
    if not targets:
        raise SlipstreamError.connection("No connect targets available")

    last_error: Optional[BaseException] = None
    for i, target in enumerate(targets):
        try:
            return await attempt(target)
        except Exception as e:  # noqa: BLE001 - re-raised below when not retryable
            last_error = e
            is_last_target = i == len(targets) - 1
            if is_last_target or not _is_connect_failure(e):
                raise

    # Unreachable — the loop above always returns or raises — but keeps
    # type checkers happy and guards against future refactors.
    assert last_error is not None
    raise last_error


# =============================================================================
# Helpers
# =============================================================================


def _parse_timestamp(value: Any) -> int:
    """Parse a timestamp from various formats to epoch ms."""
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    # ISO 8601 string
    try:
        from datetime import datetime, timezone

        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
    except (ValueError, AttributeError):
        return 0


def _parse_transaction_result(data: Dict[str, Any]) -> TransactionResult:
    routing_data = data.get("routing")
    error_data = data.get("error")

    from .types import RoutingInfo, TransactionError

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
        request_id=data.get("request_id", ""),
        transaction_id=data.get("transaction_id", ""),
        signature=data.get("signature"),
        status=data.get("status", "pending"),
        slot=data.get("slot"),
        timestamp=data.get("timestamp", 0),
        routing=routing,
        error=error,
    )
