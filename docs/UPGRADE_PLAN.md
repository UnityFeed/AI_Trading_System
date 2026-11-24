# System upgrade plan (owner, 24 Nov 2026)

Owner: "keeping to [standard-library] Python was only meant during
development. We are hitting operational limits, so we should look into
upgrading the system on all aspects: faster, more reliable, safer, and find
other tools, programs and functions to add."

The ground rules stay as they are: paper trading first, no live trading
without an explicit request, no margin, every prediction stored and scored,
no look-ahead, never merge exchanges or fabricate candles, the app binds to
127.0.0.1 only, and every claimed improvement is measured honestly
(walk-forward, years not used to choose).

Checked 24 Nov 2026: numpy 2.5, pandas 3.1, scipy 1.18, scikit-learn 1.9 and
LightGBM 4.7 all have ready-made Windows wheels for Python 3.14 and 3.15, so
they install with one `pip install` on the owner's PC.

## Where the limits are now
| Area | Limit today | Effect |
|---|---|---|
| AI | one linear learner, written by hand | cannot learn combinations of conditions ("setups"); 1h training takes ~7 min |
| Speed | indicators, features and replays in pure Python loops | lab ~9 min, training ~12 min, app start ~3-4 s and growing |
| Data | BTC only; candles + Coin Metrics + own order-flow recorder | few examples of rare setups; no funding / open interest / macro |
| Reliability | manual daily routine, no automatic backups, logs only in the console | a missed day or a broken database file is noticed late |
| Safety | no automatic test run, dependencies not pinned | a change or library update can break things silently |
| Live view | chart refreshes on reload only | owner cannot follow the forming candle (roadmap 7d) |

## Phases (each one: build, measure, owner approves before the next)

### A. Foundation + smarter AI (STARTED 24 Nov 2026)
1. [BUILT] Libraries allowed: `requirements.txt` lists numpy, scikit-learn,
   LightGBM (+ pytest). The app still starts without them (the AI then uses
   its older experts only).
2. [BUILT] Pattern experts in the learning engine (`ml_experts.py`):
   gradient-boosted trees (learn combinations of conditions) and "similar
   past situations" (nearest neighbours), retrained every 30 days on outcomes
   known by then; the blend decides how much to trust them.
3. Automatic tests on GitHub (GitHub Actions: `pytest` on every push), so a
   broken change shows a red cross before the owner pulls it.
4. Pinned versions (a lock file via `uv` or `pip-tools`) so every install
   is identical; `uv` also installs ~10x faster than pip.
5. Automatic database backups (SQLite online backup, daily, keep 14 days)
   and log files with rotation in `logs/`.

### B. More and better data
1. More coins as extra TRAINING examples for the AI (ETH and 3-5 other large
   coins, free history from Kraken/Coinbase): setups that work across coins
   are more trustworthy than BTC-only ones. Forecasts stay BTC.
2. Bybit's own BTC/USDT prices (the owner's exchange) as a 4th source, via
   `ccxt` (one library for 100+ exchanges, free).
3. Derivatives context with free history: funding rates (Bybit/Binance from
   2019-2020), open interest, Deribit volatility index (DVOL, from 2021).
4. Macro (FRED, free): dollar index, US rates, liquidity; daily, lagged.
5. Order flow: the recorder runs since 22 Nov 2026; use it once there are
   3+ months.

### C. Speed
1. Indicators, features and outcomes with numpy/pandas (vectorised):
   expected 10-50x faster; same results checked against the current code
   (the current pure-Python versions become the test reference).
2. DuckDB or Parquet files for research reads (SQLite stays the master
   store), if loading becomes the bottleneck.
3. Training session: target under 3 minutes for all timeframes.

### D. Reliability + live use
1. Windows Task Scheduler runs the daily routine and the training session
   (roadmap 7f), with a desktop shortcut.
2. Live mode (roadmap 7d): Kraken/Bybit WebSocket price stream into the
   chart, the strategy's rule checklist live, alerts before a rule triggers.
3. Notifications (Telegram or e-mail, free): paper trades, stale data, failed
   routine, a new AI forecast that changed a lot.

### E. Safety before anything real
1. Risk engine (roadmap 8) with veto power over every signal.
2. API keys (only if live trading is ever requested) in the Windows
   credential store (`keyring`), never in files; read-only keys first.

## Decisions for the owner
- Order of B/C/D after A (recommended: A -> C1 -> B1 -> D1/D2 -> B2-B4).
- Notifications: Telegram or e-mail?
- Python version: keep 3.15 in the venv (works for the libraries above), or
  a long-supported 3.13 for maximum library support.
