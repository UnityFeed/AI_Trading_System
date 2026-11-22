# AI Trading System: project guide for Claude Code

Last updated: 22 Nov 2026. Owner: UnityFeed (beginner in Python, learning while building).

**Keep this file current.** Whenever a roadmap step, known issue or decision
changes, update the relevant section here in the same commit.

## What this is
Modular, paper-trading-first Python platform for BTC/USD (1h, 4h, 1d candles).
Live trading is NOT enabled and must not be added without an explicit request.

**Owner's trading goal (21 Nov 2026):** spot only, no margin, no leverage, no
short selling: buy low, sell high. Find, from real historical data, the common
ground in the indicators (trend, momentum, oversold/overbought, volatility,
volume) that marks good moments to BUY and to SELL, using every indicator to
time those moments. A pattern only counts when it holds on years it was not
chosen on, after Kraken's real fees and slippage, compared with buy-and-hold.

**Current priority (owner, 21 Nov 2026):** a finished, usable product first:
show what the owner does (paper account), what the data is, and where to
work from. Finding a winning strategy is parked for later (roadmap step 9).

Long-term: multi-exchange data, market-structure analysis, calibrated scenario
probabilities, deterministic risk controls, paper trading, and only after
validation consider automated execution.

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
- THE APP (no terminal needed): double-click `start_app.bat` in the project
  folder. It runs `python -m scripts.run_app`: a local web server on
  http://127.0.0.1:8765 (this PC only) and opens the browser. One strategy
  choice is shared by all pages (remembered in the browser). Pages: Overview
  (the selected strategy's latest/open trade and how it is doing, its signal
  at the latest close, recent trades, paper account, data health), Chart (one
  chart for everything: full history 1h/4h/1d, indicators, the selected
  strategy's backtest trades, open-trade buy/stop lines, a BUY/SELL signal
  marker and a status strip with the rules) and Strategy tester (full-history
  backtest: vs buy-and-hold, per year, every trade, 0.25% Bybit EU / 0.80% / 0.40% Kraken fees, margin
  Off/2x/3x/5x/10x, "Test from" full history or 1 Jan of any year, "BTC
  compared with holding" ratio, and an "If you had started in..." table with
  every start year; an "All strategies compared" table at the top; Sharpe,
  Sortino, break-even fee, top-20 days, exposure-matched mix; graded
  strategies show every change of the BTC share). The button "Update data & run paper
  trader" does the daily routine. Keep the black window open; close it to stop.
- Activate venv: `.venv\Scripts\Activate.ps1` (then `python` = venv python).
  ALWAYS activate it first: the system Python (3.15) has no pytest ("No module
  named pytest" = venv not active). The prompt then starts with `(.venv)`.
- DAILY ROUTINE (update data, paper trade, rebuild dashboard):
  `python -m scripts.daily_run` (`--open` opens the page; `--skip-update`;
  first run only: `--start YYYY-MM-DD`, default 1 Jan of this year)
- Dashboard only: `python -m scripts.build_dashboard --open` -> `reports/dashboard.html`
- Stop new paper buys: `New-Item database\STOP_PAPER_TRADING` (delete it to resume)
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
- Indicators on the primary history, 1h/4h/1d: `python -m scripts.report_indicators`
- Missing Kraken hours since 2017 and whether Kraken has trades for them
  (needs internet): `python -m scripts.check_kraken_gaps`
- Continuous history: filled hours, remaining gaps, jumps between exchanges:
  `python -m scripts.report_continuous_history`
- Strategy search / backtest (all indicator combinations, 1h/4h/1d, ~30 s):
  `python -m scripts.run_backtests` (options: `--fee 0.40`, `--slippage 0.05`,
  `--timeframes 4h 1d`). Full results as CSV in `data/backtests/` (gitignored).
- Full-history test: candidates year by year + walk-forward (~1 min):
  `python -m scripts.run_walk_forward` (options: `--fee 0.40`, `--timeframes 1d`)
- Strategy research, every REGISTERED strategy with the same test (full
  history, eras, fee sensitivity, Sharpe/Sortino, break-even fee, top-20 days,
  exposure-matched mix, start years, Deflated Sharpe, PBO; ~5 s):
  `python -m scripts.run_strategy_research` (`--fee 0.40`, `--no-log`).
  `run_backtests`, `run_walk_forward` and this script append to the trials
  ledger `data/backtests/trials.csv` (gitignored, append-only).
- STRATEGY LAB (~200,000 combinations: filter x trigger x exit x trailing
  stop x core share, all CPU cores, ~6 min on 4 cores; chosen on 2013-2021 only,
  walk-forward, common ground, Deflated Sharpe, PBO):
  `python -m scripts.run_strategy_lab` (`--fee 0.80`, `--workers 2`); every
  result in `data/backtests/lab_results.csv`
- Turning points (swing lows/highs, how late each strategy acts, what features
  look like before lows/highs): `python -m scripts.run_turning_points`
- Machine learning (walk-forward logistic regression and nearest-neighbour
  "analog" models: up in 30 days, swing low within 20 days; Brier/log loss/
  calibration; trading tests; ~20 s): `python -m scripts.run_ml_research`;
  predictions kept in `data/backtests/ml_predictions_<time>.csv`
- External daily data (Coin Metrics: MVRV, market cap, hash rate; free, no
  key): `python -m scripts.update_external_data` (the daily routine and the
  app button also do it) -> `database/external_data.db`
- Order book + buy/sell order flow recorder (Kraken, from now on): double-click
  `start_recorder.bat` or `python -m scripts.record_order_flow` (`--once`,
  first run `--days 30`) -> `database/order_flow.db`

## Branch `predictive-engine` (owner, 22 Nov 2026)
Separate branch for the Predictive Market Structure & Scenario Engine (owner's
blueprint `docs/predictive_engine/2026-11-22_blueprint_predictive_market_structure.md`,
gated plan `docs/predictive_engine/PLAN.md`). Owner's end goal: scenarios with
their probabilities, targets and invalidation levels drawn on the chart, every
forecast stored and scored. The owner keeps running the daily routine / paper
accounts from the main working branch (`ccr-11be14d2-h9cw29`), not from this
one (both branches share the same database files). The engine only reads
market data and never touches the paper-trading files; its forecasts go to
their own `database/predictions.db` (phase 4).
- Market structure (phase 1): `python -m scripts.run_market_structure`
  (`--left 5 --right 5` for bigger swings): trend, last swing high/low,
  labelled swings, BOS/CHoCH/sweeps on 1w/1d/4h.

## Architecture (keep it; do not redesign without a clear reason)
- `src/data_collection/`: `MarketData` dataclass, `data_validator`, `MarketDataProvider`
  interface, `MarketDataService` (one provider at a time), `MarketDataRepository`
  (SQLite, exchange-aware upsert), providers (Kraken, Bitstamp, Coinbase),
  `MarketDataCollector` (forward collection for Kraken), Kraken trades recovery
- `src/analysis/`: `indicators.py` (hourly SMA, used by the crossover strategy),
  `technical_indicators.py` (`calculate_indicators`: EMA 20/50/200, RSI 14,
  MACD 12/26/9, Bollinger 20/2, ATR 14, volume SMA / relative volume 20; any
  timeframe), `returns.py` (`calculate_returns(candles, timeframe)`), `market_data_quality.py`
  (`get_clean_candles` applies `data/quality/confirmed_anomalies.csv` exclusions
  and skips zero-volume candles), `primary_history.py` (Bitstamp <2017, Kraken 2017+;
  `get_continuous_history` gap-filled series, `get_primary_history` segments),
  `timeframes.py` (`aggregate_hourly_candles`: 1h -> 4h/1d; `split_into_runs`:
  consecutive-candle runs for any timeframe), `daily_comparison.py`
- `src/strategies/registry.py`: `STRATEGIES` (every known strategy: id, name,
  timeframe, `StrategySpec` (kind "rules", all-in/all-out) or `ExposureSpec`
  (kind "exposure", graded 0-100% BTC), plain-language description, origin)
  and `ACTIVE_STRATEGY_ID` (followed by the paper trader)
- `src/strategies/sma_crossover.py`: long-only crossover signals (older, hourly)
- `src/backtesting/`: `market.py` (`build_market`: candles + indicators +
  which opens are tradeable), `conditions.py` (entry building blocks in three
  roles: trend filter, trigger, volume filter; exit rules; ATR stops),
  `engine.py` (`run_backtest`, `buy_and_hold`, `CostSettings`; optional
  `record_equity`), `search.py` (all 540 combinations, selection/test windows,
  ranking), `walk_forward.py` (one continuous run per combination summarised per
  year; yearly walk-forward picks chosen only on earlier years), `report.py`
  (`strategy_report`: the standard full-history test for one strategy,
  JSON-ready: summary, per year, trades, daily equity; trade markers;
  `strategy_state`: rules at the latest close, open trade with its result if
  sold now and stop, BUY/SELL signal to be carried out at the next open,
  recent trades; same continuous run as the backtest; `prepare` +
  `run_strategy` run either kind; `exposure_state` for graded ones),
  `features.py` (SMA, n-candle return, prior high/low, EWMA volatility; reset
  at gaps), `exposure.py` (graded strategies: `ExposureSpec`, `VOTES`, layers
  core/fixed weight -> volatility cap -> MVRV-Z cap (1-day lag) -> hash-rate
  filter (2-day lag); `plan`, `run_exposure_backtest` (band, fees on the
  traded amount, same fill timing), `fixed_mix` = exposure-matched benchmark),
  `metrics.py` (Sharpe, Sortino, top-20-days capture, break-even fee,
  turnover), `validation.py` (Deflated Sharpe Ratio, PBO by CSCV),
  `ledger.py` (trials ledger CSV)
- `src/paper_trading/`: `store.py` (`PaperTradingStore`, own SQLite file
  `database/paper_trading.db`: account, append-only decisions and fills),
  `accounts.py` (`EXTRA_ACCOUNTS`, `open_extra_accounts`: extra paper
  accounts side by side, one SQLite file each in database/),
  `trader.py` (`PaperTrader`, `ACTIVE_STRATEGY` = candidate 1 on 1d, $10,000
  start, safety checks: stale data, kill switch; also follows graded
  strategies: a BUY/SELL moves the account to the target share stored in the
  decision snapshot, no schema change)
- `src/reporting/dashboard.py`: `gather` + `render` -> the OFFLINE overview file
  written by `daily_run`/`build_dashboard` (the app has its own Overview); (key
  numbers + BTC price, paper account chart, strategy today, latest decisions,
  market readings 1d/4h/1h, data status, research summary, folded terminal
  commands); `page()` is the shared HTML shell (favicon, shared `CSS`) used by
  every page; `CSS` holds the design tokens (light/dark), cards (`.panel`,
  `.kpi`), tables, badges and pills. Inline SVG charts scroll sideways on
  phones. Links to app-only pages are left out of the offline file.
- `src/app/`: `routine.py` (`daily_routine`, `load_history`: shared by
  `scripts/daily_run.py` and the app button), `chart_data.py` (candles +
  indicators per timeframe in chunks, filled-candle flag, trade markers),
  `chart_page.py` (chart page + shared nav bar; TradingView Lightweight Charts
  5.2.1 from jsDelivr, Apache 2.0: 1h/4h/1d, scroll back loads older chunks,
  toggles for EMA 20/50/200, Bollinger, trades, volume, RSI, MACD, ATR),
  `strategy_page.py` (Strategy tester page, log-scale equity chart),
  `overview_page.py` (app Overview, filled from /api/strategy-state),
  `chart_page.SHARED_SELECTION_SCRIPT` (`SelectedStrategy`: the shared choice,
  key `selected-strategy`; `?strategy=` links win, else last choice, else the
  active strategy),
  `server.py` (`AppState` caches history/series/dashboard/markets/reports; stdlib
  ThreadingHTTPServer on 127.0.0.1; POST needs header `X-App-Action: 1`)
- `src/data_collection/external_data.py`: `ExternalDataStore`
  (`database/external_data.db`; first value seen is kept, later changes go to
  a `revisions` table), `fetch_coinmetrics`, `update_external_data`
- `src/data_collection/order_flow.py`: `OrderFlowStore`
  (`database/order_flow.db`: hourly buy/sell volume + exact VWAP from Kraken
  trades, order-book snapshot summaries), `collect_trade_flow`,
  `run_recorder`. Collected only; no strategy uses it yet.
  `KrakenTradesProvider.fetch_trades_with_side` keeps the taker side.
- `src/data_collection/exchange_updater.py`: `update_all_exchanges(repository,
  log)` (moved from the script; `scripts/update_all_exchanges.py` is a wrapper)
- `src/research/` (roadmap 10): `features.py` (`build_frame`: ~39 daily
  features known at the close: trend, momentum, cycle (drop from ATH, 200-week
  average), volatility, volume, candle wicks, WEEKLY chart (last completed week
  only), on-chain (lagged), Coinbase premium; each also as an expanding
  percentile rank 0..1, no look-ahead; `weekly_from_daily`, `coinbase_premium`),
  `turning_points.py` (`zigzag`, `lag_study`, `event_study`), `lab.py`
  (`building_blocks`, `LabSpec` state machine, parallel `run_search`, `walk_forward`
  single/family/top10, `lab_vote`: registry votes named
  `lab:FILTER|TRIGGER|EXIT|TRAIL`), `models.py` (logistic regression, analog
  kNN, point-in-time labels, walk-forward predictions, `score`)
- `src/predictive_engine/` (branch `predictive-engine`): `structure.py`
  (`raw_pivots`: pivot highs/lows confirmed `right` candles later;
  `analyse`: alternating labelled swings HH/LH/HL/LL, trend per candle,
  BOS/CHoCH/sweep events; all causal, truncation-tested)
- `src/risk_management/`, `src/execution/`: empty packages (not started)
- `scripts/`: update, integrity, comparison, anomaly, research and app tools;
  `scripts/archive/` holds finished one-time jobs (initial imports incl. the
  Kraken CSV import, one-off investigations) with a README; run them only as
  `python -m scripts.archive.<name>` and only with a clear reason
- `main.py`: read-only status check (database freshness, paper account)
- `tests/`: data layer, collector, SMA, returns, SMA crossover, data quality,
  primary history, continuous history, timeframes, daily comparison,
  technical indicators, Kraken gap finder, backtesting engine/search, walk-forward,
  paper trading, dashboard, app (chart data, server routes, button protection),
  strategy registry and report
  (also guards the real `confirmed_anomalies.csv` against format errors).
  `tests/helpers.py` has `hourly_candles()` for building test candles.

`MarketData` fields: exchange, symbol, market, timestamp (tz-aware UTC candle open),
open, high, low, close, volume. DB primary key:
(exchange, market, symbol, timeframe, timestamp).

## Decisions already made (do not reverse)
- Kraken is primary; Bitstamp and Coinbase are independent validation sources.
- Never merge or overwrite exchanges in the DATABASE: each exchange's rows stay
  its own. Always pass `exchange=` explicitly (repository defaults to "kraken"
  only for backward compatibility).
- Primary history (owner decisions 21 Nov 2026): Bitstamp before 2017-01-01,
  Kraken from 2017-01-01. Two views in `src/analysis/primary_history.py`:
  - `get_continuous_history` (DEFAULT for indicators/research/backtests): one
    unbroken in-memory series. Hours the primary exchange lacks (outages,
    excluded or zero-volume candles) are filled with the real clean candle of
    another exchange: Kraken period -> Coinbase, then Bitstamp; Bitstamp period
    -> Coinbase, then Kraken. Candles are relabelled `exchange="primary"`; the
    true source per hour is in `.sources`, substitutions in
    `.substituted_hours()`, every switch between exchanges with its price jump
    in `.source_changes` (`.large_jumps()` > 1%). Hours no exchange has stay gaps.
  - `get_primary_history`: separate single-exchange segments with real gaps,
    for validation and anything that must reflect one exchange only.
- Backtests must NOT fill orders on substituted hours (the primary exchange was
  down; nobody could trade there). Signals may use them. Also no fills at the
  open of the first primary-exchange hour after a substituted stretch (Kraken's
  reopening print is stale; see Status).
- Never fabricate candles: no interpolation or forward-fill. Gaps that no
  exchange covers stay gaps; rolling windows and returns reset there.
- Flag suspicious data (see `confirmed_anomalies.csv`); do not silently delete.
  Only `analysis_action` values starting with `exclude` remove a candle from
  analysis; `keep` (reviewed, genuine) and `review_pending` are notes only.
- Zero-volume candles are exchange filler (no trades, no real price).
  `get_clean_candles` skips them by default, so they become gaps. They stay in
  the database. Only Bitstamp has them (122, incl. 107 h outage 5-9 Jan 2015).
- DB migration and the Kraken CSV import are done. Never repeat them.
- Timeframes: 1h (primary), 4h, 1d, and 1w (added 22 Nov 2026: weeks start
  Monday 00:00 UTC, chart only + weekly features; a weekly value is used by a
  daily strategy only after the week has closed). 4h/1d are derived in memory from clean
  hourly candles (not stored in the DB), on UTC boundaries (4h at 00/04/../20,
  1d at 00:00), timestamp = period start. A period with any missing/excluded
  hour is skipped, never built from partial data. Verified 21 Nov 2026 against
  live APIs: all three exchanges' daily candles start 00:00 UTC and equal the
  sum of their 24 hourly candles exactly. Kraken's daily OHLC API only serves
  the last 720 days; Bitstamp and Coinbase serve full daily history.
- Indicators: computed per run of consecutive candles (`split_into_runs`), so
  they restart at every remaining gap; None until warmed up. On the continuous
  history they run straight through filled hours and the 2017 switch.
  Value stamped T uses candles up to and including period T (known at T's
  close). EMA seeded with SMA; RSI and ATR use Wilder smoothing; Bollinger uses
  population std; relative volume divides by the average of the PREVIOUS n.
- Paper trading: separate database file (never touches market_data.db). One
  decision per completed candle of the strategy timeframe (BUY/SELL/HOLD/WAIT/
  PENDING/SKIP) with a snapshot of indicators and rule states; decisions and
  fills are append-only, never edited. Orders fill at the first tradeable hour
  after the decision candle (same tradeability rules as backtests), with the
  backtest costs. Safety checks only ever BLOCK trades: stale data (> 3 h)
  stops processing; kill switch file blocks new buys. Switching strategy
  requires an explicit account reset (no silent switch).
- Paper accounts side by side (owner, 22 Nov 2026, "option 2"): the main
  account (`paper_trading.db`, candidate 1 "Daily trend + MACD", $10,000 from
  1 Jan 2026) stays untouched; extra accounts in `src/paper_trading/accounts.py`
  each follow one strategy with $3,500 (about the owner's real 3.5k) from
  2026-11-22: `paper_lab.db` = "Lab: weekly MACD + momentum, 50% core",
  `paper_core50.db` = "50% core + Daily trend + MACD". The daily routine and the
  app button run all of them; the Overview shows them side by side; `main.py`
  lists them. Compare after >= 3 months before choosing one.
- The app is local only: binds 127.0.0.1, never 0.0.0.0. It only reads the
  market DB except through the daily routine (forward candle update). The chart
  library is the one external web dependency (pinned version, needs internet);
  Python code stays standard-library only.
- EVERY strategy we find or build goes into `src/strategies/registry.py`
  (owner requirement, 21 Nov 2026). That gives it the standard test
  automatically: full-history backtest in the Strategy tester (vs buy-and-hold,
  per year, every trade, both fee levels) and its trades on the chart. Always
  show the full-history view next to the stricter walk-forward result, and
  label the full-history view as optimistic when the years it covers were
  used to choose the strategy. New building blocks go into
  `src/backtesting/conditions.py` first, with tests.
- Deterministic rules, statistics and trained models form the core; no paid LLM
  call per trade decision. The risk engine must have veto power over any signal.
- Every future prediction must be timestamped and stored, never rewritten
  afterwards. Evaluate with Brier score, log loss and calibration, not accuracy alone.
- Signals use completed candles only. Backtests must fill no earlier than the
  next candle, with fees and slippage. Avoid look-ahead bias.
- Backtest costs (owner, 22 Nov 2026: "I have my BTC on Bybit EU, under 100k,
  ~3.5k invested"): default fee 0.25% per side = Bybit EU spot VIP 0 (asset
  balance and 30-day volume < EUR 100,000; same rate for maker and taker), from
  bybit.eu/en-EU/help-center/article/Trading-Fee-Structure, read 22 Nov 2026
  (0.22% from EUR 100k volume, 0.20% 250k, 0.15% 500k; VIP 1 0.12%). Bybit
  global (bybit.com) is 0.10% but does not apply to the owner. The exact rate
  is on the owner's Bybit "My Fee Rate" page. Kraken Pro stays selectable for
  comparison: 0.80% taker / 0.40% maker at the lowest tier (kraken.com/pro/fees,
  21 Nov 2026). Price history stays Kraken BTC/USD (Bybit trades BTC/USDT or
  BTC/EUR; typical difference ~0.1%). Slippage 0.05% per side is an assumption. Long-only, all-in/all-out, no leverage by
  default.
- Margin is a SIMULATION toggle only (owner request 21 Nov 2026; the owner does
  not trade on margin): `MarginSettings` in `engine.py`, Strategy tester
  "Margin" select (1x default = identical results to no margin). The paper
  trader and any future live trading never use margin unless the owner asks.
  Kraken spot margin, long BTC/USD, from support.kraken.com read 21 Nov 2026:
  opening fee 0.025% and rollover 0.025% per 4 h, both on the borrowed USD;
  normal trading fee on opening and closing the whole position; max leverage
  BTC/USD 2-20x (international/ECP clients); margin level = equity / used
  margin; liquidation at 40% with a 2% liquidation fee (ASSUMED charged on the
  position value; Kraken does not say). Liquidation is checked on each
  candle's low; a gap below the liquidation price closes at the open.
  Buy-and-hold stays unleveraged in the comparison.
- Judging a strategy for someone starting NOW (owner, 22 Nov 2026): the goal
  is to end with more BTC than holding (sell before/into crashes, buy back
  lower). Measure it as "BTC compared with holding" = strategy end value /
  buy-and-hold end value over the same period. Never judge on one chosen start
  year: always look at the whole "If you had started in..." table (every start
  year to now) and prefer strategies that are ahead from most start years.
- Strategy selection guards against overfitting: windows 2013-2016 (bitstamp
  era) and 2017-2021 (kraken era) are used to choose; a combination is ranked
  by its WEAKEST selection window (calmar = yearly return / max drop) and needs
  a minimum number of trades. 2022-now is never used to choose, only to test.
  Never tune on, or pick by, the unseen window.

## Research input (owner, 22 Nov 2026)
Two reports in `docs/research/` (read them before strategy work):
- `2026-11-22_long_only_strategy_deep_dive_v2.md` (PRIMARY): evidence-graded
  (A-E) review. Main finding = our result: daily trend rules halve drawdowns
  but do not beat buy-and-hold on return, because BTC's gains are concentrated
  in a few rebound days when a trend filter is out. Fix: never be fully out
  (core + trend overlay, graded exposure 0-100%, banded BTC/cash rebalance,
  volatility cap). Ranked shortlist S1-S9 (section 8), methodology (trials
  ledger, walk-forward, CPCV, Deflated Sharpe, PBO, exposure-matched
  benchmark, break-even cost, top-20-days capture), free data endpoints with
  point-in-time rules. Explicit skips: halving timing, weekday effects,
  Stock-to-Flow, Pi Cycle, Fear & Greed, ETF flows, funding/OI timing,
  standalone daily RSI/Bollinger mean reversion.
- `2026-11-22_market_research_blueprint.md` (VISION, long term): multi-layer
  engine (regime, derivatives, order flow, on-chain, macro, news, options).
  Most derivatives/order-flow data has no free multi-year history, and its
  market snapshot figures are unverified; use for later phases only.
- `2026-11-22_strategy_feasibility.md` (our own check, 22 Nov 2026): which
  strategies and data are (A) possible now from our candles, (B) possible
  with free history downloads (MVRV, hash rate, FRED, funding from 2019,
  DVOL from 2021), (C) only collectable from now on (order books, open
  interest, liquidations, options). All best-evidence strategies (S1-S6,
  S8, S9) are A or B; order-flow/derivatives ideas are lowest priority at
  a 0.80% fee. Kraken public trades include the buy/sell side (CVD
  possible; `kraken_trades_provider` currently drops it).
Where the reports conflict with this project, the project wins:
- Fees: reports assume 0.10-0.26%; the owner's real fee is Bybit EU 0.25%
  (Kraken 0.80% taker / 0.40% maker for comparison). Favour low-turnover designs; always report break-even cost.
- Report 2 suggests a median composite of venues and forward-filled prices:
  NOT adopted (never merge exchanges, never fabricate candles); the continuous
  history + untradeable hours already handle outages.
- Holdout: 2022-now has been looked at many times, so it is no longer a clean
  holdout. The clean test from now on is forward paper trading; keep a log of
  every backtest trial.

## Status
Strategy lab, turning points, ML and weekly chart BUILT 22 Nov 2026 (owner:
"unleash every calculation power"), 264 tests pass. First run on the cloud
TEST DB at 0.25% fee (owner to rerun all three scripts on the real DB):
- Lab: 200,145 combinations in 5 min. Only 9 of 106,749 eligible beat holding
  in BOTH 2013-16 and 2017-21, and those did WORSE on 2022-now (33% ahead) than
  the rest (52%): picking the single best is luck. Walk-forward 2017-now: single
  best x0.64, top-10 average x0.53, best family (median) x1.54 (ahead 4/10
  years). PBO 0.07 (rankings carry over), Deflated Sharpe vs holding 0.00.
- Common ground (median over all combinations, chosen on 2013-21): 50% core
  >> 33% >> 0%; triggers that buy STRENGTH (28-day momentum in its top 20%,
  breakout above the 50-day high) beat dip buying; filters weekly MACD > signal,
  EMA50 > EMA200, close > SMA200, "miners ok"; exits close < SMA200, blow-off
  (28-day gain rank > 0.95), EMA20/50 cross down.
- Registered "Lab: weekly MACD + momentum, 50% core" (best median block per
  role on 2013-21): full history x1.39 vs holding, drop 75%, Sharpe 1.19,
  break-even fee 3.5%, ~1 trade/year, ahead from 10/13 start years; 2022-now
  (not used to choose) x1.41.
- Turning points (20% zigzag, 42 lows/43 highs): strategies buy ~45-50 days
  and 13-33% after lows, sell ~25-40 days and 14-18% below highs. Before lows:
  RSI, distance below SMA20/50, 50-day range position in their lowest 10% ->
  a low within 20 days is 2.5-2.7x more likely. Before highs: price far above
  SMA20/50/100/200-week -> 2.9-3.3x more likely.
- ML (walk-forward 2017-now, leak-free labels): "up in 30 days" has NO skill
  (Brier skill -0.21/-0.28, trading on it loses). "Swing low within 20 days"
  has real but modest skill (analog +0.12, logistic +0.06, well calibrated);
  using it to buy earlier inside 50% core + trend + MACD did not help (best of
  6 variants x1.40 vs x1.36 reference; the rest worse).
`run_strategy_research` on the REAL DB 22 Nov 2026, 0.25% fee (buy and hold
+49,161%, drop 85%, Sharpe 1.02): Lab weekly MACD + momentum 50% core is the
best registered strategy: +71,615%, x1.46 vs holding, drop 73%, Sharpe 1.20,
break-even fee 3.41%, x3.05 vs the exposure-matched mix, ahead from 10/13 start
years; by era 2013-16 x0.97, 2017-21 x1.00, 2022-now x1.44 (not used to
choose); by fee x1.48/x1.46/x1.43/x1.36 (0.10/0.25/0.40/0.80%); ~1 round trip a
year. Second: 50% core + Daily trend + MACD x1.29 (2022-now x1.23). Daily
trend + MACD x0.81 (2022-now x1.78, drop 57%). PBO across the 13 registered
strategies 0.93: their ranking on one half of the history does NOT carry over
to the other half (strategies win in different regimes), so a single winner
among them is not proven; Deflated Sharpe 0.00 for all with 227,818 trials
counted. Forward paper trading decides.
CONFIRMED on the owner's REAL DB 22 Nov 2026 (0.25% fee; run with the system
Python, not the venv, so pytest was missing there; scripts themselves ran):
- Lab: 227,781 combinations in 549 s. 18 beat holding in BOTH eras; on 2022-now
  61% of those were ahead vs 51% of the rest (choosing helps a little on real
  data, unlike the test DB). Walk-forward 2017-now: single best x0.62 (3/10
  years), top-10 x0.58 (4/10), best family (median) x1.33 (6/10). PBO 0.09,
  Deflated Sharpe vs holding 0.00. Common ground identical to the test DB:
  core 50%; trigger 28-day momentum top 20% (91% of its combinations ahead on
  2022-now, median x1.42), breakout 50d high (76%); exits close < SMA200,
  blow-off, EMA20/50 cross; filters EMA50>EMA200 (+ miners ok). The real
  Coinbase premium (test DB had none) shows up in top picks as a filter for
  buying 7-day drops.
- Turning points: 43 lows/43 highs; same lags (strategies buy ~45-50 days and
  9-31% after lows); same lifts (before lows: RSI/dist SMA20 lowest 10% ->
  2.6-2.7x; Coinbase premium highest 10% -> 2.4x; before highs: price far above
  the 200-week average -> 3.3x).
- ML: up30 no skill (-0.25/-0.21); low20 analog +0.122, logistic +0.057, well
  calibrated; early-low overlay did not beat the reference (50% core + trend +
  MACD from 2017: x1.51; best variant x1.46).
Default fee switched to Bybit EU 0.25% on 22 Nov 2026 (results below at
0.80% are kept as recorded; test DB at 0.25%: 50% core + trend + MACD x1.17,
S2 momentum x0.50 ahead from 12/13 start years, Daily trend + MACD x0.63).
Roadmap 9a-9d BUILT 22 Nov 2026 (owner: "do everything"), 250 tests pass.
First run on the cloud TEST DB (real external data from Coin Metrics, not the
owner's DB; owner to run `run_strategy_research` on the PC), fee 0.80%, full
history 2013-now, buy and hold +47,586% (worst drop 85%, Sharpe 1.02):
| strategy                    | total     | vs hold | drop | Sharpe | BE fee | starts ahead |
| Daily trend + MACD          | +21,024%  | x0.44   | 68%  | 1.08   | never  | 10/13 |
| 50% core + trend + MACD     | +47,917%  | x1.01   | 72%  | 1.12   | 0.83%  | 10/13 |
| S1 averages 20/50/100       | +4,332%   | x0.09   | 64%  | 0.88   | never  | 2/13  |
| S2 momentum 1-6 months      | +9,272%   | x0.20   | 70%  | 1.00   | never  | 3/13  |
| S3 50% core + averages      | +9,565%   | x0.20   | 72%  | 0.94   | never  | 4/13  |
| S4 averages + vol cap       | +2,965%   | x0.06   | 61%  | 0.90   | never  | 2/13  |
| S5 60% rebalanced           | +11,136%  | x0.24   | 64%  | 1.05   | never  | 3/13  |
| S6 averages + breakout      | +4,272%   | x0.09   | 61%  | 0.89   | never  | 2/13  |
| S8 averages + MVRV cap      | +1,435%   | x0.03   | 57%  | 0.74   | never  | 2/13  |
| S9 averages + hash filter   | +4,627%   | x0.10   | 62%  | 0.90   | never  | 1/13  |
- The report's S1-S9 fail at our fee: S1-type daily votes trade 13-21x the
  account per year (S5: 0.4x). Even at 0.10% fee S1 only reaches x0.61.
  The research assumed 0.10-0.26% fees; Kraken's 0.80% decides the result.
- Best: 50% core + our Daily trend + MACD overlay: level with holding over
  the full history with a smaller drop, ahead from 10/13 start years,
  Sharpe 1.12 vs 1.02, x1.70 vs the fixed 79% mix (the timing adds value),
  x1.21 at 0.10% fee. Its overlay was chosen on 2013-2021, so optimistic.
- Luck checks: Deflated Sharpe "Sharpe > 0" ~1.0 for all (easy in a bull
  market); "beats holding" (daily return above buy-and-hold) 0.00-0.01 for
  all: no strategy convincingly beats holding day by day. PBO across the 12
  = 0.39 (ranking carries over only weakly).
- CONFIRMED on the owner's REAL DB 22 Nov 2026 (`run_strategy_research`,
  0.80% fee; buy and hold +48,619%, drop 85%, Sharpe 1.02, PBO 0.31):
  | strategy                | total    | vs hold | drop | Sharpe | BE fee | vs mix | starts |
  | 50% core + trend + MACD | +54,256% | x1.12   | 69%  | 1.14   | 1.21%  | x1.93  | 9/13   |
  | Daily trend + MACD      | +27,999% | x0.58   | 58%  | 1.13   | never  | x4.12  | 9/13   |
  | Daily uptrend dip       | +22,612% | x0.47   | 78%  | 1.05   | never  | x1.98  | 11/13  |
  | Daily EMA 200 + 20/50   | +17,425% | x0.36   | 63%  | 1.16   | never  | x6.24  | 7/13   |
  | S1-S9 (report)          | +1,301% to +10,910% | x0.03-x0.23 | 57-72% | 0.72-1.04 | never | | 1-4/13 |
  50% core + trend + MACD by era: 2013-16 x0.91, 2017-21 x1.00, 2022-now x1.15;
  by fee x1.34 (0.10%) / x1.24 (0.40%) / x1.12 (0.80%). Only strategy ahead
  of holding over the full history. Caveat: its overlay was chosen on
  2013-2021 and 2022-now has been looked at often, so forward paper trading
  is the real test. Deflated Sharpe "beats holding" is 0.01 for all: it
  compares AVERAGE daily returns, which favours holding more BTC; a strategy
  can end higher (less volatility drag) with a lower daily average, so this
  check is harsh for part-invested strategies.
- Order-flow recorder tested live 22 Nov 2026: 130,559 Kraken trades in 24 h
  -> 24 hourly rows; order book 500 levels reach ~1.5% below / 3.5% above.
Done: data layer for 3 exchanges, update/import scripts, integrity, comparison and
anomaly tooling, SMA, hourly returns, SMA crossover signals.
21 Nov 2026: roadmap step 1 done (requirements.txt, collector tests rewritten for
the forward-only collector, tests for SMA/returns/crossover). Step 2 code done
(4h/1d derivation and daily check), tested on 20 days of live data from all three
exchanges (exact match). Full-history run by owner 21 Nov 2026: 0 days off by
more than 0.01% on any exchange (Kraken 717 days, Bitstamp 4,780, Coinbase 4,119;
Kraken check limited to its last 720 days). Primary history: 1h ~114,861 clean,
4h 28,698, 1d 4,768 candles; 23 days skipped in 13 years.
Step 3 done: indicators cross-checked against an independent pandas calculation
on 3,000 real Coinbase hourly candles (1h and 4h): identical to float precision.
Owner ran `report_indicators` 21 Nov 2026; latest 1d close (2026-11-20, 58,806.30)
equals Kraken's own daily close (live charts differ only by the forming candle).
Fully warmed-up rows: 1h kraken 83,592/86,593 (20 runs), 4h 18,773/21,634
(16 runs), 1d 1,350/3,593 (15 runs); bitstamp 1d 523/1,175 (5 runs).
`check_kraken_gaps` (owner, 21 Nov 2026): all 18 Kraken gaps since 2017
(82 h: Jan 2018 ~50 h, rest 1-5 h) have no Kraken trades at all = real
outages/maintenance; nothing to rebuild. Hence the continuous history.
`report_continuous_history` (owner, 21 Nov 2026): 114,981 hourly candles from
2013-10-06; 108 hours filled (83 Coinbase into Kraken period, 25 Kraken into
Bitstamp period); 87 hours no exchange has (almost all Bitstamp outage 5-9 Jan
2015); runs: 1h 21, 4h 6, 1d 5 (1d fully warmed up 4,134/4,786, was 1,350).
40 source switches, median jump 0.48%, 12 above 1%. Checked against Kraken
trades and Coinbase/Bitstamp candles:
- 2017-05-07 22:00: Kraken was 4-5% below Coinbase all evening (Bitstamp close
  to Kraken); the excluded hour had 2,509 real trades. Excluding it and filling
  from Coinbase creates a fake +5%/-10% spike. Owner decided 21 Nov 2026:
  un-excluded, now `keep` (`genuine_kraken_divergence`).
- 2019-07-15 01:00 (+6.2%), 2021-01-29 17:00 (+3.7%), Jan 2018, 2024-04-14: the
  first Kraken trade after maintenance prints at the stale pre-outage price,
  then the price falls to the other exchanges' level within the hour. Fills are
  fine; the jump is in Kraken's own reopening candle (stale open, inflated
  high/low range).

Step 4 (backtester) built 21 Nov 2026, 171 tests pass. First run on a TEST
database in the cloud session (real Bitstamp hourly + real Coinbase hourly
standing in for Kraken from 2017; NOT the owner's DB), fee 0.80%:
- 1h: 0/540 combinations beat buy-and-hold in 2022-now; ~100+ trades per
  window and ~1.7% cost per round trip destroy any edge. With zero costs the
  top 10 would beat it 8/10, so the hourly signals have some information but
  not enough to pay Kraken's fees.
- 4h: top 10 chosen on 2013-2021 all fail on 2022-now (overfitting).
- 1d: top 10 chosen on 2013-2021 beat buy-and-hold in 2022-now 7/10 (10/10 at
  0.40% fee), max drop ~37-45% vs 67%. Common ground: TREND FOLLOWING, not
  dip buying: buy when the trend is up (EMA50 > EMA200 or close > EMA200) and
  momentum turns up (MACD crosses up, or EMA20 crosses above EMA50); sell when
  EMA20 crosses below EMA50. Oversold triggers (RSI < 30/40, close below lower
  Bollinger band) did not hold up. Caveat: only 3-15 trades per window, so
  evidence is thin. Must be confirmed on the owner's real DB.

Step 5a CONFIRMED on the owner's real DB (CSVs sent 21 Nov 2026; buy-and-hold
benchmark taken from the test DB run, Bitstamp era identical data, later years
within ~0.2%: unseen B&H return ~+26%, calmar 0.07, max drop ~67%):
| unseen 2022-now: top 10 chosen on 2013-2021 beating B&H (calmar / return) |
| fee  | 1h            | 4h            | 1d              |
| 0.40 | 0/10, all 0/540 | 1/10, all 41/540 | 10/10, all 151/408 |
| 0.80 | 0/10, all 0/540 | 0/10, all 14/540 | 7/10, all 99/408   |
Best 1d candidates (both fees in the top 10, unseen at 0.80% fee):
- BUY ema50>ema200 & macd_cross_up | SELL ema20_cross_down_ema50, stop 2xATR:
  +95.5%, max drop 37%, 15 trades (0.40%: +120.6%)
- BUY close>ema200 & ema20_cross_up_ema50 | SELL ema20_cross_down_ema50,
  stop 2xATR: +128.2%, max drop 37%, 9 trades (0.40%: +145.3%)
- BUY ema50>ema200 & rsi<40 | SELL ema20_cross_down_ema50: +124.4%, max drop
  52%, 13 trades (the only dip-buy trigger in the top 10, inside an uptrend)
Building blocks on 1d (median calmar in all three windows): trend filter
ema50>ema200 and exit ema20_cross_down_ema50 are the most consistent; ATR
stops add little; exits close>bb_middle and rsi>50 (sell too early) are
consistently poor; oversold triggers without a trend filter do not hold up.
Caveats: few trades (3-15 per window); much of the unseen edge comes from
being out of the market in the 2022 bear market, which a per-year check
(5c) must confirm is not a single lucky exit.

Step 5c (part) full-history test, `run_walk_forward`, first run on the cloud
TEST database (same caveat as step 4; owner to confirm on the real DB),
fee 0.80%:
- The 3 daily candidates over 2013-now: +10,000% to +21,000% vs buy-and-hold
  +48,000%; worst drop 61-77% vs 85%; they beat buy-and-hold in only 6-7 of 14
  years. They win in falling years (2018, 2022, 2025-26: losses cut to roughly
  a third or less) and lag badly in strong rising years (2017, 2019, 2020,
  2023, 2024). The 2022-now "unseen" win came mostly from sitting out 2022.
- Walk-forward 2016-2026 (each year's pick chosen only on earlier years):
  1d +794% (worst drop 52%) vs buy-and-hold +13,550% (84%); 4h +643% (56%);
  1h -89% (96%). Picks beat buy-and-hold in 3-4 of 11 years. Even per unit of
  risk buy-and-hold wins (1d: ~22%/yr over 52% drop vs ~57%/yr over 84%).
- Conclusion so far: the trend rules are a DEFENSIVE filter (smaller crashes,
  calmer ride), not a way to beat holding BTC. They give up most of the bull
  markets. Recurring pick: trend filter ema50>ema200 + EMA20/50 or MACD cross.

Step 5c CONFIRMED on the owner's real DB (`run_walk_forward`, fee 0.80%,
21 Nov 2026, after un-excluding Kraken 2017-05-07 22:00):
| 2016-now walk-forward | total     | per year | worst drop | calmar |
| 1d picks              | +3,212%   | 37.9%    | 51.6%      | 0.73   |
| buy and hold          | +13,548%  | 57.1%    | 83.6%      | 0.68   |
| 4h picks              | +36%      | 2.8%     | 87.2%      | 0.03   |
| 1h picks              | -93.5%    |          | 97.0%      |        |
- 1d: about a quarter of buy-and-hold's total, but similar (slightly better)
  return per unit of risk and a far smaller worst drop. Picks beat
  buy-and-hold in only 3/11 years (they win falling years, lag rising ones).
  The pick was stable 2022-2026: candidate 1 (BUY ema50>ema200 &
  macd_cross_up | SELL ema20_cross_down_ema50, stop 2xATR) chosen 5 years in a
  row. Candidate 1 over 2013-now: +27,999% (53.7%/yr, worst drop 57.5%,
  calmar 0.93) vs buy-and-hold +47,988% (60.1%/yr, 84.9%, 0.71); optimistic,
  because 2013-2021 was used to choose it.
- 4h is unstable (test DB +643%, real DB +36%): no reliable edge. 1h loses
  almost everything after fees. Daily is the only usable timeframe so far.
- Un-excluding 2017-05-07 mattered: candidate 3 in 2017 went from +253% to
  +727% (the fake spike had triggered a bad trade).

Product (roadmap step 6) built 21 Nov 2026, 189 tests pass: paper trader,
dashboard, `daily_run`. Checked in the cloud on the test DB topped up to
2026-11-21 15:00: replay from 2026-01-01 gave 1 trade (buy 2026-09-22 at
86,638, sell 2026-10-15 at 81,525), -7.4%, same as the backtest's -7.4% for
candidate 1 in 2026; page renders without errors in light, dark and 390 px
phone width. Owner still to run `daily_run` on the PC.
App (roadmap step 7a) built 21 Nov 2026, 197 tests pass: `start_app.bat`,
Overview + interactive Chart, button for the daily routine. Browser-tested in
the cloud on the test DB (light, dark, 390 px phone, no JS errors; scrolling back
on 4h loaded older chunks to 2024; the button ran a real update + paper step).
Strategy tester built 21 Nov 2026, 203 tests pass: registry with the three
step 5a daily candidates; report numbers equal the walk-forward script's
(candidate 1 on the test DB: +21,024%, 33 trades, worst drop 67.8%, better
than buy-and-hold in 6/14 years; its 2026 trade equals the paper account's).
Polish pass 21 Nov 2026: all pages browser-checked in light, dark and 390 px
phone width with no JS errors and no sideways overflow.
Margin simulation built 21 Nov 2026, 209 tests pass. Candidate 1 on the test
DB, 2013-now, 0.80% fee: 1x +21,024% (worst drop 68%); 2x +572% (92%, 2
liquidations, borrowing costs 1,716% of starting money); 3x -90% (6
liquidations); 5x and 10x wiped out. Rollover 0.025% per 4 h is ~55% of the
borrowed amount per year, which eats the extra gains of a strategy that holds
for weeks to months; daily-candle lows of -30% liquidate 2x positions.
Start-year view built 22 Nov 2026, 218 tests pass (test DB, 0.80% fee):
candidate 1 is ahead of or level with holding from 10 of 13 start years
(2014-2026); behind for starts near a bottom (2019 x0.71, 2023 x0.56, 2024
x0.95), well ahead for starts near a top (2018 x1.39, 2022 x1.57, 2025 x1.18,
2026 x1.40). It behaves like crash insurance: it pays off when the start is
followed by a bear market.

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
2017-05-07 22:00 `keep` (was excluded, un-excluded by owner 21 Nov 2026 after
checking Kraken trades); five pre-2017 Kraken hours stay `review_pending` (not
used by the primary history). Excluded candles now: 4 (3 Kraken pre-2016,
1 Coinbase 2017-04-15). Lesson: before excluding a primary-exchange hour,
check that exchange's own neighbouring hours and trade count, not only other
exchanges.

Known issues:
1. [FIXED 21 Nov 2026] `main.py` is now a read-only status check.
2. Bitstamp provider assumptions not confirmed against official docs: max
   `limit=1000`, `end` and `exclude_current_candle` parameters. Coinbase provider
   was checked against docs (300-candle cap, columns time, low, high, open,
   close, volume, granularity 3600).
3. Bitstamp's pre-2017 history still has its own gaps after cleaning (e.g. the
   107 h outage 5-9 Jan 2015); these stay gaps.
4. `compare_exchange_data` and `inspect_exchange_price_outliers` read raw data
   (no exclusions, zero-volume included), so their maxima include known issues.
5. `calculate_hourly_sma` and the SMA crossover strategy are still hourly-only
   (`period_hours`); generalise when the backtester needs other timeframes.
6. Volume differs a lot between exchanges (Coinbase daily volume ~3x Kraken),
   so volume features (`volume_sma_20`, `relative_volume_20`) are distorted on
   and just after filled hours and around the 2017 switch. Price indicators are
   barely affected (typical price difference 0.15-0.22%).
7. Reopening candles after a Kraken outage have a stale open and an inflated
   high-low range, so ATR and candle-range features spike for that hour.

## Roadmap (do in order)
0. [DONE 21 Nov 2026] Data updated and verified (see Status). Bitstamp filler
   candles handled; outliers classified; primary history defined.
1. [DONE 21 Nov 2026] Housekeeping: requirements.txt, fix collector tests, tests
   for SMA, returns and crossover.
2. [DONE 21 Nov 2026] Derive 4h and 1d candles from clean hourly data, per primary-history segment (UTC boundaries, no partial
   candles, gap-aware). Compare daily with exchange daily candles.
3. [DONE 21 Nov 2026] Indicators: EMA 20/50/200, RSI, MACD, Bollinger, ATR, volume features.
   Timeframe-generic, tested, reset across gaps, no look-ahead.
4. [DONE 21 Nov 2026] Backtester + strategy search: long-only spot, next-open
   fills, Kraken fees and slippage, no fills on filled/reopening hours, every
   combination of trend filter x trigger x volume filter x exit x ATR stop on
   1h/4h/1d, chosen on 2013-2021, tested on 2022-now, vs buy-and-hold.
   NEXT: owner runs `run_backtests` on the real DB.
5. Find the common ground (owner's main goal): which indicator conditions
   reliably mark good BUY and SELL moments on real data.
   a. [DONE 21 Nov 2026] Confirm step 4 findings on the real DB, at 0.80% and
      0.40% fees: daily trend following holds up; 1h/4h do not (see Status).
   b. Widen the building blocks so every indicator is tested in every role
      (e.g. RSI and Bollinger as exits AND as filters, ATR volatility filter,
      MACD histogram turns, EMA distance, volume on exits), plus parameter
      variants (RSI levels, EMA pairs).
   c. Stronger checks against luck: [DONE 21 Nov 2026, test DB] yearly
      walk-forward and per-year results (`run_walk_forward`); owner to run it on
      the real DB. Still to do: compare against random entries with the same
      exposure.
   d. Limit-order (maker fee) execution model, since fees decide the 1h/4h result.
   e. Write the surviving rules down as a named strategy with tests.
6. [DONE 21 Nov 2026] Usable product v1: paper trader following the best
   daily rule, dashboard page, one-command daily routine (see commands).
7. Product polish:
   a. [DONE 21 Nov 2026] Click-to-start app (`start_app.bat`), interactive chart
      over the full history (1h/4h/1d, all indicators, trades), button for the
      daily routine.
   b. [DONE 21 Nov 2026] Strategy tester page + strategy registry: every strategy
      gets the full-history test and its trades on the chart.
   c. [DONE 21 Nov 2026] Margin simulation toggle in the Strategy tester.
   d. NEXT: LIVE MODE (owner wants the strategy on a live price chart): stream
      Kraken's current price into the chart (forming candle updates every few
      seconds), show the strategy's rule checklist live, and alert when a rule
      is about to trigger at the close. Decisions stay on completed candles.
   e. [DONE 21 Nov 2026] Cleanup and polish (owner request): app startup 6.6 s
      -> 3.5 s on the test DB (gap filling fetches only missing hours; one
      shared indicator computation per timeframe), duplicated signal code
      merged (`conditions.strategy_signals`), `main.py` status check fixed,
      one-time scripts archived, README rewritten, modern card layout on all
      pages (shared shell, favicon, pill nav, focus outlines, phone checks).
   e2. [DONE 21 Nov 2026] One chart + latest-trade overview (owner request): the
      Chart shows the selected strategy's backtest trades plus its current
      state (open trade lines, signal marker, rule strip); the Overview shows
      how the latest trade is doing; one shared strategy choice. Fixed: the
      Strategy tester forgot its choices between tabs; chart trade markers
      were stacked again each time older candles loaded.
   f. Schedule the daily routine automatically (Windows Task Scheduler), trade
      statistics on the overview, desktop shortcut with an icon.
8. Risk engine (proposed paper values, not approved: 0.5% risk per trade, 2% max
   daily loss, 5 positions, 2.5% aggregate open risk, no leverage, stop required,
   emergency shutdown) with veto power over the paper trader.
9. Strategy research, based on `docs/research/` (owner go-ahead 22 Nov 2026;
   replaces the parked 5b-5e list). a-d BUILT 22 Nov 2026 (see Status);
   owner to run `run_strategy_research` on the real DB:
   a. Engine: target exposure 0-100% (graded, rebalance only when the change is
      >= a band, fees on the traded amount), exposure-matched buy-and-hold
      benchmark, metrics: Sharpe, Sortino, average exposure, turnover,
      break-even cost per trade, share of the top-20 days captured.
   b. Trials ledger (every backtest run logged with parameters and results)
      and validation: walk-forward, Deflated Sharpe Ratio, PBO.
   c. Price-only candidates (report 2, section 8): S1 price/SMA ensemble
      (20/50/100), S2 time-series momentum ensemble (28/56/91/182 days), S3 core
      + overlay (50% core), S4 volatility cap, S5 banded BTC/cash rebalance
      (60%, 10 pp band), S6 Donchian as an ensemble member. Each goes into the
      registry so it gets the Strategy tester, chart and overview.
   d. External data with immutable snapshots and 1-2 day lags: Coin Metrics
      MVRV (S8 cap) and hash rate (S9 entry filter).
   e. Survivor -> paper trading for >= 3 months. [STARTED 22 Nov 2026] Owner
      chose to run candidates side by side instead of a reset: lab strategy
      and 50% core + trend + MACD, $3,500 each from 2026-11-22, next to the
      main account. Review around late Feb 2027.
      NEXT, owner decision: switch the paper account to "50% core + Daily
      trend + MACD" (needs `ACTIVE_STRATEGY_ID` change + account reset) or keep
      candidate 1. Ideas that respect the 0.80% fee: weekly decisions or a
      wider band for S1/S2 (counts as new trials: log them).
   f. Order flow (CVD, VWAP, order book) is being recorded from 22 Nov 2026
      (`start_recorder.bat`); test it once there are months of it. Show CVD on
      the chart when useful.
10. [BUILT 22 Nov 2026, test DB] Research engine: weekly chart, feature
   library, turning-point study, strategy lab, ML models (see Status). NEXT:
   owner runs `run_strategy_lab`, `run_turning_points`, `run_ml_research` on
   the real DB; then decide the paper-trading strategy (candidates: Lab weekly
   MACD + momentum 50% core, 50% core + Daily trend + MACD). Ideas: lab with
   graded (2-3 step) overlays; ML features from order flow once recorded.
   Later (vision report): regime detection, volatility forecasting, prediction
   log with calibration, derivatives/on-chain layers if data allows.

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
