"""
The predictive engine in one call: from the market history to today's
scenarios (used by the script, the forecast log and the chart).

MODEL is the model the chart and the forecast log use. It is the model with
the best walk-forward skill in scripts/run_scenario_models.py (rerun that
script to check it on new data; change it here only with that evidence).
"""

import math
from dataclasses import dataclass
from datetime import timedelta

from src.backtesting.market import Market
from src.predictive_engine.outcomes import daily_volatility, outcomes
from src.predictive_engine.scenarios import (
    KINDS, Context, Forecast, build_context, current_forecast, weekly_trend_on_days,
)
from src.predictive_engine.structure import analyse
from src.research.features import build_frame, weekly_from_daily


HORIZON = 30
K = 1.0
MIN_MOVE = 0.03
MODEL = "analog"
MODEL_VERSION = f"{MODEL}-h{HORIZON}-k{K}-v1"


def engine_context(market: Market, premium=None) -> Context:
    frame = build_frame(market, premium)
    candles = market.candles
    daily = analyse(candles, "1d").trend
    weekly_candles = weekly_from_daily(candles)
    weekly = weekly_trend_on_days(candles, weekly_candles, analyse(weekly_candles, "1w").trend)
    return build_context(frame, outcomes(market, HORIZON, K, MIN_MOVE), daily, weekly)


@dataclass(frozen=True)
class Scenarios:
    candle_time: object  # datetime of the latest daily candle (period start)
    close: float
    horizon_days: int
    move_pct: float
    target: float  # bull barrier
    stop: float  # bear barrier
    forecast: Forecast
    daily_trend: str
    weekly_trend: str | None
    swing_high: float | None
    swing_low: float | None
    model_version: str

    def as_dict(self) -> dict:
        f = self.forecast
        decide_at = self.candle_time + timedelta(days=1)  # close of the latest candle
        order = sorted(KINDS, key=lambda k: f.probabilities[k], reverse=True)
        paths = []
        for kind in order:
            days = f.median_days.get(kind) or self.horizon_days
            if kind == "range":
                days = self.horizon_days
            level = {"bull": self.target, "bear": self.stop, "range": self.close}[kind]
            paths.append({
                "kind": kind,
                "probability": round(f.probabilities[kind], 4),
                "level": round(level, 2),
                "typical_days": days,
                "by": (decide_at + timedelta(days=days)).isoformat(),
                "meaning": {
                    "bull": f"a daily close at or above {self.target:,.0f} (+{self.move_pct:.1f}%) comes first",
                    "bear": f"a daily close at or below {self.stop:,.0f} (-{self.move_pct:.1f}%) comes first",
                    "range": f"neither within {self.horizon_days} days: closes stay between "
                             f"{self.stop:,.0f} and {self.target:,.0f}",
                }[kind],
                "proven_wrong_by": {
                    "bull": f"a close at or below {self.stop:,.0f}",
                    "bear": f"a close at or above {self.target:,.0f}",
                    "range": f"a close outside {self.stop:,.0f}-{self.target:,.0f}",
                }[kind],
            })
        return {
            "candle_time": self.candle_time.isoformat(),
            "decided_at_close": decide_at.isoformat(),
            "close": self.close,
            "horizon_days": self.horizon_days,
            "move_pct": round(self.move_pct, 2),
            "target": round(self.target, 2),
            "stop": round(self.stop, 2),
            "cases": f.cases,
            "daily_trend": self.daily_trend,
            "weekly_trend": self.weekly_trend,
            "swing_high": self.swing_high,
            "swing_low": self.swing_low,
            "model_version": self.model_version,
            "scenarios": paths,
        }


def todays_scenarios(market: Market, ctx: Context | None = None) -> Scenarios:
    ctx = ctx or engine_context(market)
    i = len(market.candles) - 1
    c = market.candles[i]
    vol = daily_volatility(market)[i]
    move = max(MIN_MOVE, K * (vol or 0.0) * math.sqrt(HORIZON))
    structure = analyse(market.candles, "1d")
    return Scenarios(
        candle_time=c.timestamp, close=c.close, horizon_days=HORIZON, move_pct=move * 100,
        target=c.close * (1 + move), stop=c.close * (1 - move),
        forecast=current_forecast(ctx, MODEL),
        daily_trend=ctx.daily_trend[i], weekly_trend=ctx.weekly_trend[i],
        swing_high=structure.swing_high[i], swing_low=structure.swing_low[i],
        model_version=MODEL_VERSION,
    )
