"""
multi_region.py -- Multi-region client with leader-aware auto-routing.

MultiRegionClient connects to workers across regions and automatically routes
transactions to the region closest to the current Solana leader.
"""

import asyncio
import os

from slipstream import MultiRegionClient, SlipstreamError, config_builder
from slipstream.types import MultiRegionConfig, RoutingRecommendation, SubmitOptions


async def main() -> None:
    api_key = os.environ.get("SLIPSTREAM_API_KEY", "sk_test_example")

    config = config_builder().api_key(api_key).build()

    # Auto-discover workers across all regions
    multi = await MultiRegionClient.connect(
        config,
        MultiRegionConfig(
            auto_follow_leader=True,     # switch regions based on leader hints
            min_switch_confidence=70,    # only switch when confidence >= 70%
            switch_cooldown_ms=5000,     # wait 5s between region switches
            max_broadcast_regions=3,     # max regions for broadcast mode
        ),
    )

    print(f"Connected to regions: {multi.connected_regions()}")

    # Listen for routing changes
    def on_routing(rec: RoutingRecommendation) -> None:
        print(f"[Routing] -> {rec.best_region} (leader={rec.leader_pubkey}, "
              f"rtt={rec.expected_rtt_ms}ms, confidence={rec.confidence}%)")

    multi.on("routing_update", on_routing)

    # Submit -- auto-routes to the best region
    tx_bytes = b"\x00" * 64  # replace with real signed transaction

    try:
        result = await multi.submit_transaction(tx_bytes)
        print(f"Submitted: {result.transaction_id} (status: {result.status})")
    except SlipstreamError as e:
        print(f"Error [{e.code}]: {e}")

    # Broadcast to all regions for high-priority transactions
    try:
        result = await multi.submit_transaction_with_options(
            tx_bytes,
            SubmitOptions(broadcast_mode=True),
        )
        print(f"Broadcast result: {result.transaction_id}")
    except SlipstreamError as e:
        print(f"Broadcast error [{e.code}]: {e}")

    # Check current routing recommendation
    routing = multi.get_current_routing()
    if routing:
        print(f"\nCurrent routing: {routing.best_region}")
        print(f"  Fallbacks: {routing.fallback_regions}")

    await multi.disconnect_all()


if __name__ == "__main__":
    asyncio.run(main())
