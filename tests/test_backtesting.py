import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from src.analysis.primary_history import ContinuousHistory, PRIMARY_LABEL, SourceChange
from src.analysis.technical_indicators import IndicatorSettings
from src.backtesting.engine import CostSettings, MarginSettings, buy_and_hold, run_backtest
from src.backtesting.market import Market, build_market, untradeable_hours
from src.backtesting.search import StrategySpec, all_specs, search
from tests.helpers import BASE_TIME, hourly_candles


NO_COSTS = CostSettings(fee_pct=0.0, slippage_pct=0.0)


def make_market(opens, closes=None, tradeable=None, atr=None):
    """Hourly market with given opens/closes (close defaults to open)."""

    closes = closes or opens
    candles = [
        replace(c, open=o, close=cl, high=max(o, cl), low=min(o, cl))
        for c, o, cl in zip(hourly_candles(list(opens)), opens, closes)
    ]
    rows = [
        type("Row", (), {"values": {"atr_14": atr}, "close": c.close})()
        for c in candles
    ]
    return Market(
        timeframe="1h",
        candles=candles,
        rows=rows,
        tradeable=tradeable or [True] * len(candles),
        consecutive=[False] + [True] * (len(candles) - 1),
    )


def flags(n, *indexes):
    result = [False] * n
    for i in indexes:
        result[i] = True
    return result


class TestEngine(unittest.TestCase):

    def test_signal_fills_at_next_open(self):

        # Buy signal at close of 1 -> buy at open of 2 (=10).
        # Sell signal at close of 3 -> sell at open of 4 (=15).
        market = make_market([8, 9, 10, 12, 15, 20])

        result = run_backtest(
            market, range(6), flags(6, 1), flags(6, 3), costs=NO_COSTS
        )

        self.assertEqual(len(result.trades), 1)
        trade = result.trades[0]
        self.assertEqual(trade.entry_price, 10)
        self.assertEqual(trade.exit_price, 15)
        self.assertAlmostEqual(trade.return_pct, 50.0)
        self.assertAlmostEqual(result.final_equity, 1.5)
        self.assertEqual(trade.entry_time, BASE_TIME + timedelta(hours=2))

    def test_fees_and_slippage_are_charged_on_both_sides(self):

        market = make_market([100, 100, 100, 100])
        costs = CostSettings(fee_pct=1.0, slippage_pct=0.5)

        result = run_backtest(market, range(4), flags(4, 0), flags(4, 1), costs=costs)

        # buy at 100.5, keep 99% ; sell at 99.5, keep 99%
        expected = 0.99 / 100.5 * 99.5 * 0.99
        self.assertAlmostEqual(result.final_equity, expected)

    def test_untradeable_open_delays_the_fill(self):

        market = make_market([10, 11, 50, 13, 14], tradeable=[True, True, False, True, True])

        result = run_backtest(market, range(5), flags(5, 1), flags(5), costs=NO_COSTS)

        # Open of candle 2 (50, stale) is skipped; buy at open of 3.
        self.assertEqual(result.trades[0].entry_price, 13)

    def test_open_position_is_sold_at_the_end(self):

        market = make_market([10, 10, 20], closes=[10, 10, 30])

        result = run_backtest(market, range(3), flags(3, 0), flags(3), costs=NO_COSTS)

        self.assertEqual(result.trades[-1].exit_reason, "end")
        self.assertAlmostEqual(result.final_equity, 3.0)  # 10 -> 30

    def test_atr_stop(self):

        # Entry at 100 with ATR 5 and 2x stop -> stop at 90.
        market = make_market(
            [100, 100, 100, 95, 85, 80], closes=[100, 100, 95, 89, 80, 80], atr=5.0
        )

        result = run_backtest(
            market, range(6), flags(6, 0), flags(6), stop_atr=2.0, costs=NO_COSTS
        )

        trade = result.trades[0]
        self.assertEqual(trade.exit_reason, "stop")
        self.assertEqual(trade.exit_price, 85)  # close 89 < 90 -> sell at next open

    def test_drawdown_and_exposure(self):

        market = make_market([10, 10, 10, 10], closes=[10, 20, 10, 15])

        result = run_backtest(market, range(4), flags(4), flags(4), costs=NO_COSTS)
        self.assertEqual(result.max_drawdown_pct, 0.0)
        self.assertEqual(result.exposure_pct, 0.0)
        self.assertEqual(result.trades, [])

        held = buy_and_hold(market, range(4), NO_COSTS)
        self.assertAlmostEqual(held.max_drawdown_pct, 50.0)  # 20 -> 10
        self.assertAlmostEqual(held.final_equity, 1.5)

    def test_buy_and_hold_skips_untradeable_first_open(self):

        market = make_market([50, 10, 10], closes=[10, 10, 20], tradeable=[False, True, True])

        held = buy_and_hold(market, range(3), NO_COSTS)

        self.assertEqual(held.trades[0].entry_price, 10)
        self.assertAlmostEqual(held.final_equity, 2.0)

    def test_no_new_decision_while_an_order_waits(self):

        market = make_market([10, 11, 12, 13, 14], tradeable=[True, False, False, True, True])

        # Buy signal at close 0 waits (candles 1-2 untradeable); the sell
        # signal at close 1 is ignored because the buy has not filled yet.
        result = run_backtest(market, range(5), flags(5, 0), flags(5, 1), costs=NO_COSTS)

        self.assertEqual(result.trades[0].entry_price, 13)
        self.assertEqual(result.trades[0].exit_reason, "end")


def margin_only(leverage, **overrides):
    """Margin with no borrowing fees unless given, to check the arithmetic."""
    values = dict(leverage=leverage, open_fee_pct=0.0, rollover_fee_pct=0.0, liquidation_fee_pct=2.0)
    values.update(overrides)
    return MarginSettings(**values)


def with_lows(market, lows):
    candles = [replace(c, low=low) for c, low in zip(market.candles, lows)]
    return replace(market, candles=candles)


class TestMargin(unittest.TestCase):

    def test_leverage_one_changes_nothing(self):

        market = make_market([10, 11, 12, 13, 12, 14])
        plain = run_backtest(market, range(6), flags(6, 0), flags(6, 3), costs=CostSettings())
        same = run_backtest(market, range(6), flags(6, 0), flags(6, 3), costs=CostSettings(),
                            margin=MarginSettings(leverage=1.0))

        self.assertEqual(plain.final_equity, same.final_equity)
        self.assertEqual(plain.trades, same.trades)

    def test_two_times_leverage_doubles_the_move(self):

        # Buy at 100, sell at 110: +10% becomes +20% with 2x (no fees).
        market = make_market([100, 100, 105, 110, 110])

        result = run_backtest(market, range(5), flags(5, 0), flags(5, 2),
                              costs=NO_COSTS, margin=margin_only(2.0))

        self.assertAlmostEqual(result.final_equity, 1.2)
        self.assertAlmostEqual(result.trades[0].return_pct, 20.0)

    def test_borrowing_fees_are_charged_on_the_borrowed_amount(self):

        market = make_market([100, 100, 100, 100])
        margin = margin_only(2.0, open_fee_pct=1.0, rollover_fee_pct=1.0)

        result = run_backtest(market, range(4), flags(4, 0), flags(4, 2),
                              costs=NO_COSTS, margin=margin)

        # Borrowed 1.0: opening fee 1% = 0.01; held candles 1 and 2, each 1h
        # = 1/4 of a 4-hour rollover period: 2 x 0.25% = 0.005.
        self.assertAlmostEqual(result.margin_costs, 0.015)
        self.assertAlmostEqual(result.final_equity, 1.0 - 0.015)

    def test_liquidation_at_forty_percent_margin_level(self):

        # 3x at 100: position 3, borrowed 2, used margin 1, 0.03 BTC.
        # Liquidation when 0.03 x p - 2 = 0.4  ->  p = 80.
        market = with_lows(make_market([100, 100, 95, 90, 90]), [100, 100, 94, 75, 90])

        result = run_backtest(market, range(5), flags(5, 0), flags(5),
                              costs=NO_COSTS, margin=margin_only(3.0))

        trade = result.trades[0]
        self.assertEqual(trade.exit_reason, "liquidated")
        self.assertAlmostEqual(trade.exit_price, 80.0)
        self.assertEqual(result.liquidations, 1)
        # 0.03 x 80 less the 2% liquidation fee, minus the 2 borrowed.
        self.assertAlmostEqual(result.final_equity, 0.03 * 80 * 0.98 - 2)

    def test_gap_below_the_liquidation_price_closes_at_the_open(self):

        market = with_lows(make_market([100, 100, 70, 70]), [100, 100, 65, 70])

        result = run_backtest(market, range(4), flags(4, 0), flags(4),
                              costs=NO_COSTS, margin=margin_only(3.0))

        self.assertAlmostEqual(result.trades[0].exit_price, 70.0)
        self.assertAlmostEqual(result.final_equity, 0.03 * 70 * 0.98 - 2)

    def test_a_wiped_out_account_cannot_trade_again(self):

        market = with_lows(make_market([100, 100, 60, 60, 60, 80]), [100, 100, 55, 60, 60, 80])

        result = run_backtest(market, range(6), flags(6, 0, 3), flags(6),
                              costs=NO_COSTS, margin=margin_only(3.0))

        self.assertEqual(result.final_equity, 0.0)
        self.assertEqual(len(result.trades), 1)


class TestUntradeableHours(unittest.TestCase):

    def test_filled_hours_and_the_reopening_hour_are_blocked(self):

        candles = [
            replace(c, exchange=PRIMARY_LABEL) for c in hourly_candles([1, 2, 3, 4, 5])
        ]
        hours = [c.timestamp for c in candles]
        history = ContinuousHistory(
            candles=candles,
            sources={h: s for h, s in zip(hours, ["kraken", "coinbase", "coinbase", "kraken", "kraken"])},
            primary_by_hour={h: "kraken" for h in hours},
            source_changes=[
                SourceChange(hours[1], "kraken", "coinbase", 1, 2),
                SourceChange(hours[3], "coinbase", "kraken", 3, 4),
            ],
            unfilled_hours=[],
        )

        self.assertEqual(untradeable_hours(history), {hours[1], hours[2], hours[3]})

        market = build_market(history, "1h", IndicatorSettings(ema_periods=(2,)))
        self.assertEqual(market.tradeable, [True, False, False, False, True])


class TestSearch(unittest.TestCase):

    def test_every_combination_is_listed_once(self):

        specs = all_specs()
        self.assertEqual(len(specs), len(set(specs)))
        self.assertEqual(len(specs), 3 * 5 * 2 * 6 * 3)

    def test_search_runs_every_window(self):

        # Rising then falling prices across the window boundaries.
        start = datetime(2016, 12, 20, tzinfo=timezone.utc)
        closes = [100 + (i % 50) for i in range(24 * 30)]
        candles = [
            replace(c, exchange=PRIMARY_LABEL)
            for c in hourly_candles(closes, start=start)
        ]
        hours = [c.timestamp for c in candles]
        history = ContinuousHistory(
            candles=candles,
            sources={h: "kraken" for h in hours},
            primary_by_hour={h: "kraken" for h in hours},
            source_changes=[],
            unfilled_hours=[],
        )
        market = build_market(history, "1h")
        spec = StrategySpec("none", "rsi<40", "none", "rsi>50", None)

        scores = search(market, NO_COSTS, [spec])

        self.assertEqual(set(scores[0].results), {"bitstamp era", "kraken era"})
        self.assertGreater(len(scores[0].results["kraken era"].trades), 0)
        self.assertIn("rsi<40", spec.name)


if __name__ == "__main__":
    unittest.main()
