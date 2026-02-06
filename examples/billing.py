"""
billing.py -- Token balance, deposit address, usage history, and deposits.

Slipstream billing: 1 token = 1 query = 50,000 lamports = 0.00005 SOL.
Minimum deposit: $10 USD equivalent in SOL.
"""

import asyncio
import os

from slipstream import SlipstreamClient, config_builder
from slipstream.types import PaginationOptions


async def main() -> None:
    api_key = os.environ.get("SLIPSTREAM_API_KEY", "sk_test_example")

    config = config_builder().api_key(api_key).build()
    client = await SlipstreamClient.connect(config)

    # Check current token balance
    balance = await client.get_balance()
    print("=== Token Balance ===")
    print(f"  SOL:    {balance.balance_sol}")
    print(f"  Tokens: {balance.balance_tokens}")
    print(f"  Grace:  {balance.grace_remaining_tokens} tokens remaining")

    # Get deposit address to top up
    deposit_info = await client.get_deposit_address()
    print("\n=== Deposit Address ===")
    print(f"  Wallet:  {deposit_info.deposit_wallet}")
    print(f"  Minimum: {deposit_info.min_amount_sol} SOL")

    min_usd = SlipstreamClient.get_minimum_deposit_usd()
    print(f"  Min USD: ${min_usd:.2f}")

    # Check for pending (uncredited) deposits
    pending = await client.get_pending_deposit()
    print("\n=== Pending Deposits ===")
    print(f"  Amount:  {pending.pending_sol} SOL")
    print(f"  Count:   {pending.pending_count}")

    # View recent deposit history
    deposits = await client.get_deposit_history(PaginationOptions(limit=5))
    print("\n=== Recent Deposits ===")
    for d in deposits:
        status = "credited" if d.credited else "pending"
        print(f"  {d.amount_sol} SOL [{status}] sig={d.signature[:16]}...")

    # View recent usage (token transactions)
    usage = await client.get_usage_history(PaginationOptions(limit=10))
    print("\n=== Recent Usage ===")
    for entry in usage:
        print(f"  {entry.tx_type}: {entry.amount_lamports} lamports "
              f"(balance after: {entry.balance_after_lamports})")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
