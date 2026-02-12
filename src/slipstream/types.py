"""
AllenHarkSlipstream — Type definitions

All dataclasses and enums matching the Rust SDK API surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# =============================================================================
# Configuration
# =============================================================================


class BillingTier(str, Enum):
    FREE = "free"
    STANDARD = "standard"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class PriorityFeeSpeed(str, Enum):
    SLOW = "slow"
    FAST = "fast"
    ULTRA_FAST = "ultra_fast"


class BackoffStrategy(str, Enum):
    LINEAR = "linear"
    EXPONENTIAL = "exponential"


@dataclass
class ProtocolTimeouts:
    websocket: int = 3_000
    http: int = 5_000


@dataclass
class PriorityFeeConfig:
    enabled: bool = False
    speed: PriorityFeeSpeed = PriorityFeeSpeed.FAST
    max_tip: Optional[float] = None


@dataclass
class SlipstreamConfig:
    api_key: str
    region: Optional[str] = None
    endpoint: Optional[str] = None
    discovery_url: str = "https://discovery.slipstream.allenhark.com"
    tier: BillingTier = BillingTier.PRO
    connection_timeout: int = 10_000
    max_retries: int = 3
    leader_hints: bool = True
    stream_tip_instructions: bool = False
    stream_priority_fees: bool = False
    stream_latest_blockhash: bool = False
    stream_latest_slot: bool = False
    protocol_timeouts: ProtocolTimeouts = field(default_factory=ProtocolTimeouts)
    priority_fee: PriorityFeeConfig = field(default_factory=PriorityFeeConfig)
    retry_backoff: BackoffStrategy = BackoffStrategy.EXPONENTIAL
    min_confidence: int = 70
    idle_timeout: Optional[int] = None
    keep_alive: bool = True
    keep_alive_interval: float = 5.0
    webhook_url: Optional[str] = None
    webhook_events: List[str] = field(default_factory=lambda: ["transaction.confirmed"])
    webhook_notification_level: str = "final"


# =============================================================================
# Connection
# =============================================================================


class ConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class RateLimitInfo:
    rps: int = 100
    burst: int = 200


@dataclass
class ConnectionInfo:
    session_id: str = ""
    protocol: str = "http"
    region: Optional[str] = None
    server_time: int = 0
    features: List[str] = field(default_factory=list)
    rate_limit: RateLimitInfo = field(default_factory=RateLimitInfo)


@dataclass
class ConnectionStatus:
    state: ConnectionState = ConnectionState.DISCONNECTED
    protocol: str = "http"
    latency_ms: int = 0
    region: Optional[str] = None


@dataclass
class WorkerEndpoint:
    id: str
    region: str
    websocket: Optional[str] = None
    http: Optional[str] = None


# =============================================================================
# Streaming Messages
# =============================================================================


@dataclass
class LeaderHintMetadata:
    tpu_rtt_ms: int = 0
    region_score: float = 0.0
    leader_tpu_address: Optional[str] = None
    region_rtt_ms: Optional[Dict[str, int]] = None


@dataclass
class LeaderHint:
    timestamp: int = 0
    slot: int = 0
    expires_at_slot: int = 0
    preferred_region: str = ""
    backup_regions: List[str] = field(default_factory=list)
    confidence: int = 0
    leader_pubkey: str = ""
    metadata: LeaderHintMetadata = field(default_factory=LeaderHintMetadata)


@dataclass
class AlternativeSender:
    sender: str = ""
    tip_amount_sol: float = 0.0
    confidence: int = 0


@dataclass
class TipInstruction:
    timestamp: int = 0
    sender: str = ""
    sender_name: str = ""
    tip_wallet_address: str = ""
    tip_amount_sol: float = 0.0
    tip_tier: str = ""
    expected_latency_ms: int = 0
    confidence: int = 0
    valid_until_slot: int = 0
    alternative_senders: List[AlternativeSender] = field(default_factory=list)


@dataclass
class PriorityFee:
    timestamp: int = 0
    speed: str = ""
    compute_unit_price: int = 0
    compute_unit_limit: int = 0
    estimated_cost_sol: float = 0.0
    landing_probability: int = 0
    network_congestion: str = ""
    recent_success_rate: float = 0.0


@dataclass
class LatestBlockhash:
    blockhash: str = ""
    last_valid_block_height: int = 0
    timestamp: int = 0


@dataclass
class LatestSlot:
    slot: int = 0
    timestamp: int = 0


# =============================================================================
# Transaction
# =============================================================================


class TransactionStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    DUPLICATE = "duplicate"
    RATE_LIMITED = "rate_limited"
    INSUFFICIENT_TOKENS = "insufficient_tokens"


@dataclass
class RoutingInfo:
    region: str = ""
    sender: str = ""
    routing_latency_ms: int = 0
    sender_latency_ms: int = 0
    total_latency_ms: int = 0


@dataclass
class TransactionError:
    code: str = ""
    message: str = ""
    details: Optional[object] = None


@dataclass
class RetryOptions:
    """Retry policy options for intelligent retry behavior."""
    max_retries: int = 2
    """Maximum number of retry attempts (default: 2)"""
    backoff_base_ms: int = 100
    """Base backoff delay in milliseconds (default: 100ms, exponential with jitter)"""
    cross_sender_retry: bool = False
    """Whether to retry with a different sender on failure (default: False)"""


@dataclass
class SubmitOptions:
    broadcast_mode: bool = False
    preferred_sender: Optional[str] = None
    max_retries: int = 2
    timeout_ms: int = 30_000
    dedup_id: Optional[str] = None
    retry: Optional[RetryOptions] = None
    """Retry policy (overrides max_retries with more control)"""


@dataclass
class TransactionResult:
    request_id: str = ""
    transaction_id: str = ""
    signature: Optional[str] = None
    status: str = "pending"
    slot: Optional[int] = None
    timestamp: int = 0
    routing: Optional[RoutingInfo] = None
    error: Optional[TransactionError] = None


# =============================================================================
# Token Billing
# =============================================================================


@dataclass
class Balance:
    balance_sol: float = 0.0
    balance_tokens: int = 0
    balance_lamports: int = 0
    grace_remaining_tokens: int = 0


@dataclass
class TopUpInfo:
    deposit_wallet: str = ""
    min_amount_sol: float = 0.0
    min_amount_lamports: int = 0


@dataclass
class UsageEntry:
    timestamp: int = 0
    tx_type: str = ""
    amount_lamports: int = 0
    balance_after_lamports: int = 0
    description: Optional[str] = None


@dataclass
class DepositEntry:
    signature: str = ""
    amount_lamports: int = 0
    amount_sol: float = 0.0
    usd_value: Optional[float] = None
    sol_usd_price: Optional[float] = None
    credited: bool = False
    credited_at: Optional[str] = None
    slot: int = 0
    detected_at: str = ""
    block_time: Optional[str] = None


@dataclass
class PendingDeposit:
    pending_lamports: int = 0
    pending_sol: float = 0.0
    pending_count: int = 0
    minimum_deposit_usd: float = 10.0


@dataclass
class PaginationOptions:
    limit: Optional[int] = None
    offset: Optional[int] = None


@dataclass
class FreeTierUsage:
    used: int = 0
    remaining: int = 0
    limit: int = 100
    resets_at: str = ""


# =============================================================================
# Multi-Region Routing
# =============================================================================


class FallbackStrategy(str, Enum):
    SEQUENTIAL = "sequential"
    BROADCAST = "broadcast"
    RETRY = "retry"
    NONE = "none"


@dataclass
class RoutingRecommendation:
    best_region: str = ""
    leader_pubkey: str = ""
    slot: int = 0
    confidence: int = 0
    expected_rtt_ms: Optional[int] = None
    fallback_regions: List[str] = field(default_factory=list)
    fallback_strategy: FallbackStrategy = FallbackStrategy.RETRY
    valid_for_ms: int = 1000


@dataclass
class MultiRegionConfig:
    auto_follow_leader: bool = True
    min_switch_confidence: int = 70
    switch_cooldown_ms: int = 5000
    broadcast_high_priority: bool = False
    max_broadcast_regions: int = 3


@dataclass
class RegionStatus:
    region_id: str = ""
    available: bool = False
    latency_ms: Optional[int] = None
    leader_rtt_ms: Optional[int] = None
    score: Optional[float] = None
    worker_count: int = 0


# =============================================================================
# Metrics
# =============================================================================


@dataclass
class PingResult:
    """Result of a ping/pong exchange for keep-alive and time sync."""
    seq: int = 0
    rtt_ms: int = 0
    clock_offset_ms: int = 0
    server_time: int = 0


@dataclass
class PerformanceMetrics:
    transactions_submitted: int = 0
    transactions_confirmed: int = 0
    average_latency_ms: float = 0.0
    success_rate: float = 0.0


# =============================================================================
# Discovery
# =============================================================================


@dataclass
class DiscoveryWorkerPorts:
    quic: int = 4433
    ws: int = 9000
    http: int = 9000


@dataclass
class DiscoveryRegion:
    id: str = ""
    name: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None


@dataclass
class DiscoveryWorker:
    id: str = ""
    region: str = ""
    ip: str = ""
    ports: DiscoveryWorkerPorts = field(default_factory=DiscoveryWorkerPorts)
    healthy: bool = True
    version: Optional[str] = None


@dataclass
class DiscoveryResponse:
    regions: List[DiscoveryRegion] = field(default_factory=list)
    workers: List[DiscoveryWorker] = field(default_factory=list)
    recommended_region: Optional[str] = None


# =============================================================================
# Config Endpoint Responses
# =============================================================================


@dataclass
class TipTier:
    name: str = ""
    amount_sol: float = 0.0
    expected_latency_ms: int = 0


@dataclass
class RegionInfo:
    region_id: str = ""
    display_name: str = ""
    endpoint: str = ""
    geolocation: Optional[Dict[str, float]] = None


@dataclass
class SenderInfo:
    sender_id: str = ""
    display_name: str = ""
    tip_wallets: List[str] = field(default_factory=list)
    tip_tiers: List[TipTier] = field(default_factory=list)


# =============================================================================
# Webhook Types
# =============================================================================


class WebhookEvent(str, Enum):
    TRANSACTION_SENT = "transaction.sent"
    TRANSACTION_CONFIRMED = "transaction.confirmed"
    TRANSACTION_FAILED = "transaction.failed"
    BUNDLE_SENT = "bundle.sent"
    BUNDLE_CONFIRMED = "bundle.confirmed"
    BUNDLE_FAILED = "bundle.failed"
    BILLING_LOW_BALANCE = "billing.low_balance"
    BILLING_DEPLETED = "billing.depleted"
    BILLING_DEPOSIT_RECEIVED = "billing.deposit_received"


class WebhookNotificationLevel(str, Enum):
    """Notification level for transaction events."""
    ALL = "all"       # Receive all transaction events (sent + confirmed + failed)
    FINAL = "final"   # Receive only terminal events (confirmed + failed)
    CONFIRMED = "confirmed"  # Receive only confirmed events


@dataclass
class WebhookConfig:
    id: str = ""
    url: str = ""
    secret: Optional[str] = None
    events: List[str] = field(default_factory=list)
    notification_level: str = "final"
    is_active: bool = True
    created_at: Optional[str] = None


@dataclass
class RegisterWebhookRequest:
    url: str = ""
    events: Optional[List[str]] = None
    notification_level: Optional[str] = None


# =============================================================================
# Landing Rate Types
# =============================================================================


@dataclass
class LandingRatePeriod:
    start: str = ""
    end: str = ""


@dataclass
class SenderLandingRate:
    sender: str = ""
    total_sent: int = 0
    total_landed: int = 0
    landing_rate: float = 0.0


@dataclass
class RegionLandingRate:
    region: str = ""
    total_sent: int = 0
    total_landed: int = 0
    landing_rate: float = 0.0


@dataclass
class LandingRateStats:
    period: LandingRatePeriod = field(default_factory=LandingRatePeriod)
    total_sent: int = 0
    total_landed: int = 0
    landing_rate: float = 0.0
    by_sender: List[SenderLandingRate] = field(default_factory=list)
    by_region: List[RegionLandingRate] = field(default_factory=list)


@dataclass
class LandingRateOptions:
    """Options for querying landing rates."""
    start: Optional[str] = None
    end: Optional[str] = None


# =============================================================================
# Bundle Types
# =============================================================================


@dataclass
class BundleResult:
    """Result of a bundle submission."""
    bundle_id: str = ""
    accepted: bool = False
    signatures: List[str] = field(default_factory=list)
    sender_id: Optional[str] = None
    error: Optional[str] = None


@dataclass
class RpcError:
    """JSON-RPC error object."""
    code: int = 0
    message: str = ""
    data: Optional[Any] = None


@dataclass
class RpcResponse:
    """Raw JSON-RPC 2.0 response from the Solana RPC proxy."""
    jsonrpc: str = "2.0"
    id: Any = 1
    result: Optional[Any] = None
    error: Optional[RpcError] = None


@dataclass
class SimulationResult:
    """Result of simulating a transaction via the RPC proxy."""
    err: Optional[Any] = None
    """Error if simulation failed, None on success."""
    logs: List[str] = field(default_factory=list)
    """Program log messages."""
    units_consumed: int = 0
    """Compute units consumed."""
    return_data: Optional[Any] = None
    """Program return data (if any)."""
