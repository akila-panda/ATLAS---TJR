# ATLAS — SETUP GUIDE
### True Judas Reversal · EUR/USD · London Session

---

## WHAT THIS SYSTEM DOES

ATLAS automates the TJR (True Judas Reversal) strategy for EUR/USD during the London Kill Zone (02:00–05:00 EST). Every night it maps the Asia session range (20:00–00:00 EST), waits for a Judas sweep of the Asia high or low during the London open, confirms a 15M Change of Character and 5M displacement candle, and presents a limit-order entry at the Fair Value Gap midpoint.

**By default, the system runs in MANUAL mode.** Every signal requires your explicit confirmation before a trade is placed. No trade executes automatically until you switch to AUTO — and the system will ask you to confirm that switch with a dialog box.

---

## 1 — PREREQUISITES

Everything below must be installed before running `make dev`.

### Docker Desktop
Download and install Docker Desktop for Mac from https://docker.com/products/docker-desktop.
After installation, open Docker Desktop, go to Settings → Resources, and allocate at minimum:
- **CPU**: 4 cores
- **Memory**: 4 GB
- **Disk**: 20 GB

Verify the installation:
```bash
docker --version        # Docker version 24+ expected
docker-compose --version
```

### Node.js 20 via nvm
```bash
# Install nvm if not already installed
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash

# Reload shell
source ~/.zshrc   # or ~/.bashrc

# Install and use Node 20
nvm install 20
nvm use 20
nvm alias default 20

node --version    # v20.x.x expected
```

### Python 3.11 via pyenv
```bash
# Install pyenv if not already installed
brew install pyenv

# Add to shell profile (~/.zshrc or ~/.bashrc):
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"

# Reload shell then install Python
source ~/.zshrc
pyenv install 3.11.8
pyenv global 3.11.8

python --version   # Python 3.11.x expected
```

### MT5 via Wine (already installed)
You confirmed MT5 runs via Wine with `http://127.0.0.1:3001` already whitelisted in Tools → Options → Expert Advisors → Allow WebRequest. No changes needed to your existing MT5 setup.

Your existing EAs (`APEX2_Bridge.mq5` and `APEX_Trade_Recieve.mq5`) compile with 0 errors — ATLAS_EA.mq5 follows the same patterns and will compile cleanly.

### Code Editor
**Trae** (already in use based on your screenshots) or VS Code. Both work. The project scaffold was generated for Trae but is standard enough to open in any editor.

---

## 2 — PROJECT ARCHITECTURE

ATLAS is built as a distributed microservice system to ensure high reliability and separate concerns:

- **MT5 EA (MQL5)**: The "Sensor" and "Actuator". Runs inside Wine on Mac. Pushes every M5 candle close to the API Server via `WebRequest` and polls for new trade signals or management commands (partial closes, SL moves).
- **API Server (Node.js/TS)**: The "Bridge". Acts as a centralized message hub. Receives candles from MT5 and stores them in Redis. Forwards signals from the Signal Engine to the Frontend. Manages WebSocket connections for real-time dashboard updates.
- **Signal Engine (Python)**: The "Brain". Runs the heavy technical analysis. When a new candle arrives, it runs the full TJR strategy pipeline (Asia range detection, Judas sweep detection, 15M/5M structure analysis). It runs the 14-node Decision Tree and calculates confluence scores.
- **Frontend (React/Vite)**: The "Cockpit". Provides a beautiful, real-time dashboard for monitoring the system. Allows you to confirm signals in MANUAL mode, view the trade journal, and adjust risk settings.
- **PostgreSQL**: The "Memory". Stores all historical data — sessions, trade logs, and signal results — for later analysis and journaling.
- **Redis**: The "Short-term Memory". Handles all real-time data flow between services with sub-millisecond latency.

---

## 3 — FIRST TIME SETUP

### Step 1 — Copy and configure the environment file

```bash
cd atlas
cp .env.example .env
```

Open `.env` in your editor and make exactly these changes:

```bash
# Change this — use a strong random password (no special characters that break Postgres)
POSTGRES_PASSWORD=MyStr0ngPassword123

# Change this — generate a random 32-character string
# Run in terminal: openssl rand -hex 16
ATLAS_API_KEY=paste_your_32_char_key_here

# Your demo account balance — confirm this matches your MT5 account
ACCOUNT_BALANCE=100000

# Leave as MANUAL — do not change to AUTO until you have verified 10 correct signals
ATLAS_MODE=MANUAL
```

Everything else in `.env` can stay at its default value for a local setup.

### Step 2 — Build and start all services

```bash
make dev
```

The first run downloads Docker images and builds all three services. This takes **3–5 minutes** on a typical Mac with a good internet connection. Subsequent starts take under 30 seconds.

You will see Docker pulling images for Python 3.11, Node 20, PostgreSQL 15, Redis 7, and Nginx. When all five services show `Up` in the terminal, the system is running.

To confirm all services are healthy:
```bash
make status
```

Expected output:
```
NAME                STATUS          PORTS
atlas-signal-engine-1   Up          0.0.0.0:8001->8001/tcp
atlas-api-server-1      Up          0.0.0.0:3001->3001/tcp
atlas-frontend-1        Up          0.0.0.0:5173->5173/tcp
atlas-postgres-1        Up          0.0.0.0:5432->5432/tcp
atlas-redis-1           Up          0.0.0.0:6379->6379/tcp
```

### Step 3 — Open the dashboard

Open your browser and go to: **http://localhost:5173**

You should see the ATLAS dashboard with a dark background, the ATLAS logo in the top-left sidebar, and a `DISCONNECTED` status indicator in the top bar. The indicator will turn green once MT5 is attached and pushing candles (next section).

---

## 4 — MT5 EA SETUP

### Step 1 — Copy ATLAS_EA.mq5 into MT5

In MT5 via Wine:
```
File → Open Data Folder
```
This opens a Finder window inside the Wine filesystem. Navigate to:
```
MQL5 → Experts
```
Copy `atlas/mt5-ea/ATLAS_EA.mq5` into this `Experts` folder.

### Step 2 — Compile ATLAS_EA.mq5

In MT5:
```
Tools → MetaEditor   (or press F4)
```

In MetaEditor's left Navigator panel, under `Experts`, you should now see `ATLAS_EA` listed alongside your existing `APEX2_Bridge` and `APEX_Trade_Recieve`. Double-click `ATLAS_EA` to open it.

Press **F7** to compile.

The Errors tab at the bottom must show:
```
0 errors, 0 warnings
```

If you see any errors, confirm the file was saved completely — the most common issue is an incomplete copy.

### Step 3 — WebRequest whitelist

**No changes needed.** `http://127.0.0.1:3001` is already in your whitelist. ATLAS_EA uses the same port as your existing APEX_Trade_Recieve EA.

To confirm: Tools → Options → Expert Advisors → the URL list should show `http://127.0.0.1:3001`.

### Step 4 — Attach EA to the EURUSD M5 chart

Back in the main MT5 window:
```
View → Navigator   (or Ctrl+N)
Expert Advisors → ATLAS_EA
```

Drag `ATLAS_EA` onto your **EURUSD M5 chart** and click **OK** in the properties dialog. Leave all default settings.

> **Important:** Attach to EURUSD M5 only. The EA hardcodes EURUSD for all candle pushes and trade execution. Do not attach to any other symbol or timeframe.

### Step 5 — Enable Auto Trading

Click the **Auto Trading** button in the MT5 toolbar (the button with a play icon and "Algo Trading" label). It turns **green** when active. If it's already green from your existing EAs, no action needed.

### Step 6 — Verify candle push

Click the **Experts** tab at the bottom of MT5. Within 60 seconds of attaching the EA, you should see lines like:

```
2026.03.22 14:30:01   ATLAS EA v2.00 initialised | Magic=20240101 | Candle push: active | Signal poll: active | Manage poll: active
2026.03.22 14:30:01   ATLAS push: EURUSD 5min 80 candles | HTTP 200
2026.03.22 14:30:01   ATLAS push: EURUSD 15min 80 candles | HTTP 200
2026.03.22 14:30:01   ATLAS push: EURUSD 4h 50 candles | HTTP 200
2026.03.22 14:30:01   ATLAS push: EURUSD 1day 30 candles | HTTP 200
2026.03.22 14:30:01   ATLAS push: GBPUSD 1h 50 candles | HTTP 200
```

The `| HTTP 200` at the end of each line confirms the backend received the data.

---

## 5 — VERIFY THE CONNECTION

Three checks to run after the EA is attached:

**Check 1 — MT5 Experts tab**
You see the candle push log lines with `HTTP 200` as shown above.

**Check 2 — Dashboard connection dot**
Refresh http://localhost:5173. The connection indicator in the top bar should change from red `DISCONNECTED` to green `CONNECTED` within a few seconds of the EA pushing its first candles.

**Check 3 — Backend logs**
```bash
make logs
```

In the `api-server` log stream you should see:
```
[server] ATLAS API Server running on port 3001
candles_received symbol=EURUSD timeframe=5min count=80
candles_received symbol=EURUSD timeframe=15min count=80
```

**Check 4 — Asia range (run after 20:00 EST)**
After the Asia session opens at 20:00 EST, watch the dashboard chart. The ASH (red dashed) and ASL (green dashed) lines will appear on the EURUSD M5 chart once the range is calculated at 00:00 EST. The SessionStatus bar at the bottom will show the range pip count and a green `VALID` badge if the range is between 10 and 40 pips.

---

## 6 — DAILY ROUTINE

### 19:45 EST — Pre-session check
The system performs this automatically, but it's good practice to:
- Open the dashboard and confirm the connection dot is green
- Go to Settings and check the MT5 last-candle timestamp (green = receiving data in last 90 seconds)
- Look at the News Calendar section in Settings for any red-folder events scheduled between 02:00–05:00 EST — if a red event is within the London Kill Zone, the system will block all signals for that session automatically (Rule 7.4a)

### 20:00–00:00 EST — Asia range formation
You do not need to watch this. The system maps the Asia range automatically from the M5 candles being pushed by the EA. At 00:00 EST the ASH and ASL lines appear on the chart. The SessionStatus bar updates with the range pip count.

If the range is outside 10–40 pips, the SessionStatus badge shows `INVALID` in red and the session is flagged as NO TRADE. You will not receive any signals that session.

### 02:00–05:00 EST — London Kill Zone
This is the active window. The system scans every M5 candle close for a Judas sweep.

When a sweep is detected and all 14 decision tree nodes pass:
- The Confluence Scorecard on the right panel updates in real time showing all 8 factor scores
- The Signal Card transitions from "Waiting for LKZ sweep..." to showing the direction badge (LONG or SHORT) and trade parameters
- **In MANUAL mode**, two buttons appear at the bottom of the Signal Card: `CONFIRM TRADE` and `SKIP`

You have until 05:30 EST to confirm. After 05:30 the pending limit order expires (Rule 4.2d) and the signal card returns to waiting state.

If the decision tree fails at any node, the Signal Card shows the exact reason code (e.g. `NO_15M_CHOCH`, `SL_EXCEEDS_MAX`, `CONFLUENCE_BELOW_MIN`). This is normal — not every session produces a valid setup.

### 08:00 EST — NY open
Any open position is automatically closed by `trade_manager.py` at 08:00 EST (Rule 8.2.4: NY open time kill). You do not need to do anything. The trade closure is logged to PostgreSQL and visible in the Journal page.

No new signals are generated after 08:00 EST. The system enters a quiet period until the next Asia session opens at 20:00 EST.

---

## 7 — UNDERSTANDING MODES

### MANUAL mode (default — use this first)

Every signal that passes all 14 decision tree checks appears on the dashboard with a `CONFIRM TRADE` and `SKIP` button. No trade is placed until you click `CONFIRM TRADE`.

Use MANUAL mode to validate that the system is identifying setups correctly. For each signal, manually check on your MT5 chart:
- Is the Asia range correctly identified? (ASH/ASL lines in the right place)
- Did a Judas sweep genuinely occur? (wick beyond ASH or ASL, body closed back inside)
- Is there a visible CHoCH on the 15M chart?
- Is there a displacement candle with an FVG on the 5M chart?
- Are the entry, SL, TP1, TP2, TP3 prices where you would put them manually?

**Validate at least 10 complete signals in MANUAL mode before considering AUTO.**

### AUTO mode

In AUTO mode, the system places the trade immediately when all 14 decision tree nodes pass. No confirmation required. The signal card will still update and show the trade parameters, but by the time you see it, the order is already in MT5.

To switch: click the mode toggle button (top-right of dashboard). A browser confirmation dialog will appear explaining the consequences. Click OK to confirm.

**Only switch to AUTO after verifying at least 10 correct signals in MANUAL mode.** There is no undo on a live trade.

The system enforces these risk limits regardless of mode:
- Maximum 1% account risk per trade (Rule 7.2)
- Maximum 2% daily loss limit — session terminates automatically when reached (Rule 7.3)
- All positions closed at 08:00 EST (Rule 8.2.4)
- SL hard limit: 15 pips from entry (Rule 5.2)
- Minimum R:R: 2.0 to TP2 (Rule 7.5)

---

## 8 — EMERGENCY STOP

These options are listed from fastest to most nuclear. Use the minimum level required.

**Fastest — disable EA signal execution (leaves backend running)**
Click the **Auto Trading** button in MT5 toolbar so it turns grey. The EA will stop polling for signals and placing trades. Existing open positions remain open and you manage them manually in MT5.

**Stop specific trade — close from dashboard**
Dashboard → Open Positions → the trade card shows a **Close** button. This sends `CLOSE_ALL` to the EA via `/manage`, which closes the position at market immediately.

**Stop backend signal generation (leaves MT5 and positions intact)**
```bash
make stop
```
This stops all Docker services. The EA will show `WebRequest failed` in the Experts tab (expected — the backend is offline). Existing MT5 positions are not affected.

**Full stop — stop everything**
```bash
make stop
```
Then in MT5, drag the ATLAS_EA off the chart or click the X on the EA icon in the top-right corner of the chart. This stops both the backend and the EA.

**Nuclear — destroy all Docker data (irreversible)**
```bash
make clean
```
This runs `docker-compose down -v`, which stops all services and **destroys all PostgreSQL data** including your trade history and signal logs. Only use this if you want to start completely fresh. Your `.env` file and source code are not affected.

---

## 9 — COMMON ISSUES

### "WebRequest failed" in MT5 Experts tab

The EA cannot reach `http://127.0.0.1:3001`. Work through in order:

```bash
# Check if Docker services are running
make status
```

If any service shows `Exit` or `Restarting`:
```bash
make logs
```
Read the error output and fix the config before re-attaching the EA. The most common cause is a wrong `POSTGRES_PASSWORD` in `.env` — Postgres rejects passwords with certain special characters.

If all services show `Up` but the EA still fails: confirm `http://127.0.0.1:3001` is in the MT5 whitelist (Tools → Options → Expert Advisors). You already have this, but Wine restarts can occasionally reset the setting.

### Dashboard shows DISCONNECTED after services are running

```bash
make logs
```

Look for errors in the `api-server` stream. Common causes:
- `ATLAS_API_KEY` mismatch between `.env` and the frontend `VITE_API_KEY` — both must be identical
- WebSocket failing to upgrade — try a hard refresh in the browser (`Cmd+Shift+R`)
- CORS error — confirm `FRONTEND_ORIGIN=http://localhost:5173` in `.env`

### No signals during the London Kill Zone

This is usually correct behaviour — not every session produces a valid TJR setup. Check the signal-engine logs for the exact reason code:

```bash
docker-compose logs signal-engine --tail=50
```

Common reason codes and what they mean:

| Reason Code | Meaning |
|---|---|
| `NO_SWEEP_IN_LKZ` | No wick extended beyond ASH or ASL between 02:00–05:00 EST. Normal on ranging or trend-continuation sessions. |
| `ASIA_RANGE_TOO_NARROW` | Asia range was less than 10 pips. Insufficient liquidity pools for a valid TJR. |
| `ASIA_RANGE_TOO_WIDE` | Asia range exceeded 40 pips. Sweep confirmation becomes ambiguous. |
| `NO_15M_CHOCH` | Sweep occurred but no 15M Change of Character followed. Structural confirmation missing. |
| `CONFLUENCE_BELOW_MIN` | All structural conditions met but confluence score was below 10/21. Low-probability setup filtered. |
| `SL_EXCEEDS_MAX` | Valid setup but SL distance from entry exceeded 15 pips hard limit. Position sizing would be invalid. |
| `NEWS_FILTER_FAIL` | Red-folder news event scheduled within the LKZ. Session blocked (Rule 7.4a). |
| `SESSION_TERMINATED` | Daily 2% loss limit was reached earlier in the session. No further signals. |

All NO_TRADE decisions are logged to PostgreSQL with full decision tree state. Review them in the Journal page (http://localhost:5173/journal) to understand which condition failed.

### Want to run a backtest

Place your EURUSD M5 history CSV in `atlas/signal-engine/data/`. The CSV must have columns: `datetime,open,high,low,close,volume` with datetime in ISO-8601 format.

```bash
docker-compose run --rm signal-engine python -m strategy.backtest \
  --csv data/eurusd_m5.csv \
  --from 2024-01-01 \
  --to 2024-12-31
```

Output includes all Section 9.3 metrics: win rate TP1/TP2, average R:R, expectancy, profit factor, and max consecutive losses. A minimum sample of 50 trades is required before the edge threshold assessment is meaningful.

### Restart a single service without restarting everything

```bash
make restart-engine   # restart Python signal engine only
make restart-api      # restart Node.js API server only
```

### View live logs for a specific service

```bash
docker-compose logs -f signal-engine   # Python pipeline logs
docker-compose logs -f api-server       # Node.js bridge logs
docker-compose logs -f frontend         # Vite dev server logs
```

---

## 10 — IMPORTANT REMINDER

This system connects to a live MetaTrader 5 account. In AUTO mode, it places real trades using your demo account balance of $100,000.

**The system enforces a hard 2% daily loss limit (Rule 7.3).** When this limit is reached, the `session_terminated` flag is set in Redis, the signal engine stops generating signals, and a `SESSION TERMINATED` notice replaces the percentage in the Risk Meter gauge on the dashboard sidebar. The daily limit resets automatically at 20:00 EST when the next Asia session opens.

**Start with MANUAL mode.** The confirmation dialog is your last line of defence. Every time the CONFIRM TRADE button appears, treat it as a real trading decision — because in AUTO mode, that decision happens without you. Use the manual confirmation period to build your own judgment about what a valid TJR setup looks like, so you can catch any edge case in the signal engine's logic before it costs you money.

The TJR strategy document defines minimum backtest thresholds before live trading is appropriate:
- Win rate (TP1) ≥ 55% over 50+ trades
- Average R:R ≥ 1.8
- Expectancy ≥ +0.3R
- Profit factor ≥ 1.4

Check these thresholds in the Journal page stat cards before switching to AUTO mode.

---

*ATLAS v1.0 — TJR EUR/USD London Session · Prop desk procedure standard*