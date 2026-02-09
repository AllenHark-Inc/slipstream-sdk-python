# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Keep-alive & time sync**: Background ping loop (default 5s) measures RTT and synchronizes clocks with the server using NTP-style calculation.
- `ping()` method — send a single ping and get `PingResult(seq, rtt_ms, clock_offset_ms, server_time)`.
- `latency_ms()` — median one-way latency from sliding window of 10 samples.
- `clock_offset_ms()` — median clock offset between client and server.
- `server_time()` — current server time estimated from local clock + offset.
- `config_builder().keep_alive(bool)` — enable/disable keep-alive (default: True).
- `config_builder().keep_alive_interval(secs)` — ping interval in seconds (default: 5.0).
- `'ping'` callback fired on each successful ping with `PingResult`.
- WebSocket transport: JSON-based ping/pong messages with timing.
- **Free tier usage**: `get_free_tier_usage()` method in SDK.
- **Stream billing**: All stream subscriptions billed at 1 token per connection (1-hour reconnect grace period).
- **Latest blockhash stream**: `subscribe_latest_blockhash()` — blockhash updates every 2s.
- **Latest slot stream**: `subscribe_latest_slot()` — slot updates on every slot change (~400ms).
- **Priority tiers**: `config_builder().tier('pro')` — set billing tier (free/standard/pro/enterprise).

- Initial SDK setup.
