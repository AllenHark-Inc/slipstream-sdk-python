"""
AllenHarkSlipstream — Type definitions

All dataclasses and enums matching the Rust SDK API surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


# =============================================================================
# Configuration
# =============================================================================


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
    connection_timeout: int = 10_000
    max_retries: int = 3
    leader_hints: bool = True
    stream_tip_instructions: bool = False
    stream_priority_fees: bool = False
    protocol_timeouts: ProtocolTimeouts = field(default_factory=ProtocolTimeouts)
    priority_fee: PriorityFeeConfig = field(default_factory=PriorityFeeConfig)
    retry_backoff: BackoffStrategy = BackoffStrategy.EXPONENTIAL
    min_confidence: int = 70
    idle_timeout: Optional[int] = None


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
    leader_pubkey: Optional[str] = None
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
class SubmitOptions:
    broadcast_mode: bool = False
    preferred_sender: Optional[str] = None
    max_retries: int = 2
    timeout_ms: int = 30_000
    dedup_id: Optional[str] = None


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
    leader_pubkey: Optional[str] = None
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
