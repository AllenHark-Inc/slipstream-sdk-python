"""
AllenHarkSlipstream — HTTP REST Transport

Uses aiohttp for all REST API calls.
"""

from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional

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
    TipTier,
    TopUpInfo,
    TransactionResult,
    UsageEntry,
    WebhookConfig,
)


class HttpTransport:
    """HTTP REST transport using aiohttp."""

    def __init__(self, base_url: str, api_key: str, timeout_ms: int = 10_000) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = aiohttp.ClientTimeout(total=timeout_ms / 1000)
        self._session: Optional[aiohttp.ClientSession] = None

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
        url = f"{self._base_url}{path}"

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
