"""
deduplication.py -- Transaction deduplication patterns.

Slipstream uses vector clocks and logical timestamps for deduplication.
The SDK supports custom dedup IDs for idempotent transaction submission.
"""

import asyncio
import hashlib
import os

from slipstream import SlipstreamClient, SlipstreamError, config_builder
from slipstream.types import SubmitOptions


def compute_dedup_id(tx_bytes: bytes) -> str:
    """Derive a deterministic dedup ID from transaction bytes.

    Using a hash of the transaction ensures that resubmitting the same
    transaction produces the same dedup ID, so the server can detect
    duplicates even across client restarts.
    """
    return hashlib.sha256(tx_bytes).hexdigest()[:32]


async def submit_idempotent(
    client: SlipstreamClient,
    tx_bytes: bytes,
    label: str,
) -> None:
    """Submit a transaction with a deterministic dedup ID."""
    dedup_id = compute_dedup_id(tx_bytes)
    print(f"\n[{label}] Submitting with dedup_id={dedup_id[:16]}...")

    try:
        result = await client.submit_transaction_with_options(
            tx_bytes,
            SubmitOptions(dedup_id=dedup_id),
        )
        print(f"  Status: {result.status}")
        if result.status == "duplicate":
            print(f"  Server detected duplicate -- original ID: {result.transaction_id}")
        else:
            print(f"  Transaction ID: {result.transaction_id}")
    except SlipstreamError as e:
        print(f"  Error [{e.code}]: {e}")


async def main() -> None:
    api_key = os.environ.get("SLIPSTREAM_API_KEY", "sk_test_example")

    config = config_builder().api_key(api_key).build()
    client = await SlipstreamClient.connect(config)

    tx_bytes = b"\x00" * 64  # replace with real signed transaction

    # First submission -- should succeed
    await submit_idempotent(client, tx_bytes, "Attempt 1")

    # Second submission of the same transaction -- server detects duplicate
    await submit_idempotent(client, tx_bytes, "Attempt 2")

    # Different transaction -- different dedup ID, should succeed
    tx_bytes_2 = b"\x01" * 64
    await submit_idempotent(client, tx_bytes_2, "Different TX")

    # You can also let the server auto-generate dedup IDs by omitting dedup_id
    print("\n[Auto dedup] Submitting without explicit dedup_id...")
    try:
        result = await client.submit_transaction(tx_bytes)
        print(f"  Status: {result.status}")
        print(f"  Transaction ID: {result.transaction_id}")
    except SlipstreamError as e:
        print(f"  Error [{e.code}]: {e}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
