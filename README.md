# AI Trading System

A personal BTC/USD research and paper-trading app. It keeps 13 years of hourly
price data from three exchanges, calculates the usual indicators, tests trading
strategies honestly (with your real Bybit EU fees, no look-ahead, against simply
holding BTC), and runs the chosen strategy with virtual money.

**Live trading is not enabled.** Everything runs on your own PC.

## Start

Double-click **`start_app.bat`** in this folder. A browser tab opens:

| Page | What you see |
|---|---|
| **Overview** | Your paper account vs buy-and-hold, what the strategy says today, the market in plain words (1d / 4h / 1h), how fresh your data is |
| **Chart** | Candlesticks for the whole history (1h / 4h / 1d) with EMA, Bollinger, volume, RSI, MACD and ATR; trades of the paper account or of any strategy's backtest |
| **Strategy tester** | All strategies compared side by side; any strategy over 2013 to now (or from any start year): result per year, every trade, Sharpe, break-even fee, fee levels, optional margin simulation |

Three paper accounts run side by side (the Overview compares them): your main account
(Daily trend + MACD) and two $3,500 accounts for the best two strategies so far.

The button **Update data & run paper trader** downloads the newest candles
(and the free Coin Metrics MVRV and hash-rate data) and lets the paper
trader act on them. Keep the black window open while you
use the app; close it to stop.

Quick status check without the app: `python main.py`.

## Setup (once)

```powershell
cd C:\Users\PC\AI_Trading_System
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

The application uses only the Python standard library (`pytest` is for the
tests). The chart pages load the open-source TradingView Lightweight Charts
library from the internet.

## Where things are

```
start_app.bat           double-click to start the app
start_recorder.bat      double-click to record Kraken's order book and buy/sell flow
main.py                 quick status check
src/
  data_collection/      exchange downloads (Kraken, Bitstamp, Coinbase) and the SQLite store
  analysis/             data quality, continuous history, timeframes, indicators
  backtesting/          strategy building blocks, backtest engine, search, walk-forward, reports
  strategies/registry.py  every strategy the system knows (add new ones here)
  paper_trading/        virtual account and the trader
  app/, reporting/      the app pages and server
scripts/                command-line tools (research, data checks); archive/ = one-time jobs
tests/                  automated tests: python -m pytest -q
database/               your data (not in git: back it up yourself)
```

`CLAUDE.md` is the full project guide: every decision, the research results so
far, the roadmap and all commands.
