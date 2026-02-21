"""
streaming.py -- Subscribe to leader hints, tip instructions, and priority fees.

Streams arrive via WebSocket. The SDK reconnects automatically on disconnection.
"""

import asyncio
import os

from slipstream import SlipstreamClient, config_builder
from slipstream.types import LeaderHint, PriorityFee, TipInstruction


async def main() -> None:
    api_key = os.environ.get("SLIPSTREAM_API_KEY", "sk_test_example")

    # Enable all streams at config time so they activate on connect
    config = (
        config_builder()
        .api_key(api_key)
        .leader_hints(True)
        .stream_tip_instructions(True)
        .stream_priority_fees(True)
        .build()
    )

    client = await SlipstreamClient.connect(config)
    print("Connected -- listening for streams\n")

    # Leader hints arrive every ~250ms when confidence is above threshold
    def on_leader_hint(hint: LeaderHint) -> None:
        print(f"[Leader Hint] slot={hint.slot} region={hint.preferred_region} "
              f"confidence={hint.confidence}% leader={hint.leader_pubkey}")
        if hint.metadata.region_rtt_ms:
            for region, rtt in hint.metadata.region_rtt_ms.items():
                print(f"  {region}: {rtt}ms")

    # Tip instructions tell you the best sender and tip wallet
    def on_tip(tip: TipInstruction) -> None:
        print(f"[Tip] sender={tip.sender_name} wallet={tip.tip_wallet_address} "
              f"amount={tip.tip_amount_sol} SOL tier={tip.tip_tier} "
              f"latency={tip.expected_latency_ms}ms confidence={tip.confidence}% "
              f"valid_until={tip.valid_until_slot}")
        for alt in tip.alternative_senders:
            print(f"  alt: {alt.sender} @ {alt.tip_amount_sol} SOL ({alt.confidence}%)")

    # Priority fees update every ~1 second
    def on_fee(fee: PriorityFee) -> None:
        print(f"[Fee] speed={fee.speed} price={fee.compute_unit_price} "
              f"limit={fee.compute_unit_limit} landing={fee.landing_probability}%")

    client.on("leader_hint", on_leader_hint)
    client.on("tip_instruction", on_tip)
    client.on("priority_fee", on_fee)

    # Also get the cached latest tip at any time
    tip = client.get_latest_tip()
    if tip:
        print(f"Cached tip: {tip.sender_name} -> {tip.tip_wallet_address}")

    # Keep running until interrupted
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
