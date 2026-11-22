"""
Trials ledger (roadmap 9b): every backtest trial is written down, with its
settings and results, in data/backtests/trials.csv (on the owner's PC,
gitignored). Append-only: rows are never changed or removed.

Why: the more strategies we try, the higher the chance that the best one
only looks good by luck. The Deflated Sharpe Ratio corrects for this, but
only if we know HOW MANY trials were made and how their results varied.
This file is that memory. Scripts that try many combinations at once log
one summary row with the number of combinations in `n_trials`.
"""

import csv
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = PROJECT_ROOT / "data" / "backtests" / "trials.csv"

FIELDS = (
    "logged_at", "script", "strategy", "timeframe", "rules", "fee_pct", "slippage_pct",
    "start", "end", "n_trials", "total_return_pct", "cagr_pct", "max_drawdown_pct",
    "daily_sharpe", "sharpe", "btc_vs_hold", "note",
)


def log_trials(rows: list[dict], path: Path = DEFAULT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        if new_file:
            writer.writeheader()
        for row in rows:
            writer.writerow({"logged_at": stamp, "n_trials": 1, **row})


def read_trials(path: Path = DEFAULT_PATH) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def trial_count(rows: list[dict]) -> int:
    return sum(int(row.get("n_trials") or 1) for row in rows)


def daily_sharpes(rows: list[dict]) -> list[float]:
    """Daily Sharpe ratios of the trials that recorded one."""
    out = []
    for row in rows:
        try:
            out.append(float(row["daily_sharpe"]))
        except (KeyError, TypeError, ValueError):
            continue
    return out
