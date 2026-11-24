"""
Machine-learning research (see src/research/models.py): can a model,
trained only on earlier years, see a rise or a low coming better than the
simple base rate, and does trading on it beat holding after fees?

For each question ("up30": higher in 30 days; "low20": a swing low within
20 days) and each model (logistic regression, nearest-neighbour analog):
- walk-forward predictions for every day from 2017 on
- Brier score and log loss against the base rate, Brier skill, calibration
- trading test (up30 only): hold when the probability is high, sell when it
  is low (with a hysteresis gap), all-in or with a 50% core; BTC compared
  with holding over the predicted years

Every prediction is written to data/backtests/ml_predictions.csv with its
date (never rewritten: each run writes a new file stamped with the run
time). The run is logged in the trials ledger. The database is only read.

Usage:
    python -m scripts.run_ml_research
"""

import argparse
import csv
import os
import time
from functools import partial
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from scripts.run_strategy_lab import load_premium
from src.app.routine import load_history
from src.backtesting.engine import CostSettings, buy_and_hold
from src.backtesting.exposure import TREND_MACD, _rules_state, run_exposure_backtest
from src.backtesting.ledger import log_trials
from src.backtesting.market import build_market
from src.data_collection.external_data import ExternalDataStore
from src.data_collection.market_data_repository import MarketDataRepository
from src.research import models
from src.research.features import build_frame
from src.research.turning_points import zigzag


OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "backtests"
FIRST_YEAR = 2017
RULES = (  # (label, sell below, buy above, core)
    ("all-in above 0.55, out below 0.45", 0.45, 0.55, 0.0),
    ("all-in above 0.60, out below 0.40", 0.40, 0.60, 0.0),
    ("50% core, rest above 0.55 / below 0.45", 0.45, 0.55, 0.5),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fee", type=float, default=CostSettings().fee_pct)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--no-log", action="store_true")
    parser.add_argument("--db", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--external-db", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    started = time.time()
    costs = CostSettings(fee_pct=args.fee)
    repository = MarketDataRepository(args.db) if args.db else MarketDataRepository()
    external = (ExternalDataStore(args.external_db) if args.external_db else ExternalDataStore()).load_all()
    history = load_history(repository)
    market = build_market(history, "1d", external=external)
    frame = build_frame(market, load_premium(repository, history))
    candles = market.candles
    turns = zigzag([c.close for c in candles], [c.timestamp for c in candles], 0.20)
    # low20 is learned from the lows confirmed before each test year (no leak),
    # and scored against the lows known now.
    low_now = models.labels_low(frame, turns, 20)
    questions = {
        "up30": (models.labels_up(frame, 30), 30, None),
        "low20": (partial(models.labels_low_known_before, frame), 20, low_now),
    }

    print("MACHINE-LEARNING RESEARCH (walk-forward from 2017, each year learned only from earlier years)")
    print("=" * 92)
    print(f"{len(frame.ranks)} features as percentile ranks; fee {costs.fee_pct}% + slippage {costs.slippage_pct}%")
    print()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"ml_predictions_{stamp}.csv"
    all_predictions = {}
    with ProcessPoolExecutor(args.workers or os.cpu_count() or 1) as pool:
        for question, (labels, horizon, outcomes) in questions.items():
            for model in ("logistic", "analog"):
                t = time.time()
                preds = models.walk_forward_predictions(frame, labels, model, horizon, FIRST_YEAR, pool, outcomes)
                all_predictions[(question, model)] = preds
                first = datetime(FIRST_YEAR, 1, 1, tzinfo=timezone.utc)
                scored = outcomes if outcomes is not None else labels
                known_before = [y for i, y in enumerate(scored) if y is not None and candles[i].timestamp < first]
                base = sum(known_before) / len(known_before) if known_before else 0.5
                s = models.score(preds, base)
                print(f"{question} / {model}  ({len(preds):,} days predicted, {time.time() - t:.0f} s)")
                if s is None:
                    print("  no outcomes known yet")
                    continue
                print(f"  base rate {s.base_rate:.2f}   Brier {s.brier:.4f} vs base {s.brier_base:.4f}"
                      f"   skill {s.skill:+.3f}   log loss {s.log_loss:.4f} vs {s.log_loss_base:.4f}")
                print("  calibration (predicted -> happened, days): " + ", ".join(
                    f"{a:.2f}->{b:.2f} ({n})" for a, b, n in s.calibration))
    print("  skill > 0 means better than always predicting the base rate; around 0 = no real foresight")
    print()

    with out_path.open("w", newline="", encoding="utf-8") as handle:
        w = csv.writer(handle)
        w.writerow(["question", "model", "candle_time", "probability", "outcome"])
        for (question, model), preds in all_predictions.items():
            for p in preds:
                w.writerow([question, model, p.time.isoformat(), round(p.probability, 5),
                            "" if p.outcome is None else p.outcome])

    print("TRADING ON THE 'UP IN 30 DAYS' PROBABILITY (from 2017, vs holding over the same days)")
    window = range(next(i for i, c in enumerate(candles) if c.timestamp.year >= FIRST_YEAR), len(candles))
    held = buy_and_hold(market, window, costs)
    print(f"  buy and hold: {held.total_return_pct:+,.0f}%, worst drop {held.max_drawdown_pct:.0f}%")
    ledger_rows = []
    for model in ("logistic", "analog"):
        preds = all_predictions[("up30", model)]
        for label, low, high, core in RULES:
            targets = models.exposure_from_probability(preds, len(candles), low, high, core)
            result = run_exposure_backtest(market, window, targets, band=0.05, costs=costs)
            ratio = result.final_equity / held.final_equity
            print(f"  {model:<9} {label:<40} {result.total_return_pct:+9,.0f}%  drop {result.max_drawdown_pct:3.0f}%"
                  f"  BTC vs holding x{ratio:.2f}  ({len(result.rebalances)} trades)")
            ledger_rows.append({"script": "run_ml_research", "strategy": f"{model}: {label}", "timeframe": "1d",
                                "fee_pct": costs.fee_pct, "btc_vs_hold": round(ratio, 3),
                                "total_return_pct": round(result.total_return_pct, 2),
                                "max_drawdown_pct": round(result.max_drawdown_pct, 2),
                                "note": f"walk-forward {FIRST_YEAR}-now"})
    print()

    print("AI EARLY-LOW SIGNAL INSIDE '50% CORE + DAILY TREND + MACD' (from 2017)")
    print("  the 50% overlay is ALSO switched on when the analog model's 'low within 20 days'")
    print("  probability reaches the threshold, and stays on for the given days (or longer while")
    print("  the trend rule holds): buying earlier than the trend rule alone")
    trend = _rules_state(market, TREND_MACD)
    low_preds = {p.index: p.probability for p in all_predictions[("low20", "analog")]}
    reference = run_exposure_backtest(market, window, [0.5 + 0.5 * t for t in trend], band=0.05, costs=costs)
    print(f"  {'reference (trend rule only)':<44} BTC vs holding x{reference.final_equity / held.final_equity:.2f}"
          f"  drop {reference.max_drawdown_pct:.0f}%  ({len(reference.rebalances)} trades)")
    for threshold in (0.30, 0.35, 0.40):
        for keep in (20, 40):
            targets, early = [], 0
            for i in range(len(candles)):
                early = keep if low_preds.get(i, 0.0) >= threshold else max(0, early - 1)
                targets.append(0.5 + 0.5 * (1.0 if trend[i] == 1.0 or early > 0 else 0.0))
            result = run_exposure_backtest(market, window, targets, band=0.05, costs=costs)
            ratio = result.final_equity / held.final_equity
            label = f"low signal >= {threshold:.2f}, keep {keep} days"
            print(f"  {label:<44} BTC vs holding x{ratio:.2f}  drop {result.max_drawdown_pct:.0f}%"
                  f"  ({len(result.rebalances)} trades)")
            ledger_rows.append({"script": "run_ml_research", "strategy": f"core50 trend-macd + {label}",
                                "timeframe": "1d", "fee_pct": costs.fee_pct, "btc_vs_hold": round(ratio, 3),
                                "note": f"walk-forward {FIRST_YEAR}-now"})
    print("  6 variants tried: count the best one as the best of 6 (luck), not as a fixed rule")
    print()
    if not args.no_log:
        log_trials(ledger_rows)
        print("Logged in the trials ledger.")
    print(f"Predictions saved: {out_path}")
    print(f"Done in {time.time() - started:.0f} s. The database was only read.")


if __name__ == "__main__":
    main()
