"""
submit_transaction.py -- Submit transactions with various options.

Demonstrates SubmitOptions for controlling retry behavior, timeouts,
preferred senders, broadcast mode, and custom dedup IDs.
"""

import asyncio
import os

from slipstream import SlipstreamClient, SlipstreamError, config_builder
from slipstream.types import SubmitOptions


async def main() -> None:
    api_key = os.environ.get("SLIPSTREAM_API_KEY", "sk_test_example")

    config = config_builder().api_key(api_key).build()
    client = await SlipstreamClient.connect(config)

    tx_bytes = b"\x00" * 64  # replace with real signed transaction

    # 1. Simple submission (default options)
    print("=== Default Submit ===")
    try:
        result = await client.submit_transaction(tx_bytes)
        print(f"  ID: {result.transaction_id}  Status: {result.status}")
    except SlipstreamError as e:
        print(f"  Error: {e}")

    # 2. With a preferred sender
    print("\n=== Preferred Sender ===")
    try:
        result = await client.submit_transaction_with_options(
            tx_bytes,
            SubmitOptions(preferred_sender="nozomi"),
        )
        print(f"  Routed to sender: {result.routing.sender if result.routing else 'unknown'}")
    except SlipstreamError as e:
        print(f"  Error: {e}")

    # 3. Fast timeout with extra retries
    print("\n=== Fast Timeout + Retries ===")
    try:
        result = await client.submit_transaction_with_options(
            tx_bytes,
            SubmitOptions(timeout_ms=5_000, max_retries=5),
        )
        print(f"  Status: {result.status}")
    except SlipstreamError as e:
        print(f"  Error: {e}")

    # 4. Broadcast to all regions
    print("\n=== Broadcast Mode ===")
    try:
        result = await client.submit_transaction_with_options(
            tx_bytes,
            SubmitOptions(broadcast_mode=True),
        )
        print(f"  Status: {result.status}")
    except SlipstreamError as e:
        print(f"  Error: {e}")

    # Inspect routing details from the last result
    if result and result.routing:
        r = result.routing
        print(f"\n=== Routing Details ===")
        print(f"  Region:          {r.region}")
        print(f"  Sender:          {r.sender}")
        print(f"  Routing latency: {r.routing_latency_ms}ms")
        print(f"  Sender latency:  {r.sender_latency_ms}ms")
        print(f"  Total latency:   {r.total_latency_ms}ms")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
