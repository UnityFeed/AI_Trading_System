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

from datetime import datetime, timedelta, timezone

from src.analysis.timeframes import TIMEFRAME_HOURS
from src.backtesting.conditions import evaluate_all, strategy_signals
from src.backtesting.engine import (
    NO_MARGIN, BacktestResult, CostSettings, MarginSettings, buy_and_hold, run_backtest,
)
from src.backtesting.market import Market
from src.backtesting.walk_forward import summarize
from src.strategies.registry import StrategyDefinition


def signals(market: Market, definition: StrategyDefinition, blocks=None):
    return strategy_signals(blocks or evaluate_all(market), definition.spec)


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
        "liquidations": result.liquidations,
        # borrowing costs as % of the starting capital
        "margin_costs_pct": round(result.margin_costs * 100, 2),
    }


def btc_vs_hold(result: BacktestResult, held: BacktestResult) -> float:
    """
    BTC you end with for every 1 BTC you would have by simply holding over
    the same period (both valued at the same final price, so this is the
    ratio of the two end values).
    """
    return result.final_equity / held.final_equity if held.final_equity > 0 else 0.0


def start_years(first: datetime, last: datetime) -> list[int]:
    """Years whose 1 January lies inside the data: possible test start dates."""
    return [
        year for year in range(first.year, last.year + 1)
        if first <= datetime(year, 1, 1, tzinfo=timezone.utc) <= last
    ]


def start_year_table(
    market: Market,
    definition: StrategyDefinition,
    costs: CostSettings,
    margin: MarginSettings = NO_MARGIN,
) -> list[dict]:
    """
    "If you had started on 1 January of year Y": the strategy and
    buy-and-hold from that day to now, for every year in the data. Each
    run starts with cash; indicators are already warmed up from the
    earlier history (they only use the past).
    """
    entry, exit_signal = signals(market, definition)
    rows = []
    for year in start_years(market.candles[0].timestamp, market.candles[-1].timestamp):
        window = market.index_range(datetime(year, 1, 1, tzinfo=timezone.utc), END_OF_DATA)
        if len(window) < 2:
            continue
        result = run_backtest(market, window, entry, exit_signal, definition.spec.stop_atr,
                              costs, margin=margin)
        held = buy_and_hold(market, window, costs)
        rows.append({
            "year": year,
            "strategy_pct": round(result.total_return_pct, 2),
            "strategy_drop_pct": round(result.max_drawdown_pct, 2),
            "buy_hold_pct": round(held.total_return_pct, 2),
            "buy_hold_drop_pct": round(held.max_drawdown_pct, 2),
            "btc_vs_hold": round(btc_vs_hold(result, held), 3),
            "trades": len(result.trades),
        })
    return rows


END_OF_DATA = datetime(9999, 1, 1, tzinfo=timezone.utc)


def strategy_report(
    market: Market,
    definition: StrategyDefinition,
    costs: CostSettings,
    margin: MarginSettings = NO_MARGIN,
    start: datetime | None = None,
) -> dict:
    """`start`: test from this day on (None = the full history)."""
    window = range(len(market.candles)) if start is None else market.index_range(start, END_OF_DATA)
    if len(window) < 2:
        raise ValueError("Not enough data after the start date.")
    entry, exit_signal = signals(market, definition)
    result = run_backtest(
        market, window, entry, exit_signal, definition.spec.stop_atr, costs,
        record_equity=True, margin=margin,
    )
    held = buy_and_hold(market, window, costs, record_equity=True)

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
        "margin": {
            "leverage": margin.leverage,
            "open_fee_pct": margin.open_fee_pct,
            "rollover_fee_pct": margin.rollover_fee_pct,
            "rollover_hours": margin.rollover_hours,
            "liquidation_level_pct": margin.liquidation_level_pct,
            "liquidation_fee_pct": margin.liquidation_fee_pct,
        },
        "start": None if start is None else start.date().isoformat(),
        "summary": {**summary(result), "btc_vs_hold": round(btc_vs_hold(result, held), 3)},
        "buy_and_hold": summary(held),
        "by_start_year": start_year_table(market, definition, costs, margin),
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
            "These results include years that were used to choose this strategy, so they "
            "are optimistic. The walk-forward test is stricter, and forward paper trading "
            "is the only clean test."
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


def strategy_state(
    market: Market,
    definition: StrategyDefinition,
    costs: CostSettings = CostSettings(),
    recent: int = 5,
) -> dict:
    """
    Where a strategy stands now, on the same continuous run as its backtest:
    the rules at the latest completed candle, the open trade (if any) with
    its result if sold at the latest close, a new BUY/SELL signal at that
    close (it would be carried out at the next open), and the last trades.
    """

    spec = definition.spec
    blocks = evaluate_all(market)
    entry, exit_signal = strategy_signals(blocks, spec)
    result = run_backtest(
        market, range(len(market.candles)), entry, exit_signal, spec.stop_atr, costs
    )

    last_i = len(market.candles) - 1
    last = market.candles[last_i]
    period = timedelta(hours=TIMEFRAME_HOURS[market.timeframe])

    rules = [
        {"role": "Trend filter", "rule": spec.trend, "met": blocks["trend"][spec.trend][last_i]},
        {"role": "Buy trigger", "rule": spec.trigger, "met": blocks["trigger"][spec.trigger][last_i]},
    ]
    if spec.volume != "none":
        rules.append({"role": "Volume filter", "rule": spec.volume, "met": blocks["volume"][spec.volume][last_i]})
    rules.append({"role": "Sell rule", "rule": spec.exit, "met": exit_signal[last_i]})

    trades = result.trades
    open_trade = trades[-1] if trades and trades[-1].exit_reason == "end" else None
    closed = [t for t in trades if t.exit_reason != "end"]

    position = None
    signal = None
    if open_trade is not None:
        stop = None
        if spec.stop_atr:
            # The stop is set from the ATR of the candle that gave the buy signal.
            entry_index = next(i for i, c in enumerate(market.candles) if c.timestamp == open_trade.entry_time)
            j = entry_index - 1
            while j > 0 and not entry[j]:
                j -= 1
            atr = market.rows[j].values.get("atr_14")
            stop = open_trade.entry_price - spec.stop_atr * atr if atr is not None else None
        position = {
            "entry_time": open_trade.entry_time.isoformat(),
            "entry_price": round(open_trade.entry_price, 2),
            "price_change_pct": round((last.close / open_trade.entry_price - 1) * 100, 2),
            "result_if_sold_pct": round(open_trade.return_pct, 2),
            "days_held": round((last.timestamp + period - open_trade.entry_time) / timedelta(days=1), 1),
            "stop_price": None if stop is None else round(stop, 2),
            "stop_distance_pct": None if stop is None else round((last.close / stop - 1) * 100, 2),
        }
        if stop is not None and last.close < stop:
            signal = {"action": "SELL", "reason": "the close is below the stop"}
        elif exit_signal[last_i]:
            signal = {"action": "SELL", "reason": f"sell rule: {spec.exit}"}
    elif entry[last_i]:
        signal = {"action": "BUY", "reason": "all buy rules are met"}

    def trade_dict(t):
        return {
            "entry_time": t.entry_time.isoformat(), "entry_price": round(t.entry_price, 2),
            "exit_time": t.exit_time.isoformat(), "exit_price": round(t.exit_price, 2),
            "return_pct": round(t.return_pct, 2), "exit_reason": t.exit_reason,
            "days_held": round((t.exit_time - t.entry_time) / timedelta(days=1), 1),
        }

    return {
        "strategy": {"id": definition.id, "name": definition.name, "timeframe": definition.timeframe,
                     "description": definition.description},
        "costs": {"fee_pct": costs.fee_pct, "slippage_pct": costs.slippage_pct},
        "candle_time": last.timestamp.isoformat(),
        "close": last.close,
        "next_close": (last.timestamp + 2 * period).isoformat(),
        "rules": rules,
        "position": position,
        "signal": signal,
        "last_closed_trade": trade_dict(closed[-1]) if closed else None,
        "recent_trades": [trade_dict(t) for t in reversed(closed[-recent:])],
        "trades_total": len(closed),
    }
