"""
advanced_config.py -- Demonstrate all ConfigBuilder options.

Most users only need api_key(). This example shows every available option.
"""

import asyncio
import os

from slipstream import SlipstreamClient, config_builder
from slipstream.types import (
    BackoffStrategy,
    PriorityFeeConfig,
    PriorityFeeSpeed,
    ProtocolTimeouts,
)


async def main() -> None:
    api_key = os.environ.get("SLIPSTREAM_API_KEY", "sk_test_example")

    config = (
        config_builder()
        # Required
        .api_key(api_key)

        # Region preference (optional -- discovery picks the best if omitted)
        .region("us-east")

        # Direct endpoint (optional -- skips discovery entirely)
        # .endpoint("http://worker-ip:9000")

        # Custom discovery URL (optional -- default is production)
        # .discovery_url("https://discovery.allenhark.network")

        # Connection settings
        .connection_timeout(10_000)  # 10 seconds
        .max_retries(3)
        .idle_timeout(60_000)        # disconnect after 60s idle

        # Streaming subscriptions activated on connect
        .leader_hints(True)
        .stream_tip_instructions(True)
        .stream_priority_fees(True)

        # Protocol timeouts
        .protocol_timeouts(ProtocolTimeouts(
            websocket=3_000,  # 3s WebSocket timeout
            http=5_000,       # 5s HTTP timeout
        ))

        # Priority fee configuration
        .priority_fee(PriorityFeeConfig(
            enabled=True,
            speed=PriorityFeeSpeed.FAST,  # SLOW, FAST, or ULTRA_FAST
            max_tip=0.01,                 # cap at 0.01 SOL
        ))

        # Retry strategy
        .retry_backoff(BackoffStrategy.EXPONENTIAL)  # or LINEAR

        # Minimum confidence for accepting leader hints (0-100)
        .min_confidence(70)

        .build()
    )

    client = await SlipstreamClient.connect(config)

    # Inspect the resolved configuration
    resolved = client.config()
    print(f"Region:          {resolved.region}")
    print(f"Endpoint:        {resolved.endpoint}")
    print(f"Max retries:     {resolved.max_retries}")
    print(f"Leader hints:    {resolved.leader_hints}")
    print(f"Priority fee:    {resolved.priority_fee.speed.value}")
    print(f"Backoff:         {resolved.retry_backoff.value}")
    print(f"Min confidence:  {resolved.min_confidence}")

    # Connection details
    status = client.connection_status()
    print(f"\nProtocol: {status.protocol}")
    print(f"State:    {status.state.value}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
