import csv
from datetime import datetime, timezone
from pathlib import Path

from src.data_collection.market_data_repository import MarketDataRepository


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXCLUSIONS_FILE = (
    PROJECT_ROOT / "data" / "quality" / "confirmed_anomalies.csv"
)


def _utc_timestamp(value: str) -> str:
    timestamp = datetime.fromisoformat(
        value.strip().replace("Z", "+00:00")
    )

    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError(
            f"Exclusion timestamp must include a timezone: {value}"
        )

    return timestamp.astimezone(timezone.utc).isoformat()


def load_excluded_candle_keys(
    exclusions_file: str | Path = DEFAULT_EXCLUSIONS_FILE,
) -> set[tuple[str, str, str, str, str]]:

    exclusions_file = Path(exclusions_file)

    if not exclusions_file.is_file():
        raise FileNotFoundError(
            f"Exclusions file not found: {exclusions_file}"
        )

    required_columns = {
        "exchange",
        "symbol",
        "market",
        "timeframe",
        "timestamp",
        "analysis_action",
    }

    excluded_keys = set()

    with exclusions_file.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as file:

        reader = csv.DictReader(file)

        if not reader.fieldnames:
            raise ValueError("The exclusions CSV has no header row.")

        missing_columns = required_columns - set(reader.fieldnames)

        if missing_columns:
            raise ValueError(
                "Exclusions CSV is missing columns: "
                + ", ".join(sorted(missing_columns))
            )

        for line_number, row in enumerate(reader, start=2):

            action = (row["analysis_action"] or "").strip().lower()

            # Only actions beginning with "exclude" affect analysis.
            if not action.startswith("exclude"):
                continue

            try:
                key = (
                    row["exchange"].strip().lower(),
                    row["symbol"].strip(),
                    row["market"].strip(),
                    row["timeframe"].strip(),
                    _utc_timestamp(row["timestamp"]),
                )
            except (AttributeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid exclusion on CSV line {line_number}: {exc}"
                ) from exc

            excluded_keys.add(key)

    return excluded_keys


def get_clean_candles(
    repository: MarketDataRepository,
    symbol: str,
    market: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    exchange: str = "kraken",
    exclusions_file: str | Path = DEFAULT_EXCLUSIONS_FILE,
):
    """Return stored candles after applying the analysis exclusion list."""

    excluded_keys = load_excluded_candle_keys(exclusions_file)

    stored_candles = repository.get_candles(
        symbol=symbol,
        market=market,
        timeframe=timeframe,
        start=start,
        end=end,
        exchange=exchange,
    )

    clean_candles = []

    for candle in stored_candles:
        key = (
            candle.exchange.strip().lower(),
            candle.symbol,
            candle.market,
            timeframe,
            candle.timestamp.astimezone(timezone.utc).isoformat(),
        )

        if key not in excluded_keys:
            clean_candles.append(candle)

    return clean_candles