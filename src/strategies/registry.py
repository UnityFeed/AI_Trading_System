"""
The list of strategies the system knows.

Every strategy we find or build is added here. Being on this list is what
makes it available everywhere: the Strategy tester page (full-history
backtest, per-year results, every trade), the trade markers on the chart,
and (for the one marked ACTIVE) the paper trader.

Two kinds:
- "rules" (spec): all-in / all-out, a combination of the building blocks in
  src/backtesting/conditions.py (trend filter, buy trigger, volume filter,
  sell rule, optional ATR stop) on one timeframe;
- "exposure" (exposure): graded, holds 0-100% in BTC, see
  src/backtesting/exposure.py (roadmap 9c, from docs/research/).
"""

from dataclasses import dataclass

from src.backtesting.exposure import ExposureSpec
from src.backtesting.search import StrategySpec


@dataclass(frozen=True)
class StrategyDefinition:
    id: str  # short, stable, used in URLs
    name: str
    timeframe: str
    spec: StrategySpec | None  # rules strategies
    description: str  # plain language: what it does
    origin: str  # where it came from and how it was chosen
    exposure: ExposureSpec | None = None  # graded-exposure strategies

    @property
    def kind(self) -> str:
        return "exposure" if self.exposure is not None else "rules"

    @property
    def rules_text(self) -> str:
        return self.exposure.name if self.exposure is not None else self.spec.name


SMA_VOTES = ("close>sma20", "close>sma50", "close>sma100")
MOMENTUM_VOTES = ("ret28>0", "ret56>0", "ret91>0", "ret182>0")
FIXED_IN_ADVANCE = (
    "Rules and settings taken unchanged from the research report (fixed in "
    "advance, not tuned on our data)."
)


STRATEGIES: tuple[StrategyDefinition, ...] = (
    StrategyDefinition(
        id="trend-macd-1d",
        name="Daily trend + MACD",
        timeframe="1d",
        spec=StrategySpec("ema50>ema200", "macd_cross_up", "none", "ema20_cross_down_ema50", 2.0),
        description=(
            "Buy when the long trend is up (EMA 50 above EMA 200) and MACD crosses above "
            "its signal line. Sell when EMA 20 crosses below EMA 50, or when the price "
            "closes 2x ATR below the buy price."
        ),
        origin=(
            "Step 5a candidate 1: top 10 on 2013-2021 at both fees; chosen by the "
            "walk-forward for 2022-2026 five years in a row."
        ),
    ),
    StrategyDefinition(
        id="trend-ema-cross-1d",
        name="Daily EMA 200 + EMA 20/50 cross",
        timeframe="1d",
        spec=StrategySpec("close>ema200", "ema20_cross_up_ema50", "none", "ema20_cross_down_ema50", 2.0),
        description=(
            "Buy when the price is above EMA 200 and EMA 20 crosses above EMA 50. Sell when "
            "EMA 20 crosses back below EMA 50, or on a 2x ATR stop."
        ),
        origin="Step 5a candidate 2 (top 10 on 2013-2021 at both fees).",
    ),
    StrategyDefinition(
        id="trend-dip-1d",
        name="Daily uptrend dip (RSI < 40)",
        timeframe="1d",
        spec=StrategySpec("ema50>ema200", "rsi<40", "none", "ema20_cross_down_ema50", None),
        description=(
            "Buy a dip (RSI below 40) only while the long trend is up (EMA 50 above EMA 200). "
            "Sell when EMA 20 crosses below EMA 50."
        ),
        origin="Step 5a candidate 3: the only dip-buying rule in the top 10.",
    ),
    # -- graded exposure (roadmap 9c), from the research report --------------
    StrategyDefinition(
        id="sma-ensemble-1d",
        name="S1 Price above averages (20/50/100)",
        timeframe="1d",
        spec=None,
        exposure=ExposureSpec("BTC share = votes close>SMA20/50/100 (0, 1/3, 2/3, 1) | band 12.5%", SMA_VOTES),
        description=(
            "Three votes: is the close above its 20-, 50- and 100-day average? Hold 0%, 33%, "
            "67% or 100% in BTC depending on how many say yes. Trades only when the share "
            "changes by at least 12.5 points."
        ),
        origin=f"Report shortlist #1 (evidence A). {FIXED_IN_ADVANCE}",
    ),
    StrategyDefinition(
        id="momentum-ensemble-1d",
        name="S2 Momentum 1-6 months",
        timeframe="1d",
        spec=None,
        exposure=ExposureSpec("BTC share = votes price above 28/56/91/182 days ago | band 12.5%", MOMENTUM_VOTES),
        description=(
            "Four votes: is the price higher than 28, 56, 91 and 182 days ago? Hold 0-100% "
            "in BTC in steps of 25%."
        ),
        origin=f"Report shortlist #2 (evidence A for the signal). {FIXED_IN_ADVANCE}",
    ),
    StrategyDefinition(
        id="core50-sma-1d",
        name="S3 50% core + averages",
        timeframe="1d",
        spec=None,
        exposure=ExposureSpec("50% always + 50% x votes close>SMA20/50/100 | band 12.5%", SMA_VOTES, core=0.5),
        description=(
            "Always keep 50% in BTC; the other 50% follows S1 (price above its 20/50/100-day "
            "averages). Never fully out, so it keeps part of the big rebound days."
        ),
        origin=f"Report shortlist #3 (the direct fix for missing rebound days). {FIXED_IN_ADVANCE}",
    ),
    StrategyDefinition(
        id="core50-trend-macd-1d",
        name="50% core + Daily trend + MACD",
        timeframe="1d",
        spec=None,
        exposure=ExposureSpec("50% always + 50% while 'Daily trend + MACD' holds (no stop) | band 12.5%",
                              ("trend-macd",), core=0.5),
        description=(
            "Always keep 50% in BTC; the other 50% is in BTC while our Daily trend + MACD "
            "strategy would be holding (its stop is not used). Our best rule, but never fully out."
        ),
        origin=(
            "Report shortlist #3 (core + overlay) with our step 5a candidate 1 as the overlay "
            "instead of S1. Core 50% fixed in advance."
        ),
    ),
    StrategyDefinition(
        id="sma-volcap-1d",
        name="S4 Averages + volatility cap",
        timeframe="1d",
        spec=None,
        exposure=ExposureSpec("S1 x min(1, 60% / yearly volatility) | band 12.5%", SMA_VOTES, vol_target_pct=60),
        description=(
            "S1, but hold less BTC when the price swings wildly: the share is multiplied by "
            "60% / current yearly volatility (if volatility is 80%, hold 3/4 of the S1 share)."
        ),
        origin=f"Report shortlist #4 (risk control, expect lower return). {FIXED_IN_ADVANCE}",
    ),
    StrategyDefinition(
        id="rebalance-60-1d",
        name="S5 60% BTC, rebalanced",
        timeframe="1d",
        spec=None,
        exposure=ExposureSpec("60% BTC / 40% cash, rebalance when 10 points off", fixed_weight=0.6, band=0.10),
        description=(
            "Always aim for 60% BTC and 40% cash. When BTC's share drifts more than 10 points "
            "away (after a big rise or fall), trade back to 60%: sells after rises, buys after falls."
        ),
        origin=f"Report shortlist #5 (no timing at all; the simplest alternative core). {FIXED_IN_ADVANCE}",
    ),
    StrategyDefinition(
        id="sma-donchian-1d",
        name="S6 Averages + breakout vote",
        timeframe="1d",
        spec=None,
        exposure=ExposureSpec("votes close>SMA20/50/100 + breakout 50/20 days | band 12.5%",
                              SMA_VOTES + ("donchian50/20",)),
        description=(
            "S1 plus a fourth vote: yes after a close above the highest high of the previous "
            "50 days, until a close below the lowest low of the previous 20 days."
        ),
        origin=f"Report shortlist #8 (breakout as one ensemble member). {FIXED_IN_ADVANCE}",
    ),
    StrategyDefinition(
        id="sma-mvrv-1d",
        name="S8 Averages + MVRV cap",
        timeframe="1d",
        spec=None,
        exposure=ExposureSpec("S1, at most 100/50/25% when MVRV-Z < 3 / 3-5 / >= 5 (1-day delay) | band 12.5%",
                              SMA_VOTES, mvrv_cap=True),
        description=(
            "S1, but hold at most 50% in BTC when it is expensive compared with what holders "
            "paid (MVRV-Z 3-5) and at most 25% when very expensive (5 or more). Uses Coin "
            "Metrics data from the day before."
        ),
        origin=f"Report shortlist #6 (on-chain valuation as a slow cap; evidence C). {FIXED_IN_ADVANCE}",
    ),
    StrategyDefinition(
        id="sma-hashrate-1d",
        name="S9 Averages + hash-rate filter",
        timeframe="1d",
        spec=None,
        exposure=ExposureSpec("S1, no increases while hash rate 30d avg < 60d avg (2-day delay) | band 12.5%",
                              SMA_VOTES, hash_filter=True),
        description=(
            "S1, but never raise the BTC share while miners are under stress (30-day average "
            "hash rate below the 60-day average). Lowering is always allowed."
        ),
        origin=f"Report shortlist #7 (hash-rate trend; evidence B-). {FIXED_IN_ADVANCE}",
    ),
)

ACTIVE_STRATEGY_ID = "trend-macd-1d"  # followed by the paper trader


def get_strategy(strategy_id: str) -> StrategyDefinition:
    for strategy in STRATEGIES:
        if strategy.id == strategy_id:
            return strategy
    raise KeyError(f"Unknown strategy: {strategy_id}")


def active_strategy() -> StrategyDefinition:
    return get_strategy(ACTIVE_STRATEGY_ID)
