"""
signal-engine/data_pipeline/validate.py
Phase 1 gate: prove the data is sound before any strategy conclusion rests on it.

Checks structural integrity, Dukascopy padding removal, and — the part that
matters for ATLAS — that the EST session windows the strategy depends on are
actually populated.
"""
from __future__ import annotations

import sys

import pandas as pd
import pytz

from data_pipeline.adapter import load_candle_sets

EST = pytz.timezone("America/New_York")
PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((PASS if ok else FAIL, name, detail))


def as_frame(candles) -> pd.DataFrame:
    return pd.DataFrame([{
        "time": c.time, "open": c.open, "high": c.high,
        "low": c.low, "close": c.close, "volume": c.volume,
    } for c in candles])


def main() -> int:
    sets = load_candle_sets(quiet=True)
    frames = {tf: as_frame(c) for tf, c in sets.items()}

    # ── Structural integrity ─────────────────────────────────────────────────
    for tf, df in frames.items():
        bad = ((df.high < df.low) | (df.high < df.open) | (df.high < df.close) |
               (df.low > df.open) | (df.low > df.close)).sum()
        check(f"{tf}: OHLC consistent", bad == 0, f"{bad} violations")
        check(f"{tf}: no zero-volume padding", (df.volume < 1).sum() == 0,
              f"{(df.volume < 1).sum()} bars")
        check(f"{tf}: chronological, no duplicates",
              df.time.is_monotonic_increasing and not df.time.duplicated().any())
        check(f"{tf}: prices plausible for EURUSD",
              0.9 < df.low.min() and df.high.max() < 1.7,
              f"{df.low.min():.4f}-{df.high.max():.4f}")

    # ── Padding removal: the FX week really opens 21:00 UTC Sunday ───────────
    m5 = frames["5min"]
    sun = m5[m5.time.dt.dayofweek == 6]
    check("Sunday bars start at 21:00 UTC (not midnight)",
          sun.time.dt.hour.min() == 21,
          f"earliest Sunday hour = {sun.time.dt.hour.min()}")
    check("no Saturday bars", (m5.time.dt.dayofweek == 5).sum() == 0)

    gaps = m5.time.diff().dropna()
    weekend = gaps[gaps > pd.Timedelta("12h")]
    check("weekend gaps ~48h (market shut Fri night -> Sun night)",
          40 <= weekend.median().total_seconds() / 3600 <= 50,
          f"median {weekend.median().total_seconds()/3600:.1f}h, n={len(weekend)}")

    # ── Coverage is even year to year ────────────────────────────────────────
    per_year = m5.groupby(m5.time.dt.year).size()
    full = per_year[(per_year.index > per_year.index.min()) &
                    (per_year.index < per_year.index.max())]
    spread = (full.max() - full.min()) / full.mean()
    check("M5 bars per year within 5%", spread < 0.05, f"spread {spread*100:.1f}%")

    # ── Timeframe alignment ──────────────────────────────────────────────────
    check("4h bars land on 0/4/8/12/16/20 UTC",
          set(frames["4h"].time.dt.hour.unique()) <= {0, 4, 8, 12, 16, 20})
    check("15min bars land on :00/:15/:30/:45",
          set(frames["15min"].time.dt.minute.unique()) == {0, 15, 30, 45})
    check("M5 count ≈ 3x M15 count",
          abs(len(frames["5min"]) / len(frames["15min"]) - 3) < 0.05,
          f"ratio {len(frames['5min'])/len(frames['15min']):.3f}")

    # ── ATLAS session windows must actually be populated ─────────────────────
    est_hour = m5.time.dt.tz_convert(EST).dt.hour
    asia = m5[(est_hour >= 20) | (est_hour < 0)]          # 20:00-00:00 EST
    lkz = m5[(est_hour >= 2) & (est_hour < 5)]            # 02:00-05:00 EST
    check("Asia window (20:00-00:00 EST) populated", len(asia) > 100_000,
          f"{len(asia):,} M5 bars")
    check("London Kill Zone (02:00-05:00 EST) populated", len(lkz) > 100_000,
          f"{len(lkz):,} M5 bars")

    # A tradeable Asia session needs ~48 M5 bars; count sessions with >= 40.
    asia_sessions = asia.groupby(asia.time.dt.tz_convert(EST).dt.date).size()
    good = (asia_sessions >= 40).sum()
    check("≥2,000 complete Asia sessions available", good >= 2_000,
          f"{good:,} sessions with ≥40 M5 bars")

    # ── Report ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 74)
    print("PHASE 1 DATA VALIDATION")
    print("=" * 74)
    for status, name, detail in results:
        mark = "✓" if status == PASS else "✗"
        print(f"  {mark} {status}  {name:<48} {detail}")

    failures = sum(1 for s, _, _ in results if s == FAIL)
    print("=" * 74)
    print(f"  {len(results) - failures}/{len(results)} checks passed")
    if failures:
        print(f"  {failures} FAILED — do not proceed to Phase 2")
    print("=" * 74)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
