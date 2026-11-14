from dataclasses import dataclass
from datetime import datetime, timedelta

from src.analysis.indicators import SimpleMovingAverage


@dataclass(frozen=True)
class SmaCrossoverSignal:
    exchange: str
    symbol: str
    candle_timestamp: datetime
    action: str
    fast_sma: float
    slow_sma: float


def generate_sma_crossover_signals(
    fast_averages: list[SimpleMovingAverage],
    slow_averages: list[SimpleMovingAverage],
) -> list[SmaCrossoverSignal]:
    """
    Generate long-only SMA crossover signals.

    An upward cross emits ENTER_LONG; a downward cross emits EXIT_LONG.
    Each signal uses completed-candle SMA values. A later backtest should
    simulate execution no earlier than the next candle.
    """

    if not fast_averages or not slow_averages:
        return []

    fast_period = fast_averages[0].period_hours
    slow_period = slow_averages[0].period_hours

    if fast_period >= slow_period:
        raise ValueError(
            "The fast SMA period must be shorter than the slow SMA period."
        )

    first = fast_averages[0]

    for average in fast_averages + slow_averages:
        if average.exchange.lower() != first.exchange.lower():
            raise ValueError(
                "Generate signals for one exchange at a time."
            )

        if average.symbol != first.symbol:
            raise ValueError(
                "Generate signals for one symbol at a time."
            )

    if any(
        average.period_hours != fast_period
        for average in fast_averages
    ):
        raise ValueError("Fast SMA values must use one period.")

    if any(
        average.period_hours != slow_period
        for average in slow_averages
    ):
        raise ValueError("Slow SMA values must use one period.")

    fast_by_time = {
        average.timestamp: average
        for average in fast_averages
    }
    slow_by_time = {
        average.timestamp: average
        for average in slow_averages
    }

    if len(fast_by_time) != len(fast_averages):
        raise ValueError("Duplicate timestamps found in fast SMA values.")

    if len(slow_by_time) != len(slow_averages):
        raise ValueError("Duplicate timestamps found in slow SMA values.")

    common_times = sorted(
        set(fast_by_time) & set(slow_by_time)
    )

    signals = []
    previous_time = None
    previous_fast = None
    previous_slow = None
    in_position = False

    for timestamp in common_times:

        fast_value = fast_by_time[timestamp].value
        slow_value = slow_by_time[timestamp].value

        if previous_time is not None:
            elapsed = timestamp - previous_time

            if elapsed != timedelta(hours=1):
                # Do not infer a crossover across a missing hour.
                previous_fast = None
                previous_slow = None

        if previous_fast is not None and previous_slow is not None:

            crossed_up = (
                previous_fast <= previous_slow
                and fast_value > slow_value
            )

            crossed_down = (
                previous_fast >= previous_slow
                and fast_value < slow_value
            )

            if crossed_up and not in_position:
                signals.append(
                    SmaCrossoverSignal(
                        exchange=first.exchange,
                        symbol=first.symbol,
                        candle_timestamp=timestamp,
                        action="ENTER_LONG",
                        fast_sma=fast_value,
                        slow_sma=slow_value,
                    )
                )
                in_position = True

            elif crossed_down and in_position:
                signals.append(
                    SmaCrossoverSignal(
                        exchange=first.exchange,
                        symbol=first.symbol,
                        candle_timestamp=timestamp,
                        action="EXIT_LONG",
                        fast_sma=fast_value,
                        slow_sma=slow_value,
                    )
                )
                in_position = False

        previous_time = timestamp
        previous_fast = fast_value
        previous_slow = slow_value

    return signals