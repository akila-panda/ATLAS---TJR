"""
signal-engine/data_pipeline/dukascopy.py
Free historical FX bars from Dukascopy's public datafeed.

No account, no API key, no subscription. Each UTC day is one LZMA-compressed
.bi5 file of 24-byte records: uint32 second-offset from midnight, int32 OHLC
scaled by the instrument point, float32 volume.

Raw files are cached under data/raw/<SYMBOL>/ so a re-run costs nothing.
"""
from __future__ import annotations

import datetime as dt
import lzma
import random
import struct
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import requests

BASE = "https://datafeed.dukascopy.com/datafeed"
HEADERS = {"User-Agent": "Mozilla/5.0"}
REC_SIZE = 24
ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"


class MissingDay(Exception):
    """A day that could not be fetched after repeated retries."""


def point_size(symbol: str) -> float:
    """JPY crosses quote to 3 decimals, everything else to 5."""
    return 1e-3 if "JPY" in symbol.upper() else 1e-5


def _url(symbol: str, day: dt.date) -> str:
    # Dukascopy months are zero-indexed.
    return (f"{BASE}/{symbol}/{day.year}/{day.month - 1:02d}/{day.day:02d}"
            f"/BID_candles_min_1.bi5")


def _fetch_day(symbol: str, day: dt.date, session: requests.Session) -> bytes:
    """Raw .bi5 bytes for one day, from the disk cache when present."""
    cache = RAW / symbol / f"{day:%Y-%m-%d}.bi5"
    if cache.exists():
        return cache.read_bytes()

    cache.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(8):
        try:
            r = session.get(_url(symbol, day), headers=HEADERS, timeout=60)
        except requests.RequestException:
            time.sleep(1.5 * 2 ** attempt + random.random())
            continue
        if r.status_code == 200:
            cache.write_bytes(r.content)
            return r.content
        if r.status_code == 404:          # holiday / no session
            cache.write_bytes(b"")
            return b""
        # 503 is their load balancer throttling us — back off and retry.
        time.sleep(1.5 * 2 ** attempt + random.random())

    # Deliberately not cached, so a later run retries this day.
    raise MissingDay(day)


def _decode_day(raw: bytes, day: dt.date, scale: float) -> pd.DataFrame:
    if not raw:
        return pd.DataFrame()

    data = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE).decompress(raw)
    n = len(data) // REC_SIZE
    if n == 0:
        return pd.DataFrame()

    rows = struct.unpack(">" + "Iiiiif" * n, data[: n * REC_SIZE])
    arr = np.array(rows, dtype=object).reshape(n, 6)
    midnight = pd.Timestamp(dt.datetime(day.year, day.month, day.day,
                                        tzinfo=dt.timezone.utc))

    df = pd.DataFrame({
        "time":   midnight + pd.to_timedelta(arr[:, 0].astype("int64"), unit="s"),
        "open":   arr[:, 1].astype("int64") * scale,
        "close":  arr[:, 2].astype("int64") * scale,
        "low":    arr[:, 3].astype("int64") * scale,
        "high":   arr[:, 4].astype("int64") * scale,
        "volume": arr[:, 5].astype("float64"),
    })

    # Dukascopy pads closed-market minutes two ways: all-zero records, and flat
    # zero-volume bars carrying the last traded price (all day Sunday until the
    # 21:00 UTC open — ~17% of a naive series). Neither is tradeable.
    real = (df["open"] > 0) & (df["volume"] > 0)
    return df.loc[real, ["time", "open", "high", "low", "close", "volume"]]


def load_m1(symbol: str, start: str, end: str, workers: int = 24,
            quiet: bool = False) -> pd.DataFrame:
    """1-minute bars over [start, end), downloading only what isn't cached."""
    scale = point_size(symbol)
    # Saturdays never trade; Sunday opens late but does trade.
    days = [d.date() for d in pd.date_range(start, end, freq="D", inclusive="left")
            if d.weekday() != 5]

    frames: list[pd.DataFrame] = []
    missing: list[dt.date] = []
    done = 0

    with requests.Session() as session, ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_fetch_day, symbol, d, session): d for d in days}
        for fut in as_completed(futures):
            day = futures[fut]
            try:
                frames.append(_decode_day(fut.result(), day, scale))
            except MissingDay:
                missing.append(day)       # one bad day must not kill the run
            done += 1
            if not quiet and (done % 500 == 0 or done == len(days)):
                print(f"  {symbol}: {done}/{len(days)} days"
                      f"{f' ({len(missing)} unavailable)' if missing else ''}",
                      flush=True)

    if missing:
        print(f"  note: {len(missing)} day(s) unavailable, e.g. {sorted(missing)[:5]}")
        print("        re-run to retry them; cached days are skipped.")

    usable = [f for f in frames if not f.empty]
    if not usable:
        raise RuntimeError(f"no data for {symbol} between {start} and {end}")

    df = pd.concat(usable, ignore_index=True)
    return df.sort_values("time").drop_duplicates("time").reset_index(drop=True)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Download Dukascopy 1-minute bars")
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--end", default=dt.date.today().isoformat())
    a = ap.parse_args()

    print(f"Downloading {a.symbol} 1-minute bars {a.start} -> {a.end}")
    m1 = load_m1(a.symbol, a.start, a.end)
    print(f"  {len(m1):,} bars  ({m1.time.min()} .. {m1.time.max()})")
