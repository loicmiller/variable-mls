"""The hashrate fluctuation gamma, measured two ways on a chain of headers.

The (gamma, s)-respecting property bounds the ratio of the largest to the smallest honest hashrate within any s
rounds of 18 seconds. A chain yields about one block every 33 rounds, so the hashrate is never observed round by round.

- classic: the hashrate is estimated from the work and time of the last K_SMOOTH blocks, on a grid of rounds; over
  each window of s rounds, the worst max/min, and the 1%-99% ratio summarised by its maximum, q95 and q99 over the
  windows. This is the estimator behind gamma = 1.54 (q95 at s = 72,000) in the papers.
- bound: gamma(s, w), the largest ratio between the mean hashrates of two disjoint sub-windows of w seconds within a
  window of s rounds. Blocks found in a sub-window are Poisson, of mean proportional to h * E, E the integral of 1/D
  over the sub-window (its exposure); given the blocks of both sub-windows, those of the first are binomial, which
  gives an exact interval on the ratio. A Bonferroni correction over the pairs of a period turns these into an
  interval on gamma(s, w), and a ratio of means never exceeds the ratio of extremes, so the lower bound also bounds the
  gamma of the definition.

Both take `since`, a Unix time: only the blocks found from then on count. The hashrate varied far more in 2009-2012
than since, so a recent gamma is the one that matters for a proof built today.

    result = classic(load_headers('headers/headers.json'))
"""

import multiprocessing as mp

import numpy as np
import pandas as pd
from scipy.special import betaincinv

from vmls.chain import GENESIS_TARGET, bits_to_target

ROUND_SECONDS = 18
DAY = 86400
K_SMOOTH = 1008  # Blocks of the smoothing window, at the knee of the K_GRID sweep.
K_GRID = [144, 432, 1008, 2016, 4032, 8064]
ALPHA_INNER = 0.01  # Quantiles of the robust ratio inside a window.
S_VALUES = (72_000, 105_000, 145_000, 271_000)
W_DAYS = (1, 3, 7, 14)
CELLS_PER_W = 4  # Positions of the sub-windows, per sub-window.
ALPHA = 0.05  # Probability that an interval on gamma(s, w) misses it.
# By height; the last period ends at the tip.
PERIODS = [('2009-2012', 1, 210_000), ('2012-2016', 210_000, 420_000), ('2016-2020', 420_000, 630_000),
           ('2020-2024', 630_000, 840_000), ('2024-2026', 840_000, None), ('since-2016', 420_000, None), ('all', 1, None)]
# Requirement 2 of the papers, gamma < (a (tau-1) (2m+k) lambda / (c m theta) - zeta) / 2 at lambda = 1.4, zeta -> 0.
REQUIREMENT_2 = {'a=0.9, c=1.35': 1.516, 'a=0.99, c=1.05': 2.144, 'a, c -> 1': 2.274}
ATTACK_S = 105_000  # The window of the zero-difficulty attack, in rounds.

_CHAIN = None  # The chain the bound workers share, set before the pool forks.


# The classic estimator.

def load_blocks(headers: list[dict], since: int | None = None) -> pd.DataFrame:
    """The blocks the classic estimator uses: those with a positive time since the previous block.

    Args:
        headers: The headers, one per height.
        since: Unix time; blocks found before it are left out.

    Returns:
        The height, time and difficulty of each block; the time of the genesis block and the number of headers are
        in the attrs.
    """
    df = pd.DataFrame({'time': [header['time'] for header in headers]})
    df['difficulty'] = [GENESIS_TARGET / bits_to_target(header['bits']) for header in headers]
    genesis_time = int(df['time'].iloc[0])
    df['height'] = df.index
    df = df[df['time'].diff() > 0].copy()
    if since is not None:
        df = df[df['time'] >= since].copy()
    df.attrs['genesis_time'] = genesis_time
    df.attrs['n_headers'] = len(headers)
    return df


def smoothed_rounds(blocks: pd.DataFrame, k_smooth: int = K_SMOOTH) -> pd.DataFrame:
    """Hashrate per round, from the work and time of the last k_smooth blocks, empty rounds interpolated.

    Blocks are sorted by time; Bitcoin timestamps are not monotonic, so this is not the height order.

    Args:
        blocks: The output of load_blocks.
        k_smooth: Blocks of the smoothing window.

    Returns:
        The columns round_idx and hashrate, without gaps.
    """
    tmp = blocks[['time', 'difficulty']].sort_values('time').reset_index(drop=True)
    work = tmp['difficulty'].rolling(window=k_smooth, min_periods=k_smooth).sum() * (2 ** 256 / GENESIS_TARGET)
    elapsed = tmp['time'] - tmp['time'].shift(k_smooth)
    tmp['hashrate'] = work / elapsed
    tmp = tmp.dropna(subset=['hashrate'])
    tmp = tmp[elapsed.loc[tmp.index] > 0]
    tmp['round_idx'] = (tmp['time'] - blocks.attrs['genesis_time']) // ROUND_SECONDS
    observed = tmp.groupby('round_idx')['hashrate'].mean()
    full = observed.reindex(pd.RangeIndex(int(observed.index.min()), int(observed.index.max()) + 1, name='round_idx'))
    return full.interpolate(method='linear').ffill().bfill().reset_index()


def max_min(h: pd.Series, s: int) -> float:
    """The worst max/min of the hashrate over the windows of s rounds."""
    window = h.rolling(window=s, min_periods=s)
    return float((window.max() / window.min()).max())


def classic_gamma(h: pd.Series, s: int) -> dict:
    """The classic statistics of the hashrate over the windows of s rounds.

    Args:
        h: The hashrate per round.
        s: The window, in rounds.

    Returns:
        The worst max/min ('classic'), and the 1%-99% ratio of each window summarised by its maximum, q95 and q99.
    """
    window = h.rolling(window=s, min_periods=s)
    ratios = (window.quantile(1.0 - ALPHA_INNER) / window.quantile(ALPHA_INNER)).dropna()
    return {'s': s, 'days': s * ROUND_SECONDS / DAY, 'n_windows': len(ratios), 'classic': max_min(h, s),
            'robust_max': float(ratios.max()), 'q95': float(ratios.quantile(0.95)), 'q99': float(ratios.quantile(0.99))}


def knee(gammas: dict[int, float]) -> int:
    """The smoothing window at the knee of the log-log curve: the one farthest from the chord between its ends."""
    x = np.log10(list(gammas.keys()))
    y = np.log10(list(gammas.values()))
    distance = np.abs((y[-1] - y[0]) * x - (x[-1] - x[0]) * y + x[-1] * y[0] - y[-1] * x[0]) / np.hypot(y[-1] - y[0],
                                                                                                         x[-1] - x[0])
    return list(gammas.keys())[int(distance.argmax())]


def gamma_over_time(blocks: pd.DataFrame, rounds: pd.DataFrame, s: int) -> pd.DataFrame:
    """The max/min of each window of s rounds, by the height and time at which the window ends.

    Args:
        blocks: The output of load_blocks.
        rounds: The output of smoothed_rounds.
        s: The window, in rounds.

    Returns:
        The columns height, time and gamma, one row per window.
    """
    window = rounds['hashrate'].rolling(window=s, min_periods=s)
    gamma_t = (window.max() / window.min()).dropna()
    meta = (blocks.assign(round_idx=(blocks['time'] - blocks.attrs['genesis_time']) // ROUND_SECONDS)
            .groupby('round_idx').agg(height=('height', 'max'), time=('time', 'max')))
    aligned = meta.reindex(rounds['round_idx']).ffill().bfill().astype(int).reset_index()
    return pd.DataFrame({'height': aligned.loc[gamma_t.index, 'height'].to_numpy(),
                         'time': aligned.loc[gamma_t.index, 'time'].to_numpy(),
                         'gamma': gamma_t.to_numpy()})


def classic(headers: list[dict], since: int | None = None, s_values: tuple[int, ...] = S_VALUES) -> dict:
    """The classic estimator on a chain of headers.

    Args:
        headers: The headers, one per height.
        since: Unix time; only blocks found from then on are used.
        s_values: The windows, in rounds.

    Returns:
        One row per window (see classic_gamma). Over the whole chain (since is None), also the max/min at s = 271,000
        for each smoothing window of K_GRID ('k_gamma'), its knee, and the max/min at the tip and its peak after 2015.
    """
    blocks = load_blocks(headers, since)
    rounds = smoothed_rounds(blocks, K_SMOOTH)
    h = rounds['hashrate'].astype(float)
    h = h[h > 0].reset_index(drop=True)
    with mp.get_context('fork').Pool(len(s_values)) as pool:
        rows = pool.starmap(classic_gamma, [(h, s) for s in s_values])
    result = {'n_headers': blocks.attrs['n_headers'], 'since': since, 'from_time': int(blocks['time'].min()),
              'rounds': len(h), 'rows': rows}
    if since is None:
        k_gamma = {k: max_min(smoothed_rounds(blocks, k)['hashrate'].astype(float), 271_000) for k in K_GRID}
        over_time = gamma_over_time(blocks, rounds, 271_000)
        result |= {'k_gamma': k_gamma, 'knee': knee(k_gamma),
                   'evolution_s_271000': {'last': float(over_time['gamma'].iloc[-1]),
                                          'peak_after_2015': float(over_time.loc[over_time['height'] > 340_000,
                                                                                 'gamma'].max())}}
    return result


# gamma(s, w) with exact intervals.

class Chain:
    """What gamma(s, w) needs from a chain: when blocks were found, and the integral of 1/D over time.

    Args:
        times: Time of each block, in seconds.
        change_times: Times from which each difficulty applies, the first one being the start of the chain.
        difficulties: Difficulty applying from each of these times.
    """

    def __init__(self, times: np.ndarray, change_times: np.ndarray, difficulties: np.ndarray):
        """Sorts the block times and sums 1/D from the end of the chain."""
        self.times = np.sort(times)
        self.start, self.end = float(self.times[0]), float(self.times[-1])
        self.knots = np.append(change_times, max(self.end, change_times[-1]) + 1.0)
        # Summed from the end: D grows by 14 orders of magnitude, so a sum from 2009 could not hold a day of 2026.
        self.exposure_at_knots = -np.concatenate((np.cumsum((np.diff(self.knots) / difficulties)[::-1])[::-1], [0.0]))

    def exposure(self, t: np.ndarray) -> np.ndarray:
        """Integral of 1/D over time at the given times, up to a constant: only differences mean something."""
        return np.interp(t, self.knots, self.exposure_at_knots)

    def count(self, t: np.ndarray) -> np.ndarray:
        """Number of blocks found before each of the given times."""
        return np.searchsorted(self.times, t, side='left')


def chain_from_headers(headers: list[dict], median_time_past: bool = False) -> tuple[Chain, np.ndarray]:
    """The Chain of exported headers, without the genesis block and the gap after it.

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
        For each threshold, the share of windows below it by the estimate (optimistic) and by the upper bound
        (cautious), and the number of windows.
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
        roll = lambda x: pd.Series(x).rolling(span, min_periods=1).max().shift(-(span - 1)).to_numpy()[:starts]  # noqa: E731
        point_window, upper_window = np.fmax(point_window, roll(point)), np.fmax(upper_window, roll(upper))
    shares = {name: {'estimate': float((point_window < value).mean()), 'bound': float((upper_window < value).mean())}
              for name, value in thresholds.items()}
    return shares | {'windows': int(starts)}


def difficulty_rounds(blocks: pd.DataFrame) -> pd.DataFrame:
    """Hashrate per round from the difficulty alone, D / 10 minutes, up to a constant.

    Args:
        blocks: The output of load_blocks.

    Returns:
        The columns round_idx and hashrate, without gaps.
    """
    observed = (blocks.assign(round_idx=(blocks['time'] - blocks.attrs['genesis_time']) // ROUND_SECONDS)
                .groupby('round_idx')['difficulty'].mean())
    full = observed.reindex(pd.RangeIndex(int(observed.index.min()), int(observed.index.max()) + 1, name='round_idx'))
    return full.interpolate(method='linear').ffill().bfill().rename('hashrate').reset_index()


def windowed(rounds: pd.DataFrame, s_rounds: int) -> tuple[pd.Series, pd.Series]:
    """The two classic statistics at every window of s rounds.

    Args:
        rounds: The hashrate per round.
        s_rounds: The window, in rounds.

    Returns:
        The max/min and the 1%-99% ratio of each window, indexed by the round at which it ends.
    """
    series = pd.Series(rounds['hashrate'].to_numpy(dtype=float), index=rounds['round_idx'].to_numpy())
    window = series.rolling(s_rounds, min_periods=s_rounds)
    return window.max() / window.min(), window.quantile(1 - ALPHA_INNER) / window.quantile(ALPHA_INNER)


def _bracket_task(name: str, t_from: float, t_to: float, s_rounds: int, w_days: float) -> dict | None:
    """One cell of the table of brackets, on the chain the workers share."""
    row = bracket(_CHAIN, s_rounds, w_days, t_from, t_to)
    return None if row is None else row | {'period': name}


def _classic_by_period(method: str, rounds: pd.DataFrame, s_rounds: int, spans: dict) -> dict:
    """The classic statistics on each period: the worst max/min and the q95 of the 1%-99% ratio.

    Args:
        method: 'old' (the classic estimator) or 'difficulty' (D / 10 minutes).
        rounds: Its hashrate per round.
        s_rounds: The window, in rounds.
        spans: First and last round of each period.

    Returns:
        The statistics, by period.
    """
    max_mins, robust = windowed(rounds, s_rounds)
    periods = {}
    for name, (r_from, r_to) in spans.items():
        c, q = max_mins.loc[r_from + s_rounds:r_to], robust.loc[r_from + s_rounds:r_to]
        periods[name] = {'max_min': float(c.max()), 'q95': float(q.quantile(0.95))}
    return {'method': method, 's': s_rounds, 'periods': periods}


def bound(headers: list[dict], since: int | None = None, workers: int = 16) -> dict:
    """gamma(s, w) by period, the classic statistics on the same periods, and the share of windows open to the attack.

    Args:
        headers: The headers, one per height.
        since: Unix time. If given, a single period from the first block found then to the tip replaces PERIODS.
        workers: Processes.

    Returns:
        The brackets of every period, window and sub-window; the classic statistics ('old': the classic estimator and
        D / 10 minutes) on the same periods; on the reference period ('since-2016', or the single period), the share of
        windows of ATTACK_S rounds below each REQUIREMENT_2 threshold, and the brackets with the median time past.
    """
    global _CHAIN
    _CHAIN, time = chain_from_headers(headers)
    monotonic = np.maximum.accumulate(time)
    if since is None:
        periods, reference = PERIODS, 'since-2016'
    else:
        first = int(np.searchsorted(monotonic, since))
        reference = f'since-{since}'
        periods = [(reference, max(first, 1), None)]
    spans, tasks = {}, []
    for name, first, last in periods:
        t_from = float(monotonic[first])
        t_to = float(time[-1] if last is None else monotonic[last - 1])
        spans[name] = (t_from, t_to)
        tasks += [(name, t_from, t_to, s, w) for s in S_VALUES for w in W_DAYS if 2 * w * DAY <= s * ROUND_SECONDS]
    context = mp.get_context('fork')
    with context.Pool(workers) as pool:
        rows = [row for row in pool.starmap(_bracket_task, tasks, chunksize=1) if row is not None]

    blocks = load_blocks(headers)
    genesis = blocks.attrs['genesis_time']
    round_spans = {name: (int((a - genesis) // ROUND_SECONDS), int((b - genesis) // ROUND_SECONDS))
                   for name, (a, b) in spans.items()}
    series = {'old': smoothed_rounds(blocks, K_SMOOTH), 'difficulty': difficulty_rounds(blocks)}
    with context.Pool(min(workers, 8)) as pool:
        old = pool.starmap(_classic_by_period, [(method, rounds, s, round_spans) for method, rounds in series.items()
                                                for s in S_VALUES], chunksize=1)

    t_from, t_to = spans[reference]
    attack = {f'w={w}': attack_windows(_CHAIN, ATTACK_S, w, t_from, t_to, REQUIREMENT_2) for w in (1, 3, 7)}

    _CHAIN, _ = chain_from_headers(headers, median_time_past=True)
    with context.Pool(workers) as pool:
        mtp = [row for row in pool.starmap(_bracket_task, [t for t in tasks if t[0] == reference], chunksize=1) if row]
    key = reference.replace('-', '_')
    return {'n_headers': len(time), 'alpha': ALPHA, 'cells_per_w': CELLS_PER_W, 'spans': spans, 'brackets': rows,
            'old': old, f'attack_share_{key}': {'s': ATTACK_S, 'by_w': attack}, f'median_time_past_{key}': mtp}
