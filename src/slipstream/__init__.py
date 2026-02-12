"""
AllenHarkSlipstream — Python SDK for Slipstream

High-performance Solana transaction relay with leader-proximity-aware routing.

Example::

    from slipstream import SlipstreamClient, config_builder

    config = (
        config_builder()
        .api_key("sk_test_12345678")
        .region("us-east")
        .build()
    )

    client = await SlipstreamClient.connect(config)

    # Submit a transaction
    result = await client.submit_transaction(tx_bytes)
    print(f"TX: {result.transaction_id}")

    # Subscribe to leader hints
    client.on("leader_hint", lambda hint: print(f"Leader in {hint.preferred_region}"))
    await client.subscribe_leader_hints()

    # Check token balance
    balance = await client.get_balance()
    print(f"Balance: {balance.balance_sol} SOL ({balance.balance_tokens} tokens)")
"""

__version__ = "0.1.0"

# Client classes
from .client import SlipstreamClient
from .multi_region import MultiRegionClient

# Configuration
from .config import ConfigBuilder, config_builder

# Discovery
from .discovery import discover, DEFAULT_DISCOVERY_URL

# Error types
from .errors import SlipstreamError

# Worker selector (advanced usage)
from .worker_selector import WorkerSelector

# Types — re-export all
from .types import (
    # Config types
    SlipstreamConfig,
    BillingTier,
    ProtocolTimeouts,
    PriorityFeeConfig,
    PriorityFeeSpeed,
    BackoffStrategy,
    # Connection types
    ConnectionInfo,
    ConnectionStatus,
    ConnectionState,
    WorkerEndpoint,
    RateLimitInfo,
    # Streaming message types
    LeaderHint,
    LeaderHintMetadata,
    TipInstruction,
    AlternativeSender,
    PriorityFee,
    LatestBlockhash,
    LatestSlot,
    # Transaction types
    TransactionResult,
    TransactionStatus,
    SubmitOptions,
    RetryOptions,
    RoutingInfo,
    TransactionError,
    # Token billing types
    Balance,
    TopUpInfo,
    UsageEntry,
    DepositEntry,
    PendingDeposit,
    PaginationOptions,
    FreeTierUsage,
    # Multi-region types
    RoutingRecommendation,
    FallbackStrategy,
    MultiRegionConfig,
    RegionStatus,
    # Metrics
    PerformanceMetrics,
    # Config endpoint responses
    RegionInfo,
    SenderInfo,
    TipTier,
    # Webhook types
    WebhookEvent,
    WebhookNotificationLevel,
    WebhookConfig,
    RegisterWebhookRequest,
    # Landing rate types
    LandingRateStats,
    LandingRatePeriod,
    SenderLandingRate,
    RegionLandingRate,
    LandingRateOptions,
    # Bundle types
    BundleResult,
    # RPC proxy types
    RpcResponse,
    RpcError,
    SimulationResult,
)

__all__ = [
    "__version__",
    # Clients
    "SlipstreamClient",
    "MultiRegionClient",
    # Config
    "ConfigBuilder",
    "config_builder",
    # Discovery
    "discover",
    "DEFAULT_DISCOVERY_URL",
    # Errors
    "SlipstreamError",
    # Worker
    "WorkerSelector",
    # Types
    "SlipstreamConfig",
    "BillingTier",
    "ProtocolTimeouts",
    "PriorityFeeConfig",
    "PriorityFeeSpeed",
    "BackoffStrategy",
    "ConnectionInfo",
    "ConnectionStatus",
    "ConnectionState",
    "WorkerEndpoint",
    "RateLimitInfo",
    "LeaderHint",
    "LeaderHintMetadata",
    "TipInstruction",
    "AlternativeSender",
    "PriorityFee",
    "LatestBlockhash",
    "LatestSlot",
    "TransactionResult",
    "TransactionStatus",
    "SubmitOptions",
    "RetryOptions",
    "RoutingInfo",
    "TransactionError",
    "Balance",
    "TopUpInfo",
    "UsageEntry",
    "DepositEntry",
    "PendingDeposit",
    "PaginationOptions",
    "FreeTierUsage",
    "RoutingRecommendation",
    "FallbackStrategy",
    "MultiRegionConfig",
    "RegionStatus",
    "PerformanceMetrics",
    "RegionInfo",
    "SenderInfo",
    "TipTier",
    "WebhookEvent",
    "WebhookNotificationLevel",
    "WebhookConfig",
    "RegisterWebhookRequest",
    "LandingRateStats",
    "LandingRatePeriod",
    "SenderLandingRate",
    "RegionLandingRate",
    "LandingRateOptions",
    "BundleResult",
    "RpcResponse",
    "RpcError",
    "SimulationResult",
]
