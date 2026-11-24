# AI Trading System: project guide for Claude Code

Last updated: 24 Nov 2026. Owner: UnityFeed (beginner in Python, learning while building).

**Keep this file current.** Whenever a roadmap step, known issue or decision
changes, update the relevant section here in the same commit. Detailed results
and the full status log live in `docs/HISTORY.md` (append new detailed results
there; keep only the summary here).

## What this is
Modular, paper-trading-first Python platform for BTC (1h, 4h, 1d, 1w candles),
with a learning AI that draws scenario forecasts on the chart.
Live trading is NOT enabled and must not be added without an explicit request.

**Owner's trading goal (21 Nov 2026):** spot only, no margin, no leverage, no
short selling: buy low, sell high. Find, from real historical data, the common
ground in the indicators (trend, momentum, oversold/overbought, volatility,
volume) that marks good moments to BUY and to SELL. A pattern only counts when
it holds on years it was not chosen on, after real fees and slippage, compared
with buy-and-hold.

**Priorities:** a finished, usable product (app, paper accounts, data health);
the predictive engine (owner's end goal: the most probable scenarios with their
probabilities, targets and invalidation levels drawn on the chart, every
forecast stored and scored); upgrades per `docs/UPGRADE_PLAN.md`.

## Environment
- Windows, PowerShell, project at `C:\Users\PC\AI_Trading_System`, venv `.venv`.
- ONE working branch: `ccr-11be14d2-h9cw29` (the `predictive-engine` branch was
  merged into it on 24 Nov 2026 and is no longer used).
- Databases in `database\` (all gitignored, never commit them): `market_data.db`
  (hourly candles of Bitstamp, Kraken, Coinbase, Bybit), `paper_trading.db` +
  `paper_lab.db` + `paper_core50.db` (paper accounts), `external_data.db` (Coin
  Metrics), `other_markets.db` (S&P 500, Nasdaq 100, Dow, gold, silver),
  `training_coins.db` (ETH, BNB, XRP, SOL, TRX for the AI), `predictions.db`
  (forecast log), `order_flow.db` (recorder). Automatic backup of
  `market_data.db` once per UTC day before each data update to
  `database\backups\` (newest 7 kept).
- Libraries (allowed since 24 Nov 2026): `requirements.txt` = numpy (REQUIRED),
  scikit-learn, LightGBM, tzdata, pytest (dev). `start_app.bat` installs them
  when one is missing; otherwise `.venv\Scripts\python -m pip install -r requirements.txt`.
- GitHub Actions (`.github/workflows/tests.yml`) runs pytest on Windows
  (Python 3.13 + 3.14) after every push.
- Git via GitHub Desktop; never commit `.env`, API keys or databases.
- Claude Code cloud sessions do NOT have the owner's databases (they use test
  copies). Anything that needs real data is run by the owner on the PC and the
  output pasted back. Bybit blocks the cloud's country (HTTP 403).

## Common commands (PowerShell, from the project root)
ALWAYS activate the venv first: `.venv\Scripts\Activate.ps1` (prompt shows
`(.venv)`; "No module named pytest" = venv not active). Run scripts as modules
(`python -m scripts.name`, no `.py`).
- THE APP: double-click `start_app.bat` (local web server on
  http://127.0.0.1:8765, this PC only). Pages: Overview (selected strategy's
  trade and signal, paper accounts side by side, data health), Chart (full
  history 1h/4h/1d/1w, indicators, strategy trades, market structure,
  support/resistance + Fibonacci, patterns, volume profile, AI forecast per
  timeframe with replay), Strategy tester (full-history backtest vs
  buy-and-hold, per year, start years, fees 0.25% Bybit / 0.80% / 0.40%
  Kraken, margin simulation). Button "Update data & run paper trader" = daily
  routine. Keep the black window open.
- DAILY ROUTINE: `python -m scripts.daily_run` (`--open`, `--skip-update`):
  backup, candles of all exchanges, Coin Metrics, other markets, then every
  paper account.
- AI TRAINING SESSION (~25 min the first time incl. the coin download, then
  ~13 min; all cores): `python -m scripts.train_engine` (`--timeframes 1d 4h`,
  `--workers 2`, `--memorised 1`, `--coins off`, `--no-coin-update`,
  `--markets compact|full`) -> `data\predictive\engine_cache.pkl` (the app
  starts with it; newer candles are learned live) + `forecasts_<tf>_h<h>.csv`.
- Data updates on their own: `update_all_exchanges` (Bybit's first run
  downloads its history from 2021), `update_external_data`,
  `update_other_markets`, `update_training_coins`.
- Data checks: `check_database_integrity`, `check_latest_data`,
  `compare_exchange_data`, `report_data_coverage`,
  `inspect_exchange_price_outliers`, `scan_data_anomalies`,
  `compare_daily_candles` (internet), `check_kraken_gaps` (internet),
  `report_continuous_history`, `report_indicators`.
- Strategy research (append to the trials ledger `data\backtests\trials.csv`):
  `run_backtests` (`--fee`, `--timeframes 4h 1d`), `run_walk_forward`,
  `run_strategy_research` (every registered strategy), `run_strategy_lab`
  (~200,000 combinations, ~6-9 min), `run_turning_points`, `run_ml_research`.
- Predictive engine reports: `run_market_structure`, `run_scenario_outcomes`,
  `run_scenario_models`, `run_learning_replay`.
- Paper trading kill switch: `New-Item database\STOP_PAPER_TRADING` (delete to resume).
- Order flow recorder: `start_recorder.bat` (`record_order_flow`).
- Tests: `python -m pytest -q`. Status check: `python main.py`.

## Architecture (keep it; do not redesign without a clear reason)
- `src/data_collection/`: `MarketData`, validator, provider interface,
  `MarketDataService`, `MarketDataRepository` (SQLite, exchange-aware upsert),
  providers Kraken, Bitstamp, Coinbase, `bybit_provider` (Bybit v5 kline,
  api.bybit.eu then api.bybit.com), Kraken trades recovery
  (`backfill_historical_data`), `exchange_updater` (forward update of all four
  exchanges, Bybit full first download), `backup` (daily DB backup),
  `external_data` (Coin Metrics; first value kept, revisions table),
  `other_markets` (Yahoo Finance daily, own DB, first value kept),
  `training_coins` (Binance public data, own DB), `order_flow` (recorder).
- `src/analysis/`: `technical_indicators` (EMA 20/50/200, RSI 14, MACD,
  Bollinger, ATR, volume; numpy where it helps), `timeframes`
  (aggregation 1h -> 4h/1d/1w, runs), `market_data_quality`
  (`get_clean_candles`: exclusions + zero-volume skip), `primary_history`
  (`get_trading_history` = THE price history; `get_continuous_history` and
  `get_primary_history` for validation), `returns`, `indicators` (old hourly
  SMA), `daily_comparison`.
- `src/strategies/registry.py`: every strategy (rules or graded exposure),
  `ACTIVE_STRATEGY_ID`.
- `src/backtesting/`: `market` (candles + indicators + tradeable opens),
  `conditions`, `engine` (costs, margin simulation), `search`, `walk_forward`,
  `report` (standard full-history test, strategy state), `features`,
  `exposure` (graded strategies), `metrics`, `validation` (Deflated Sharpe,
  PBO), `ledger`.
- `src/paper_trading/`: `store` (append-only decisions and fills),
  `accounts` (extra accounts side by side), `trader` (safety checks; each
  decision stores its `price_source`).
- `src/research/`: `features` (daily feature frame, expanding ranks, no
  look-ahead), `other_market_features`, `turning_points`, `lab`, `models`.
- `src/predictive_engine/`: `structure` (swings, BOS/CHoCH, causal),
  `outcomes` (bull/bear/range first-barrier labels, any timeframe), `levels`
  (S/R zones, Fibonacci, ADX, regime), `volume_profile`, `patterns`
  (life cycle, track record), `scenarios` + `engine` (phase 3 models, report
  only), `forecast_log` (immutable forecasts + outcomes, per timeframe),
  `mtf` (multi-timeframe inputs with completed higher-timeframe context),
  `learner` (candle-by-candle replay, experts + Hedge blend, 10 setting
  versions, self-correction, memorised passes, nested choice), `ml_experts`
  (walk-forward LightGBM trees + analog kNN, pooled with the training coins,
  time-aligned), `training` (parallel training session, compact cache),
  `service` (`EngineService` for the app: forecasts and chart tools for now
  or any past candle, background preparation).
- `src/app/`: `server` (127.0.0.1 only; POST needs header `X-App-Action: 1`;
  indicators per timeframe computed on first use), `routine`
  (`daily_routine`, `load_history`), `chart_data`, `chart_page`
  (Lightweight Charts 5.2.1 from jsDelivr), `strategy_page`, `overview_page`.
- `src/reporting/dashboard.py`: offline overview file + shared page shell/CSS.
- `src/risk_management/`, `src/execution/`: empty (not started).
- `scripts/` (tools above), `scripts/archive/` (finished one-time jobs; run
  only with a clear reason), `main.py` (read-only status check), `tests/`.

`MarketData` fields: exchange, symbol, market, timestamp (tz-aware UTC candle
open), open, high, low, close, volume. DB key: (exchange, market, symbol,
timeframe, timestamp).

## Decisions already made (do not reverse without the owner)
- PRICE SOURCE (owner, 24 Nov 2026: "I don't like that the BTC price is mixed
  from different sources", choice "longest history first"): ONE source for
  every hour it has: Bitstamp BTC/USD (complete since Oct 2013). Only hours
  Bitstamp lacks (excluded or zero-volume candles, outages) are filled, in
  order of stored history size: Kraken, Coinbase, Bybit BTC/USDT
  (`primary_history.PRICE_SOURCES`, `get_trading_history`). Filled hours are
  "substituted": never a fill there, grey on the chart. Used everywhere: app,
  chart, paper trading, AI, backtests, research. If the first source has no
  data at all, the next one becomes the main source. Test DB: 114,950 of
  114,960 hours from Bitstamp, no source jump above 1%. (Earlier the same day:
  Bybit from 2021 as the main price; replaced by this decision.)
- Exchanges in the DATABASE are never merged or overwritten: each keeps its own
  rows. Always pass `exchange=` explicitly. Bybit = exchange "bybit", symbol
  "BTC/USDT" (the owner's exchange; fees are Bybit's). Kraken, Coinbase and
  Bybit are validation and fill-in sources.
- Never fabricate candles: no interpolation or forward-fill. Gaps no exchange
  covers stay gaps; indicators and returns restart there. 4h/1d/1w candles are
  derived in memory from complete sets of clean hours on UTC boundaries (weeks
  start Monday); a period with a missing hour is skipped.
- Flag suspicious data in `data/quality/confirmed_anomalies.csv`; never delete
  silently. Only `analysis_action` starting with `exclude` removes a candle.
  Zero-volume candles (Bitstamp filler) are skipped, so they become gaps.
- DB migration and the Kraken CSV import are done. Never repeat them.
- Indicators: value stamped T uses candles up to and including T (known at T's
  close). EMA seeded with SMA; RSI and ATR Wilder; Bollinger population std;
  relative volume divides by the PREVIOUS n.
- Signals use completed candles only; fills no earlier than the next candle's
  open, with fees and slippage; no fills on substituted hours or on the first
  main-source hour after a substituted stretch (stale reopening prints).
- Costs (owner, 22 Nov 2026, Bybit EU, < EUR 100k): default fee 0.25% per side
  (Bybit EU spot VIP 0, bybit.eu fee page read 22 Nov 2026; exact rate on the
  owner's "My Fee Rate" page); Kraken 0.80% taker / 0.40% maker selectable for
  comparison; slippage 0.05% per side (assumption). Long-only, all-in/all-out
  or graded 0-100%, no leverage.
- Margin is a SIMULATION toggle only (Strategy tester). The paper trader and
  any future live trading never use margin unless the owner asks. Kraken margin
  terms in `engine.py` (read 21 Nov 2026).
- Paper trading: own database files; one decision per completed candle with a
  snapshot; decisions and fills append-only, never edited; safety checks only
  BLOCK (stale data > 3 h, kill switch). Switching strategy requires an
  explicit account reset. Accounts side by side (owner, 22 Nov 2026): main
  `paper_trading.db` ("Daily trend + MACD", $10,000 from 1 Jan 2026),
  `paper_lab.db` ("Lab: weekly MACD + momentum, 50% core") and
  `paper_core50.db` ("50% core + Daily trend + MACD"), $3,500 each from
  22 Nov 2026. Compare after >= 3 months (late Feb 2027).
- EVERY strategy goes into `src/strategies/registry.py` (standard test, chart
  trades). Show the full-history view next to the walk-forward result; label
  the full-history view optimistic when its years were used to choose. New
  building blocks go into `src/backtesting/conditions.py` first, with tests.
- Strategy selection guards against overfitting: choose on 2013-2016 and
  2017-2021 (rank by the WEAKEST window), never on 2022-now. 2022-now has been
  looked at often, so forward paper trading is the clean test. Log every trial.
- Judging a strategy for someone starting NOW: "BTC compared with holding"
  over every start year ("If you had started in..." table), not one year.
- Deterministic rules, statistics and trained models form the core; no paid LLM
  call per decision. A future risk engine must have veto power over any signal.
- Every prediction is timestamped and stored, never rewritten; scored with
  Brier score, log loss and calibration (`predictions.db`).
- The AI (predictive engine): causal only (truncation tests for every
  detector and learner); honest results = nested walk-forward (each year uses
  the setting version that was best on EARLIER years); memorised passes are
  reported only, never used. The engine never trades and never touches the
  paper-trading files.
- AI inputs (24 Nov 2026): training coins ETH, BNB, XRP, SOL, TRX (owner: pure
  training, not tracked or traded) are ON (they improved 1d/4h on the test DB);
  other markets (stocks, gold, silver) are collected but OFF as inputs
  (`other_market_features.AI_MODE = "off"`: they made forecasts worse); stocks
  and commodities would need their own AI later (owner).
- The app binds 127.0.0.1 only and only writes market data through the daily
  routine. The chart library (pinned) is the one web dependency.

## Research input (owner, 22 Nov 2026)
Reports in `docs/research/` (read before strategy work): the long-only deep
dive v2 (PRIMARY: never be fully out; core + trend overlay; graded exposure;
methodology), the market research blueprint (vision, later phases), our
feasibility check. The project wins where they conflict: real fees (0.25%
Bybit, not 0.10%), no merged/forward-filled prices, forward paper trading as
the clean test. Predictive engine: owner's blueprint and the gated plan in
`docs/predictive_engine/`.

## Status (summary; details and every number in `docs/HISTORY.md`)
- Data verified 21 Nov 2026 (integrity, cross-exchange, daily candles equal the
  exchanges' own). Price source switched to Bitstamp-first on 24 Nov 2026:
  owner to rerun `daily_run` (downloads Bybit, paper accounts), then
  `train_engine`, `run_strategy_research` on the PC.
- Strategies (real DB, 22 Nov 2026, 0.25% fee, old price history): best
  registered "Lab: weekly MACD + momentum, 50% core" x1.46 vs holding (drop
  73%, ~1 trade/year, ahead from 10/13 start years); "50% core + Daily trend +
  MACD" x1.29; "Daily trend + MACD" x0.81 with a much smaller drop. PBO across
  registered strategies 0.93: no single proven winner; paper trading decides.
  Hourly and 4h rule strategies do not survive fees.
- AI (test DB, 24 Nov 2026, honest nested result, skill vs base rate): 1h
  +4.5% / +5.6% / +4.7% (1/3/7 days), 4h +2.2% / +3.6% / +3.7% (1/7/14 days),
  1d +1.6% / +1.3% / +1.0% (7/14/30 days). Real but small edges; treat the
  chances as rough odds. Owner to train on the real DB.
- Upgrades done 24 Nov 2026: libraries, pattern experts, GitHub Actions,
  backups, speed (app start ~1.4 s, training ~3x faster), cleanup run
  (dead code removed, every script run against a test DB).

Known issues:
1. Bitstamp provider assumptions not confirmed against official docs (max
   `limit=1000`, `end`, `exclude_current_candle`).
2. Bitstamp's own outage 5-9 Jan 2015 (107 h of zero-volume filler) is only
   partly covered by other exchanges; uncovered hours stay gaps.
3. `compare_exchange_data` / `inspect_exchange_price_outliers` read raw data
   (no exclusions), so their maxima include known issues.
4. Volume differs between exchanges, so volume features are distorted on
   filled hours (rare now: Bitstamp is complete).
5. Yahoo Finance (other markets) is not an official API; it may change.

## Roadmap (next steps; full text in `docs/HISTORY.md`)
1. Owner: run the daily routine, `train_engine` and `run_strategy_research` on
   the real DB with the Bitstamp-first prices; paste the output.
2. Live mode: stream the current price into the chart, live rule checklist,
   alerts before a rule triggers (decisions stay on completed candles).
3. Upgrade plan (`docs/UPGRADE_PLAN.md`): logs with rotation, numpy indicators
   (EMA/RSI/MACD/ATR), Windows Task Scheduler for the routine and training,
   notifications (Telegram or e-mail), funding rates / open interest, macro.
4. Paper-account review late Feb 2027; then decide the strategy to follow.
5. Risk engine with veto power (proposed paper values: 0.5% risk per trade,
   2% max daily loss, stop required, emergency shutdown) before anything real.
6. Predictive engine ideas: Elliott Wave / trend lines (only if they add
   skill), order flow once months are recorded, stocks/commodities AI.

## How to work with the owner
- Beginner: explain important decisions in plain language. Give exact
  PowerShell commands.
- Autonomy is REVIEW: propose and make changes, the owner inspects and approves.
  No destructive actions (deleting data, rewriting git history, force push,
  touching the database files) without asking first. Back up the DB before any
  schema or data change.
- Batch related changes into one coherent step; preserve working components.
- Be honest about what is verified (ran it) versus assumed. Verify exchange API
  details against current official docs, do not assume limits.
- Commit after complete features with descriptive messages, and update this file.
