"""
Checks against luck (roadmap 9b). The more strategies are tried, the more
likely the best one only looks good by chance. Two standard checks:

Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014): the probability
that a strategy's true Sharpe ratio is above zero, after correcting for
(1) how many strategies were tried (N trials: the best of many random
strategies has a high Sharpe by luck alone), (2) how different their
Sharpe ratios were, and (3) non-normal returns (skew, fat tails).
Above 0.95 = unlikely to be luck.

Probability of Backtest Overfitting, PBO (Bailey, Borwein, Lopez de
Prado, Zhu, 2017), by combinatorially symmetric cross-validation: cut the
history into S blocks; for every way of choosing half of them, pick the
strategy with the best Sharpe on that half and see where it ranks on the
other half. PBO = how often the pick lands in the bottom half of the
other half. Around 0.5 or more = choosing the "best" is no better than a
coin flip; low (e.g. < 0.2) = the ranking carries over.

Everything is in daily (per-period) units unless named otherwise.
"""

import math
from itertools import combinations
from statistics import NormalDist

EULER_GAMMA = 0.5772156649015329
_NORMAL = NormalDist()


def moments(returns: list[float]) -> tuple[float, float, float, float]:
    """mean, standard deviation, skewness, kurtosis (normal = 3)."""
    n = len(returns)
    mean = sum(returns) / n
    variance = sum((r - mean) ** 2 for r in returns) / n
    std = math.sqrt(variance)
    if std == 0:
        return mean, 0.0, 0.0, 3.0
    skew = sum((r - mean) ** 3 for r in returns) / n / std ** 3
    kurt = sum((r - mean) ** 4 for r in returns) / n / std ** 4
    return mean, std, skew, kurt


def expected_max_sharpe(n_trials: int, sharpe_variance: float) -> float:
    """The Sharpe ratio the best of n_trials skill-less strategies would reach by luck."""
    if n_trials < 2 or sharpe_variance <= 0:
        return 0.0
    return math.sqrt(sharpe_variance) * (
        (1 - EULER_GAMMA) * _NORMAL.inv_cdf(1 - 1 / n_trials)
        + EULER_GAMMA * _NORMAL.inv_cdf(1 - 1 / (n_trials * math.e))
    )


def deflated_sharpe(returns: list[float], n_trials: int, sharpe_variance: float) -> float | None:
    """
    Probability (0..1) that the true Sharpe is above what luck explains.
    `sharpe_variance`: variance of the daily Sharpe ratios of all trials.
    """
    if len(returns) < 3:
        return None
    mean, std, skew, kurt = moments(returns)
    if std == 0:
        return None
    sr = mean / std
    benchmark = expected_max_sharpe(n_trials, sharpe_variance)
    denominator = 1 - skew * sr + (kurt - 1) / 4 * sr * sr
    if denominator <= 0:
        return None
    z = (sr - benchmark) * math.sqrt(len(returns) - 1) / math.sqrt(denominator)
    return _NORMAL.cdf(z)


def daily_sharpe(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    mean, std, _, _ = moments(returns)
    return 0.0 if std == 0 else mean / std


def probability_of_overfitting(matrix: list[list[float]], blocks: int = 16) -> float | None:
    """
    `matrix`: one row per day, one column per strategy (daily returns, same
    days for all). Returns PBO (0..1), or None with fewer than 2 strategies
    or too few days.
    """
    days = len(matrix)
    if not matrix or len(matrix[0]) < 2 or days < blocks * 5:
        return None
    k = len(matrix[0])
    blocks -= blocks % 2
    size = days // blocks

    # Per block and strategy: count, sum and sum of squares of the returns.
    stats = []
    for b in range(blocks):
        rows = matrix[b * size:(b + 1) * size if b < blocks - 1 else days]
        stats.append([
            (len(rows), sum(r[j] for r in rows), sum(r[j] * r[j] for r in rows))
            for j in range(k)
        ])

    def block_sharpes(chosen) -> list[float]:
        out = []
        for j in range(k):
            n = sum(stats[b][j][0] for b in chosen)
            s = sum(stats[b][j][1] for b in chosen)
            q = sum(stats[b][j][2] for b in chosen)
            mean = s / n
            variance = max(q / n - mean * mean, 0.0)
            out.append(mean / math.sqrt(variance) if variance > 0 else 0.0)
        return out

    below = total = 0
    everything = set(range(blocks))
    for chosen in combinations(range(blocks), blocks // 2):
        inside = block_sharpes(chosen)
        outside = block_sharpes(sorted(everything - set(chosen)))
        best = max(range(k), key=lambda j: inside[j])
        rank = 1 + sum(outside[j] < outside[best] for j in range(k))
        omega = rank / (k + 1)
        total += 1
        if omega <= 0.5:
            below += 1
    return below / total
