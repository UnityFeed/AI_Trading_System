
import json
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class KrakenTradesProvider:
    """
    Retrieves historical trades from Kraken.

    fetch_trades returns tuples (timestamp, price, volume);
    fetch_trades_with_side adds the side of the taker (the one who traded
    at once against a waiting order): "b" = a buyer lifted an ask,
    "s" = a seller hit a bid. Buy minus sell volume is the order flow
    (CVD, cumulative volume delta).
    """

    exchange = "kraken"

    BASE_URL = "https://api.kraken.com/0/public/Trades"
    PAIR = "XBTUSD"

    def fetch_trades(
        self,
        start: datetime,
        end: datetime,
    ) -> list[tuple[datetime, float, float]]:
        return [
            (timestamp, price, volume)
            for timestamp, price, volume, _ in self.fetch_trades_with_side(start, end)
        ]

    def fetch_trades_with_side(
        self,
        start: datetime,
        end: datetime,
    ) -> list[tuple[datetime, float, float, str]]:

        if (
            start.tzinfo is None
            or start.utcoffset() is None
            or end.tzinfo is None
            or end.utcoffset() is None
        ):
            raise ValueError("Start and end must be timezone-aware.")

        start = start.astimezone(timezone.utc)
        end = end.astimezone(timezone.utc)

        if start >= end:
            raise ValueError("Start must be earlier than end.")

        # Kraken's pagination cursor uses nanoseconds.
        since = str(int(start.timestamp()) * 1_000_000_000 - 1)

        trades = []
        reached_end = False

        while not reached_end:

            params = {
                "pair": self.PAIR,
                "since": since,
            }

            request = Request(
                f"{self.BASE_URL}?{urlencode(params)}",
                headers={
                    "User-Agent": "AI-Trading-System/1.0"
                },
            )

            response_data = None

            for attempt in range(5):
                try:
                    with urlopen(request, timeout=30) as response:
                        response_data = json.loads(
                            response.read().decode("utf-8")
                        )

                    if response_data.get("error"):
                        raise RuntimeError(
                            f"Kraken API error: {response_data['error']}"
                        )

                    break

                except Exception:
                    if attempt == 4:
                        raise

                    time.sleep(3 * (attempt + 1))

            result = response_data["result"]

            pair_keys = [
                key for key in result
                if key != "last"
            ]

            if len(pair_keys) != 1:
                raise RuntimeError(
                    "Unexpected Kraken Trades response."
                )

            raw_trades = result[pair_keys[0]]
            next_since = str(result["last"])

            if not raw_trades:
                break

            for row in raw_trades:

                trade_timestamp = Decimal(row[2])

                whole_seconds = int(trade_timestamp)
                microseconds = int(
                    (trade_timestamp - Decimal(whole_seconds))
                    * Decimal(1_000_000)
                )

                timestamp = (
                    datetime.fromtimestamp(
                        whole_seconds,
                        tz=timezone.utc,
                    )
                    + timedelta(microseconds=microseconds)
                )

                if timestamp < start:
                    continue

                if timestamp >= end:
                    reached_end = True
                    break

                trades.append((
                    timestamp,
                    float(row[0]),
                    float(row[1]),
                    str(row[3]),
                ))

            if reached_end:
                break

            if int(next_since) <= int(since):
                raise RuntimeError(
                    "Kraken pagination cursor did not advance."
                )

            since = next_since

        return trades
