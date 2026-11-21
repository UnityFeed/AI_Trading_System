"""
Paper trader: follows one strategy with virtual money, using the same
rules and building blocks as the backtester.

For every completed candle of the strategy's timeframe (one per day for
"1d") it records one decision at the close: BUY, SELL, HOLD (in BTC, no
reason to sell), WAIT (in cash, no reason to buy), PENDING (an order is
still waiting) or SKIP (a safety check blocked a buy).

A BUY or SELL becomes an order that fills at the open of the first
tradeable hour after the decision candle ends (normally 00:00 UTC the
next day for daily candles), with Kraken fees and slippage. Hours filled
in from another exchange, and Kraken's stale reopening hour, are skipped.

Safety checks (they can block, never force, a trade):
- stale data: if the newest hourly candle is older than MAX_DATA_AGE,
  nothing is processed until the data is updated;
- kill switch: while the file database/STOP_PAPER_TRADING exists, no new
  BUY is made (selling stays possible).
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.analysis.primary_history import ContinuousHistory
from src.analysis.timeframes import TIMEFRAME_HOURS
from src.backtesting.conditions import evaluate_all
from src.backtesting.engine import CostSettings
from src.backtesting.market import build_market, untradeable_hours
from src.backtesting.search import StrategySpec
from src.paper_trading.store import PROJECT_ROOT, PaperTradingStore


# The rule the walk-forward kept choosing in 2022-2026 (see CLAUDE.md).
ACTIVE_STRATEGY = StrategySpec(
    "ema50>ema200", "macd_cross_up", "none", "ema20_cross_down_ema50", 2.0
)
ACTIVE_TIMEFRAME = "1d"
STARTING_CASH = 10_000.0
MAX_DATA_AGE = timedelta(hours=3)
KILL_SWITCH = PROJECT_ROOT / "database" / "STOP_PAPER_TRADING"


@dataclass
class StepReport:
    decisions: list[str] = field(default_factory=list)
    fills: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def condition_snapshot(blocks, spec: StrategySpec, row, i: int) -> dict:
    """What the strategy saw at candle i: indicator values and rule states."""
    values = {k: (round(v, 4) if v is not None else None) for k, v in row.values.items()}
    return {
        "indicators": values,
        "rules": {
            f"trend: {spec.trend}": blocks["trend"][spec.trend][i],
            f"trigger: {spec.trigger}": blocks["trigger"][spec.trigger][i],
            f"volume: {spec.volume}": blocks["volume"][spec.volume][i],
            f"exit: {spec.exit}": blocks["exit"][spec.exit][i],
        },
    }


class PaperTrader:

    def __init__(
        self,
        store: PaperTradingStore,
        spec: StrategySpec = ACTIVE_STRATEGY,
        timeframe: str = ACTIVE_TIMEFRAME,
        costs: CostSettings = CostSettings(),
        kill_switch: Path = KILL_SWITCH,
    ):
        self.store = store
        self.spec = spec
        self.timeframe = timeframe
        self.costs = costs
        self.kill_switch = kill_switch

    def ensure_account(self, start_candle: datetime, cash: float = STARTING_CASH):
        account = self.store.get_account()
        if account is None:
            account = self.store.create_account(
                self.spec.name, self.timeframe, cash, start_candle
            )
        elif account.strategy != self.spec.name or account.timeframe != self.timeframe:
            raise RuntimeError(
                "The paper account follows a different strategy "
                f"({account.strategy}, {account.timeframe}). Reset it to switch."
            )
        return account

    def step(self, history: ContinuousHistory, now: datetime | None = None) -> StepReport:
        report = StepReport()
        account = self.store.get_account()
        if account is None:
            raise RuntimeError("No paper account; call ensure_account first.")

        now = now or datetime.now(timezone.utc)
        if not history.candles:
            report.warnings.append("No market data.")
            return report

        newest_hour = history.candles[-1].timestamp
        if now - (newest_hour + timedelta(hours=1)) > MAX_DATA_AGE:
            report.warnings.append(
                f"Data is stale (newest hour {newest_hour.isoformat()}); "
                "update the data first. Nothing was processed."
            )
            return report

        market = build_market(history, self.timeframe)
        blocks = evaluate_all(market)
        hourly = {c.timestamp: c for c in history.candles}
        blocked = untradeable_hours(history)
        period = timedelta(hours=TIMEFRAME_HOURS[self.timeframe])

        def try_fill(decision_candle: datetime, until: datetime) -> None:
            """Fill a waiting order at the first tradeable hour before `until`."""
            nonlocal account
            if account.pending_side is None:
                return
            hour = decision_candle + period
            while hour < until and hour <= newest_hour:
                candle = hourly.get(hour)
                if candle is not None and hour not in blocked:
                    self._fill(account, candle, report)
                    account = self.store.get_account()
                    return
                hour += timedelta(hours=1)

        for i, candle in enumerate(market.candles):
            if candle.timestamp < account.start_candle:
                continue
            if account.last_processed and candle.timestamp <= account.last_processed:
                continue

            # A waiting order fills inside this candle (never later).
            if account.last_processed is not None:
                try_fill(account.last_processed, candle.timestamp + period)

            action, reason = self._decide(account, blocks, market, i)
            snapshot = condition_snapshot(blocks, self.spec, market.rows[i], i)
            decision_id = self.store.add_decision(
                candle.timestamp, action, reason, candle.close, snapshot
            )
            report.decisions.append(
                f"{candle.timestamp.date()} {action}: {reason} (close {candle.close:,.2f})"
            )

            updates = {"last_processed": candle.timestamp}
            if action in ("BUY", "SELL"):
                updates["pending_side"] = action.lower()
                updates["pending_decision_id"] = decision_id
                if action == "BUY":
                    atr = market.rows[i].values.get("atr_14")
                    updates["stop_price"] = (
                        candle.close - self.spec.stop_atr * atr
                        if self.spec.stop_atr and atr else None
                    )
            self.store.update_account(**updates)
            account = self.store.get_account()

        # Fill as soon as the next hour after the last decision is available.
        if account.last_processed is not None:
            try_fill(account.last_processed, newest_hour + timedelta(hours=1))

        return report

    def _decide(self, account, blocks, market, i: int) -> tuple[str, str]:
        spec = self.spec
        close = market.candles[i].close

        if account.pending_side:
            return "PENDING", f"{account.pending_side} order still waiting for a tradeable open"

        if account.btc == 0:
            wants = (
                blocks["trend"][spec.trend][i]
                and blocks["trigger"][spec.trigger][i]
                and blocks["volume"][spec.volume][i]
            )
            if not wants:
                return "WAIT", "buy rules not all met"
            if self.kill_switch.exists():
                return "SKIP", "kill switch is on (database/STOP_PAPER_TRADING)"
            return "BUY", f"{spec.trend} and {spec.trigger}"

        if account.stop_price is not None and close < account.stop_price:
            return "SELL", f"close below stop {account.stop_price:,.2f}"
        if blocks["exit"][spec.exit][i]:
            return "SELL", spec.exit
        return "HOLD", "no sell rule triggered"

    def _fill(self, account, candle, report: StepReport) -> None:
        fee_rate = self.costs.fee_pct / 100
        slip = self.costs.slippage_pct / 100

        if account.pending_side == "buy":
            price = candle.open * (1 + slip)
            fee = account.cash * fee_rate
            btc = (account.cash - fee) / price
            cash_after, btc_after = 0.0, btc
            # The stop was set as (decision close - k x ATR); keep that
            # distance but measure it from the real fill price.
            stop = None
            if account.stop_price is not None:
                decision = next(
                    d for d in self.store.decisions()
                    if d.id == account.pending_decision_id
                )
                stop = price - (decision.close - account.stop_price)
            self.store.update_account(
                cash=0.0, btc=btc, pending_side=None, pending_decision_id=None,
                entry_price=price, stop_price=stop,
            )
        else:
            price = candle.open * (1 - slip)
            gross = account.btc * price
            fee = gross * fee_rate
            btc = account.btc
            cash_after, btc_after = gross - fee, 0.0
            self.store.update_account(
                cash=cash_after, btc=0.0, pending_side=None, pending_decision_id=None,
                entry_price=None, stop_price=None,
            )

        self.store.add_fill(
            account.pending_decision_id, candle.timestamp, account.pending_side,
            price, fee, btc, cash_after, btc_after,
        )
        report.fills.append(
            f"{candle.timestamp:%Y-%m-%d %H:%M} {account.pending_side.upper()} "
            f"{btc:.6f} BTC at {price:,.2f} (fee {fee:,.2f} USD)"
        )
