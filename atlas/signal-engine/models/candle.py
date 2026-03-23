"""
signal-engine/models/candle.py
Candle dataclass and CandleBuffer ring-buffer store.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from collections import deque
from typing import Dict, List, Optional
from config import PIP_SIZE


@dataclass
class Candle:
    symbol:    str
    timeframe: str       # "5min" | "15min" | "4h" | "1h" | "1day"
    time:      datetime  # candle open time (UTC stored, EST conversion in strategy)
    open:      float
    high:      float
    low:       float
    close:     float
    volume:    int = 0

    # ── Price helpers ──────────────────────────────────────────────────────────

    def body_size(self) -> float:
        """Absolute body size in price."""
        return abs(self.close - self.open)

    def body_pips(self) -> float:
        """Absolute body size in pips (EUR/USD: PIP_SIZE = 0.0001)."""
        return self.body_size() / PIP_SIZE

    def wick_high_pips(self) -> float:
        """Upper wick size in pips (high − max(open, close))."""
        return (self.high - max(self.open, self.close)) / PIP_SIZE

    def wick_low_pips(self) -> float:
        """Lower wick size in pips (min(open, close) − low)."""
        return (min(self.open, self.close) - self.low) / PIP_SIZE

    def total_range_pips(self) -> float:
        """Full candle range high-to-low in pips."""
        return (self.high - self.low) / PIP_SIZE

    def is_bullish(self) -> bool:
        """Close > open."""
        return self.close > self.open

    def is_bearish(self) -> bool:
        """Close < open."""
        return self.close < self.open

    def mid(self) -> float:
        """Candle midpoint price."""
        return (self.high + self.low) / 2.0


class CandleBuffer:
    """
    In-memory ring buffer keyed by timeframe string.
    Thread-safe for single-threaded async usage (FastAPI).
    """

    # Maximum candles to retain per timeframe
    _MAX_SIZE: Dict[str, int] = {
        "5min":  500,   # ~41 hours of M5
        "15min": 300,   # ~75 hours of M15
        "4h":    100,
        "1h":    200,
        "1day":  60,
    }
    _DEFAULT_MAX = 200

    def __init__(self) -> None:
        self._buffers: Dict[str, deque] = {}

    def _get_or_create(self, tf: str) -> deque:
        if tf not in self._buffers:
            maxlen = self._MAX_SIZE.get(tf, self._DEFAULT_MAX)
            self._buffers[tf] = deque(maxlen=maxlen)
        return self._buffers[tf]

    def append(self, candle: Candle) -> None:
        """
        Append a candle to the appropriate timeframe buffer.
        Replaces the last candle if it has the same open time (in-progress bar update).
        """
        buf = self._get_or_create(candle.timeframe)
        if buf and buf[-1].time == candle.time:
            # Replace: pop the unfinished candle, append the updated one
            buf.pop()
        buf.append(candle)

    def append_bulk(self, candles: List[Candle]) -> None:
        """
        Bulk-load a list of candles (oldest-first from MT5 push).
        Merges with existing data; newer timestamps overwrite.
        """
        for c in candles:
            self.append(c)

    def get(self, tf: str, n: int) -> List[Candle]:
        """
        Return the last n candles for timeframe tf, oldest-first.
        Returns fewer if the buffer contains less than n candles.
        """
        buf = self._get_or_create(tf)
        candles = list(buf)
        return candles[-n:] if len(candles) >= n else candles

    def latest(self, tf: str) -> Optional[Candle]:
        """Return the most recent candle for timeframe tf, or None."""
        buf = self._get_or_create(tf)
        return buf[-1] if buf else None

    def count(self, tf: str) -> int:
        """Return the number of candles stored for timeframe tf."""
        return len(self._buffers.get(tf, []))

    def all_timeframes(self) -> List[str]:
        """Return list of timeframe keys that have at least one candle."""
        return [tf for tf, buf in self._buffers.items() if buf]