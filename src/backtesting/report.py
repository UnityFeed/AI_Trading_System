"""
Full-history backtest report for one strategy: the standard test every
strategy in the registry gets (Strategy tester page).

It runs the strategy once over the whole continuous history with the same
engine, costs and fill rules as all other backtests, next to buy-and-hold,
and returns plain data (ready for JSON): summary numbers, results per
calendar year, every trade, and the account value per day.

Honesty note shown with every report: the full history includes the years
used to choose the strategy, so this view is optimistic. The walk-forward
(scripts/run_walk_forward.py) is the stricter test.
"""

from datetime import datetime, timedelta

from src.backtesting.conditions import evaluate_all
from src.backtesting.engine import BacktestResult, CostSettings, buy_and_hold, run_backtest
from src.backtesting.market import Market
from src.backtesting.walk_forward import summarize
from src.strategies.registry import StrategyDefinition


def signals(market: Market, definition: StrategyDefinition, blocks=None):
    blocks = blocks or evaluate_all(market)
    spec = definition.spec
    entry = [
        a and b and c for a, b, c in zip(
            blocks["trend"][spec.trend], blocks["trigger"][spec.trigger], blocks["volume"][spec.volume]
        )
    ]
    return entry, blocks["exit"][spec.exit]


def daily_points(result: BacktestResult) -> list[list]:
    """Account value at the last candle of every UTC day: [unix seconds of the day, value]."""
    points = {}
    for timestamp, value in result.equity_curve:
        day = timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
        points[day] = value
    return [[int(day.timestamp()), round(value, 6)] for day, value in sorted(points.items())]


def summary(result: BacktestResult) -> dict:
    trades = result.trades
    held_days = [
        (t.exit_time - t.entry_time) / timedelta(days=1) for t in trades
    ]
    returns = [t.return_pct for t in trades]
    return {
        "start": result.start.isoformat(),
        "end": result.end.isoformat(),
        "total_return_pct": round(result.total_return_pct, 2),
        "yearly_pct": round(result.cagr_pct, 2),
        "max_drawdown_pct": round(result.max_drawdown_pct, 2),
        "calmar": round(result.calmar, 3),
        "trades": len(trades),
        "win_rate_pct": round(result.win_rate_pct, 1),
        "average_trade_pct": round(result.average_trade_pct, 2),
        "best_trade_pct": round(max(returns), 2) if returns else None,
        "worst_trade_pct": round(min(returns), 2) if returns else None,
        "average_days_held": round(sum(held_days) / len(held_days), 1) if held_days else None,
        "exposure_pct": round(result.exposure_pct, 1),
    }


def strategy_report(market: Market, definition: StrategyDefinition, costs: CostSettings) -> dict:
    full = range(len(market.candles))
    entry, exit_signal = signals(market, definition)
    result = run_backtest(market, full, entry, exit_signal, definition.spec.stop_atr, costs, record_equity=True)
    held = buy_and_hold(market, full, costs, record_equity=True)

    per_year_strategy = summarize(result).years
    per_year_held = summarize(held).years
    years = []
    for year in sorted(per_year_held):
        s, h = per_year_strategy.get(year), per_year_held[year]
        years.append({
            "year": year,
            "strategy_pct": None if s is None else round(s.return_pct, 2),
            "strategy_drop_pct": None if s is None else round(s.max_drawdown_pct, 2),
            "trades": 0 if s is None else s.trades,
            "buy_hold_pct": round(h.return_pct, 2),
            "buy_hold_drop_pct": round(h.max_drawdown_pct, 2),
        })

    return {
        "strategy": {
            "id": definition.id, "name": definition.name, "timeframe": definition.timeframe,
            "rules": definition.spec.name, "description": definition.description,
            "origin": definition.origin,
        },
        "costs": {"fee_pct": costs.fee_pct, "slippage_pct": costs.slippage_pct},
        "summary": summary(result),
        "buy_and_hold": summary(held),
        "years": years,
        "trades": [
            {
                "entry_time": t.entry_time.isoformat(), "entry_price": round(t.entry_price, 2),
                "exit_time": t.exit_time.isoformat(), "exit_price": round(t.exit_price, 2),
                "return_pct": round(t.return_pct, 2), "exit_reason": t.exit_reason,
                "days_held": round((t.exit_time - t.entry_time) / timedelta(days=1), 1),
                # Still holding at the end of the data: valued at the last close, not sold.
                "open": t.exit_reason == "end",
            }
            for t in result.trades
        ],
        "equity": daily_points(result),
        "buy_and_hold_equity": daily_points(held),
        "note": (
            "This test covers every year, including the years used to choose the strategy, "
            "so it is optimistic. The walk-forward test is stricter."
        ),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def trade_markers_from_report(report: dict, timeframe: str) -> list[dict]:
    """Entry and exit of every backtest trade as chart markers for `timeframe`."""
    from src.analysis.timeframes import period_start

    markers = []
    for trade in report["trades"]:
        sides = [("buy", "entry_time", "entry_price")]
        if not trade["open"]:
            sides.append(("sell", "exit_time", "exit_price"))
        for side, key, price in sides:
            when = datetime.fromisoformat(trade[key])
            markers.append({
                "time": int(period_start(when, timeframe).timestamp()),
                "side": side,
                "price": trade[price],
            })
    return markers
