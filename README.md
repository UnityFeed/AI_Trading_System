# AI Trading System

A personal BTC research and paper-trading app with a learning AI. It keeps 13
years of hourly BTC prices (one consistent source: Bitstamp, with its few
missing hours filled from Kraken, Coinbase or Bybit), calculates the usual
indicators, tests trading strategies honestly (with your real Bybit EU fees,
no look-ahead, against simply holding BTC), runs strategies with virtual
money, and draws the AI's scenario forecasts on the chart.

**Live trading is not enabled.** Everything runs on your own PC.

## Start

Double-click **`start_app.bat`** in this folder (the first time it also
installs the required libraries). A browser tab opens:

| Page | What you see |
|---|---|
| **Overview** | The selected strategy's trade and signal, your three paper accounts side by side, how fresh your data is |
| **Chart** | Candlesticks for the whole history (1h / 4h / 1d / 1w) with indicators, strategy trades, market structure, support/resistance, Fibonacci, chart patterns, volume profile and the AI forecast (with a replay through history) |
| **Strategy tester** | All strategies compared; any strategy from 2013 (or any start year) to now: result per year, every trade, Sharpe, break-even fee, fee levels, optional margin simulation |

The button **Update data & run paper trader** downloads the newest candles and
the free external data, then lets the paper accounts act. Keep the black window
open while you use the app; close it to stop.

Train the AI (all timeframes, about 15-25 minutes):
`python -m scripts.train_engine`. Quick status check: `python main.py`.

## Setup (once)

```powershell
cd C:\Users\PC\AI_Trading_System
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

Libraries: numpy, scikit-learn, LightGBM, tzdata (and pytest for the tests).
The chart pages load the open-source TradingView Lightweight Charts library
from the internet.

## Where things are

```
start_app.bat           double-click to start the app
start_recorder.bat      double-click to record Kraken's order book and buy/sell flow
main.py                 quick status check
src/
  data_collection/      downloads (Bitstamp, Kraken, Coinbase, Bybit, Coin Metrics,
                        other markets, training coins), SQLite stores, backups
  analysis/             data quality, the one price history, timeframes, indicators
  backtesting/          strategy building blocks, backtest engine, search, walk-forward, reports
  strategies/registry.py  every strategy the system knows (add new ones here)
  paper_trading/        virtual accounts and the trader
  research/             feature library, strategy lab, turning points, ML research
  predictive_engine/    market structure, chart tools, the learning AI and its training
  app/, reporting/      the app pages and server
scripts/                command-line tools (data, research, training); archive/ = one-time jobs
tests/                  automated tests: python -m pytest -q
docs/                   plans, research reports, project history
database/               your data (not in git: backed up daily to database\backups\)
```

`CLAUDE.md` is the project guide (decisions, commands, current status);
`docs/HISTORY.md` holds every result recorded so far.
