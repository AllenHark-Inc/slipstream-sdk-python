"""
AllenHarkSlipstream — Configuration builder
"""

from __future__ import annotations

from typing import Optional

from .errors import SlipstreamError
from .types import (
    BackoffStrategy,
    BillingTier,
    PriorityFeeConfig,
    PriorityFeeSpeed,
    ProtocolTimeouts,
    SlipstreamConfig,
)


class ConfigBuilder:
    """Fluent configuration builder for SlipstreamClient."""

    def __init__(self) -> None:
        self._api_key: Optional[str] = None
        self._region: Optional[str] = None
        self._endpoint: Optional[str] = None
        self._discovery_url: Optional[str] = None
        self._tier: BillingTier = BillingTier.PRO
        self._connection_timeout: int = 10_000
        self._max_retries: int = 3
        self._leader_hints: bool = True
        self._stream_tip_instructions: bool = False
        self._stream_priority_fees: bool = False
        self._protocol_timeouts: ProtocolTimeouts = ProtocolTimeouts()
        self._priority_fee: PriorityFeeConfig = PriorityFeeConfig()
        self._retry_backoff: BackoffStrategy = BackoffStrategy.EXPONENTIAL
        self._min_confidence: int = 70
        self._idle_timeout: Optional[int] = None

    def api_key(self, key: str) -> ConfigBuilder:
        self._api_key = key
        return self

    def region(self, region: str) -> ConfigBuilder:
        self._region = region
        return self

    def endpoint(self, url: str) -> ConfigBuilder:
        self._endpoint = url
        return self

    def discovery_url(self, url: str) -> ConfigBuilder:
        self._discovery_url = url
        return self

    def tier(self, tier: BillingTier) -> ConfigBuilder:
        self._tier = tier
        return self

    def connection_timeout(self, ms: int) -> ConfigBuilder:
        self._connection_timeout = ms
        return self

    def max_retries(self, n: int) -> ConfigBuilder:
        self._max_retries = n
        return self

    def leader_hints(self, enabled: bool) -> ConfigBuilder:
        self._leader_hints = enabled
        return self

    def stream_tip_instructions(self, enabled: bool) -> ConfigBuilder:
        self._stream_tip_instructions = enabled
        return self

    def stream_priority_fees(self, enabled: bool) -> ConfigBuilder:
        self._stream_priority_fees = enabled
        return self

    def protocol_timeouts(self, timeouts: ProtocolTimeouts) -> ConfigBuilder:
        self._protocol_timeouts = timeouts
        return self

    def priority_fee(self, config: PriorityFeeConfig) -> ConfigBuilder:
        self._priority_fee = config
        return self

    def retry_backoff(self, strategy: BackoffStrategy) -> ConfigBuilder:
        self._retry_backoff = strategy
        return self

    def min_confidence(self, confidence: int) -> ConfigBuilder:
        self._min_confidence = confidence
        return self

    def idle_timeout(self, ms: int) -> ConfigBuilder:
        self._idle_timeout = ms
        return self

    def build(self) -> SlipstreamConfig:
        if not self._api_key:
            raise SlipstreamError.config("api_key is required")

        if self._min_confidence < 0 or self._min_confidence > 100:
            raise SlipstreamError.config("min_confidence must be between 0 and 100")

        from .discovery import DEFAULT_DISCOVERY_URL

        return SlipstreamConfig(
            api_key=self._api_key,
            region=self._region,
            endpoint=self._endpoint,
            discovery_url=self._discovery_url or DEFAULT_DISCOVERY_URL,
            tier=self._tier,
            connection_timeout=self._connection_timeout,
            max_retries=self._max_retries,
            leader_hints=self._leader_hints,
            stream_tip_instructions=self._stream_tip_instructions,
            stream_priority_fees=self._stream_priority_fees,
            protocol_timeouts=self._protocol_timeouts,
            priority_fee=self._priority_fee,
            retry_backoff=self._retry_backoff,
            min_confidence=self._min_confidence,
            idle_timeout=self._idle_timeout,
        )


def config_builder() -> ConfigBuilder:
    """Create a new ConfigBuilder instance."""
    return ConfigBuilder()


def get_http_endpoint(config: SlipstreamConfig) -> str:
    """Get the HTTP base URL from config.

    If an explicit endpoint is set, uses that.
    Otherwise, uses the discovery URL for control plane API calls.
    Worker connections are resolved via discovery in client.connect().
    """
    if config.endpoint:
        return config.endpoint.rstrip("/")
    return config.discovery_url.rstrip("/")


def get_ws_endpoint(config: SlipstreamConfig) -> str:
    """Get the WebSocket URL from config."""
    if config.endpoint:
        http_url = config.endpoint.rstrip("/")
        ws_url = http_url.replace("https://", "wss://").replace("http://", "ws://")
        return f"{ws_url}/ws"
    # Placeholder — real WS endpoint is resolved via discovery
    return ""
