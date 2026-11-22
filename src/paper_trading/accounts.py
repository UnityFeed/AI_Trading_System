"""
Extra paper accounts that run side by side with the main one (owner,
22 Nov 2026: "option 2"): each follows one registered strategy with its own
virtual money, in its own SQLite file in database/, so the strategies can be
compared on the same days going forward (the only clean test left).

The main account (database/paper_trading.db, the ACTIVE strategy in the
registry) is unchanged. An extra account is created on its first run and
acts from its fixed start day; once created it is never switched or reset
automatically (switching needs an explicit reset, as for the main account).
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.paper_trading.store import PROJECT_ROOT, PaperTradingStore
from src.strategies.registry import get_strategy


@dataclass(frozen=True)
class ExtraAccount:
    id: str
    strategy_id: str
    filename: str  # in database/
    starting_cash: float
    start: datetime  # first daily candle the account acts on

    @property
    def definition(self):
        return get_strategy(self.strategy_id)


START_2026_11_22 = datetime(2026, 11, 22, tzinfo=timezone.utc)

EXTRA_ACCOUNTS: tuple[ExtraAccount, ...] = (
    ExtraAccount("lab", "lab-weekly-momentum-core50-1d", "paper_lab.db", 3_500.0, START_2026_11_22),
    ExtraAccount("core50", "core50-trend-macd-1d", "paper_core50.db", 3_500.0, START_2026_11_22),
)


def open_extra_accounts(folder: Path | None = None) -> list[tuple[ExtraAccount, PaperTradingStore]]:
    folder = folder or PROJECT_ROOT / "database"
    return [(a, PaperTradingStore(folder / a.filename)) for a in EXTRA_ACCOUNTS]
