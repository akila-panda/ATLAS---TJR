"""
signal-engine/config.py
ATLAS System — TJR EUR/USD Strategy Constants
All values sourced directly from the TJR Operational Document.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ─── Environment ──────────────────────────────────────────────────────────────
REDIS_URL       = os.getenv("REDIS_URL",       "redis://redis:6379")
POSTGRES_DSN    = os.getenv("POSTGRES_DSN",    "postgresql://atlas_user:atlas@postgres:5432/atlas")
ACCOUNT_BALANCE = float(os.getenv("ACCOUNT_BALANCE", "100000"))
ATLAS_MODE      = os.getenv("ATLAS_MODE",      "MANUAL")   # "MANUAL" | "AUTO"
LOG_LEVEL       = os.getenv("LOG_LEVEL",       "info")

# ─── Broker Timezone ──────────────────────────────────────────────────────────
# MT5 sends candle open times in broker server time (NOT UTC).
# Most ECN brokers (IC Markets, Pepperstone, etc.) run on:
#   UTC+2 (EET)  — last Sunday October  → last Sunday March  (winter)
#   UTC+3 (EEST) — last Sunday March    → last Sunday October (summer)
# March 2026 = EEST = UTC+3.
# UPDATE THIS each DST transition, or fix the EA to send UTC (see fix_broker_timezone.md).
BROKER_UTC_OFFSET_HOURS = int(os.getenv("BROKER_UTC_OFFSET_HOURS", "3"))

# ─── Session Timing (EST hours) ───────────────────────────────────────────────
ASIA_START_EST  = 20    # Asia range formation window opens  20:00 EST (Rule 1.1)
ASIA_END_EST    = 0     # Asia range formation window closes 00:00 EST (Rule 1.1)
LKZ_START_EST   = 2     # London Kill Zone opens  02:00 EST (Section 8)
LKZ_END_EST     = 5     # London Kill Zone closes 05:00 EST (Section 8)
ENTRY_EXPIRY_H  = 5     # Limit order cancel hour  05:xx EST (Rule 4.2d)
ENTRY_EXPIRY_M  = 30    # Limit order cancel minute :30      (Rule 4.2d)
NY_OPEN_KILL_H  = 8     # NY open time kill 08:00 EST        (Rule 8.2.4)
LATE_LKZ_H      = 4     # Late LKZ starts 04:56 EST          (Rule 2.1a)
LATE_LKZ_M      = 56

# ─── Asia Range Parameters ────────────────────────────────────────────────────
ASIA_RANGE_MIN_PIPS = 10   # Rule 1.2: range < 10 pips → NO TRADE
ASIA_RANGE_MAX_PIPS = 40   # Rule 1.2: range > 40 pips → NO TRADE
WIDE_RANGE_PIPS     = 38   # Rule 1.4: 38–40 pips → elevated R:R requirement
CONTAMINATION_BODY_PIPS    = 15  # Rule 1.3: news candle body threshold
CONTAMINATION_MAX_CANDLES  = 3   # Rule 1.3: >= 3 contaminated candles → NO TRADE

# ─── Sweep Parameters ─────────────────────────────────────────────────────────
SWEEP_MIN_PIPS = 3   # Rule 2.2: extension < 3 pips → INVALIDATED
SWEEP_MAX_PIPS = 8   # Rule 2.2: extension > 8 pips → apply breakout filter

# ─── Stop Loss Parameters ─────────────────────────────────────────────────────
SL_BUFFER_PIPS          = 3    # Rule 5.1: standard buffer beyond sweep wick
SL_BUFFER_ELEVATED_PIPS = 5    # Rule 5.1c: elevated when ATR high or deep sweep
SL_MAX_PIPS             = 15   # Rule 5.2: hard SL limit from entry price

# ─── Risk / Reward ────────────────────────────────────────────────────────────
MIN_RR            = 2.0   # Rule 7.5: minimum R:R to TP2 (standard)
MIN_RR_WIDE_RANGE = 2.5   # Rule 1.4: elevated R:R for 38–40 pip range sessions
MAX_RISK_PCT      = 1.0   # Rule 7.2: 1% risk per trade
LATE_LKZ_RISK_PCT = 0.5   # Rule 2.1a: 0.5% risk for late LKZ sweeps (04:56+)
MAX_DAILY_LOSS_PCT= 2.0   # Rule 7.3: 2% daily max → session terminated

# ─── Confluence Scoring ───────────────────────────────────────────────────────
MIN_CONFLUENCE = 10   # Section 10: minimum score out of 21 to take a trade

# ─── TP Partial Close Percentages ────────────────────────────────────────────
TP1_CLOSE_PCT = 40   # Rule 6.2c: close 40% of position at TP1
TP2_CLOSE_PCT = 35   # Rule 6.3:  close 35% of position at TP2 (25% runs to TP3)

# ─── Entry / Displacement ─────────────────────────────────────────────────────
DISPLACEMENT_MULT = 1.5   # Rule 4.1b: displacement body >= 1.5× avg of prev 5

# ─── EUR/USD Instrument Constants ─────────────────────────────────────────────
PIP_SIZE        = 0.0001   # EUR/USD pip size
PIP_VALUE_STD   = 10.0     # USD per pip per standard lot (Rule 7.1)
SYMBOL          = "EURUSD"
MAGIC_NUMBER    = 20240101

# ─── Grade Thresholds (Section 9.2) ───────────────────────────────────────────
GRADE_APLUS_MIN = 18
GRADE_A_MIN     = 14
GRADE_B_MIN     = 10   # same as MIN_CONFLUENCE