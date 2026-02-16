"""Tests for the Slipstream Python SDK."""

import pytest

from slipstream.config import ConfigBuilder, config_builder, get_http_endpoint, get_ws_endpoint
from slipstream.errors import SlipstreamError
from slipstream.types import (
    BackoffStrategy,
    BillingTier,
    BundleResult,
    ConnectionState,
    FallbackStrategy,
    LandingRateStats,
    LandingRatePeriod,
    LatestBlockhash,
    LatestSlot,
    LeaderHint,
    LeaderHintMetadata,
    MultiRegionConfig,
    PriorityFee,
    PriorityFeeConfig,
    PriorityFeeSpeed,
    ProtocolTimeouts,
    RegionLandingRate,
    RetryOptions,
    RoutingInfo,
    RoutingRecommendation,
    RpcError,
    RpcResponse,
    SenderLandingRate,
    SimulationResult,
    SlipstreamConfig,
    SubmitOptions,
    TransactionError,
    TransactionResult,
    TransactionStatus,
    WebhookEvent,
    WebhookNotificationLevel,
)


# ============================================================================
# ConfigBuilder Tests
# ============================================================================


class TestConfigBuilder:
    def test_build_with_api_key(self):
        config = config_builder().api_key("sk_test_123").build()
        assert config.api_key == "sk_test_123"
        assert config.tier == BillingTier.PRO
        assert config.connection_timeout == 10_000
        assert config.max_retries == 3
        assert config.leader_hints is True
        assert config.keep_alive is True
        assert config.min_confidence == 70

    def test_missing_api_key_raises(self):
        with pytest.raises(SlipstreamError) as exc_info:
            config_builder().build()
        assert exc_info.value.code == "CONFIG"
        assert "api_key" in str(exc_info.value)

    def test_all_options(self):
        config = (
            config_builder()
            .api_key("sk_live_abc")
            .region("us-west")
            .endpoint("https://worker.example.com")
            .tier(BillingTier.ENTERPRISE)
            .connection_timeout(5_000)
            .max_retries(5)
            .leader_hints(False)
            .stream_tip_instructions(True)
            .stream_priority_fees(True)
            .stream_latest_blockhash(True)
            .stream_latest_slot(True)
            .min_confidence(90)
            .keep_alive(False)
            .keep_alive_interval(10.0)
            .idle_timeout(30_000)
            .retry_backoff(BackoffStrategy.LINEAR)
            .webhook_url("https://example.com/webhook")
            .webhook_events(["transaction.confirmed", "transaction.failed"])
            .webhook_notification_level("all")
            .build()
        )
        assert config.region == "us-west"
        assert config.endpoint == "https://worker.example.com"
        assert config.tier == BillingTier.ENTERPRISE
        assert config.connection_timeout == 5_000
        assert config.max_retries == 5
        assert config.leader_hints is False
        assert config.stream_tip_instructions is True
        assert config.stream_priority_fees is True
        assert config.stream_latest_blockhash is True
        assert config.stream_latest_slot is True
        assert config.min_confidence == 90
        assert config.keep_alive is False
        assert config.keep_alive_interval == 10.0
        assert config.idle_timeout == 30_000
        assert config.retry_backoff == BackoffStrategy.LINEAR
        assert config.webhook_url == "https://example.com/webhook"
        assert config.webhook_events == ["transaction.confirmed", "transaction.failed"]
        assert config.webhook_notification_level == "all"

    def test_invalid_min_confidence_low(self):
        with pytest.raises(SlipstreamError):
            config_builder().api_key("sk_test_123").min_confidence(-1).build()

    def test_invalid_min_confidence_high(self):
        with pytest.raises(SlipstreamError):
            config_builder().api_key("sk_test_123").min_confidence(101).build()

    def test_protocol_timeouts_defaults(self):
        config = config_builder().api_key("sk_test_123").build()
        assert config.protocol_timeouts.websocket == 3_000
        assert config.protocol_timeouts.http == 5_000

    def test_custom_protocol_timeouts(self):
        config = (
            config_builder()
            .api_key("sk_test_123")
            .protocol_timeouts(ProtocolTimeouts(websocket=2_000, http=3_000))
            .build()
        )
        assert config.protocol_timeouts.websocket == 2_000
        assert config.protocol_timeouts.http == 3_000

    def test_priority_fee_config(self):
        config = (
            config_builder()
            .api_key("sk_test_123")
            .priority_fee(PriorityFeeConfig(enabled=True, speed=PriorityFeeSpeed.ULTRA_FAST, max_tip=0.01))
            .build()
        )
        assert config.priority_fee.enabled is True
        assert config.priority_fee.speed == PriorityFeeSpeed.ULTRA_FAST
        assert config.priority_fee.max_tip == 0.01

    def test_config_builder_factory_returns_new(self):
        b1 = config_builder()
        b2 = config_builder()
        assert b1 is not b2

    def test_fluent_chaining(self):
        builder = config_builder()
        result = builder.api_key("sk_test_123")
        assert result is builder  # Returns self for chaining


# ============================================================================
# Endpoint Helper Tests
# ============================================================================


class TestEndpointHelpers:
    def test_http_endpoint_discovery_url(self):
        config = config_builder().api_key("sk_test_123").build()
        url = get_http_endpoint(config)
        assert url != ""
        assert not url.endswith("/")

    def test_http_endpoint_explicit(self):
        config = config_builder().api_key("sk_test_123").endpoint("https://worker.example.com/").build()
        assert get_http_endpoint(config) == "https://worker.example.com"

    def test_ws_endpoint_from_https(self):
        config = config_builder().api_key("sk_test_123").endpoint("https://worker.example.com").build()
        assert get_ws_endpoint(config) == "wss://worker.example.com/ws"

    def test_ws_endpoint_from_http(self):
        config = config_builder().api_key("sk_test_123").endpoint("http://localhost:9000").build()
        assert get_ws_endpoint(config) == "ws://localhost:9000/ws"

    def test_ws_endpoint_empty_when_no_endpoint(self):
        config = config_builder().api_key("sk_test_123").build()
        assert get_ws_endpoint(config) == ""


# ============================================================================
# SlipstreamError Tests
# ============================================================================


class TestSlipstreamError:
    def test_config_error(self):
        err = SlipstreamError.config("bad config")
        assert isinstance(err, SlipstreamError)
        assert isinstance(err, Exception)
        assert err.code == "CONFIG"
        assert str(err) == "bad config"

    def test_connection_error(self):
        err = SlipstreamError.connection("conn failed")
        assert err.code == "CONNECTION"

    def test_auth_error(self):
        err = SlipstreamError.auth("unauthorized")
        assert err.code == "AUTH"

    def test_protocol_error(self):
        err = SlipstreamError.protocol("unsupported")
        assert err.code == "PROTOCOL"

    def test_transaction_error(self):
        err = SlipstreamError.transaction("tx failed")
        assert err.code == "TRANSACTION"

    def test_timeout_error(self):
        err = SlipstreamError.timeout(5000)
        assert err.code == "TIMEOUT"
        assert "5000" in str(err)

    def test_all_protocols_failed(self):
        err = SlipstreamError.all_protocols_failed()
        assert err.code == "ALL_PROTOCOLS_FAILED"

    def test_rate_limited_default(self):
        err = SlipstreamError.rate_limited()
        assert err.code == "RATE_LIMITED"
        assert str(err) == "Rate limited"

    def test_not_connected(self):
        err = SlipstreamError.not_connected()
        assert err.code == "NOT_CONNECTED"

    def test_stream_closed(self):
        err = SlipstreamError.stream_closed()
        assert err.code == "STREAM_CLOSED"

    def test_insufficient_tokens(self):
        err = SlipstreamError.insufficient_tokens()
        assert err.code == "INSUFFICIENT_TOKENS"

    def test_internal_error(self):
        err = SlipstreamError.internal("oops")
        assert err.code == "INTERNAL"
        assert str(err) == "oops"

    def test_error_has_details(self):
        err = SlipstreamError("CUSTOM", "msg", {"foo": "bar"})
        assert err.details == {"foo": "bar"}


# ============================================================================
# Enum Tests
# ============================================================================


class TestEnums:
    def test_transaction_status_values(self):
        assert TransactionStatus.PENDING == "pending"
        assert TransactionStatus.PROCESSING == "processing"
        assert TransactionStatus.SENT == "sent"
        assert TransactionStatus.CONFIRMED == "confirmed"
        assert TransactionStatus.FAILED == "failed"
        assert TransactionStatus.DUPLICATE == "duplicate"
        assert TransactionStatus.RATE_LIMITED == "rate_limited"
        assert TransactionStatus.INSUFFICIENT_TOKENS == "insufficient_tokens"

    def test_connection_state_values(self):
        assert ConnectionState.DISCONNECTED == "disconnected"
        assert ConnectionState.CONNECTING == "connecting"
        assert ConnectionState.CONNECTED == "connected"
        assert ConnectionState.ERROR == "error"

    def test_fallback_strategy_values(self):
        assert FallbackStrategy.SEQUENTIAL == "sequential"
        assert FallbackStrategy.BROADCAST == "broadcast"
        assert FallbackStrategy.RETRY == "retry"
        assert FallbackStrategy.NONE == "none"

    def test_priority_fee_speed_values(self):
        assert PriorityFeeSpeed.SLOW == "slow"
        assert PriorityFeeSpeed.FAST == "fast"
        assert PriorityFeeSpeed.ULTRA_FAST == "ultra_fast"

    def test_backoff_strategy_values(self):
        assert BackoffStrategy.LINEAR == "linear"
        assert BackoffStrategy.EXPONENTIAL == "exponential"

    def test_billing_tier_values(self):
        assert BillingTier.FREE == "free"
        assert BillingTier.STANDARD == "standard"
        assert BillingTier.PRO == "pro"
        assert BillingTier.ENTERPRISE == "enterprise"

    def test_webhook_event_values(self):
        assert WebhookEvent.TRANSACTION_SENT == "transaction.sent"
        assert WebhookEvent.TRANSACTION_CONFIRMED == "transaction.confirmed"
        assert WebhookEvent.TRANSACTION_FAILED == "transaction.failed"
        assert WebhookEvent.BUNDLE_SENT == "bundle.sent"
        assert WebhookEvent.BUNDLE_CONFIRMED == "bundle.confirmed"
        assert WebhookEvent.BUNDLE_FAILED == "bundle.failed"
        assert WebhookEvent.BILLING_LOW_BALANCE == "billing.low_balance"
        assert WebhookEvent.BILLING_DEPLETED == "billing.depleted"
        assert WebhookEvent.BILLING_DEPOSIT_RECEIVED == "billing.deposit_received"

    def test_webhook_notification_level_values(self):
        assert WebhookNotificationLevel.ALL == "all"
        assert WebhookNotificationLevel.FINAL == "final"
        assert WebhookNotificationLevel.CONFIRMED == "confirmed"


# ============================================================================
# Type Dataclass Tests
# ============================================================================


class TestTypeStructures:
    def test_transaction_result(self):
        result = TransactionResult(
            request_id="req-1",
            transaction_id="tx-1",
            signature="abc123",
            status=TransactionStatus.CONFIRMED,
            slot=12345,
            timestamp=1000000,
            routing=RoutingInfo(
                region="us-west",
                sender="0slot",
                routing_latency_ms=1,
                sender_latency_ms=5,
                total_latency_ms=6,
            ),
        )
        assert result.request_id == "req-1"
        assert result.status == TransactionStatus.CONFIRMED
        assert result.routing is not None
        assert result.routing.region == "us-west"
        assert result.routing.total_latency_ms == 6

    def test_transaction_result_with_error(self):
        result = TransactionResult(
            request_id="req-2",
            transaction_id="tx-2",
            status=TransactionStatus.FAILED,
            error=TransactionError(code="SENDER_ERROR", message="Sender unavailable"),
        )
        assert result.error is not None
        assert result.error.code == "SENDER_ERROR"

    def test_leader_hint(self):
        hint = LeaderHint(
            timestamp=1000,
            slot=100,
            expires_at_slot=104,
            preferred_region="eu-west",
            backup_regions=["us-east", "asia"],
            confidence=85,
            leader_pubkey="Validator1...",
            metadata=LeaderHintMetadata(
                tpu_rtt_ms=15,
                region_score=92.0,
                leader_tpu_address="1.2.3.4:8001",
                region_rtt_ms={"eu-west": 15, "us-east": 80},
            ),
        )
        assert hint.confidence == 85
        assert hint.metadata.region_rtt_ms is not None
        assert hint.metadata.region_rtt_ms["eu-west"] == 15

    def test_priority_fee(self):
        fee = PriorityFee(
            timestamp=1000,
            speed="fast",
            compute_unit_price=1500,
            compute_unit_limit=200_000,
            estimated_cost_sol=0.0003,
            landing_probability=95,
            network_congestion="medium",
            recent_success_rate=0.92,
        )
        assert fee.compute_unit_price == 1500
        assert fee.landing_probability == 95

    def test_latest_blockhash(self):
        bh = LatestBlockhash(
            blockhash="GHtXQBsoZE8Z...",
            last_valid_block_height=180_000_000,
            timestamp=1000,
        )
        assert bh.blockhash == "GHtXQBsoZE8Z..."

    def test_latest_slot(self):
        slot = LatestSlot(slot=250_000_000, timestamp=1000)
        assert slot.slot == 250_000_000

    def test_submit_options_defaults(self):
        opts = SubmitOptions()
        assert opts.broadcast_mode is False
        assert opts.preferred_sender is None
        assert opts.max_retries == 2
        assert opts.timeout_ms == 30_000
        assert opts.dedup_id is None
        assert opts.retry is None

    def test_submit_options_all_fields(self):
        opts = SubmitOptions(
            broadcast_mode=True,
            preferred_sender="0slot",
            max_retries=5,
            timeout_ms=60_000,
            dedup_id="dedup-123",
            retry=RetryOptions(max_retries=3, backoff_base_ms=200, cross_sender_retry=True),
        )
        assert opts.broadcast_mode is True
        assert opts.retry is not None
        assert opts.retry.cross_sender_retry is True

    def test_bundle_result(self):
        result = BundleResult(
            bundle_id="bundle-1",
            accepted=True,
            signatures=["sig1", "sig2"],
            sender_id="0slot",
        )
        assert result.accepted is True
        assert len(result.signatures) == 2

    def test_multi_region_config_defaults(self):
        config = MultiRegionConfig()
        assert config.auto_follow_leader is True
        assert config.min_switch_confidence == 70
        assert config.switch_cooldown_ms == 5000
        assert config.broadcast_high_priority is False
        assert config.max_broadcast_regions == 3

    def test_routing_recommendation(self):
        rec = RoutingRecommendation(
            best_region="us-west",
            leader_pubkey="Val1...",
            slot=100,
            confidence=90,
            expected_rtt_ms=15,
            fallback_regions=["eu-west"],
            fallback_strategy=FallbackStrategy.SEQUENTIAL,
            valid_for_ms=500,
        )
        assert rec.best_region == "us-west"
        assert rec.fallback_strategy == FallbackStrategy.SEQUENTIAL

    def test_landing_rate_stats(self):
        stats = LandingRateStats(
            period=LandingRatePeriod(start="2026-02-15T00:00:00Z", end="2026-02-16T00:00:00Z"),
            total_sent=1000,
            total_landed=920,
            landing_rate=0.92,
            by_sender=[SenderLandingRate(sender="0slot", total_sent=500, total_landed=475, landing_rate=0.95)],
            by_region=[RegionLandingRate(region="us-west", total_sent=600, total_landed=558, landing_rate=0.93)],
        )
        assert stats.landing_rate == 0.92
        assert len(stats.by_sender) == 1
        assert stats.by_region[0].region == "us-west"

    def test_rpc_response_success(self):
        resp = RpcResponse(
            jsonrpc="2.0",
            id=1,
            result={"blockhash": "abc123"},
        )
        assert resp.result is not None
        assert resp.error is None

    def test_rpc_response_error(self):
        resp = RpcResponse(
            jsonrpc="2.0",
            id=1,
            error=RpcError(code=-32600, message="Invalid Request"),
        )
        assert resp.error is not None
        assert resp.error.code == -32600

    def test_simulation_result(self):
        result = SimulationResult(
            err=None,
            logs=["Program executed", "Instruction complete"],
            units_consumed=50_000,
        )
        assert result.err is None
        assert len(result.logs) == 2
        assert result.units_consumed == 50_000

    def test_slipstream_config_defaults(self):
        config = SlipstreamConfig(api_key="sk_test_123")
        assert config.tier == BillingTier.PRO
        assert config.connection_timeout == 10_000
        assert config.max_retries == 3
        assert config.leader_hints is True
        assert config.stream_tip_instructions is False
        assert config.keep_alive is True
        assert config.min_confidence == 70
        assert config.webhook_events == ["transaction.confirmed"]
        assert config.webhook_notification_level == "final"
