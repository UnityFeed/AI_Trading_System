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
- 22 Nov 2026: branch created; blueprint saved; phase 1 core built
  (`structure.py`: confirmed pivots, swing labels, trend state, BOS/CHoCH,
  sweeps; tests; `scripts/run_market_structure.py`). Next: run it on the real
  DB, then structure features into the research tools (end of phase 1),
  then phase 2.
