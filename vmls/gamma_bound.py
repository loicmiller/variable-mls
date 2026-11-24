"""gamma(s, w): the hashrate fluctuation as the definition asks it, a worst case, with exact confidence intervals.

The (gamma, s)-respecting property bounds the ratio of the honest hashrate between any two rounds at most s apart, but a
chain yields about one block every 33 rounds, so it cannot be tested round by round. gamma(s, w) is the largest ratio
between the mean hashrates of two disjoint sub-windows of w seconds within a window of s rounds. Blocks found in a
sub-window are Poisson, of mean proportional to h * E, where E is the integral of 1/D over the sub-window (its
exposure); given the blocks of both sub-windows, those of the first are binomial, which gives an exact interval on the
ratio. A Bonferroni correction over all the pairs of a period turns these into an interval on gamma(s, w), and a ratio
of means never exceeds the ratio of extremes, so the lower bound also bounds the gamma of the definition.
"""

import numpy as np
import pandas as pd
from scipy.special import betaincinv

from vmls.chain import GENESIS_TARGET, bits_to_target
from vmls.gamma import ALPHA_INNER, K_SMOOTH, ROUND_SECONDS, smoothed_rounds

DAY = 86400
CELLS_PER_W = 4  # Positions of the sub-windows, per sub-window.
ALPHA = 0.05
EPOCH = 2016
TARGET_SPACING = 600


class Chain:
    """What the measure needs from a chain: when blocks were found, and the integral of 1/D over time.

    Args:
        times: Time of each block, in seconds.
        change_times: Times from which each difficulty applies, the first one being the start of the chain.
        difficulties: Difficulty applying from each of these times.
    """

    def __init__(self, times: np.ndarray, change_times: np.ndarray, difficulties: np.ndarray):
        """Sorts the block times and sums the difficulty from the end of the chain."""
        self.times = np.sort(times)
        self.start, self.end = float(self.times[0]), float(self.times[-1])
        self.knots = np.append(change_times, max(self.end, change_times[-1]) + 1.0)
        # Summed from the end: D grows by 14 orders of magnitude, so a sum from 2009 could not hold a day of 2026.
        self.exposure_at_knots = -np.concatenate((np.cumsum((np.diff(self.knots) / difficulties)[::-1])[::-1], [0.0]))

    def exposure(self, t: np.ndarray) -> np.ndarray:
        """Integral of 1/D over time, up to a constant: only differences mean something.

        Args:
            t: The times.

        Returns:
            The exposure at these times.
        """
        return np.interp(t, self.knots, self.exposure_at_knots)

    def count(self, t: np.ndarray) -> np.ndarray:
        """Number of blocks found before each time.

        Args:
            t: The times.

        Returns:
            The counts.
        """
        return np.searchsorted(self.times, t, side='left')


def chain_from_headers(headers: list[dict], median_time_past: bool = False) -> tuple[Chain, np.ndarray]:
    """The chain of exported headers, without the genesis block and the gap after it.

    Args:
        headers: The headers, one per height.
        median_time_past: Whether to use the median of the last 11 timestamps instead of the miner's timestamp.

    Returns:
        The chain, and the time of each block in height order.
    """
    time = pd.Series([header['time'] for header in headers], dtype=float)
    if median_time_past:
        time = time.rolling(11, min_periods=1).median()
    time = time.to_numpy()
    difficulty = np.array([GENESIS_TARGET / bits_to_target(header['bits']) for header in headers])
    # A difficulty applies from the moment the block before it was found; change points must be monotonic.
    monotonic = np.maximum.accumulate(time)
    changes = np.flatnonzero(np.diff(difficulty) != 0) + 1
    changes = changes[changes > 1]
    change_times = np.concatenate(([monotonic[1]], monotonic[changes - 1]))
    values = np.concatenate(([difficulty[1]], difficulty[changes]))
    return Chain(time[1:], change_times, values), time


def cells(chain: Chain, w_seconds: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Blocks and exposure of the sub-windows of w seconds, at every position of the grid.

    Args:
        chain: The chain.
        w_seconds: Length of a sub-window.

    Returns:
        The start of each sub-window, its number of blocks and its exposure.
    """
    step = w_seconds / CELLS_PER_W
    positions = chain.start + step * np.arange(int((chain.end - chain.start - w_seconds) / step) + 1)
    blocks = chain.count(positions + w_seconds) - chain.count(positions)
    return positions, blocks, chain.exposure(positions + w_seconds) - chain.exposure(positions)


def ratio_bounds(n_a: np.ndarray, n_b: np.ndarray, e_a: np.ndarray, e_b: np.ndarray,
                 alpha: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Exact interval on h_a / h_b: given n_a + n_b, n_a is binomial of parameter h_a e_a / (h_a e_a + h_b e_b).

    Args:
        n_a: Blocks of the first sub-windows.
        n_b: Blocks of the second sub-windows.
        e_a: Exposure of the first sub-windows.
        e_b: Exposure of the second sub-windows.
        alpha: Error of each interval, shared between its two sides.

    Returns:
        The estimate, the lower bound and the upper bound of each ratio.
    """
    low, high = np.zeros(len(n_a)), np.ones(len(n_a))
    some_a, some_b = n_a > 0, n_b > 0
    low[some_a] = betaincinv(n_a[some_a], n_b[some_a] + 1.0, alpha / 2)
    high[some_b] = betaincinv(n_a[some_b] + 1.0, n_b[some_b], 1 - alpha / 2)
    with np.errstate(divide='ignore', invalid='ignore'):
        scale = e_b / e_a
        return np.where(n_a + n_b > 0, n_a / n_b * scale, np.nan), low / (1 - low) * scale, high / (1 - high) * scale


def bracket(chain: Chain, s_rounds: int, w_days: float, t_from: float | None = None, t_to: float | None = None,
            alpha: float = ALPHA) -> dict | None:
    """Interval on gamma(s, w) over a period.

    The sub-windows sit on a grid of step w / CELLS_PER_W, and their mean weighs each moment by 1/D, as blocks do.
    Both directions of a pair use the same interval, inverted.

    Args:
        chain: The chain.
        s_rounds: The window, in rounds.
        w_days: The sub-windows, in days.
        t_from: Start of the period, the start of the chain if None.
        t_to: End of the period, the end of the chain if None.
        alpha: Probability that the interval misses gamma(s, w).

    Returns:
        The bounds, the estimate, the number of pairs and where the estimate and the upper bound are reached; None if
        the period cannot hold a pair.
    """
    w_seconds = w_days * DAY
    positions, n, e = cells(chain, w_seconds)
    step = w_seconds / CELLS_PER_W
    t_from = chain.start if t_from is None else t_from
    t_to = chain.end if t_to is None else t_to
    inside = np.flatnonzero((positions >= t_from) & (positions + w_seconds <= t_to))
    max_lag = int((s_rounds * ROUND_SECONDS - w_seconds) / step)
    if len(inside) <= CELLS_PER_W or max_lag < CELLS_PER_W:
        return None
    first, last = int(inside[0]), int(inside[-1])
    lags = np.arange(CELLS_PER_W, min(max_lag, last - first) + 1)
    n_pairs = int(((last - first + 1) - lags).sum())
    alpha_pair = alpha / n_pairs

    best = {'point': (1.0, None), 'lower': (1.0, None), 'upper': (1.0, None)}
    for lag in lags:
        a = np.arange(first, last - lag + 1)
        point, low, high = ratio_bounds(n[a], n[a + lag], e[a], e[a + lag], alpha_pair)
        with np.errstate(divide='ignore'):
            values = {'point': np.maximum(point, 1 / point), 'lower': np.maximum(low, 1 / high),
                      'upper': np.maximum(high, 1 / low)}
        for key, value in values.items():
            if np.isnan(value).all():
                continue
            i = int(np.nanargmax(value))
            if value[i] > best[key][0]:
                best[key] = (float(value[i]), (float(positions[a[i]]), float(positions[a[i] + lag])))
    return {'s': s_rounds, 'w_days': w_days, 'pairs': n_pairs, 'lower': best['lower'][0], 'upper': best['upper'][0],
            'point': best['point'][0], 'point_at': best['point'][1], 'upper_at': best['upper'][1]}


def attack_windows(chain: Chain, s_rounds: int, w_days: float, t_from: float, t_to: float,
                   thresholds: dict[str, float]) -> dict:
    """Share of the windows of s rounds that satisfy a bound on gamma, since an adversary chooses when to start.

    Args:
        chain: The chain.
        s_rounds: The window of the attack, in rounds.
        w_days: The sub-windows, in days.
        t_from: Start of the period.
        t_to: End of the period.
        thresholds: Largest gamma allowed, by name.

    Returns:
        For each threshold, the share of windows below it by the estimate (optimistic) and by the upper bound (cautious),
        and the number of windows.
    """
    w_seconds = w_days * DAY
    positions, n, e = cells(chain, w_seconds)
    keep = np.flatnonzero((positions >= t_from) & (positions + w_seconds <= t_to))
    positions, n, e = positions[keep], n[keep], e[keep]
    width = int((s_rounds * ROUND_SECONDS - w_seconds) / (w_seconds / CELLS_PER_W))
    starts = len(positions) - width
    lags = np.arange(CELLS_PER_W, width + 1)
    alpha_pair = ALPHA / int((width + 1 - lags).sum())
    point_window, upper_window = np.ones(starts), np.ones(starts)
    for lag in lags:
        a = np.arange(len(positions) - lag)
        point, low, high = ratio_bounds(n[a], n[a + lag], e[a], e[a + lag], alpha_pair)
        with np.errstate(divide='ignore'):
            point, upper = np.maximum(point, 1 / point), np.maximum(high, 1 / low)
        span = width - lag + 1  # Pairs at this lag that fit in a window, by their first sub-window.
        point_window = np.fmax(point_window, pd.Series(point).rolling(span, min_periods=1).max().shift(-(span - 1)).to_numpy()[:starts])
        upper_window = np.fmax(upper_window, pd.Series(upper).rolling(span, min_periods=1).max().shift(-(span - 1)).to_numpy()[:starts])
    shares = {name: {'estimate': float((point_window < value).mean()), 'bound': float((upper_window < value).mean())}
              for name, value in thresholds.items()}
    return shares | {'windows': int(starts)}


def difficulty_rounds(blocks: pd.DataFrame) -> pd.DataFrame:
    """Hashrate per round from the difficulty alone, D / 10 minutes, up to a constant.

    Args:
        blocks: The output of vmls.gamma.load_blocks.

    Returns:
        The columns round_idx and hashrate, without gaps.
    """
    observed = (blocks.assign(round_idx=(blocks['time'] - blocks.attrs['genesis_time']) // ROUND_SECONDS)
                .groupby('round_idx')['difficulty'].mean())
    full = observed.reindex(pd.RangeIndex(int(observed.index.min()), int(observed.index.max()) + 1, name='round_idx'))
    return full.interpolate(method='linear').ffill().bfill().rename('hashrate').reset_index()


def windowed(rounds: pd.DataFrame, s_rounds: int) -> tuple[pd.Series, pd.Series]:
    """The two statistics of the gamma notebook at every window of s rounds.

    Args:
        rounds: The hashrate per round.
        s_rounds: The window, in rounds.

    Returns:
        The max/min and the 1%-99% ratio of each window, indexed by the round at which it ends.
    """
    series = pd.Series(rounds['hashrate'].to_numpy(dtype=float), index=rounds['round_idx'].to_numpy())
    window = series.rolling(s_rounds, min_periods=s_rounds)
    return window.max() / window.min(), window.quantile(1 - ALPHA_INNER) / window.quantile(ALPHA_INNER)


def scenario_hashrate(name: str, grid_days: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """A known hashrate path, after a burn-in at the rate the difficulty expects.

    Args:
        name: 'constant', 'dip-<days>' (half the hashrate for that many days) or 'ramp' (three times more over 60 days).
        grid_days: The times, in days.
        rng: The random generator, which places the dip.

    Returns:
        The hashrate at these times.
    """
    h = np.ones(len(grid_days))
    if name.startswith('dip-'):
        start = rng.uniform(60, 74)
        h[(grid_days >= start) & (grid_days < start + float(name[4:]))] = 0.5
    elif name == 'ramp':
        h = np.interp(grid_days, [60, 120], [1, 3])
    return h


def simulate_chain(name: str, days: float, seed: int) -> tuple[Chain, pd.DataFrame, np.ndarray, np.ndarray, np.ndarray]:
    """Mines a chain with the retargeting of Bitcoin on a known hashrate path.

    Args:
        name: The scenario, see scenario_hashrate.
        days: Length of the chain, in days.
        seed: The seed.

    Returns:
        The chain, its blocks for the notebook's estimators, a fine time grid, the hashrate on it, and the integral
        of h/D on it.
    """
    rng = np.random.default_rng(seed)
    grid = np.arange(0, days * DAY + 300, 300.0)
    h = scenario_hashrate(name, grid / DAY, rng)
    work = np.concatenate(([0.0], np.cumsum(h[:-1] * 300.0)))  # Up to the constant of a hashrate of 1 at difficulty 1.
    times, difficulties, change_times, values = [], [], [0.0], [1.0]
    t, d = 0.0, 1.0
    while t < days * DAY:
        found = np.interp(np.interp(t, grid, work) + np.cumsum(rng.exponential(TARGET_SPACING * d, EPOCH)), work, grid)
        keep = found < days * DAY
        times.append(found[keep])
        difficulties.append(np.full(int(keep.sum()), d))
        if not keep.all():
            break
        t = float(found[-1])
        d = d * float(np.clip(EPOCH * TARGET_SPACING / (found[-1] - found[0]), 0.25, 4))
        change_times.append(t)
        values.append(d)
    times, difficulties = np.concatenate(times), np.concatenate(difficulties)
    chain = Chain(times, np.array(change_times), np.array(values))
    blocks = pd.DataFrame({'time': times.astype(np.int64), 'difficulty': difficulties, 'height': np.arange(len(times))})
    blocks.attrs['genesis_time'] = 0
    blocks.attrs['n_headers'] = len(times)
    d_on_grid = np.array(values)[np.clip(np.searchsorted(change_times, grid, side='right') - 1, 0, len(values) - 1)]
    return chain, blocks, grid, h, np.concatenate(([0.0], np.cumsum((h / d_on_grid)[:-1] * 300.0)))


def true_gamma(chain: Chain, grid: np.ndarray, weighted: np.ndarray, s_rounds: int, w_days: float) -> float:
    """gamma(s, w) of a simulated chain, on the grid and with the weights of the measure.

    Args:
        chain: The chain.
        grid: The fine time grid.
        weighted: The integral of h/D on it.
        s_rounds: The window, in rounds.
        w_days: The sub-windows, in days.

    Returns:
        gamma(s, w).
    """
    w_seconds = w_days * DAY
    positions, _, e = cells(chain, w_seconds)
    mean = (np.interp(positions + w_seconds, grid, weighted) - np.interp(positions, grid, weighted)) / e
    best = 1.0
    for lag in range(CELLS_PER_W, int((s_rounds * ROUND_SECONDS - w_seconds) / (w_seconds / CELLS_PER_W)) + 1):
        ratio = mean[:-lag] / mean[lag:]
        best = max(best, float(ratio.max()), float((1 / ratio).max()))
    return best


def simulation(name: str, days: float, seed: int, with_notebook: bool) -> dict:
    """The new measure, and optionally the notebook's two estimators, on one simulated chain, against the truth.

    Args:
        name: The scenario, see scenario_hashrate.
        days: Length of the chain, in days.
        seed: The seed.
        with_notebook: Whether to also run the notebook's estimator and D / 10 minutes.

    Returns:
        What each method returns and the truth, for s = 72,000 and 105,000 rounds.
    """
    chain, blocks, grid, h, weighted = simulate_chain(name, days, seed)
    out = {'scenario': name, 'seed': seed, 'blocks': len(chain.times)}
    for s_rounds in (72_000, 105_000):
        width = int(s_rounds * ROUND_SECONDS / 300)
        series = pd.Series(h)
        pointwise = float((series.rolling(width).max() / series.rolling(width).min()).max())
        row = {'definition': pointwise}
        for w_days in (1, 3, 7):
            b = bracket(chain, s_rounds, w_days)
            truth = true_gamma(chain, grid, weighted, s_rounds, w_days)
            row[f'new-w{w_days}'] = {'lower': b['lower'], 'upper': b['upper'], 'point': b['point'], 'truth': truth,
                                     'covers_truth': bool(b['lower'] <= truth <= b['upper']),
                                     'covers_definition': bool(b['lower'] <= pointwise <= b['upper'])}
        if with_notebook:
            for method, rounds in (('old', smoothed_rounds(blocks, K_SMOOTH)), ('difficulty', difficulty_rounds(blocks))):
                classic, robust = windowed(rounds, s_rounds)
                row[method] = {'max_min': float(classic.max()), 'q95': float(robust.quantile(0.95))}
        out[str(s_rounds)] = row
    return out


def summarize(results: list[dict]) -> dict:
    """Medians and 10th-90th percentiles of the runs of one scenario, and how often the intervals hold the truth.

    Args:
        results: Outputs of simulation for one scenario.

    Returns:
        The summary, by window.
    """
    def spread(values: list[float]) -> dict:
        """Median, 10th and 90th percentiles of a list of values."""
        return {'median': float(np.median(values)), 'p10': float(np.percentile(values, 10)),
                'p90': float(np.percentile(values, 90))}

    summary = {'runs': len(results), 'blocks': int(np.median([r['blocks'] for r in results]))}
    for s in ('72000', '105000'):
        rows = [r[s] for r in results]
        block = {'definition': spread([r['definition'] for r in rows])}
        for key in rows[0]:
            if key.startswith('new-'):
                block[key] = {stat: spread([r[key][stat] for r in rows]) for stat in ('lower', 'upper', 'point', 'truth')}
                block[key]['coverage_truth'] = float(np.mean([r[key]['covers_truth'] for r in rows]))
                block[key]['coverage_definition'] = float(np.mean([r[key]['covers_definition'] for r in rows]))
            elif key in ('old', 'difficulty'):
                block[key] = {stat: spread([r[key][stat] for r in rows]) for stat in ('max_min', 'q95')}
        summary[s] = block
    return summary


def coverage_run(retargets: bool, seed: int) -> dict[str, bool]:
    """Whether the interval holds gamma = 1 on a two-year chain at a constant hashrate.

    Args:
        retargets: Whether the chain retargets as Bitcoin does, or keeps a difficulty of 1.
        seed: The seed.

    Returns:
        For s = 72,000 and 105,000 rounds and w = 3 and 7 days, whether the lower bound is at most 1.
    """
    if retargets:
        chain = simulate_chain('constant', 730, 5_000_000 + seed)[0]
    else:
        times = np.cumsum(np.random.default_rng(7_000_000 + seed).exponential(TARGET_SPACING, int(730 * 144 * 1.1)))
        chain = Chain(times[times < 730 * DAY], np.array([0.0]), np.array([1.0]))
    return {f's={s},w={w}': bool(bracket(chain, s, w)['lower'] <= 1.0) for s in (72_000, 105_000) for w in (3, 7)}
