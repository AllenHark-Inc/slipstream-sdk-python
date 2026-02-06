[![allenhark.com](https://allenhark.com/allenhark-logo.png)](https://allenhark.com)

# Slipstream Python SDK

The official Python client for **AllenHark Slipstream**, the high-performance Solana transaction relay and intelligence network.

[![PyPI](https://img.shields.io/pypi/v/allenhark-slipstream.svg)](https://pypi.org/project/allenhark-slipstream/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

## Features

- **Discovery-based connection** -- auto-discovers workers, no manual endpoint configuration
- **Leader-proximity routing** -- real-time leader hints route transactions to the nearest region
- **Multi-region support** -- connect to workers across regions, auto-route based on leader schedule
- **Streaming subscriptions** -- leader hints, tip instructions, priority fees via WebSocket
- **Token billing** -- check balance, deposit SOL, view usage history
- **Protocol fallback** -- WebSocket with automatic HTTP fallback
- **Fully async** -- built on `asyncio` and `aiohttp`
- **Type hints** -- complete type coverage with dataclasses and enums
- **Python 3.9+**

## Installation

```bash
pip install allenhark-slipstream
```

## Quick Start

```python
import asyncio
from slipstream import SlipstreamClient, config_builder

async def main():
    # Connect with just an API key -- discovery handles the rest
    config = config_builder().api_key("sk_live_your_key_here").build()
    client = await SlipstreamClient.connect(config)

    # Submit a signed transaction
    result = await client.submit_transaction(tx_bytes)
    print(f"Submitted: {result.transaction_id} (status: {result.status})")

    # Check token balance
    balance = await client.get_balance()
    print(f"Balance: {balance.balance_sol} SOL ({balance.balance_tokens} tokens)")

    await client.disconnect()

asyncio.run(main())
```

## Configuration

Use `config_builder()` to create a `SlipstreamConfig`:

```python
from slipstream import config_builder
from slipstream.types import ProtocolTimeouts, PriorityFeeConfig, PriorityFeeSpeed, BackoffStrategy

config = (
    config_builder()
    .api_key("sk_live_your_key_here")
    .region("us-east")
    .min_confidence(80)
    .build()
)
```

### ConfigBuilder Reference

| Method | Type | Default | Description |
|--------|------|---------|-------------|
| `api_key(key)` | `str` | *required* | API key (must start with `sk_`) |
| `region(region)` | `str` | `None` | Preferred region for worker selection |
| `endpoint(url)` | `str` | `None` | Override discovery with a direct endpoint |
| `discovery_url(url)` | `str` | `https://discovery.slipstream.allenhark.com` | Custom discovery service URL |
| `connection_timeout(ms)` | `int` | `10000` | Connection timeout in milliseconds |
| `max_retries(n)` | `int` | `3` | Maximum retry attempts |
| `leader_hints(enabled)` | `bool` | `True` | Auto-subscribe to leader hints on connect |
| `stream_tip_instructions(enabled)` | `bool` | `False` | Auto-subscribe to tip instructions on connect |
| `stream_priority_fees(enabled)` | `bool` | `False` | Auto-subscribe to priority fees on connect |
| `protocol_timeouts(timeouts)` | `ProtocolTimeouts` | `ws=3000, http=5000` | Per-protocol timeout configuration |
| `priority_fee(config)` | `PriorityFeeConfig` | `enabled=False, speed=FAST` | Priority fee settings |
| `retry_backoff(strategy)` | `BackoffStrategy` | `EXPONENTIAL` | Retry backoff strategy (`LINEAR` or `EXPONENTIAL`) |
| `min_confidence(n)` | `int` | `70` | Minimum confidence (0-100) for leader hint acceptance |
| `idle_timeout(ms)` | `int` | `None` | Disconnect after idle period |

## Connecting

### Auto-Discovery (Recommended)

The SDK automatically discovers available workers through the discovery service. No manual endpoint configuration is needed:

```python
from slipstream import SlipstreamClient, config_builder

# Minimal -- discovery finds the best worker
config = config_builder().api_key("sk_live_xxx").build()
client = await SlipstreamClient.connect(config)

# Prefer a specific region
config = config_builder().api_key("sk_live_xxx").region("us-east").build()
client = await SlipstreamClient.connect(config)
```

### Direct Endpoint (Advanced)

Override discovery to connect to a specific worker:

```python
config = (
    config_builder()
    .api_key("sk_live_xxx")
    .endpoint("http://worker-ip:9000")
    .build()
)
client = await SlipstreamClient.connect(config)
```

## Transaction Submission

### Basic Submission

```python
result = await client.submit_transaction(tx_bytes)
print(f"ID: {result.transaction_id}")
print(f"Status: {result.status}")
print(f"Signature: {result.signature}")
```

### Submission with Options

```python
from slipstream.types import SubmitOptions

options = SubmitOptions(
    broadcast_mode=False,         # True to send to all regions
    preferred_sender=None,        # Specific sender ID, or None for auto
    max_retries=2,                # Retry attempts on failure
    timeout_ms=30_000,            # Timeout per attempt
    dedup_id="my-unique-id",      # Custom deduplication ID
)

result = await client.submit_transaction_with_options(tx_bytes, options)
```

### Transaction Result

The `TransactionResult` dataclass contains:

```python
result.request_id         # Internal request ID
result.transaction_id     # Slipstream transaction ID
result.signature          # Solana transaction signature (when confirmed)
result.status             # "pending", "sent", "confirmed", "failed", etc.
result.slot               # Solana slot (when confirmed)
result.timestamp          # Unix timestamp in milliseconds
result.routing            # RoutingInfo (region, sender, latencies)
result.error              # TransactionError (on failure)
```

## Streaming

### Leader Hints

Leader hints tell you which region is closest to the current Solana leader. They arrive every 250ms when confidence is above the threshold:

```python
def on_leader_hint(hint):
    print(f"Slot {hint.slot}: route to {hint.preferred_region}")
    print(f"  Leader: {hint.leader_pubkey}")
    print(f"  Confidence: {hint.confidence}%")
    print(f"  TPU RTT: {hint.metadata.tpu_rtt_ms}ms")

client.on("leader_hint", on_leader_hint)
await client.subscribe_leader_hints()
```

### Tip Instructions

Tip instructions provide the current best sender, tip wallet, and amount:

```python
def on_tip(tip):
    print(f"Sender: {tip.sender_name}")
    print(f"  Wallet: {tip.tip_wallet_address}")
    print(f"  Amount: {tip.tip_amount_sol} SOL")
    print(f"  Tier: {tip.tip_tier}")
    print(f"  Latency: {tip.expected_latency_ms}ms")

client.on("tip_instruction", on_tip)
await client.subscribe_tip_instructions()
```

You can also get the latest cached tip without subscribing:

```python
tip = client.get_latest_tip()
```

### Priority Fees

Priority fee recommendations update every second:

```python
def on_fee(fee):
    print(f"Speed: {fee.speed}")
    print(f"  CU price: {fee.compute_unit_price}")
    print(f"  CU limit: {fee.compute_unit_limit}")
    print(f"  Cost: {fee.estimated_cost_sol} SOL")
    print(f"  Landing probability: {fee.landing_probability}%")

client.on("priority_fee", on_fee)
await client.subscribe_priority_fees()
```

### Auto-Subscribe on Connect

Enable streaming subscriptions at configuration time so they activate immediately on connect:

```python
config = (
    config_builder()
    .api_key("sk_live_xxx")
    .leader_hints(True)                  # default True
    .stream_tip_instructions(True)       # default False
    .stream_priority_fees(True)          # default False
    .build()
)

client = await SlipstreamClient.connect(config)
# Streams are already active -- just register listeners
client.on("leader_hint", on_leader_hint)
client.on("tip_instruction", on_tip)
client.on("priority_fee", on_fee)
```

## Token Billing

Slipstream uses a token-based billing system. 1 token = 1 query = 50,000 lamports = 0.00005 SOL. Minimum deposit is $10 USD equivalent in SOL.

### Check Balance

```python
balance = await client.get_balance()
print(f"SOL:    {balance.balance_sol}")
print(f"Tokens: {balance.balance_tokens}")
print(f"Grace:  {balance.grace_remaining_tokens}")
```

### Get Deposit Address

```python
deposit = await client.get_deposit_address()
print(f"Send SOL to: {deposit.deposit_wallet}")
print(f"Minimum:     {deposit.min_amount_sol} SOL")
```

### View Usage History

```python
from slipstream.types import PaginationOptions

entries = await client.get_usage_history(PaginationOptions(limit=50))
for entry in entries:
    print(f"  {entry.tx_type}: {entry.amount_lamports} lamports")
```

### Deposit History and Pending Deposits

```python
deposits = await client.get_deposit_history()
for d in deposits:
    print(f"  {d.amount_sol} SOL (credited: {d.credited})")

pending = await client.get_pending_deposit()
print(f"Pending: {pending.pending_sol} SOL ({pending.pending_count} deposits)")
```

### Minimum Deposit

```python
min_usd = SlipstreamClient.get_minimum_deposit_usd()  # $10.00
```

## Multi-Region Routing

The `MultiRegionClient` connects to workers across multiple regions and automatically routes transactions to the region closest to the current Solana leader:

### Auto-Discovery

```python
from slipstream import MultiRegionClient, config_builder

config = config_builder().api_key("sk_live_xxx").build()
multi = await MultiRegionClient.connect(config)

# Transactions are auto-routed to the best region
result = await multi.submit_transaction(tx_bytes)

print(f"Connected regions: {multi.connected_regions()}")
await multi.disconnect_all()
```

### Manual Worker Configuration

```python
from slipstream import MultiRegionClient, config_builder
from slipstream.types import WorkerEndpoint, MultiRegionConfig

config = config_builder().api_key("sk_live_xxx").build()

workers = [
    WorkerEndpoint(id="w1", region="us-east", http="http://10.0.1.1:9000"),
    WorkerEndpoint(id="w2", region="eu-central", http="http://10.0.2.1:9000"),
    WorkerEndpoint(id="w3", region="asia-pacific", http="http://10.0.3.1:9000"),
]

multi = await MultiRegionClient.create(
    config,
    workers,
    MultiRegionConfig(
        auto_follow_leader=True,
        min_switch_confidence=70,
        switch_cooldown_ms=5000,
        broadcast_high_priority=False,
        max_broadcast_regions=3,
    ),
)

result = await multi.submit_transaction(tx_bytes)
```

### Routing Events

```python
def on_routing_update(recommendation):
    print(f"Routing to: {recommendation.best_region}")
    print(f"  Leader: {recommendation.leader_pubkey}")
    print(f"  RTT: {recommendation.expected_rtt_ms}ms")

multi.on("routing_update", on_routing_update)
```

### Broadcast Mode

Send a transaction to multiple regions simultaneously:

```python
from slipstream.types import SubmitOptions

result = await multi.submit_transaction_with_options(
    tx_bytes,
    SubmitOptions(broadcast_mode=True),
)
```

## Error Handling

All SDK errors extend `SlipstreamError` with a `code` and `message`:

```python
from slipstream import SlipstreamError

try:
    result = await client.submit_transaction(tx_bytes)
except SlipstreamError as e:
    print(f"Error [{e.code}]: {e}")
    # Error codes: CONFIG, CONNECTION, AUTH, PROTOCOL, TRANSACTION,
    #              TIMEOUT, RATE_LIMITED, NOT_CONNECTED, STREAM_CLOSED,
    #              INSUFFICIENT_TOKENS, ALL_PROTOCOLS_FAILED, INTERNAL
```

### Common Error Scenarios

```python
try:
    client = await SlipstreamClient.connect(config)
except SlipstreamError as e:
    if e.code == "CONNECTION":
        print("No healthy workers available")
    elif e.code == "AUTH":
        print("Invalid API key")

try:
    result = await client.submit_transaction(tx_bytes)
except SlipstreamError as e:
    if e.code == "INSUFFICIENT_TOKENS":
        balance = await client.get_balance()
        deposit = await client.get_deposit_address()
        print(f"Low balance: {balance.balance_tokens} tokens")
        print(f"Deposit SOL to: {deposit.deposit_wallet}")
    elif e.code == "RATE_LIMITED":
        print("Slow down -- rate limit exceeded")
    elif e.code == "TIMEOUT":
        print("Transaction timed out")
```

## Connection Status and Metrics

```python
# Connection status
status = client.connection_status()
print(f"State: {status.state}")       # connected, disconnected, etc.
print(f"Protocol: {status.protocol}") # ws or http
print(f"Region: {status.region}")
print(f"Latency: {status.latency_ms}ms")

# Performance metrics
metrics = client.metrics()
print(f"Submitted: {metrics.transactions_submitted}")
print(f"Confirmed: {metrics.transactions_confirmed}")
print(f"Avg latency: {metrics.average_latency_ms:.1f}ms")
print(f"Success rate: {metrics.success_rate:.1%}")
```

## Routing Recommendation

Ask the server for the current best region:

```python
rec = await client.get_routing_recommendation()
print(f"Best region: {rec.best_region}")
print(f"Leader: {rec.leader_pubkey}")
print(f"Confidence: {rec.confidence}%")
print(f"Fallbacks: {rec.fallback_regions}")
```

## Events

Register listeners with `client.on(event, callback)` and remove with `client.off(event, callback)`. Callbacks can be sync or async functions.

| Event | Payload | Description |
|-------|---------|-------------|
| `leader_hint` | `LeaderHint` | Region recommendation update |
| `tip_instruction` | `TipInstruction` | Tip wallet/amount update |
| `priority_fee` | `PriorityFee` | Priority fee recommendation |
| `transaction_update` | `TransactionResult` | Transaction status change |
| `connected` | -- | WebSocket connected |
| `disconnected` | -- | WebSocket disconnected |
| `error` | `Exception` | Transport error |

## Examples

| File | Description |
|------|-------------|
| [`examples/basic.py`](examples/basic.py) | Connect and submit a transaction |
| [`examples/streaming.py`](examples/streaming.py) | Leader hints, tips, and priority fee streams |
| [`examples/billing.py`](examples/billing.py) | Balance, deposits, and usage history |
| [`examples/multi_region.py`](examples/multi_region.py) | Multi-region auto-routing |
| [`examples/advanced_config.py`](examples/advanced_config.py) | All ConfigBuilder options |
| [`examples/submit_transaction.py`](examples/submit_transaction.py) | Transaction with SubmitOptions |
| [`examples/priority_fees.py`](examples/priority_fees.py) | Priority fee configuration and monitoring |
| [`examples/deduplication.py`](examples/deduplication.py) | Deduplication patterns |

## License

Apache-2.0
