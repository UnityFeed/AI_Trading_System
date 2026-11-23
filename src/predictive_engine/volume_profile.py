"""
Volume profile (predictive engine): how much was traded at each price over a
period, estimated from HOURLY candles: each hour's volume is spread evenly
over its low-high range. This is an approximation, not a true traded-volume
profile (that needs every trade; the order-flow recorder collects those from
now on).

  POC  point of control: the price bin with the most volume
  VAH / VAL  value area high / low: the smallest range around the POC that
       holds `value_area` (70%) of the volume
"""

from dataclasses import dataclass

from src.data_collection.market_data import MarketData


@dataclass(frozen=True)
class VolumeProfile:
    bins: list[tuple[float, float, float]]  # (low, high, volume)
    poc: float
    vah: float
    val: float
    approximate: bool = True


def volume_profile(hours: list[MarketData], bins: int = 60, value_area: float = 0.70) -> VolumeProfile | None:
    if not hours:
        return None
    low = min(h.low for h in hours)
    high = max(h.high for h in hours)
    if high <= low:
        return None
    step = (high - low) / bins
    volume = [0.0] * bins
    for h in hours:
        if h.volume <= 0:
            continue
        if h.high <= h.low:
            volume[min(int((h.close - low) / step), bins - 1)] += h.volume
            continue
        first = min(int((h.low - low) / step), bins - 1)
        last = min(int((h.high - low) / step), bins - 1)
        span = h.high - h.low
        for b in range(first, last + 1):
            b_low, b_high = low + b * step, low + (b + 1) * step
            overlap = min(b_high, h.high) - max(b_low, h.low)
            if overlap > 0:
                volume[b] += h.volume * overlap / span
    total = sum(volume)
    if total <= 0:
        return None
    poc_bin = max(range(bins), key=lambda b: volume[b])
    lo = hi = poc_bin
    covered = volume[poc_bin]
    while covered < value_area * total and (lo > 0 or hi < bins - 1):
        below = volume[lo - 1] if lo > 0 else -1.0
        above = volume[hi + 1] if hi < bins - 1 else -1.0
        if above >= below:
            hi += 1
            covered += volume[hi]
        else:
            lo -= 1
            covered += volume[lo]
    return VolumeProfile(
        [(low + b * step, low + (b + 1) * step, volume[b]) for b in range(bins)],
        poc=low + (poc_bin + 0.5) * step, vah=low + (hi + 1) * step, val=low + lo * step,
    )
