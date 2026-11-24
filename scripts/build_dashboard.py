"""
Build the dashboard page from the database (read-only) and the paper
account, and write it to reports/dashboard.html.

Usage:
    python -m scripts.build_dashboard           (build)
    python -m scripts.build_dashboard --open    (build and open in the browser)
"""

import argparse
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from src.analysis.primary_history import get_trading_history
from src.app.routine import HISTORY_START
from src.data_collection.external_data import ExternalDataStore
from src.data_collection.market_data_repository import MarketDataRepository
from src.paper_trading.store import PaperTradingStore
from src.reporting.dashboard import gather, render
from src.strategies.registry import active_strategy


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT_ROOT / "reports" / "dashboard.html"


def build(
    repository: MarketDataRepository | None = None,
    store: PaperTradingStore | None = None,
    history=None,
    output: Path = OUTPUT,
) -> Path:
    repository = repository or MarketDataRepository()
    store = store or PaperTradingStore()
    if history is None:
        end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        history = get_trading_history(repository=repository, start=HISTORY_START, end=end)

    output.parent.mkdir(parents=True, exist_ok=True)
    exposure = active_strategy().exposure
    # External data is only read when the active strategy uses it.
    external = ExternalDataStore().load_all() if exposure and exposure.needs_external else {}
    output.write_text(render(gather(repository, history, store, external=external)), encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--open", action="store_true", help="open the page in your browser")
    parser.add_argument("--db", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--paper-db", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    path = build(
        MarketDataRepository(args.db) if args.db else None,
        PaperTradingStore(args.paper_db) if args.paper_db else None,
    )
    print(f"Dashboard written to {path}")
    if args.open:
        webbrowser.open(path.as_uri())


if __name__ == "__main__":
    main()
