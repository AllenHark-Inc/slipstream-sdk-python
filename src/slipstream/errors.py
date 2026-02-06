"""
AllenHarkSlipstream — Error types
"""

from __future__ import annotations

from typing import Optional


class SlipstreamError(Exception):
    """Base error for all Slipstream SDK errors."""

    def __init__(self, code: str, message: str, details: Optional[object] = None):
        super().__init__(message)
        self.code = code
        self.details = details

    @staticmethod
    def config(msg: str) -> SlipstreamError:
        return SlipstreamError("CONFIG", msg)

    @staticmethod
    def connection(msg: str) -> SlipstreamError:
        return SlipstreamError("CONNECTION", msg)

    @staticmethod
    def auth(msg: str) -> SlipstreamError:
        return SlipstreamError("AUTH", msg)

    @staticmethod
    def protocol(msg: str) -> SlipstreamError:
        return SlipstreamError("PROTOCOL", msg)

    @staticmethod
    def transaction(msg: str) -> SlipstreamError:
        return SlipstreamError("TRANSACTION", msg)

    @staticmethod
    def timeout(ms: int) -> SlipstreamError:
        return SlipstreamError("TIMEOUT", f"Operation timed out after {ms}ms")

    @staticmethod
    def all_protocols_failed() -> SlipstreamError:
        return SlipstreamError("ALL_PROTOCOLS_FAILED", "All connection protocols failed")

    @staticmethod
    def rate_limited(msg: str = "Rate limited") -> SlipstreamError:
        return SlipstreamError("RATE_LIMITED", msg)

    @staticmethod
    def not_connected() -> SlipstreamError:
        return SlipstreamError("NOT_CONNECTED", "Client is not connected")

    @staticmethod
    def stream_closed() -> SlipstreamError:
        return SlipstreamError("STREAM_CLOSED", "Stream has been closed")

    @staticmethod
    def insufficient_tokens() -> SlipstreamError:
        return SlipstreamError("INSUFFICIENT_TOKENS", "Insufficient token balance")

    @staticmethod
    def internal(msg: str) -> SlipstreamError:
        return SlipstreamError("INTERNAL", msg)
