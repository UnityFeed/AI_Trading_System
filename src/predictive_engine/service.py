"""
The predictive engine as the app uses it: everything computed once per data
load, then served for "now" or for any past day AS IT WAS KNOWN THEN (replay).

  scenarios(horizon, day, timeframe)
                           the learning engine's bull/bear/range forecast made
                           at that candle's close (1h, 4h or 1d), its experts
                           and their weights, targets, typical time, and (if
                           decided) the outcome. Forecasts come from the saved
                           training session (`training.py`: 10 setting
                           versions, chosen year by year on earlier years
                           only) where it covers the candle, else from a live
                           honest replay with the version chosen most recently
  tools(timeframe, until)  support/resistance zones, Fibonacci levels, chart
                           patterns with their status, ADX regime and the
                           volume profile, using only swings confirmed by then
  curve(horizon)           the learning curve per year
"""

import bisect
import math
import os
import threading
from datetime import datetime, timedelta

from src.backtesting.market import Market
from src.data_collection.market_data import MarketData
from src.analysis.timeframes import TIMEFRAME_HOURS
from src.predictive_engine import learner, training
from src.predictive_engine import targets as targets_mod
from src.research import other_market_features
from src.predictive_engine.levels import adx, fibonacci, regime, support_resistance
from src.predictive_engine.outcomes import candle_volatility, default_min_move, outcomes
from src.predictive_engine.patterns import detect_patterns, status_at, swings_known_over_time, track_record
from src.predictive_engine.structure import analyse
from src.predictive_engine.volume_profile import volume_profile


K = 1.0


def horizon_label(timeframe: str, horizon: int) -> str:
    hours = horizon * TIMEFRAME_HOURS[timeframe]
    if hours % 24:
        return f"{hours} hours"
    days = hours // 24
    return "1 day" if days == 1 else f"{days} days"


def _t(dt: datetime) -> int:
    return int(dt.timestamp())


class EngineService:

    def __init__(self, daily: Market, hourly: list[MarketData], markets: dict | None = None,
                 cache: dict | None = None, timeframes=("1d",), patterns: bool = True, coin_loader=None):
        """`markets`: 1h/4h/1d/1w markets (only needed for 1h/4h forecasts); `cache`: a saved training session."""
        self.market = daily
        self.hourly = hourly
        self.hour_times = [h.timestamp for h in hourly]
        self.times = [c.timestamp for c in daily.candles]
        self.markets = dict(markets or {})
        self.markets["1d"] = daily
        self.cache = cache
        if cache and cache.get("markets_mode") in other_market_features.MODES:
            other_market_features.AI_MODE = cache["markets_mode"]  # same inputs as the training session
        self.patterns = patterns  # trees + analog experts (when the libraries are installed)
        self.coin_loader = coin_loader  # () -> {coin: {tf: Market}}: training coins for the pattern experts
        self._coins = None
        self.replays: dict = {}  # timeframe -> {horizon: Replay}
        self.info: dict = {}  # timeframe -> {horizon: training-session details or None}
        self.vols: dict = {}
        self.preparing: dict = {}  # timeframe -> threading.Thread
        self.errors: dict = {}
        self.lock = threading.Lock()
        for tf in timeframes:
            self.prepare(tf)
        self.vol = self.vols.get("1d") or candle_volatility(daily)
        self.tool_cache: dict = {}
        self._target_data: dict = {}  # (timeframe, horizon) -> excursions + past AI chances

    # -- learning ---------------------------------------------------------------

    def horizons(self, timeframe: str) -> tuple:
        return learner.TF_HORIZONS[timeframe]

    def ready(self, timeframe: str) -> bool:
        return timeframe in self.replays

    def prepare(self, timeframe: str) -> None:
        """Build the replays of one timeframe (from the training session where it still matches the data)."""
        if timeframe in self.replays:
            return
        market = self.markets[timeframe]
        times = [c.timestamp for c in market.candles]
        saved = (self.cache or {}).get("timeframes", {}).get(timeframe)
        usable = 0  # candles covered by the training session
        if saved and saved["first"] == times[0].isoformat():
            end = datetime.fromisoformat(saved["end"])
            k = bisect.bisect_right(times, end)
            if k == saved["n"] and times[k - 1] == end:
                usable = k
        replays, info = {}, {}
        inputs = pattern = coins = None
        for h in self.horizons(timeframe):
            out = outcomes(market, h, k=K)
            saved_h = saved["horizons"].get(h) if saved else None
            s = saved_h if usable else None
            if s is not None and usable == len(times):
                r = s["replay"]
            else:
                inputs = inputs or training.inputs_for(self.markets, timeframe)
                config = next((c for c in learner.CONFIGS if saved_h and c.name == saved_h["current_config"]),
                              learner.Config())
                extra = None
                if self.patterns:
                    if pattern is None:
                        pattern = training.pattern_inputs(self.markets, timeframe, inputs)
                        coins = training.coin_rows(self.coin_markets(), timeframe, pattern[0])
                    extra = training.pattern_experts(pattern[1], out, timeframe, market, coins,
                                                     n_jobs=os.cpu_count() or 1, horizon=h)
                live = training.pack(learner.replay(market, h, *inputs, config=config, outcome_list=out,
                                                    extra_experts=extra))
                r = live if s is None else _Stitched(s["replay"], live, usable)
            r.outcomes = out
            replays[h] = r
            info[h] = None if saved_h is None else {k: saved_h[k] for k in ("table", "current_config", "configs", "nested", "memorised")}
        self.vols[timeframe] = candle_volatility(market)
        with self.lock:
            self.info[timeframe] = info
            self.replays[timeframe] = replays

    def coin_markets(self) -> dict:
        if self._coins is None:
            try:
                self._coins = self.coin_loader() if self.coin_loader else {}
            except Exception:  # training data is optional
                self._coins = {}
        return self._coins

    def prepare_in_background(self, timeframe: str) -> None:
        with self.lock:
            if timeframe in self.replays or timeframe in self.preparing:
                return

            def run():
                try:
                    self.prepare(timeframe)
                except Exception as error:  # shown to the user instead of hanging forever
                    self.errors[timeframe] = str(error)

            self.preparing[timeframe] = threading.Thread(target=run, daemon=True)
            self.preparing[timeframe].start()

    # -- scenarios ------------------------------------------------------------

    def day_index(self, day: datetime | None, timeframe: str = "1d") -> int:
        times = self.times if timeframe == "1d" else [c.timestamp for c in self.markets[timeframe].candles]
        if day is None:
            return len(times) - 1
        k = bisect.bisect_right(times, day) - 1
        return max(0, k)

    def typical_days(self, horizon: int, i: int, timeframe: str = "1d") -> dict:
        """Median candles each outcome took, over outcomes known at candle i."""
        r = self.replays[timeframe][horizon]
        days = {k: [] for k in learner.KINDS}
        for o in r.outcomes[max(0, i - 20000):i + 1]:
            if o is not None and o.decided_index <= i:
                days[o.kind].append(o.days)
        return {k: (sorted(v)[len(v) // 2] if v else horizon) for k, v in days.items()}

    def scenarios(self, horizon: int, day: datetime | None = None, timeframe: str = "1d") -> dict:
        if not self.ready(timeframe):
            self.prepare(timeframe)
        r = self.replays[timeframe][horizon]
        market = self.markets[timeframe]
        times = [c.timestamp for c in market.candles] if timeframe != "1d" else self.times
        i = self.day_index(day, timeframe)
        while i > 0 and r.forecasts[i] is None:
            i -= 1
        c = market.candles[i]
        p = r.forecasts[i]
        if p is None:
            return {"error": "no forecast this early in the history"}
        vol = self.vols[timeframe]
        move = max(default_min_move(timeframe), K * (vol[i] or 0.0) * math.sqrt(horizon))
        target, stop = c.close * (1 + move), c.close * (1 - move)
        period = timedelta(hours=TIMEFRAME_HOURS[timeframe])
        decided_at = c.timestamp + period
        typical = self.typical_days(horizon, i, timeframe)
        label = horizon_label(timeframe, horizon)
        close_word = {"1h": "an hourly close", "4h": "a 4-hour close", "1d": "a daily close"}[timeframe]
        paths = []
        for kind in sorted(learner.KINDS, key=lambda k: -p[k]):
            candles = horizon if kind == "range" else typical[kind]
            paths.append({
                "kind": kind, "probability": round(p[kind], 4),
                "level": round({"bull": target, "bear": stop, "range": c.close}[kind], 2),
                "typical_days": round(candles * TIMEFRAME_HOURS[timeframe] / 24, 2), "typical_candles": candles,
                "by": (decided_at + period * candles).isoformat(),
                "meaning": {
                    "bull": f"{close_word} at or above {target:,.0f} (+{move * 100:.1f}%) comes first",
                    "bear": f"{close_word} at or below {stop:,.0f} (-{move * 100:.1f}%) comes first",
                    "range": f"neither within {label}: closes stay between {stop:,.0f} and {target:,.0f}",
                }[kind],
                "proven_wrong_by": {"bull": f"a close at or below {stop:,.0f}",
                                    "bear": f"a close at or above {target:,.0f}",
                                    "range": f"a close outside {stop:,.0f}-{target:,.0f}"}[kind],
            })
        o = r.outcomes[i]
        info = self.info[timeframe].get(horizon)
        return {
            "timeframe": timeframe, "candle_time": c.timestamp.isoformat(), "time": _t(c.timestamp), "close": c.close,
            "horizon_days": horizon, "horizon_candles": horizon, "horizon_label": label,
            "move_pct": round(move * 100, 2),
            "target": round(target, 2), "stop": round(stop, 2),
            "scenarios": paths,
            "experts": {e: {k: round(v, 4) for k, v in probs.items()} for e, probs in r.experts[i].items()},
            "weights": {e: round(v, 3) for e, v in r.weights[i].items()},
            "outcome": None if o is None else {
                "kind": o.kind, "days": o.days, "decided_time": _t(times[o.decided_index]),
            },
            "score_so_far": self.score_until(horizon, i, timeframe),
            "model_version": f"{learner.VERSION}-{timeframe}-h{horizon}",
            "cases": sum(1 for x in r.outcomes[:i + 1] if x is not None and x.decided_index <= i),
            "training": None if info is None else {
                "version_now": info["current_config"],
                "honest_skill": info["nested"].get("brier_skill"),
                "memorised_skill": [m.get("brier_skill") for m in info["memorised"]],
                "versions": [{"name": v["name"], "skill": v.get("brier_skill")} for v in info["configs"]],
                "choice_per_year": info["table"],
            },
            "targets": self.targets(horizon, i, timeframe),
        }

    def targets(self, horizon: int, i: int, timeframe: str = "1d") -> list[dict]:
        """Real chart levels above and below the price at candle i, each with its chance to be reached in time."""
        market = self.markets[timeframe]
        c = market.candles[i]
        vol = self.vols[timeframe]
        if not vol[i]:
            return []
        key = (timeframe, horizon)
        if key not in self._target_data:
            r = self.replays[timeframe][horizon]
            self._target_data[key] = (
                targets_mod.excursions(market.candles, market.consecutive, vol, horizon),
                targets_mod.chances_array(r.forecasts, "bull"),
                targets_mod.chances_array(r.forecasts, "bear"),
            )
        exc, bull, bear = self._target_data[key]
        tools = self.tools(timeframe, market.candles, c.timestamp)
        structure = self.tool_cache[(timeframe, id(market.candles))][0]
        scale = vol[i] * math.sqrt(horizon)
        move = max(default_min_move(timeframe), K * scale)
        levels = targets_mod.candidate_levels(
            c.close, tools, structure.swing_high[i], structure.swing_low[i],
            extra=((c.close * (1 + move), "AI bull target (1 typical move)"),
                   (c.close * (1 - move), "AI bear target (1 typical move)")))
        for level in levels:
            units = abs(level["distance_pct"]) / 100 / scale
            chance, cases = targets_mod.touch_chance(i, units, level["side"], exc,
                                                     bull if level["side"] == "up" else bear)
            level["chance"] = None if math.isnan(chance) else round(chance, 3)
            level["cases"] = cases
        return levels

    def score_until(self, horizon: int, i: int, timeframe: str = "1d") -> dict:
        """The engine's Brier skill vs the base rate over forecasts decided by candle i."""
        r = self.replays[timeframe][horizon]
        n = b = bb = hits = 0.0
        for j in range(i + 1):
            o = r.outcomes[j]
            if o is None or o.decided_index > i:
                continue
            p = r.forecasts[j]
            if p is None:
                continue
            n += 1
            b += learner.brier(p, o.kind)
            bb += learner.brier(r.experts[j]["base"], o.kind)
            hits += max(p, key=p.get) == o.kind
        if not n:
            return {"scored": 0}
        return {"scored": int(n), "brier_skill": round(1 - b / bb, 4), "top_hit_rate": round(hits / n, 3)}

    def curve(self, horizon: int, timeframe: str = "1d") -> list:
        r = self.replays[timeframe][horizon]
        if not r.learning_curve:
            r.learning_curve = learner.learning_curve(r, self.markets[timeframe])
        return [{"year": y, "days": n, "skill": round(1 - b / bb, 4)} for y, n, b, bb in r.learning_curve]

    # -- chart tools -------------------------------------------------------------

    def tools(self, timeframe: str, candles: list[MarketData], until: datetime | None = None) -> dict:
        key = (timeframe, id(candles))
        if key not in self.tool_cache:
            self.tool_cache[key] = (analyse(candles, timeframe), detect_patterns(candles, timeframe), adx(candles))
        structure, patterns, adx_values = self.tool_cache[key]
        times = [c.timestamp for c in candles]
        i = len(candles) - 1 if until is None else max(0, bisect.bisect_right(times, until) - 1)
        price = candles[i].close
        known = []
        for k, swings, _ in swings_known_over_time(candles, timeframe):  # the swings as known at candle i
            if k == i:
                known = list(swings)
                break
        zones = support_resistance(known, price, i, lookback={"1h": 24 * 60, "4h": 6 * 180}.get(timeframe, 365))
        below = sorted([z for z in zones if z.kind == "support"], key=lambda z: -z.high)[:3]
        above = sorted([z for z in zones if z.kind == "resistance"], key=lambda z: z.low)[:3]
        fib = fibonacci(known, i)
        shown = []
        for p in patterns:
            status = status_at(p, i)
            if status is None or (p.end_index is not None and p.end_index < i - 20):  # finished ones fade after 20 candles
                continue
            end = i if p.end_index is None or p.end_index > i else p.end_index
            shown.append({
                "kind": p.kind, "direction": p.direction if status != "candidate" or p.direction != "either" else "either",
                "status": status,
                "points": [{"time": _t(times[q.index]), "price": q.price} for q in p.points],
                "neckline": [{"time": _t(times[p.neckline[0]]), "price": p.line_at(p.neckline, p.neckline[0])},
                             {"time": _t(times[end]), "price": p.line_at(p.neckline, end)}],
                "lower": None if p.lower is None else [
                    {"time": _t(times[p.lower[0]]), "price": p.line_at(p.lower, p.lower[0])},
                    {"time": _t(times[end]), "price": p.line_at(p.lower, end)}],
                "target": p.target if status != "candidate" else None,
                "invalidation": p.invalidation or None,
                "label_time": _t(times[p.points[-1].index]),
            })
        a = adx_values[i]
        vol_rank = None
        if timeframe == "1d" and self.vol[i] is not None:
            past = sorted(v for v in self.vol[:i + 1] if v is not None)
            vol_rank = bisect.bisect_left(past, self.vol[i]) / len(past)
        end_time = times[i] + timedelta(hours={"1h": 1, "4h": 4, "1d": 24, "1w": 168}[timeframe])
        k_end = bisect.bisect_left(self.hour_times, end_time)
        window_hours = {"1h": 24 * 7, "4h": 24 * 30, "1d": 24 * 90, "1w": 24 * 365}[timeframe]
        profile = volume_profile(self.hourly[max(0, k_end - window_hours):k_end], bins=40)
        return {
            "timeframe": timeframe, "time": _t(times[i]), "price": price,
            "zones": [{"low": z.low, "high": z.high, "touches": z.touches, "kind": z.kind} for z in below + above],
            "fibonacci": None if fib is None else {
                "direction": fib.direction, "start": fib.start, "end": fib.end,
                "levels": [{"name": name, "price": level} for name, level in fib.all_levels()],
            },
            "patterns": shown[-12:],
            "pattern_track_record": track_record(patterns),
            "adx": None if a is None else round(a, 1),
            "regime": regime(a, vol_rank),
            "volume_profile": None if profile is None else {
                "poc": profile.poc, "vah": profile.vah, "val": profile.val, "days": window_hours // 24,
                "approximate": True,
            },
        }


class _Stitched:
    """Training-session forecasts up to `split`, live replay forecasts after it."""

    def __init__(self, saved: learner.Replay, live: learner.Replay, split: int):
        self.horizon = live.horizon
        self.forecasts = _Join(saved.forecasts, live.forecasts, split)
        self.experts = _Join(saved.experts, live.experts, split)
        self.weights = _Join(saved.weights, live.weights, split)
        self.outcomes = live.outcomes
        self.learning_curve = []
        self.config = live.config


class _Join:
    def __init__(self, first, second, split):
        self.first, self.second, self.split = first, second, split

    def __len__(self):
        return len(self.second)

    def __getitem__(self, i):
        if i < 0:
            i += len(self)
        return self.first[i] if i < self.split else self.second[i]
