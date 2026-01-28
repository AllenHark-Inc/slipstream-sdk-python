# AllenHarkSlipstream

Python SDK for Slipstream - Solana transaction relay. 

## Installation

```bash
pip install AllenHarkSlipstream
```

## Quick Start

```python
from slipstream import SlipstreamClient

async def main():
    client = SlipstreamClient(api_key="sk_live_...")
    await client.connect()
    
    # Subscribe to tips
    async for tip in client.subscribe_tips():
        print(f"Tip: {tip.amount} SOL to {tip.wallet}")
    
    # Submit transaction
    result = await client.submit_transaction(tx)
```

## Features

- **asyncio Native** - Fully async
- **gRPC/WebSocket** - Protocol fallback
- **Type Hints** - Full typing support
- **Python 3.9+** - Modern Python

## Documentation

