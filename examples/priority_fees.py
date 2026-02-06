"""
priority_fees.py -- Configure and monitor priority fees.

Priority fees help transactions land faster during network congestion.
The SDK streams real-time fee recommendations from the Slipstream network.
"""

import asyncio
import os

from slipstream import SlipstreamClient, config_builder
from slipstream.types import PriorityFee, PriorityFeeConfig, PriorityFeeSpeed


async def main() -> None:
    api_key = os.environ.get("SLIPSTREAM_API_KEY", "sk_test_example")

    # Configure priority fees at the SDK level
    config = (
        config_builder()
        .api_key(api_key)
        .priority_fee(PriorityFeeConfig(
            enabled=True,
            speed=PriorityFeeSpeed.FAST,  # SLOW, FAST, or ULTRA_FAST
            max_tip=0.005,                # cap tip at 0.005 SOL
        ))
        .stream_priority_fees(True)  # auto-subscribe on connect
        .build()
    )

    client = await SlipstreamClient.connect(config)
    print("Connected -- streaming priority fee recommendations\n")

    # Track fee history for analysis
    fee_history: list[PriorityFee] = []

    def on_fee(fee: PriorityFee) -> None:
        fee_history.append(fee)
        congestion = fee.network_congestion
        icon = "!!!" if congestion == "high" else "..." if congestion == "low" else " ! "
        print(f"  [{icon}] {fee.speed:10s}  CU price={fee.compute_unit_price:>8d}  "
              f"limit={fee.compute_unit_limit:>7d}  "
              f"cost={fee.estimated_cost_sol:.6f} SOL  "
              f"landing={fee.landing_probability}%  "
              f"success={fee.recent_success_rate:.0%}")

    client.on("priority_fee", on_fee)

    # Collect data for a few seconds
    print("Speed       CU Price    CU Limit   Cost (SOL)      Landing  Success")
    print("-" * 80)

    try:
        await asyncio.sleep(10)
    except KeyboardInterrupt:
        pass

    # Summarize
    if fee_history:
        avg_price = sum(f.compute_unit_price for f in fee_history) / len(fee_history)
        avg_landing = sum(f.landing_probability for f in fee_history) / len(fee_history)
        print(f"\nSummary ({len(fee_history)} samples):")
        print(f"  Avg CU price:         {avg_price:.0f}")
        print(f"  Avg landing prob:     {avg_landing:.0f}%")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
