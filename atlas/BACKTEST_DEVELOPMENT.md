# ATLAS — Backtest Development Plan

Status: **Phase 2 complete — GATE FAILED (26 trades < 50)** · Next: Phase 5 · Created 2026-09-17 · EUR/USD, London Kill Zone

Working document. Tick boxes as we go, record real numbers in the Results
tables, and do not skip a phase gate.

---

## Why this exists

ATLAS enforces four thresholds before AUTO mode is permitted (SETUP.md §10):

| Metric | Minimum | Target |
|---|---|---|
| Win rate (TP1) | 55% | 65% |
| Average R:R | 1.8 | 2.3 |
| Expectancy | +0.3R | +0.5R |
| Profit factor | 1.4 | 1.8 |

**None of these can currently be measured.** `strategy/backtest.py` is 483
lines of working simulation logic with no CLI, no CSV loader, no `__main__`,
and no data directory. The documented command in SETUP.md §9 cannot run.

The goal of this plan is to make those four numbers real, and to make them
trustworthy enough to bet on.

## What the research says (2026-09-17)

Searched before building. Summary, because it shapes Phase 4:

- **Supported:** stop orders cluster at obvious levels and price sweeps them;
  London-open volatility patterns are among the most replicated findings in FX.
- **Contradicted:** Osler (NY Fed Staff Report 150) finds stop-loss orders
  cause *price cascades* — continuation, not reversal. Take-profit orders cause
  reversals. TJR assumes sweeping a stop cluster reverses; the microstructure
  evidence points the other way.
- **Mitigating:** Rules 2.3 (wick-only) and 2.4 (three-factor breakout filter)
  exist precisely to reject continuation cases. ATLAS filters for the subset
  that already reversed. Whether that subset is *predictable* is untested.
- **Unresolved:** no rigorous public backtest of this setup on intraday FX
  exists. The one serious ICT study (StatOasis, 648 backtests) used daily bars
  on US equity ETFs and did not test Judas swing, London session or Asia range.

**Conclusion: the question is genuinely open.** That is why we test both
directions in Phase 4 rather than only the one TJR asserts.

---

## Ground rules

1. **UTC everywhere in backtest.** `Candle.time` is documented UTC; strategy
   code converts to EST internally. The backtest never uses
   `BROKER_UTC_OFFSET_HOURS` — that constant exists only for live MT5 feeds.
2. **Do not change live-path behaviour to make a backtest pass.** If the
   backtest exposes a bug, fix the bug and note it here.
3. **Out-of-sample is sacred.** Split date fixed in Phase 3 and never moved
   afterwards. No parameter chosen on OOS data.
4. **Record every number in this file.** A result not written down did not happen.
5. **Costs stay conservative.** Keep the existing 1.5-pip spread (Rule 9.4b).
   Do not reduce it to improve results.

---

## Phase 0 — Fix the blockers

Make the code under test match the code that would run live.

- [x] Wire `start_scheduler()` / `stop_scheduler()` into `main.py` lifespan.
      Currently defined in `scheduler.py` and **never called anywhere** — the
      20:00 EST daily reset never runs, so `session_terminated` is permanent
      once set, contradicting SETUP.md §10.
- [x] Fix `htf_context.py:111` — `weekly_swept` is hardcoded `False` and never
      set, so `htf_bias_score` caps at 2 instead of 3. Every setup scores one
      confluence point below true value against a `MIN_CONFLUENCE=10` gate.
      Either compute it from weekly candles or document it as deliberately unused.
- [x] Add `venv/` to `.gitignore` and `git rm -r --cached signal-engine/venv`
      (6,872 tracked files, 111 MB `.git`).
- [x] Delete or archive `frontend/src1/` — full duplicate of `src/` with
      drifted contents and no CSS.
- [x] Commit the 18 files of uncommitted work before we start changing things.

**Gate:** `docker-compose up` still healthy; dashboard still loads; no
behaviour change other than the scheduler now running.

**Gate status — PASSED.** `make dev` brings all five services up. The
signal-engine log now prints `scheduler_started jobs=2` at boot, which it
never did before this phase. `/health` returns ok in MANUAL mode; Postgres
migration 001 applied; WebSocket subscribed to 4 Redis channels.

**A third bug surfaced while closing the gate:** the frontend service exposed
`80/tcp` with no host port mapping, so `http://localhost:5173` had never
resolved — despite SETUP.md §3 telling you to open it and `FRONTEND_ORIGIN`
naming it for CORS. Added `ports: ["5173:80"]`. Dashboard now returns HTTP 200.

**Also fixed, beyond the original list:** `frontend/.env.local` held a live
`VITE_API_KEY` and was not matched by `.gitignore` — committing Phase 0 as
found would have pushed it to GitHub. `.gitignore` now covers `.env.*`, and
every line had trailing whitespace which was cleaned up. `frontend.zip` build
artefact dropped.

---

## Phase 1 — Data pipeline

Give ATLAS its own free, reproducible market data.

- [x] Create `signal-engine/data_pipeline/` and port the Dukascopy fetcher
      (public datafeed, no account, no key).
- [x] `fetch.py` — download 1-minute bars, cache raw `.bi5` per day on disk.
- [x] **Strip padded bars.** Dukascopy pads closed-market minutes with flat,
      zero-volume bars carrying the last price — all day Sunday until the
      21:00 UTC open, ~17% of a naive 15M series. Filter on `volume > 0`.
- [x] `adapter.py` — resample cached M1 into the four `List[Candle]` that
      `run_backtest()` expects. Timeframe strings must match exactly:
      `"5min"`, `"15min"`, `"4h"`, `"1day"`. Cast volume to `int`.
- [x] Validation script: zero OHLC violations, no zero-volume bars, weekend
      gaps ~48h, Sunday bars start at 21:00 UTC, bar counts even across years.

**Deliverable:** 11.7 years EUR/USD (2015-01-01 → 2026-09-16), ~4.36M M1 bars,
all four timeframes derived from one aligned source.

**Gate: PASSED — 26/26 checks.**

| | |
|---|---|
| Period | 2015-01-01 → 2026-09-16 (11.71 years) |
| M1 source bars | 4,363,701 |
| 5min / 15min / 4h / 1day | 875,713 / 291,953 / 18,866 / 3,662 |
| Complete Asia sessions | 3,044 |
| M5 bars in LKZ (02:00–05:00 EST) | 109,458 |
| Bars-per-year spread | 0.4% |
| OHLC violations | 0 |

Run it with `./venv/bin/python -m data_pipeline.validate`.

**Two data traps found and handled:**

1. Dukascopy pads closed-market minutes with flat zero-volume bars carrying
   the last traded price — all day Sunday until the 21:00 UTC open, ~17% of a
   naive series. A zero-range 4H candle is trivially "swept and engulfed" by
   whatever follows, which would have manufactured phantom signals. Filtered
   at the M1 stage on `volume > 0`.
2. Dukascopy volume is a float that drops far below 1.0 in thin sessions (min
   observed 0.000876). `Candle.volume` is typed `int`, so a plain cast floored
   125 real M5 bars to zero and made them look like padding. Bars that traded
   now keep a floor of 1. Note backtest volume units differ from live (the EA
   sends tick counts) — nothing in `strategy/` reads it, so it is
   informational only.

**Note:** Phase 0 Docker gate now closed — see Phase 0 above.

---

## Phase 2 — Make the backtest runnable

- [x] Add `__main__` + `argparse` to `strategy/backtest.py` so the command
      already documented in SETUP.md §9 actually works:
      `python -m strategy.backtest --from 2015-01-01 --to 2026-09-16`
- [x] Wire the adapter in as the data source (keep an optional `--csv` path so
      the documented CSV workflow also works).
- [x] Neutralise Redis/Postgres dependencies in backtest mode — `htf_context`
      must be computed per-session from D1/H4 rather than read from Redis.
- [x] First full run. Report Section 9.3 metrics.
- [x] Sanity-check 3 trades by hand against the raw bars: Asia range correct,
      sweep genuine, CHoCH present, FVG midpoint right, SL/TP placed correctly.

### Results — Phase 2 (2015-01-01 → 2026-09-16, 3,661 sessions)

| Metric | Value | Threshold | Pass? |
|---|---|---|---|
| **Total trades** | **26** | ≥50 | **FAIL** |
| Win rate TP1 | 17.4% | ≥55% | FAIL |
| Win rate TP2 | 4.3% | ≥40% | FAIL |
| Avg R:R | −0.02 | ≥1.8 | FAIL |
| Expectancy | −0.018R | ≥+0.3R | FAIL |
| Profit factor | 0.25 | ≥1.4 | FAIL |
| Max consecutive losses | 11 | — | — |
| Net P&L | −$7,226.67 | — | — |

TP1/TP2/TP3 hits 4/1/1 · SL hits 19 · runtime 2m41s.

**Five defects found while making the CLI work** — see commit
`fix(phase-2)`. In order of severity:

1. `now_utc` pinned to session end (08:00 EST) → `is_fvg_expired()` always
   true → node 14 could never pass → **zero trades over any period**.
2. Whole-session candle visibility → `detect_sweep` saw unclosed bars.
   Both fixed by stepping bar by bar at each M5 close, as live does.
3. `post_entry` began at the sweep candle, not the entry decision.
4. `_simulate_outcome` returned on first TP touch, discarding the runner, and
   reported R for wins but raw **pips** for losses.
5. `expectancy_r` substituted `avg_win = 2.0` when `avg_rr_achieved` was
   negative — it reported **+0.500R "PASS"** beside PF 0.25 and a negative
   P&L. Expectancy is one of the four go-live gates; it was structurally
   incapable of reporting failure.

Also: `_slice_candles` rescanned all 875k M5 candles per session (~3.6bn
iterations). Replaced with a bisect-backed `CandleIndex`; full run went from
not finishing to 2m41s.

### Session funnel — where the 3,635 NO_TRADE sessions die

Run with `./venv/bin/python -m strategy.funnel`.

| Stage | Sessions lost | % of all |
|---|---|---|
| no session data (weekends) | 616 | 16.8% |
| Asia range invalid | 484 | 13.2% |
| **sweep invalid** | **2,335** | **63.8%** |
| no 15M CHoCH | 171 | 4.7% |
| no displacement | 14 | 0.4% |
| decision tree rejected | 15 | 0.4% |
| **ENTER** | **26** | **0.7%** |

Terminal reasons: `BREAKOUT_NOT_JUDAS` 1,256 (34.3%) · `DOL_AMBIGUOUS` 484 ·
`DOUBLE_SWEEP` 413 · `ASIA_RANGE_TOO_NARROW` 309 · `NO_SWEEP_IN_LKZ` 178 ·
`NO_15M_CHOCH` 171 · `ASIA_RANGE_TOO_WIDE` 159 · `INSUFFICIENT_RR` 15.

**The sweep-validity stage kills 91% of sessions that reach it.** Of those,
Rule 2.4's breakout filter alone accounts for over half.

**Gate: FAILED — 26 trades over 11.7 years, against a 50-trade minimum.**

Per the plan, we do not proceed to Phase 3. A 26-trade sample cannot separate
signal from noise: the strategy is not measurably profitable *or* unprofitable
at this sample size. **Go to Phase 5** — the filters are too tight to
accumulate evidence, and that is itself the finding.

---

## Phase 3 — Make the result trustworthy

A single number over all history is how people talk themselves into dead
strategies. This phase is the guardrail.

- [ ] **In-sample / out-of-sample split.** Fix the date (proposed 2021-06-01),
      record it here, never move it. Report both halves separately.
- [ ] **Random-entry control.** N random entries at the same session times,
      same SL distances, same TP structure, 300+ runs. Does TJR beat the
      distribution? At 2:1 a random entry already wins ~33% — the R:R is a
      denominator, not an edge.
- [ ] **Node-failure histogram.** Which of the 14 decision-tree nodes rejects
      the most setups? Tells us where the strategy is filtering vs over-filtering.
- [ ] **Per-year and per-grade breakdown** (A+/A/B). Does confluence grade
      actually predict outcome? If not, the whole scorecard is decoration.

### Results — Phase 3

| Test | Result | Verdict |
|---|---|---|
| In-sample expectancy | | |
| Out-of-sample expectancy | | |
| Strategy vs random (percentile) | | |
| Top rejecting node | | |
| Does grade predict outcome? | | |

**Gate:** positive expectancy in **both** halves, and beating >95% of random
runs. Anything less is not an edge.

---

## Phase 4 — Reversal vs continuation

The research question. Same data, same sessions, same risk model, inverted
direction.

- [ ] Add an `--invert` mode: on a BSL sweep go **long** (with the sweep)
      instead of short; on SSL go short. Everything else identical.
- [ ] Run both hypotheses over the full period with the Phase 3 rigor applied.
- [ ] Test the Rule 2.4 breakout filter's actual discriminating power: of
      sweeps it classifies as "Judas", what fraction reverse? Of those it
      classifies as "breakout", what fraction continue? If the two rates are
      the same, the filter is doing nothing.

### Results — Phase 4

| Hypothesis | Trades | Win rate | Expectancy | OOS holds? |
|---|---|---|---|---|
| Reversal (TJR as written) | | | | |
| Continuation (inverted) | | | | |
| Rule 2.4 filter discriminates? | | | | |

**This phase produces a publishable answer either way** — the reversal premise
is either supported against Osler, or it isn't.

---

## Phase 5 — Parameter sensitivity

`config.py` contains ~20 asserted constants. Each is someone's opinion until
measured. One change at a time, scored IS **and** OOS.

- [ ] `SWEEP_MIN_PIPS` (3) / `SWEEP_MAX_PIPS` (8)
- [ ] `ASIA_RANGE_MIN_PIPS` (10) / `ASIA_RANGE_MAX_PIPS` (40)
- [ ] `MIN_CONFLUENCE` (10 of 21)
- [ ] `SL_MAX_PIPS` (15)
- [ ] `DISPLACEMENT_MULT` (1.5)
- [ ] `SL_BUFFER_PIPS` (3) / elevated (5)
- [ ] LKZ window bounds (02:00–05:00 EST)
- [ ] TP structure and partial-close percentages (40/35/25)

**Gate:** a change only counts if it improves **both** halves. Record rejected
changes too — knowing a knob does nothing is worth as much as knowing it helps.

---

## Phase 6 — Verdict

- [ ] Fill every Results table above.
- [ ] Write the honest verdict: does TJR clear its own four thresholds on 11.7
      years of out-of-sample-validated data?
- [ ] If yes: proceed to MANUAL-mode live validation (SETUP.md §7, 10 signals).
- [ ] If no: record what failed and why. A documented negative result is a
      success for this project.

---

## Known limitations — state these with every result

1. **No historical news data.** News filter is node 1; with an empty cache it
   always passes. The backtest will see *more* trades than live would,
   including sessions live-ATLAS would block. Results optimistic on this axis.
2. **Different broker's quotes.** `SWEEP_MIN_PIPS=3` is near the noise floor of
   inter-broker quote differences. Dukascopy's Asia high will not match your
   broker's to the pip. Session-level conclusions hold; borderline sweeps won't.
3. **Fill assumptions.** Limit entries assumed filled when touched; no partial
   fills, no requotes, no weekend gap risk modelled.
4. **Spread is flat 1.5 pips.** Real spreads widen at rollover and on news —
   exactly when some of these setups trigger.
5. **Survivorship in the rules themselves.** TJR's rules were authored after
   observing this market. Some fit is baked in before we start; only OOS
   performance speaks to that.

---

## Progress log

| Date | Phase | Note |
|---|---|---|
| 2026-09-17 | — | Plan created. Research reviewed. Nothing built yet. |
| 2026-09-17 | 2 | Backtest runnable for the first time. 5 correctness defects fixed + bisect optimisation. Full run: **26 trades / 3,661 sessions, expectancy −0.018R**. Gate FAILED (26 < 50). Funnel shows sweep validity kills 91% of surviving sessions. Proceeding to Phase 5, not Phase 3. |
| 2026-09-17 | 0 | Docker gate closed. `scheduler_started jobs=2` confirmed in the running stack. Found and fixed a third bug: frontend had no host port mapping, dashboard was unreachable. |
| 2026-09-17 | 1 | Data pipeline built: `dukascopy.py`, `adapter.py`, `validate.py`. 26/26 checks pass on 11.71 years EURUSD. Padding filter and volume-cast traps fixed. Cache reused from prior work — no download needed. |
| 2026-09-17 | 0 | Branch `phase-0-blockers`. Scheduler wired into lifespan; `weekly_swept` implemented from Daily candles per Rule 3.1c. Repo: 6,962 -> 89 tracked files, venv untracked, `src1` archived, `.env.local` leak closed. 5 commits. Docker gate outstanding. |
