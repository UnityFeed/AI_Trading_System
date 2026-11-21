# AI Trading System: project guide for Claude Code

Last updated: 21 Nov 2026. Owner: UnityFeed (beginner in Python, learning while building).

**Keep this file current.** Whenever a roadmap step, known issue or decision
changes, update the relevant section here in the same commit.

## What this is
Modular, paper-trading-first Python platform, currently BTC/USD on 1h candles.
Live trading is NOT enabled and must not be added without an explicit request.
Long-term goal: collect multi-exchange data, analyse market structure, produce
calibrated scenario probabilities, run deterministic risk controls, paper trade,
and only after validation consider automated execution.

## Environment
- Windows, PowerShell, project at `C:\Users\PC\AI_Trading_System`, venv `.venv`
- SQLite database at `database\market_data.db` (gitignored; back it up separately)
- Application code uses only the Python standard library; `requirements.txt`
  lists only `pytest` (dev). Install: `.venv\Scripts\python -m pip install -r requirements.txt`
- Git via GitHub Desktop; never commit `.env`, API keys or the database
- Claude Code cloud sessions do NOT have the database. Anything that needs real
  data must be run by the owner on the PC and the output pasted back.

## Common commands (PowerShell, from the project root)
Run scripts as modules (`-m scripts.name`, no `.py`) because imports start with `src.`.
- Activate venv: `.venv\Scripts\Activate.ps1` (then `python` = venv python)
- Tests: `python -m pytest -q`
- Fetch latest candles for all 3 exchanges: `python -m scripts.update_all_exchanges`
  (forward-only from each exchange's latest stored candle; Kraken's OHLC API only
  serves roughly the last 720 hourly candles, so gaps older than ~30 days need the
  Kraken trades recovery instead)
- Data checks: `python -m scripts.check_database_integrity`,
  `python -m scripts.check_latest_data`, `python -m scripts.compare_exchange_data`
- Per-year gaps and zero-volume candles: `python -m scripts.report_data_coverage`
- Largest cross-exchange price differences: `python -m scripts.inspect_exchange_price_outliers`
- Daily candle check (needs internet) and 4h/1d counts: `python -m scripts.compare_daily_candles`

## Architecture (keep it; do not redesign without a clear reason)
- `src/data_collection/`: `MarketData` dataclass, `data_validator`, `MarketDataProvider`
  interface, `MarketDataService` (one provider at a time), `MarketDataRepository`
  (SQLite, exchange-aware upsert), providers (Kraken, Bitstamp, Coinbase),
  `MarketDataCollector` (forward collection for Kraken), Kraken trades recovery
- `src/analysis/`: `indicators.py` (SMA), `returns.py`, `market_data_quality.py`
  (`get_clean_candles` applies `data/quality/confirmed_anomalies.csv` exclusions
  and skips zero-volume candles), `primary_history.py` (Bitstamp <2017, Kraken 2017+),
  `timeframes.py` (`aggregate_hourly_candles`: 1h -> 4h/1d), `daily_comparison.py`
- `src/strategies/sma_crossover.py`: long-only crossover signals
- `src/risk_management/`, `src/execution/`: empty packages (not started)
- `scripts/`: import, update, integrity, comparison and anomaly tools
- `tests/`: data layer, collector, SMA, returns, SMA crossover, data quality,
  primary history, timeframes, daily comparison
  (also guards the real `confirmed_anomalies.csv` against format errors).
  `tests/helpers.py` has `hourly_candles()` for building test candles.

`MarketData` fields: exchange, symbol, market, timestamp (tz-aware UTC candle open),
open, high, low, close, volume. DB primary key:
(exchange, market, symbol, timeframe, timestamp).

## Decisions already made (do not reverse)
- Kraken is primary; Bitstamp and Coinbase are independent validation sources.
- NEVER merge exchange candles into one synthetic series. Never overwrite one
  exchange's rows with another's.
- Primary history (owner decision 21 Nov 2026): Bitstamp before 2017-01-01,
  Kraken from 2017-01-01 (first full-coverage Kraken year). Use
  `get_primary_history` (`src/analysis/primary_history.py`). It returns separate
  single-exchange segments, never one merged list: run indicators/returns/
  backtests per segment, so the switch-over acts as a gap. Nothing is copied in
  the DB. Report backtest results per segment as well as combined. Always pass `exchange=` explicitly (repository
  defaults to "kraken" only for backward compatibility).
- Do NOT fill missing hours with fabricated candles. Preserve gaps. Rolling windows
  and returns reset or skip across gaps. Do not train sequences across gaps.
- Flag suspicious data (see `confirmed_anomalies.csv`); do not silently delete.
  Only `analysis_action` values starting with `exclude` remove a candle from
  analysis; `keep` (reviewed, genuine) and `review_pending` are notes only.
- Zero-volume candles are exchange filler (no trades, no real price).
  `get_clean_candles` skips them by default, so they become gaps. They stay in
  the database. Only Bitstamp has them (122, incl. 107 h outage 5-9 Jan 2015).
- DB migration and the Kraken CSV import are done. Never repeat them.
- Timeframes: 1h (primary), 4h, 1d. 4h/1d are derived in memory from clean
  hourly candles (not stored in the DB), on UTC boundaries (4h at 00/04/../20,
  1d at 00:00), timestamp = period start. A period with any missing/excluded
  hour is skipped, never built from partial data. Verified 21 Nov 2026 against
  live APIs: all three exchanges' daily candles start 00:00 UTC and equal the
  sum of their 24 hourly candles exactly. Kraken's daily OHLC API only serves
  the last 720 days; Bitstamp and Coinbase serve full daily history.
- Deterministic rules, statistics and trained models form the core; no paid LLM
  call per trade decision. The risk engine must have veto power over any signal.
- Every future prediction must be timestamped and stored, never rewritten
  afterwards. Evaluate with Brier score, log loss and calibration, not accuracy alone.
- Signals use completed candles only. Backtests must fill no earlier than the
  next candle, with fees and slippage. Avoid look-ahead bias.

## Status
Done: data layer for 3 exchanges, update/import scripts, integrity, comparison and
anomaly tooling, SMA, hourly returns, SMA crossover signals.
21 Nov 2026: roadmap step 1 done (requirements.txt, collector tests rewritten for
the forward-only collector, tests for SMA/returns/crossover). Step 2 code done
(4h/1d derivation and daily check), tested on 20 days of live data from all three
exchanges (exact match); full-history run on the real DB pending (owner).

Step 0 results (owner ran on PC, 21 Nov 2026, data current to 2026-11-21 11:00 UTC;
SQLite integrity ok, 0 duplicates, 0 invalid OHLCV, 0 non-aligned timestamps):
| exchange | first candle      | candles | missing hours |
| bitstamp | 2013-10-06 00:00  | 115,068 | 0             |
| coinbase | 2015-07-20 21:00  |  99,344 | 55            |
| kraken   | 2013-10-06 21:00  | 104,172 | 10,875 (largest gaps all 2013-2014) |
Per year (`report_data_coverage`): Kraken is sparse before 2016 (2013: 60%,
2014: 38%, 2015: 50% of hours; 2016: 98%; 2017+: >99.4%) and early Kraken hourly
volume is tiny (5-40 BTC vs ~1,500 on Bitstamp), which explains most outliers.
Coinbase gaps are small and scattered (max 22 h/year in 2018).
Avg close difference between exchanges 0.13-0.22%. `compare_exchange_data` does
NOT apply `confirmed_anomalies.csv`: its 171.96% (bitstamp/kraken) and 19.33%
(coinbase/kraken) maxima are the known Kraken anomalies 2013-11-10 04:00 and
2015-11-03 10:00 (difference is relative to the mean of the two closes).
Outlier review: Coinbase 2017-12-07 15-18h `keep` (genuine premium); Kraken
2017-05-07 22:00 excluded (owner, `exclude_owner_reviewed`); five pre-2017 Kraken
hours stay `review_pending` (not used by the primary history).

Known issues:
1. `main.py` prints "Database: Connected" without testing the connection, and only
   initialises the collector.
2. Bitstamp provider assumptions not confirmed against official docs: max
   `limit=1000`, `end` and `exclude_current_candle` parameters. Coinbase provider
   was checked against docs (300-candle cap, columns time, low, high, open,
   close, volume, granularity 3600).
3. Bitstamp's pre-2017 history still has its own gaps after cleaning (e.g. the
   107 h outage 5-9 Jan 2015); these stay gaps.
4. `compare_exchange_data` and `inspect_exchange_price_outliers` read raw data
   (no exclusions, zero-volume included), so their maxima include known issues.
5. `calculate_hourly_sma` and `calculate_hourly_returns` assume 1h spacing; make
   them timeframe-generic in step 3 before using them on 4h/1d candles.

## Roadmap (do in order)
0. [DONE 21 Nov 2026] Data updated and verified (see Status). Bitstamp filler
   candles handled; outliers classified; primary history defined.
1. [DONE 21 Nov 2026] Housekeeping: requirements.txt, fix collector tests, tests
   for SMA, returns and crossover.
2. [CODE DONE 21 Nov 2026, owner to run `compare_daily_candles` on the real DB]
   Derive 4h and 1d candles from clean hourly data, per primary-history segment (UTC boundaries, no partial
   candles, gap-aware). Compare daily with exchange daily candles.
3. Indicators: EMA 20/50/200, RSI, MACD, Bollinger, ATR, volume features.
   Timeframe-generic, tested, reset across gaps, no look-ahead.
4. Minimal backtester (next-candle fills, fees, slippage, vs buy-and-hold).
5. Risk engine (proposed paper values, not approved: 0.5% risk per trade, 2% max
   daily loss, 5 positions, 2.5% aggregate open risk, no leverage, stop required,
   emergency shutdown), then paper-trading loop.
6. Regime detection, historical analogues, scenario engine, probability
   calibration, prediction log, ML. Only after the data foundation is validated.

## How to work with the owner
- Beginner: explain important decisions (timestamps, pagination, validation,
  database behaviour) in plain language. Give exact PowerShell commands.
- Autonomy is REVIEW: propose and make changes, but the owner inspects and approves.
  No destructive actions (deleting data, rewriting git history, force push,
  touching the database file) without asking first. Back up the DB before any
  schema or data change.
- Batch related changes into one coherent step; don't ask the owner to test every
  tiny change. Preserve working components.
- Be honest about what is verified (ran it) versus assumed. Verify exchange API
  details against current official docs, do not assume limits.
- Commit after complete features with descriptive messages, and update this file.
