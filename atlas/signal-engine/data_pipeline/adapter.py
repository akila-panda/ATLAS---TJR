"""
signal-engine/data_pipeline/adapter.py
Turns cached 1-minute bars into the four Candle lists run_backtest() expects.

All four timeframes are derived from one aligned M1 source, so session
boundaries line up exactly — no cross-source drift.

Timezone: Candle.time is UTC throughout, matching models/candle.py. The
strategy converts to EST internally. BROKER_UTC_OFFSET_HOURS is deliberately
NOT applied here — that constant exists only for live MT5 feeds, which send
broker server time. Backtests run on true UTC.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from models.candle import Candle
from data_pipeline.dukascopy import load_m1

ROOT = Path(__file__).resolve().parent.parent

# ATLAS timeframe label -> pandas resample rule. Labels must match exactly what
# CandleBuffer and the strategy modules use.
TIMEFRAMES: dict[str, str] = {
    "5min":  "5min",
    "15min": "15min",
    "4h":    "4h",
    "1day":  "1D",
}


def resample(m1: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Aggregate M1 into `rule` bars, labelled by OPEN time (TradingView/MT5 convention)."""
    out = (
        m1.set_index("time")
          .resample(rule, label="left", closed="left")
          .agg(open=("open", "first"), high=("high", "max"),
               low=("low", "min"), close=("close", "last"),
               volume=("volume", "sum"))
          .dropna(subset=["open"])
    )
    return out.reset_index()


def to_candles(df: pd.DataFrame, symbol: str, timeframe: str) -> list[Candle]:
    """
    DataFrame -> list[Candle], oldest first.

    Candle.volume is declared int, but Dukascopy reports traded amount as a
    float that can be far below 1.0 in thin sessions (min observed 0.000876).
    A plain int() cast would floor those to 0 and make real bars look like
    removed padding, so any bar that traded keeps a floor of 1.

    Note the units differ from live: the MT5 EA sends tick counts, Dukascopy
    sends traded amount. Nothing in strategy/ reads Candle.volume, so this is
    informational only — but do not compare backtest volume against live.
    """
    return [
        Candle(
            symbol=symbol,
            timeframe=timeframe,
            time=t.to_pydatetime(),      # tz-aware UTC
            open=float(o), high=float(h), low=float(l), close=float(c),
            volume=max(1, int(round(float(v)))),
        )
        for t, o, h, l, c, v in zip(df["time"], df["open"], df["high"],
                                    df["low"], df["close"], df["volume"])
    ]


def load_candle_sets(
    symbol: str = "EURUSD",
    start: str = "2015-01-01",
    end: str = "2026-09-17",
    quiet: bool = False,
) -> dict[str, list[Candle]]:
    """
    Every timeframe the backtest needs, keyed by ATLAS timeframe label.

    Returns {"5min": [...], "15min": [...], "4h": [...], "1day": [...]}
    """
    if not quiet:
        print(f"Loading {symbol} {start} -> {end}")

    m1 = load_m1(symbol, start, end, quiet=quiet)
    if not quiet:
        print(f"  {len(m1):,} 1-minute bars "
              f"({m1.time.min():%Y-%m-%d} .. {m1.time.max():%Y-%m-%d})")

    sets: dict[str, list[Candle]] = {}
    for label, rule in TIMEFRAMES.items():
        bars = resample(m1, rule)
        sets[label] = to_candles(bars, symbol, label)
        if not quiet:
            print(f"  {label:<6} {len(bars):>8,} bars")

    return sets


def save_csv(symbol: str = "EURUSD", start: str = "2015-01-01",
             end: str = "2026-09-17") -> None:
    """Write each timeframe to data/<SYMBOL>_<TF>.csv for inspection."""
    m1 = load_m1(symbol, start, end)
    out = ROOT / "data"
    out.mkdir(exist_ok=True)
    for label, rule in TIMEFRAMES.items():
        bars = resample(m1, rule)
        path = out / f"{symbol}_{label}.csv"
        bars.to_csv(path, index=False)
        print(f"  {label:<6} {len(bars):>8,} bars -> {path.name}")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Build ATLAS candle sets from cached M1")
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--end", default="2026-09-17")
    ap.add_argument("--csv", action="store_true", help="also write CSV files")
    a = ap.parse_args()

    if a.csv:
        save_csv(a.symbol, a.start, a.end)
    else:
        sets = load_candle_sets(a.symbol, a.start, a.end)
        print("\nfirst/last of each timeframe:")
        for label, candles in sets.items():
            print(f"  {label:<6} {candles[0].time}  ..  {candles[-1].time}")
