"""
Automatic database backups (upgrade plan A5).

`backup_database` copies a SQLite file with SQLite's own online backup (safe
while the app has the file open) to `database/backups/<name>_<YYYY-MM-DD>.db`,
at most once per UTC day, and keeps the newest `keep` copies of that file.
It only ever writes into the backup folder; the database itself is only read.
"""

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


def backup_database(db_path: str | Path, folder: str | Path | None = None, keep: int = 7,
                    today: datetime | None = None) -> Path | None:
    """Back up `db_path` once per day. Returns the new backup's path, or None if today's exists or no database."""
    db_path = Path(db_path)
    if not db_path.exists():
        return None
    folder = Path(folder) if folder else db_path.parent / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    day = (today or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    target = folder / f"{db_path.stem}_{day}.db"
    if target.exists():
        return None
    partial = target.with_suffix(".partial")
    with closing(sqlite3.connect(db_path)) as source, closing(sqlite3.connect(partial)) as copy:
        source.backup(copy)
    partial.replace(target)
    old = sorted(folder.glob(f"{db_path.stem}_????-??-??.db"))
    for path in old[:-keep]:
        path.unlink()
    return target
