# Predictive engine: build plan (branch `predictive-engine`)

Owner's goal (22 Nov 2026): a tool that draws the most probable future
scenarios on the chart, with their chances, targets and invalidation levels,
that the owner can follow next to live charts to see whether it works.

Source: `2026-11-22_blueprint_predictive_market_structure.md` (owner's
blueprint, kept unchanged). This plan is the slimmed, gated version agreed
in the review: each phase must show measurable value before the next one
adds complexity.

## Ground rules (from the blueprint and CLAUDE.md)
- Causal only: every value at candle i uses candles up to and including i.
  A swing point counts only from the candle that CONFIRMS it. Every detector
  is tested with the truncation test (result on a shortened history = the same
  part of the result on the full history).
- Forecasts are stored when made and never rewritten (own database file,
  `database/predictions.db`; never the paper-trading or market files).
- Probabilities are scored (Brier score, log loss, calibration) against the
  base rate, year by year (walk-forward), and always shown with the number of
  past cases behind them.
- The engine never trades. Strategies may later read its output.
- Standard library only (as the rest of the project), unless the owner
  approves a library.

## Phases
| # | What | Output | Gate to continue |
|---|---|---|---|
| 1 | Market structure: confirmed swings, HH/HL/LH/LL, trend state, break of structure (BOS), change of character (CHoCH), liquidity sweeps, on 1d/4h/1w | `src/predictive_engine/structure.py`, `scripts/run_market_structure.py` | tests incl. truncation; structure events as research features add lift or skill in `run_ml_research` / the lab |
| 2 | Scenario outcomes with exact definitions: within H days, does the price reach +X% first (bullish), -Y% first (bearish), or neither (range)? X and Y scale with volatility (ATR). | outcome labels, base rates | labels tested; base rates per regime |
| 3 | Scenario probabilities: analog (nearest past situations) + logistic models on features incl. structure; walk-forward; calibrated; sample size per forecast | daily 3-way probabilities | Brier skill > 0 on unseen years |
| 4 | Forecast log: one immutable forecast per day (time, inputs, model version, probabilities, targets, invalidation), scored later when the outcome is known | `database/predictions.db`, daily routine step | runs daily; scores accumulate |
| 5 | Chart: scenario paths drawn from the last candle: green/red/grey dashed paths to target zones, invalidation lines, probabilities and case counts in a panel; past forecasts can be replayed | Chart page layer + API | readable, no JS errors, phone width |
| 6 | Classic patterns (double top/bottom, triangles, head and shoulders) as extra features, kept only if they add skill | pattern detectors with life-cycle states | measurable skill gain |
| 7 | Fibonacci / Elliott Wave: last, only if 1-6 show value | | |

End state = phases 1-5 working: the chart shows the current structure, the
2-3 most probable scenarios with their probability, number of similar past
cases, target zone and invalidation level, updated every day, and every
forecast is stored and scored so the owner can see whether it works.

## Status
- 23 Nov 2026 (later), phases 6-7 + the learning engine BUILT (test DB; owner
  to confirm on the real DB with `run_learning_replay`):
  - Chart tools (`levels.py`, `volume_profile.py`): support/resistance zones
    (confirmed swings within 1.5%, touches = strength), automatic Fibonacci of
    the last confirmed swing, ADX regime, volume profile (POC / value area,
    estimated from hourly candles). Toggles "Support/resistance + Fibonacci",
    "Volume profile"; regime in the tools strip.
  - Patterns (`patterns.py`): double top/bottom, (inverse) head and
    shoulders, ascending/descending/symmetrical triangles from swings known at
    the time; life cycle candidate -> confirmed -> hit/failed/expired; patterns
    the price had already left when they became known are skipped. Track record
    (test DB): inverse H&S 68% hit, ascending triangle 56%, double bottom 48%,
    H&S 47%, double top 42%, descending triangle 43%, symmetrical triangle 17%.
    Toggle "Patterns" draws outline, neckline, target and status.
  - Learning engine (`learner.py`, the owner's "AI that trains on the chart"):
    replays every day from the first candle, learns from each outcome when it
    becomes known, predicts bull/bear/range for 7/14/30 days from 51 features
    (research features + structure + S/R distance + Fibonacci position + ADX +
    patterns); experts base / structure / regime / learned (online softmax),
    blended with learned Hedge weights (fixed share 5%, slow forgetting).
    Settings changed ONCE after a first run (learned model overconfident,
    weights collapsing): learning rate 0.05 -> 0.01, L2 1e-4 -> 1e-3, Hedge
    eta 0.5 -> 0.1, forgetting 0.995 -> 0.999, learned model pulled to the base
    rate while it has few examples. Result 2017-now: 7 days +1.1% vs base
    (top scenario right 61%), 14 days +0.2%, 30 days -0.5%; uneven per year.
    A look-ahead in the S/R / Fibonacci inputs (final swing list) was found by
    the truncation test and fixed (swings as known each day).
  - Replay on the chart (`service.py`, `/api/scenarios?h=&date=`,
    `/api/tools?tf=&until=`): pick a date, step, play, "show what happened",
    back to now; the chart hides everything after the replay day and shows the
    AI's forecast, its trust in each expert and its score up to that day.
    Live forecasts (no date) are logged per horizon in `predictions.db`.
  - Report: `python -m scripts.run_learning_replay`.
- 23 Nov 2026, phases 3-5 BUILT (test DB; owner to confirm on the real DB):
  - Phase 3 `scenarios.py` + `engine.py` (MODEL = analog, horizon 30 days,
    barriers 1x typical move): models base / structure / analog, walk-forward
    2017-now, 3,581 days. Skill vs the base rate: analog Brier +0.7%
    (log loss +0.1%), structure -0.4%: direction 30 days ahead is barely
    predictable; the range probability is the best-calibrated part (analog
    said 0.54 -> 0.58 happened, 0.63 -> 0.68). Gate "Brier skill > 0": only
    just passed; the chart shows the skill next to every forecast.
  - Phase 4 `forecast_log.py`: `database/predictions.db`, one forecast per
    daily candle and model version, never overwritten; outcomes added when
    decided; track record (scored count, Brier, log loss, top-scenario hit
    rate). Recorded by the app whenever the scenarios are computed.
  - Phase 5 chart: toggle "Scenarios (next 30 days)": strip with the three
    chances, targets, typical days, cases, model skill and track record;
    on 1d dashed paths from the last close to the bull/bear targets and a
    dotted range band, with 35 empty future days; target lines on other
    timeframes. API `/api/scenarios`.
  - Next ideas (owner to choose): historical replay of past forecasts on the
    chart; improve the model (direction is near-random; range/volatility is
    more predictable, so a "big move vs range" view may be more useful);
    shorter horizons (7/14 days) for watching live charts.
- 23 Nov 2026 (test DB; owner to confirm on the real DB):
  - Structure on the chart: toggle "Structure" (swing labels HH/HL/LH/LL,
    BOS/CHoCH arrows, dotted last swing high/low lines, trend in the status
    strip) on 1h/4h/1d/1w, from `/api/structure`.
  - Phase 1 gate: structure added to the research features (daily trend,
    weekly trend from completed weeks, distance to last swing high/low, days
    since CHoCH) and lab blocks. Turning points: lift ~2.6 before lows (about
    the same as existing distance-from-average features). Lab (255,597
    combinations): structure filters dominate the 2013-21 ranking but do NOT
    carry over (walk-forward family x0.85 vs x1.54 without them; top 25 ahead
    on 2022-now 10/25); exit "weekly structure turns down" holds up (70% of its
    combinations ahead on 2022-now). Verdict: no gain for trading strategies;
    kept as context for scenarios, where it clearly shifts the odds.
  - Phase 2 built: `outcomes.py` (bull/bear/range over 30 days, barriers at
    1x volatility-scaled typical move, median 16%), `run_scenario_outcomes`.
    Base rates all days: bull 32.5%, bear 18.5%, range 48.9%. Daily+weekly
    up: bull 40.0% / bear 14.8%; both down: bull 25.8% / bear 15.6% / range
    58.6% (today's situation). Next: phase 3 (models must beat these rates).
- 22 Nov 2026: branch created; blueprint saved; phase 1 core built
  (`structure.py`: confirmed pivots, swing labels, trend state, BOS/CHoCH,
  sweeps; tests; `scripts/run_market_structure.py`). Next: run it on the real
  DB, then structure features into the research tools (end of phase 1),
  then phase 2.
