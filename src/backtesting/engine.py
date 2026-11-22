"""
Long-only spot backtester: buy with all available cash, sell everything.
No margin, no leverage, no short selling.

Timing (no look-ahead):
- A decision is made at the CLOSE of candle i, using only information up
  to and including candle i.
- The order fills at the OPEN of the next tradeable candle (i+1, or later
  if i+1 is not tradeable: the primary exchange was down or had just
  reopened at a stale price).
- While an order is waiting, no new decision is made.

Costs on every fill:
- slippage: buy price = open x (1 + slippage), sell price = open x (1 - slippage)
- fee: a percentage of the trade value (Kraken charges fees per side)

ATR stop (optional): sell when a candle closes below
entry price - stop_atr x ATR(at the entry signal). Checked at the close,
filled at the next open, like every other exit.

An open position is valued at each candle's close; at the end of the
window it is sold at the last close (with costs) so results compare fairly.
"""

from dataclasses import dataclass, field
from datetime import datetime

from src.analysis.timeframes import TIMEFRAME_HOURS
from src.backtesting.market import Market


HOURS_PER_YEAR = 365.25 * 24


@dataclass(frozen=True)
class CostSettings:
    fee_pct: float = 0.80  # Kraken Pro taker fee, lowest tier (checked 21 Nov 2026)
    slippage_pct: float = 0.05  # assumption for BTC/USD market orders


@dataclass(frozen=True)
class MarginSettings:
    """
    Simulated margin (borrowed money) for long positions. leverage 1.0 means
    no margin: nothing below applies and results are exactly the same as
    without margin.

    Defaults: Kraken spot margin, long BTC/USD (Kraken lends USD), from
    Kraken's support pages read 21 Nov 2026: opening and rollover fee 0.025%
    of the borrowed USD (rollover every 4 hours); liquidation at 40% margin
    level (equity / used margin) with a 2% liquidation fee instead of the
    trading fee. ASSUMPTION: the 2% is charged on the position value (Kraken
    does not say on what). The normal trading fee applies to opening and
    closing the whole position.
    """

    leverage: float = 1.0
    open_fee_pct: float = 0.025  # once, on the borrowed USD
    rollover_fee_pct: float = 0.025  # on the borrowed USD, every 4 hours held
    rollover_hours: float = 4.0
    liquidation_level_pct: float = 40.0
    liquidation_fee_pct: float = 2.0  # on the position value (assumption)

    @property
    def enabled(self) -> bool:
        return self.leverage > 1.0


NO_MARGIN = MarginSettings()


@dataclass(frozen=True)
class Trade:
    entry_time: datetime
    entry_price: float  # after slippage
    exit_time: datetime
    exit_price: float  # after slippage
    return_pct: float  # after fees and slippage
    exit_reason: str  # "signal", "stop", "end" or "liquidated"


@dataclass(frozen=True)
class Rebalance:
    """One change of the BTC share by a graded-exposure strategy."""

    time: datetime
    price: float  # after slippage
    from_weight: float  # share of the account in BTC just before (at the open)
    to_weight: float  # share right after
    traded: float  # value bought or sold, as a share of the account
    fee: float  # fee paid, in starting-capital units


@dataclass
class BacktestResult:
    start: datetime
    end: datetime
    final_equity: float  # starts at 1.0
    max_drawdown_pct: float
    exposure_pct: float  # share of candles holding BTC
    trades: list[Trade] = field(default_factory=list)
    # (candle timestamp, account value at its close); only when requested
    equity_curve: list[tuple[datetime, float]] = field(default_factory=list)
    margin_costs: float = 0.0  # opening + rollover fees paid, in starting-capital units
    liquidations: int = 0
    # Graded-exposure runs only (src/backtesting/exposure.py):
    rebalances: list[Rebalance] = field(default_factory=list)
    end_weight: float | None = None  # BTC share at the last close (before the final sale)
    pending_target: float | None = None  # decided at the last close, not filled yet

    @property
    def turnover(self) -> float:
        """Value traded as a share of the account, summed (a full buy + sell = 2)."""
        if self.rebalances:
            return sum(r.traded for r in self.rebalances)
        return 2.0 * len(self.trades)

    @property
    def total_return_pct(self) -> float:
        return (self.final_equity - 1.0) * 100.0

    @property
    def years(self) -> float:
        return (self.end - self.start).total_seconds() / 3600 / HOURS_PER_YEAR

    @property
    def cagr_pct(self) -> float:
        if self.years <= 0 or self.final_equity <= 0:
            return -100.0
        return (self.final_equity ** (1 / self.years) - 1.0) * 100.0

    @property
    def calmar(self) -> float:
        """Yearly growth divided by the worst drop: return per unit of pain."""
        if self.max_drawdown_pct <= 0:
            return 0.0
        return self.cagr_pct / self.max_drawdown_pct

    @property
    def win_rate_pct(self) -> float:
        if not self.trades:
            return 0.0
        wins = sum(trade.return_pct > 0 for trade in self.trades)
        return wins / len(self.trades) * 100.0

    @property
    def average_trade_pct(self) -> float:
        if not self.trades:
            return 0.0
        return sum(t.return_pct for t in self.trades) / len(self.trades)


def run_backtest(
    market: Market,
    window: range,
    entry: list[bool],
    exit: list[bool],
    stop_atr: float | None = None,
    costs: CostSettings = CostSettings(),
    record_equity: bool = False,
    margin: MarginSettings = NO_MARGIN,
) -> BacktestResult:
    """
    Simulate one strategy on market candles with indexes in `window`.
    `entry` / `exit` hold one decision per candle of the whole market.

    With margin (leverage above 1) a buy uses equity x leverage; the extra is
    borrowed ("debt"). Opening and rollover fees are added to the debt. If a
    candle's low reaches the liquidation price (margin level =
    equity / initial margin at the liquidation level), the position is closed
    there (or at the open if the candle already opened below it).
    """

    if not window:
        raise ValueError("The backtest window contains no candles.")

    candles = market.candles
    fee = costs.fee_pct / 100.0
    slip = costs.slippage_pct / 100.0

    cash = 1.0
    btc = 0.0
    debt = 0.0  # what is owed: borrowed USD + fees added to it (margin only)
    borrowed = 0.0
    initial_margin = 0.0
    margin_costs = 0.0
    liquidations = 0
    hours_per_candle = TIMEFRAME_HOURS[market.timeframe]
    pending = None  # "buy" or "sell"
    pending_reason = ""
    entry_time = None
    entry_price = 0.0
    entry_cash = 0.0
    stop_price = None
    signal_index = None

    peak = 1.0
    max_drawdown = 0.0
    held_candles = 0
    trades: list[Trade] = []
    curve: list[tuple[datetime, float]] = []

    for i in window:
        candle = candles[i]

        # 1. Fill a waiting order at this candle's open, if allowed.
        if pending and market.tradeable[i]:
            if pending == "buy" and cash <= 0:
                pending = None  # account wiped out: nothing left to trade with
            elif pending == "buy" and margin.enabled:
                entry_price = candle.open * (1 + slip)
                entry_cash = cash
                position = cash * margin.leverage
                borrowed = position - cash
                opening_fee = borrowed * margin.open_fee_pct / 100
                btc = position / entry_price
                debt = borrowed + position * fee + opening_fee
                initial_margin = position / margin.leverage
                margin_costs += opening_fee
                cash = 0.0
                entry_time = candle.timestamp
                if stop_atr is not None:
                    atr = market.rows[signal_index].values.get("atr_14")
                    stop_price = (
                        entry_price - stop_atr * atr if atr is not None else None
                    )
            elif pending == "buy":
                entry_price = candle.open * (1 + slip)
                entry_cash = cash
                btc = cash * (1 - fee) / entry_price
                cash = 0.0
                entry_time = candle.timestamp
                if stop_atr is not None:
                    atr = market.rows[signal_index].values.get("atr_14")
                    stop_price = (
                        entry_price - stop_atr * atr if atr is not None else None
                    )
            else:
                exit_price = candle.open * (1 - slip)
                cash = max(0.0, btc * exit_price * (1 - fee) - debt)
                btc = 0.0
                debt = 0.0
                trades.append(Trade(
                    entry_time=entry_time,
                    entry_price=entry_price,
                    exit_time=candle.timestamp,
                    exit_price=exit_price,
                    return_pct=(cash / entry_cash - 1.0) * 100.0,
                    exit_reason=pending_reason,
                ))
                stop_price = None
            pending = None

        # 1b. Margin: borrowing costs, and forced close (liquidation).
        if margin.enabled and btc > 0:
            rollover = (
                borrowed * margin.rollover_fee_pct / 100
                * hours_per_candle / margin.rollover_hours
            )
            debt += rollover
            margin_costs += rollover
            liquidation_price = (
                debt + margin.liquidation_level_pct / 100 * initial_margin
            ) / btc
            if candle.low <= liquidation_price:
                exit_price = min(liquidation_price, candle.open) * (1 - slip)
                cash = max(0.0, btc * exit_price * (1 - margin.liquidation_fee_pct / 100) - debt)
                trades.append(Trade(
                    entry_time=entry_time, entry_price=entry_price,
                    exit_time=candle.timestamp, exit_price=exit_price,
                    return_pct=(cash / entry_cash - 1.0) * 100.0,
                    exit_reason="liquidated",
                ))
                btc = 0.0
                debt = 0.0
                stop_price = None
                pending = None
                liquidations += 1

        # 2. Value the account at the close.
        equity = cash + btc * candle.close - debt
        if record_equity:
            curve.append((candle.timestamp, equity))
        if btc > 0:
            held_candles += 1
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, (peak - equity) / peak)

        # 3. Decide at the close (only if no order is waiting).
        if pending is None:
            if btc == 0 and entry[i]:
                pending = "buy"
                signal_index = i
            elif btc > 0:
                if stop_price is not None and candle.close < stop_price:
                    pending, pending_reason = "sell", "stop"
                elif exit[i]:
                    pending, pending_reason = "sell", "signal"

    # Sell what is left at the last close so every result ends in cash.
    if window and btc > 0:
        last = candles[window[-1]]
        exit_price = last.close * (1 - slip)
        cash = max(0.0, btc * exit_price * (1 - fee) - debt)
        trades.append(Trade(
            entry_time=entry_time,
            entry_price=entry_price,
            exit_time=last.timestamp,
            exit_price=exit_price,
            return_pct=(cash / entry_cash - 1.0) * 100.0,
            exit_reason="end",
        ))

    return BacktestResult(
        start=candles[window[0]].timestamp,
        end=candles[window[-1]].timestamp,
        final_equity=cash,
        max_drawdown_pct=max_drawdown * 100.0,
        exposure_pct=held_candles / len(window) * 100.0,
        trades=trades,
        equity_curve=curve,
        margin_costs=margin_costs,
        liquidations=liquidations,
    )


def buy_and_hold(
    market: Market,
    window: range,
    costs: CostSettings = CostSettings(),
    record_equity: bool = False,
) -> BacktestResult:
    """
    Buy at the first tradeable open inside the window and hold until the
    last close (sold there with costs). The benchmark every strategy must
    be compared with.
    """

    fee = costs.fee_pct / 100.0
    slip = costs.slippage_pct / 100.0
    candles = market.candles

    first = next((i for i in window if market.tradeable[i]), None)
    if first is None:
        raise ValueError("No tradeable candle in the window.")

    entry_price = candles[first].open * (1 + slip)
    btc = (1 - fee) / entry_price

    peak = 1.0
    max_drawdown = 0.0
    curve: list[tuple[datetime, float]] = []

    for i in window:
        equity = 1.0 if i < first else btc * candles[i].close
        if record_equity:
            curve.append((candles[i].timestamp, equity))
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, (peak - equity) / peak)

    last = candles[window[-1]]
    exit_price = last.close * (1 - slip)
    final = btc * exit_price * (1 - fee)

    return BacktestResult(
        start=candles[window[0]].timestamp,
        end=last.timestamp,
        final_equity=final,
        max_drawdown_pct=max_drawdown * 100.0,
        exposure_pct=(window.stop - first) / len(window) * 100.0,
        trades=[Trade(
            entry_time=candles[first].timestamp,
            entry_price=entry_price,
            exit_time=last.timestamp,
            exit_price=exit_price,
            return_pct=(final - 1.0) * 100.0,
            exit_reason="end",
        )],
        equity_curve=curve,
    )
