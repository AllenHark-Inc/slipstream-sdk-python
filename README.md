[![allenhark.com](https://allenhark.com/allenhark-logo.png)](https://allenhark.com)

# Slipstream Python SDK

The official Python client for **AllenHark Slipstream**, the high-performance Solana transaction relay and intelligence network.

[![PyPI](https://img.shields.io/pypi/v/allenhark-slipstream.svg)](https://pypi.org/project/allenhark-slipstream/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

## Features

- **Discovery-based connection** -- auto-discovers workers, no manual endpoint configuration
- **Leader-proximity routing** -- real-time leader hints route transactions to the nearest region
- **Multi-region support** -- connect to workers across regions, auto-route based on leader schedule
- **6 real-time streams** -- leader hints, tip instructions, priority fees, latest blockhash, latest slot, transaction updates
- **Stream billing** -- each stream costs 1 token; 1-hour reconnect grace period
- **Billing tiers** -- Free (100 tx/day), Standard, Pro, Enterprise with tier-specific rate limits and pricing
- **Token billing** -- check balance, deposit SOL, view usage and deposit history
- **Keep-alive & time sync** -- background ping with RTT measurement and NTP-style clock synchronization
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
    client = await SlipstreamClient.connect(
        config_builder().api_key("sk_live_your_key_here").build()
    )

    # Submit a signed transaction
    result = await client.submit_transaction(tx_bytes)
    print(f"TX: {result.transaction_id} ({result.status})")

    # Check balance
    balance = await client.get_balance()
    print(f"Balance: {balance.balance_tokens} tokens")

    await client.disconnect()

asyncio.run(main())
```

---

## Configuration

### ConfigBuilder Reference

Use `config_builder()` to create a `SlipstreamConfig`. Only `api_key` is required.

```python
from slipstream import config_builder
from slipstream.types import BillingTier, PriorityFeeConfig, PriorityFeeSpeed

config = (
    config_builder()
    .api_key("sk_live_your_key_here")
    .region("us-east")
    .tier(BillingTier.PRO)
    .min_confidence(80)
    .build()
)
```

| Method | Type | Default | Description |
|--------|------|---------|-------------|
| `api_key(key)` | `str` | **required** | API key (must start with `sk_`) |
| `region(region)` | `str` | `None` | Preferred region (e.g., `"us-east"`, `"eu-central"`) |
| `endpoint(url)` | `str` | `None` | Override discovery with explicit worker endpoint |
| `discovery_url(url)` | `str` | `https://discovery.slipstream.allenhark.com` | Custom discovery service URL |
| `tier(tier)` | `BillingTier` | `BillingTier.PRO` | Billing tier: `FREE`, `STANDARD`, `PRO`, `ENTERPRISE` |
| `connection_timeout(ms)` | `int` | `10000` | Connection timeout in milliseconds |
| `max_retries(n)` | `int` | `3` | Maximum retry attempts for failed requests |
| `leader_hints(enabled)` | `bool` | `True` | Auto-subscribe to leader hint stream on connect |
| `stream_tip_instructions(enabled)` | `bool` | `False` | Auto-subscribe to tip instruction stream on connect |
| `stream_priority_fees(enabled)` | `bool` | `False` | Auto-subscribe to priority fee stream on connect |
| `stream_latest_blockhash(enabled)` | `bool` | `False` | Auto-subscribe to latest blockhash stream on connect |
| `stream_latest_slot(enabled)` | `bool` | `False` | Auto-subscribe to latest slot stream on connect |
| `protocol_timeouts(timeouts)` | `ProtocolTimeouts` | `ws=3000, http=5000` | Per-protocol timeout in ms |
| `priority_fee(config)` | `PriorityFeeConfig` | `enabled=False, speed=FAST` | Priority fee optimization (see below) |
| `retry_backoff(strategy)` | `BackoffStrategy` | `EXPONENTIAL` | Retry backoff: `LINEAR` or `EXPONENTIAL` |
| `min_confidence(n)` | `int` | `70` | Minimum confidence (0-100) for leader hint routing |
| `keep_alive(enabled)` | `bool` | `True` | Enable background keep-alive ping loop |
| `keep_alive_interval(secs)` | `float` | `5.0` | Keep-alive ping interval in seconds |
| `idle_timeout(ms)` | `int` | `None` | Disconnect after idle period |

### Billing Tiers

Each API key has a billing tier that determines transaction cost, rate limits, and priority queuing. Set the tier to match your API key's assigned tier:

```python
from slipstream.types import BillingTier

config = (
    config_builder()
    .api_key("sk_live_your_key_here")
    .tier(BillingTier.PRO)   # FREE, STANDARD, PRO, or ENTERPRISE
    .build()
)
```

| Tier | Cost per TX | Cost per Stream | Rate Limit | Burst | Priority Slots | Daily Limit |
|------|------------|-----------------|------------|-------|----------------|-------------|
| **FREE** | 0 (counter) | 0 (counter) | 5 rps | 10 | 5 concurrent | 100 tx/day |
| **STANDARD** | 50,000 lamports (0.00005 SOL) | 50,000 lamports | 5 rps | 10 | 10 concurrent | Unlimited |
| **PRO** | 100,000 lamports (0.0001 SOL) | 50,000 lamports | 20 rps | 50 | 50 concurrent | Unlimited |
| **ENTERPRISE** | 1,000,000 lamports (0.001 SOL) | 50,000 lamports | 100 rps | 200 | 200 concurrent | Unlimited |

- **Free tier**: Uses a daily counter instead of token billing. Transactions and stream subscriptions both decrement the counter. Resets at UTC midnight.
- **Standard/Pro/Enterprise**: Deducted from token balance per transaction. Stream subscriptions cost 1 token each with a 1-hour reconnect grace period.

### PriorityFeeConfig

Controls automatic priority fee optimization for transactions.

```python
from slipstream.types import PriorityFeeConfig, PriorityFeeSpeed

config = (
    config_builder()
    .api_key("sk_live_your_key_here")
    .priority_fee(PriorityFeeConfig(
        enabled=True,
        speed=PriorityFeeSpeed.ULTRA_FAST,
        max_tip=0.01,  # Max 0.01 SOL
    ))
    .build()
)
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | `bool` | `False` | Enable automatic priority fee optimization |
| `speed` | `PriorityFeeSpeed` | `FAST` | Fee tier: `SLOW`, `FAST`, or `ULTRA_FAST` |
| `max_tip` | `Optional[float]` | `None` | Maximum tip in SOL (caps the priority fee) |

**PriorityFeeSpeed tiers:**

| Speed | Compute Unit Price | Landing Probability | Use Case |
|-------|-------------------|--------------------|---------|
| `SLOW` | Low | ~60-70% | Cost-sensitive, non-urgent transactions |
| `FAST` | Medium | ~85-90% | Default balance of cost and speed |
| `ULTRA_FAST` | High | ~95-99% | Time-critical trading, MEV protection |

### ProtocolTimeouts

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `websocket` | `int` | `3000` | WebSocket connection timeout (ms) |
| `http` | `int` | `5000` | HTTP request timeout (ms) |

### Protocol Fallback Chain

**WebSocket** (3s) -> **HTTP** (5s)

---

## Connecting

### Auto-Discovery (Recommended)

```python
from slipstream import SlipstreamClient, config_builder

# Minimal -- discovery finds the best worker
config = config_builder().api_key("sk_live_xxx").build()
client = await SlipstreamClient.connect(config)

# With region preference
config = config_builder().api_key("sk_live_xxx").region("us-east").build()
client = await SlipstreamClient.connect(config)
```

### Direct Endpoint (Advanced)

```python
config = (
    config_builder()
    .api_key("sk_live_xxx")
    .endpoint("http://worker-ip:9000")
    .build()
)
client = await SlipstreamClient.connect(config)
```

### Connection Info

```python
info = client.connection_info()
print(f"Session: {info.session_id}")
print(f"Protocol: {info.protocol}")   # "ws" or "http"
print(f"Region: {info.region}")
print(f"Rate limit: {info.rate_limit.rps} rps (burst: {info.rate_limit.burst})")
```

---

## Transaction Submission

### Basic Submit

```python
result = await client.submit_transaction(tx_bytes)
print(f"TX ID: {result.transaction_id}")
print(f"Status: {result.status}")
print(f"Signature: {result.signature}")
```

### Submit with Options

```python
from slipstream.types import SubmitOptions

result = await client.submit_transaction_with_options(tx_bytes, SubmitOptions(
    broadcast_mode=True,          # Fan-out to multiple regions
    preferred_sender="nozomi",    # Prefer a specific sender
    max_retries=5,                # Override default retry count
    timeout_ms=10_000,            # Custom timeout
    dedup_id="my-unique-id",      # Custom deduplication ID
))
```

#### SubmitOptions Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `broadcast_mode` | `bool` | `False` | Fan-out to multiple regions simultaneously |
| `preferred_sender` | `Optional[str]` | `None` | Prefer a specific sender (e.g., `"nozomi"`, `"0slot"`) |
| `max_retries` | `int` | `2` | Retry attempts on failure |
| `timeout_ms` | `int` | `30000` | Timeout per attempt in milliseconds |
| `dedup_id` | `Optional[str]` | `None` | Custom deduplication ID (prevents double-submit) |

### TransactionResult Fields

| Field | Type | Description |
|-------|------|-------------|
| `request_id` | `str` | Internal request ID |
| `transaction_id` | `str` | Slipstream transaction ID |
| `signature` | `Optional[str]` | Solana transaction signature (base58, when confirmed) |
| `status` | `str` | Current status (see table below) |
| `slot` | `Optional[int]` | Solana slot (when confirmed) |
| `timestamp` | `int` | Unix timestamp in milliseconds |
| `routing` | `Optional[RoutingInfo]` | Routing details (region, sender, latencies) |
| `error` | `Optional[TransactionError]` | Error details (on failure) |

### TransactionStatus Values

| Status | Description |
|--------|-------------|
| `"pending"` | Received, not yet processed |
| `"processing"` | Being validated and routed |
| `"sent"` | Forwarded to sender |
| `"confirmed"` | Confirmed on Solana |
| `"failed"` | Failed permanently |
| `"duplicate"` | Deduplicated (already submitted) |
| `"rate_limited"` | Rate limit exceeded for your tier |
| `"insufficient_tokens"` | Token balance too low (or free tier daily limit reached) |

### RoutingInfo Fields

| Field | Type | Description |
|-------|------|-------------|
| `region` | `str` | Region that handled the transaction |
| `sender` | `str` | Sender service used |
| `routing_latency_ms` | `int` | Time spent in routing logic (ms) |
| `sender_latency_ms` | `int` | Time spent in sender submission (ms) |
| `total_latency_ms` | `int` | Total end-to-end latency (ms) |

---

## Streaming

Real-time data feeds over WebSocket. Register callbacks with `client.on(event, callback)`, remove with `client.off(event, callback)`. Callbacks can be sync or async.

**Billing:** Each stream subscription costs **1 token (0.00005 SOL)**. If the SDK reconnects within 1 hour for the same stream, no re-billing occurs (reconnect grace period). Free-tier keys deduct from the daily counter instead of tokens.

### Leader Hints

Which region is closest to the current Solana leader. Emitted every 250ms when confidence >= threshold.

```python
def on_leader_hint(hint):
    print(f"Slot {hint.slot}: route to {hint.preferred_region}")
    print(f"  Leader: {hint.leader_pubkey}")
    print(f"  Confidence: {hint.confidence}%")
    print(f"  TPU RTT: {hint.metadata.tpu_rtt_ms}ms")
    print(f"  Backups: {hint.backup_regions}")

client.on("leader_hint", on_leader_hint)
await client.subscribe_leader_hints()
```

#### LeaderHint Fields

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | `int` | Unix millis |
| `slot` | `int` | Current slot |
| `expires_at_slot` | `int` | Slot when this hint expires |
| `preferred_region` | `str` | Best region for current leader |
| `backup_regions` | `List[str]` | Fallback regions in priority order |
| `confidence` | `int` | Confidence score (0-100) |
| `leader_pubkey` | `str` | Current leader validator pubkey |
| `metadata.tpu_rtt_ms` | `int` | RTT to leader's TPU from preferred region (ms) |
| `metadata.region_score` | `float` | Region quality score |
| `metadata.leader_tpu_address` | `Optional[str]` | Leader's TPU address (ip:port) |
| `metadata.region_rtt_ms` | `Optional[Dict[str, int]]` | Per-region RTT to leader |

### Tip Instructions

Wallet address and tip amount for building transactions in streaming tip mode.

```python
def on_tip(tip):
    print(f"Sender: {tip.sender_name} ({tip.sender})")
    print(f"  Wallet: {tip.tip_wallet_address}")
    print(f"  Amount: {tip.tip_amount_sol} SOL (tier: {tip.tip_tier})")
    print(f"  Latency: {tip.expected_latency_ms}ms, Confidence: {tip.confidence}%")
    for alt in tip.alternative_senders:
        print(f"  Alt: {alt.sender} @ {alt.tip_amount_sol} SOL")

client.on("tip_instruction", on_tip)
await client.subscribe_tip_instructions()

# Latest cached tip (no subscription required)
tip = client.get_latest_tip()
```

#### TipInstruction Fields

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | `int` | Unix millis |
| `sender` | `str` | Sender ID |
| `sender_name` | `str` | Human-readable sender name |
| `tip_wallet_address` | `str` | Tip wallet address (base58) |
| `tip_amount_sol` | `float` | Required tip amount in SOL |
| `tip_tier` | `str` | Tip tier name |
| `expected_latency_ms` | `int` | Expected submission latency (ms) |
| `confidence` | `int` | Confidence score (0-100) |
| `valid_until_slot` | `int` | Slot until which this tip is valid |
| `alternative_senders` | `List[AlternativeSender]` | Alternative sender options (`sender`, `tip_amount_sol`, `confidence`) |

### Priority Fees

Network-condition-based fee recommendations, updated every second.

```python
def on_fee(fee):
    print(f"Speed: {fee.speed}")
    print(f"  CU price: {fee.compute_unit_price} micro-lamports")
    print(f"  CU limit: {fee.compute_unit_limit}")
    print(f"  Est cost: {fee.estimated_cost_sol} SOL")
    print(f"  Landing probability: {fee.landing_probability}%")
    print(f"  Congestion: {fee.network_congestion}")
    print(f"  Recent success rate: {fee.recent_success_rate:.1%}")

client.on("priority_fee", on_fee)
await client.subscribe_priority_fees()
```

#### PriorityFee Fields

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | `int` | Unix millis |
| `speed` | `str` | Fee speed tier (`"slow"`, `"fast"`, `"ultra_fast"`) |
| `compute_unit_price` | `int` | Compute unit price in micro-lamports |
| `compute_unit_limit` | `int` | Recommended compute unit limit |
| `estimated_cost_sol` | `float` | Estimated total priority fee in SOL |
| `landing_probability` | `int` | Estimated landing probability (0-100) |
| `network_congestion` | `str` | Network congestion level (`"low"`, `"medium"`, `"high"`) |
| `recent_success_rate` | `float` | Recent success rate (0.0-1.0) |

### Latest Blockhash

Streams the latest blockhash every 2 seconds. Build transactions without a separate RPC call.

```python
def on_blockhash(bh):
    print(f"Blockhash: {bh.blockhash}")
    print(f"  Valid until block height: {bh.last_valid_block_height}")

client.on("latest_blockhash", on_blockhash)
await client.subscribe_latest_blockhash()
```

#### LatestBlockhash Fields

| Field | Type | Description |
|-------|------|-------------|
| `blockhash` | `str` | Latest blockhash (base58) |
| `last_valid_block_height` | `int` | Last valid block height for this blockhash |
| `timestamp` | `int` | Unix millis when fetched |

### Latest Slot

Streams the current confirmed slot on every slot change (~400ms).

```python
def on_slot(data):
    print(f"Current slot: {data.slot}")

client.on("latest_slot", on_slot)
await client.subscribe_latest_slot()
```

#### LatestSlot Fields

| Field | Type | Description |
|-------|------|-------------|
| `slot` | `int` | Current confirmed slot number |
| `timestamp` | `int` | Unix millis |

### Transaction Updates

Real-time status updates for submitted transactions.

```python
def on_tx_update(update):
    print(f"TX {update.transaction_id}: {update.status}")
    if update.routing:
        print(f"  Routed via {update.routing.region} -> {update.routing.sender}")

client.on("transaction_update", on_tx_update)
```

### Auto-Subscribe on Connect

Enable streams at configuration time so they activate immediately:

```python
config = (
    config_builder()
    .api_key("sk_live_xxx")
    .leader_hints(True)                  # default: True
    .stream_tip_instructions(True)       # default: False
    .stream_priority_fees(True)          # default: False
    .stream_latest_blockhash(True)       # default: False
    .stream_latest_slot(True)            # default: False
    .build()
)

client = await SlipstreamClient.connect(config)
# All 5 streams are active -- just register listeners
client.on("leader_hint", on_leader_hint)
client.on("tip_instruction", on_tip)
client.on("priority_fee", on_fee)
client.on("latest_blockhash", on_blockhash)
client.on("latest_slot", on_slot)
```

### All Events

| Event | Payload | Description |
|-------|---------|-------------|
| `leader_hint` | `LeaderHint` | Region recommendation update (every 250ms) |
| `tip_instruction` | `TipInstruction` | Tip wallet/amount update |
| `priority_fee` | `PriorityFee` | Priority fee recommendation (every 1s) |
| `latest_blockhash` | `LatestBlockhash` | Latest blockhash (every 2s) |
| `latest_slot` | `LatestSlot` | Current confirmed slot (~400ms) |
| `transaction_update` | `TransactionResult` | Transaction status change |
| `connected` | -- | WebSocket connected |
| `disconnected` | -- | WebSocket disconnected |
| `ping` | `PingResult` | Keep-alive ping result (RTT, clock offset) |
| `error` | `Exception` | Transport error |

---

## Keep-Alive & Time Sync

Background keep-alive mechanism providing latency measurement and NTP-style clock synchronization.

```python
# Enabled by default (5s interval)
config = (
    config_builder()
    .api_key("sk_live_your_key_here")
    .keep_alive(True)              # default: True
    .keep_alive_interval(5.0)      # default: 5.0 seconds
    .build()
)

client = await SlipstreamClient.connect(config)

# Manual ping
ping = await client.ping()
print(f"RTT: {ping.rtt_ms}ms, Clock offset: {ping.clock_offset_ms}ms")

# Derived measurements (median from sliding window of 10 samples)
latency = client.latency_ms()       # int | None (RTT / 2)
offset = client.clock_offset_ms()   # int | None
server_now = client.server_time()   # int (unix ms, local time + offset)

# Listen for ping events
def on_ping(result):
    print(f"Ping #{result.seq}: RTT {result.rtt_ms}ms, offset {result.clock_offset_ms}ms")

client.on("ping", on_ping)
```

#### PingResult Fields

| Field | Type | Description |
|-------|------|-------------|
| `seq` | `int` | Sequence number |
| `rtt_ms` | `int` | Round-trip time in milliseconds |
| `clock_offset_ms` | `int` | Clock offset: `server_time - (client_send_time + rtt/2)` (can be negative) |
| `server_time` | `int` | Server timestamp at time of pong (unix millis) |

---

## Token Billing

Token-based billing system. Paid tiers (Standard/Pro/Enterprise) deduct tokens per transaction and stream subscription. Free tier uses a daily counter.

### Token Economics

| Unit | Value |
|------|-------|
| 1 token | 1 transaction (Standard tier) |
| 1 token | 50,000 lamports |
| 1 token | 0.00005 SOL |
| 1 stream subscription | 1 token (with 1-hour reconnect grace) |
| Min deposit | $10 USD equivalent in SOL |
| Initial balance (new key) | 0.01 SOL (200 tokens) |
| Grace period | -0.001 SOL (-20 tokens) before hard block |

### Check Balance

```python
balance = await client.get_balance()
print(f"SOL:    {balance.balance_sol}")
print(f"Tokens: {balance.balance_tokens}")
print(f"Lamports: {balance.balance_lamports}")
print(f"Grace remaining: {balance.grace_remaining_tokens} tokens")
```

#### Balance Fields

| Field | Type | Description |
|-------|------|-------------|
| `balance_sol` | `float` | Balance in SOL |
| `balance_tokens` | `int` | Balance in tokens (1 token = 1 query) |
| `balance_lamports` | `int` | Balance in lamports |
| `grace_remaining_tokens` | `int` | Grace tokens remaining before hard block |

### Get Deposit Address

```python
deposit = await client.get_deposit_address()
print(f"Send SOL to: {deposit.deposit_wallet}")
print(f"Minimum: {deposit.min_amount_sol} SOL")
```

### Minimum Deposit

Deposits must reach **$10 USD equivalent** in SOL before tokens are credited. Deposits below this threshold accumulate as pending.

```python
min_usd = SlipstreamClient.get_minimum_deposit_usd()  # 10.0

pending = await client.get_pending_deposit()
print(f"Pending: {pending.pending_sol} SOL ({pending.pending_count} deposits)")
```

### Usage History

```python
from slipstream.types import PaginationOptions

entries = await client.get_usage_history(PaginationOptions(limit=50))
for entry in entries:
    print(f"{entry.tx_type}: {entry.amount_lamports} lamports (balance: {entry.balance_after_lamports})")
```

### Deposit History

```python
deposits = await client.get_deposit_history()
for d in deposits:
    print(f"{d.amount_sol} SOL | ${d.usd_value or 0:.2f} USD | {'CREDITED' if d.credited else 'PENDING'}")
```

### Free Tier Usage

For free-tier API keys, check the daily usage counter:

```python
usage = await client.get_free_tier_usage()
print(f"Used: {usage.used}/{usage.limit}")       # e.g. 42/100
print(f"Remaining: {usage.remaining}")             # e.g. 58
print(f"Resets at: {usage.resets_at}")             # UTC midnight ISO string
```

#### FreeTierUsage Fields

| Field | Type | Description |
|-------|------|-------------|
| `used` | `int` | Transactions used today |
| `remaining` | `int` | Remaining transactions today |
| `limit` | `int` | Daily transaction limit (100) |
| `resets_at` | `str` | UTC midnight reset time (RFC 3339) |

---

## Multi-Region Routing

`MultiRegionClient` connects to workers across multiple regions and automatically routes transactions to the region closest to the current Solana leader.

### Auto-Discovery

```python
from slipstream import MultiRegionClient, config_builder

config = config_builder().api_key("sk_live_xxx").build()
multi = await MultiRegionClient.connect(config)

# Transactions auto-route to the best region
result = await multi.submit_transaction(tx_bytes)

print(f"Connected regions: {multi.connected_regions()}")

# Listen for routing changes
def on_routing_update(rec):
    print(f"Routing to: {rec.best_region} (confidence: {rec.confidence}%)")
    print(f"  Leader: {rec.leader_pubkey}")

multi.on("routing_update", on_routing_update)

await multi.disconnect_all()
```

### Manual Worker Configuration

```python
from slipstream import MultiRegionClient, config_builder
from slipstream.types import WorkerEndpoint, MultiRegionConfig

workers = [
    WorkerEndpoint(id="w1", region="us-east", http="http://10.0.1.1:9000"),
    WorkerEndpoint(id="w2", region="eu-central", http="http://10.0.2.1:9000"),
    WorkerEndpoint(id="w3", region="asia-pacific", http="http://10.0.3.1:9000"),
]

multi = await MultiRegionClient.create(
    config_builder().api_key("sk_live_xxx").build(),
    workers,
    MultiRegionConfig(
        auto_follow_leader=True,
        min_switch_confidence=70,
        switch_cooldown_ms=5000,
        broadcast_high_priority=False,
        max_broadcast_regions=3,
    ),
)
```

#### MultiRegionConfig Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `auto_follow_leader` | `bool` | `True` | Auto-switch region based on leader hints |
| `min_switch_confidence` | `int` | `70` | Minimum confidence (0-100) to trigger region switch |
| `switch_cooldown_ms` | `int` | `5000` | Cooldown between region switches (ms) |
| `broadcast_high_priority` | `bool` | `False` | Broadcast high-priority transactions to all regions |
| `max_broadcast_regions` | `int` | `3` | Maximum regions for broadcast mode |

### Routing Recommendation

Ask the server for the current best region:

```python
rec = await client.get_routing_recommendation()
print(f"Best: {rec.best_region} ({rec.confidence}%)")
print(f"Leader: {rec.leader_pubkey}")
print(f"Fallbacks: {rec.fallback_regions} ({rec.fallback_strategy})")
print(f"Valid for: {rec.valid_for_ms}ms")
```

#### RoutingRecommendation Fields

| Field | Type | Description |
|-------|------|-------------|
| `best_region` | `str` | Recommended region |
| `leader_pubkey` | `str` | Current leader validator pubkey |
| `slot` | `int` | Current slot |
| `confidence` | `int` | Confidence score (0-100) |
| `expected_rtt_ms` | `Optional[int]` | Expected RTT to leader from best region (ms) |
| `fallback_regions` | `List[str]` | Fallback regions in priority order |
| `fallback_strategy` | `FallbackStrategy` | `SEQUENTIAL`, `BROADCAST`, `RETRY`, or `NONE` |
| `valid_for_ms` | `int` | Time until this recommendation expires (ms) |

---

## Deduplication

Prevent duplicate submissions with `dedup_id`:

```python
from slipstream.types import SubmitOptions

result = await client.submit_transaction_with_options(tx_bytes, SubmitOptions(
    dedup_id="unique-tx-id-12345",
    max_retries=5,
))

# Same dedup_id across retries = safe from double-spend
```

---

## Connection Status & Metrics

```python
# Connection status
status = client.connection_status()
print(f"State: {status.state}")       # "connected", "disconnected", etc.
print(f"Protocol: {status.protocol}") # "ws" or "http"
print(f"Region: {status.region}")
print(f"Latency: {status.latency_ms}ms")

# Performance metrics
metrics = client.metrics()
print(f"Submitted: {metrics.transactions_submitted}")
print(f"Confirmed: {metrics.transactions_confirmed}")
print(f"Avg latency: {metrics.average_latency_ms:.1f}ms")
print(f"Success rate: {metrics.success_rate:.1%}")
```

---

## Error Handling

```python
from slipstream import SlipstreamError

try:
    result = await client.submit_transaction(tx_bytes)
except SlipstreamError as e:
    if e.code == "INSUFFICIENT_TOKENS":
        balance = await client.get_balance()
        deposit = await client.get_deposit_address()
        print(f"Low balance: {balance.balance_tokens} tokens")
        print(f"Deposit to: {deposit.deposit_wallet}")
    elif e.code == "RATE_LIMITED":
        print("Slow down -- rate limited for your tier")
    elif e.code == "TIMEOUT":
        print("Transaction timed out")
    elif e.code == "CONNECTION":
        print(f"Connection error: {e}")
    else:
        print(f"Error [{e.code}]: {e}")
```

### Error Codes

| Code | Description |
|------|-------------|
| `CONFIG` | Invalid configuration |
| `CONNECTION` | Connection failure |
| `AUTH` | Authentication failure (invalid API key) |
| `PROTOCOL` | Protocol-level error |
| `TRANSACTION` | Transaction submission error |
| `TIMEOUT` | Operation timed out |
| `RATE_LIMITED` | Rate limit exceeded for your tier |
| `NOT_CONNECTED` | Client not connected |
| `STREAM_CLOSED` | WebSocket stream closed |
| `INSUFFICIENT_TOKENS` | Token balance too low (or free tier daily limit reached) |
| `ALL_PROTOCOLS_FAILED` | All connection protocols failed |
| `INTERNAL` | Internal SDK error |

---

## Examples

| File | Description |
|------|-------------|
| [`examples/basic.py`](examples/basic.py) | Connect and submit a transaction |
| [`examples/streaming.py`](examples/streaming.py) | Leader hints, tips, priority fees, blockhash, slot streams |
| [`examples/billing.py`](examples/billing.py) | Balance, deposits, and usage history |
| [`examples/multi_region.py`](examples/multi_region.py) | Multi-region auto-routing |
| [`examples/advanced_config.py`](examples/advanced_config.py) | All ConfigBuilder options |
| [`examples/submit_transaction.py`](examples/submit_transaction.py) | Transaction with SubmitOptions |
| [`examples/priority_fees.py`](examples/priority_fees.py) | Priority fee configuration and monitoring |
| [`examples/deduplication.py`](examples/deduplication.py) | Deduplication patterns |

## License

Apache-2.0
