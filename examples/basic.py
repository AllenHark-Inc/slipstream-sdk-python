"""
basic.py -- Connect to Slipstream and submit a transaction.

The SDK auto-discovers workers via the discovery service.
No manual endpoint configuration needed.
"""

import asyncio
import os

from slipstream import SlipstreamClient, SlipstreamError, config_builder


async def main() -> None:
    api_key = os.environ.get("SLIPSTREAM_API_KEY", "sk_test_example")

    # Build config -- discovery handles worker selection automatically
    config = (
        config_builder()
        .api_key(api_key)
        .region("us-east")  # optional: prefer a region
        .build()
    )

    # Connect (discovers workers, establishes WebSocket, falls back to HTTP)
    client = await SlipstreamClient.connect(config)
    print(f"Connected via {client.connection_status().protocol}")
    print(f"Region: {client.connection_status().region}")

    # Build your signed transaction bytes (placeholder)
    tx_bytes = b"\x00" * 64  # replace with real signed transaction

    try:
        result = await client.submit_transaction(tx_bytes)
        print(f"Transaction ID: {result.transaction_id}")
        print(f"Status: {result.status}")
        if result.signature:
            print(f"Signature: {result.signature}")
        if result.routing:
            print(f"Routed via: {result.routing.region} -> {result.routing.sender}")
            print(f"Total latency: {result.routing.total_latency_ms}ms")
    except SlipstreamError as e:
        print(f"Submission failed [{e.code}]: {e}")

    # Check performance metrics
    metrics = client.metrics()
    print(f"\nMetrics: {metrics.transactions_submitted} submitted, "
          f"{metrics.success_rate:.0%} success rate")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
