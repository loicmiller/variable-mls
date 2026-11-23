###############################################################################
# Imports

import argparse
import json
import multiprocessing as mp

import matplotlib
matplotlib.use('pdf')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.special import betaincinv
from scipy.stats import binomtest

from gamma_at_height import ALPHA_INNER, K_SMOOTH, ROUND_SECONDS, load_blocks, smoothed_rounds



###############################################################################
# Constants

DAY = 86400
S_VALUES = [72_000, 105_000, 145_000, 271_000]
W_DAYS = [1, 3, 7, 14]
CELLS_PER_W = 4 # Positions of the sub-windows, per sub-window.
ALPHA = 0.05
EPOCH = 2016
TARGET_SPACING = 600

# By height. The last one ends at the tip.
PERIODS = [('2009-2012', 1, 210_000), ('2012-2016', 210_000, 420_000), ('2016-2020', 420_000, 630_000), ('2020-2024', 630_000, 840_000), ('2024-2026', 840_000, None), ('since-2016', 420_000, None), ('all', 1, None)]

# Requirement 2, gamma < (a (tau-1) (2m+k) lambda / (c m theta) - zeta) / 2, at lambda = 1.4 and zeta -> 0, for three values of a/c.
REQUIREMENT_2 = {'a=0.9, c=1.35': 1.516, 'a=0.99, c=1.05': 2.144, 'a, c -> 1': 2.274}
ATTACK_S = 105_000

BLUE, ORANGE, GRAY = '#2a78d6', '#eb6834', '#52514e'



###############################################################################
# The measure

class Chain:
    """
    What the measure needs from a chain: when blocks were found, and the integral of 1/D over time.

    Args:
    - times (numpy.ndarray): The time of each block, in seconds.
    - change_times (numpy.ndarray): The times from which each difficulty applies, the first one being the start of the chain.
    - difficulties (numpy.ndarray): The difficulty applying from each of these times.
    """

    def __init__(self, times, change_times, difficulties):
        self.times = np.sort(times)
        self.start, self.end = float(self.times[0]), float(self.times[-1])
        knots = np.append(change_times, max(self.end, change_times[-1]) + 1.0)
        self.knots = knots
        # Summed from the end: D grows by 14 orders of magnitude, and a sum from 2009 would be too large to hold a day of 2026.
        self.exposure_at_knots = -np.concatenate((np.cumsum((np.diff(knots) / difficulties)[::-1])[::-1], [0.0]))

    def exposure(self, t):
        """
        The integral of 1/D over time, up to a constant: only differences mean something.

        Args:
        - t (numpy.ndarray): The times.

        Returns:
        - numpy.ndarray: The exposure at these times.
        """
        return np.interp(t, self.knots, self.exposure_at_knots)

    def count(self, t):
        """
        The number of blocks found before t.

        Args:
        - t (numpy.ndarray): The times.

        Returns:
        - numpy.ndarray: The number of blocks at these times.
        """
        return np.searchsorted(self.times, t, side='left')


def chain_from_headers(path, median_time_past=False):
    """
    Builds the chain of a headers file, without the genesis block and the gap that follows it.

    Args:
    - path (str): The headers file.
    - median_time_past (bool): Whether to use the median of the last 11 timestamps instead of the timestamp set by the miner.

    Returns:
    - tuple: The Chain, and the time and height of each block in height order.
    """
    with open(path) as f:
        headers = json.load(f)
    time = pd.Series([header['time'] for header in headers], dtype=float)
    if median_time_past:
        time = time.rolling(11, min_periods=1).median()
    time = time.to_numpy()
    bits = [int(header['bits'], 16) for header in headers]
    difficulty = np.array([(0xffff << 208) / ((b & 0xffffff) << (8 * ((b >> 24) - 3))) for b in bits])

    # A difficulty applies from the moment the block before it was found. Timestamps are not monotonic, change points must be.
    monotonic = np.maximum.accumulate(time)
    changes = np.flatnonzero(np.diff(difficulty) != 0) + 1
    changes = changes[changes > 1]
    change_times = np.concatenate(([monotonic[1]], monotonic[changes - 1]))
    values = np.concatenate(([difficulty[1]], difficulty[changes]))
    return Chain(time[1:], change_times, values), time


def cells(chain, w_seconds):
    """
    Blocks and exposure of the sub-windows of w seconds, at every position of the grid.

    Args:
    - chain (Chain): The chain.
    - w_seconds (float): The length of a sub-window.

    Returns:
    - tuple: The start of each sub-window, its number of blocks and its exposure.
    """
    step = w_seconds / CELLS_PER_W
    positions = chain.start + step * np.arange(int((chain.end - chain.start - w_seconds) / step) + 1)
    return positions, chain.count(positions + w_seconds) - chain.count(positions), chain.exposure(positions + w_seconds) - chain.exposure(positions)


def ratio_bounds(n_a, n_b, e_a, e_b, alpha):
    """
    Exact interval on h_a / h_b: given n_a + n_b, n_a is binomial, of parameter h_a e_a / (h_a e_a + h_b e_b).

    Args:
    - n_a (numpy.ndarray): The blocks of the first sub-window.
    - n_b (numpy.ndarray): The blocks of the second sub-window.
    - e_a (numpy.ndarray): The exposure of the first sub-window.
    - e_b (numpy.ndarray): The exposure of the second sub-window.
    - alpha (float): The error of each interval, shared between its two sides.

    Returns:
    - tuple: The estimate, and the lower and upper bounds, of h_a / h_b.
    """
    low, high = np.zeros(len(n_a)), np.ones(len(n_a))
    some_a, some_b = n_a > 0, n_b > 0
    low[some_a] = betaincinv(n_a[some_a], n_b[some_a] + 1.0, alpha / 2)
    high[some_b] = betaincinv(n_a[some_b] + 1.0, n_b[some_b], 1 - alpha / 2)
    with np.errstate(divide='ignore', invalid='ignore'):
        scale = e_b / e_a
        return np.where(n_a + n_b > 0, n_a / n_b * scale, np.nan), low / (1 - low) * scale, high / (1 - high) * scale


def bracket(chain, s_rounds, w_days, t_from=None, t_to=None, alpha=ALPHA, table=None):
    """
    gamma(s, w) on a period: the largest ratio between the mean hashrates of two disjoint sub-windows of a window of s rounds.

    Args:
    - chain (Chain): The chain.
    - s_rounds (int): The window, in rounds.
    - w_days (float): The sub-windows, in days.
    - t_from (float): The start of the period.
    - t_to (float): The end of the period.
    - alpha (float): The probability that the interval misses gamma(s, w).
    - table (tuple): The output of cells, if already computed.

    Returns:
    - dict: The bounds, the estimate, and where they are reached.

    Notes:
    - Bonferroni over all the pairs of the period. Both directions of a pair use the same interval, inverted.
    - The sub-windows are on a grid, and their mean weighs each moment by 1/D, as blocks do.
    """
    w_seconds = w_days * DAY
    positions, n, e = table if table is not None else cells(chain, w_seconds)
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
            values = {'point': np.maximum(point, 1 / point), 'lower': np.maximum(low, 1 / high), 'upper': np.maximum(high, 1 / low)}
        for key, value in values.items():
            if np.isnan(value).all():
                continue
            i = int(np.nanargmax(value))
            if value[i] > best[key][0]:
                best[key] = (float(value[i]), (float(positions[a[i]]), float(positions[a[i] + lag])))
    return {
        's': s_rounds, 'w_days': w_days, 'pairs': n_pairs,
        'lower': best['lower'][0], 'upper': best['upper'][0], 'point': best['point'][0],
        'point_at': best['point'][1], 'upper_at': best['upper'][1],
    }


def attack_windows(chain, s_rounds, w_days, t_from, t_to, thresholds):
    """
    The share of the dates at which a window of s rounds satisfies Requirement 2, since the adversary chooses when to start.

    Args:
    - chain (Chain): The chain.
    - s_rounds (int): The window of the attack, in rounds.
    - w_days (float): The sub-windows, in days.
    - t_from (float): The start of the period.
    - t_to (float): The end of the period.
    - thresholds (dict): The largest gamma allowed by Requirement 2, by name.

    Returns:
    - dict: For each threshold, the share of windows below it, by the estimate (optimistic) and by the bound (cautious).
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
        span = width - lag + 1 # The pairs at this lag that fit in a window, by their first sub-window.
        point_window = np.fmax(point_window, pd.Series(point).rolling(span, min_periods=1).max().shift(-(span - 1)).to_numpy()[:starts])
        upper_window = np.fmax(upper_window, pd.Series(upper).rolling(span, min_periods=1).max().shift(-(span - 1)).to_numpy()[:starts])
    return {name: {'estimate': float((point_window < value).mean()), 'bound': float((upper_window < value).mean())} for name, value in thresholds.items()} | {'windows': int(starts)}



###############################################################################
# The two other methods

def difficulty_rounds(frame):
    """
    The hashrate per round from the difficulty alone: D / 10 minutes, up to a constant.

    Args:
    - frame (pd.DataFrame): The blocks, as load_blocks returns them.

    Returns:
    - pd.DataFrame: The columns round_idx and hashrate, without gaps.
    """
    observed = frame.assign(round_idx=(frame['time'] - frame.attrs['genesis_time']) // ROUND_SECONDS).groupby('round_idx')['difficulty'].mean()
    full = observed.reindex(pd.RangeIndex(int(observed.index.min()), int(observed.index.max()) + 1, name='round_idx'))
    return full.interpolate(method='linear').ffill().bfill().rename('hashrate').reset_index()


def windowed(rounds, s_rounds):
    """
    The two statistics of the notebook, at every window of s rounds.

    Args:
    - rounds (pd.DataFrame): The hashrate per round.
    - s_rounds (int): The window, in rounds.

    Returns:
    - tuple: The max/min and the 1%-99% ratio of each window, indexed by the round at which it ends.
    """
    series = pd.Series(rounds['hashrate'].to_numpy(dtype=float), index=rounds['round_idx'].to_numpy())
    window = series.rolling(s_rounds, min_periods=s_rounds)
    return window.max() / window.min(), window.quantile(1 - ALPHA_INNER) / window.quantile(ALPHA_INNER)


def old_statistics(task):
    """
    The statistics of the notebook on each period.

    Args:
    - task (tuple): The method, its hashrate per round, the window in rounds, and the rounds of each period.

    Returns:
    - dict: For each period, the worst max/min and the q95 of the 1%-99% ratio.
    """
    method, rounds, s_rounds, spans = task
    classic, robust = windowed(rounds, s_rounds)
    out = {}
    for name, (r_from, r_to) in spans.items():
        c, q = classic.loc[r_from + s_rounds:r_to], robust.loc[r_from + s_rounds:r_to]
        out[name] = {'max_min': float(c.max()), 'q95': float(q.quantile(0.95))}
    return {'method': method, 's': s_rounds, 'periods': out}



###############################################################################
# Simulation

def scenario_hashrate(name, grid_days, rng):
    """
    A known hashrate path, starting after a burn-in at the rate the difficulty expects.

    Args:
    - name (str): 'constant', 'dip-<days>' or 'ramp'.
    - grid_days (numpy.ndarray): The times, in days.
    - rng (numpy.random.Generator): The random generator.

    Returns:
    - numpy.ndarray: The hashrate at these times.
    """
    h = np.ones(len(grid_days))
    if name.startswith('dip-'):
        start = rng.uniform(60, 74)
        h[(grid_days >= start) & (grid_days < start + float(name[4:]))] = 0.5
    elif name == 'ramp':
        h = np.interp(grid_days, [60, 120], [1, 3])
    return h


def simulate_chain(name, days, seed):
    """
    Mines a chain with the retargeting of Bitcoin on a known hashrate path.

    Args:
    - name (str): The scenario.
    - days (float): The length of the chain, in days.
    - seed (int): The seed.

    Returns:
    - tuple: The Chain, a frame for the two other methods, the fine time grid, its hashrate, and the integral of h/D on it.
    """
    rng = np.random.default_rng(seed)
    grid = np.arange(0, days * DAY + 300, 300.0)
    h = scenario_hashrate(name, grid / DAY, rng)
    work = np.concatenate(([0.0], np.cumsum(h[:-1] * 300.0))) # Up to the constant of a hashrate of 1 at difficulty 1.
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

    frame = pd.DataFrame({'time': times.astype(np.int64), 'difficulty': difficulties, 'height': np.arange(len(times))})
    frame.attrs['genesis_time'] = 0
    frame.attrs['n_headers'] = len(times)
    d_on_grid = np.array(values)[np.clip(np.searchsorted(change_times, grid, side='right') - 1, 0, len(values) - 1)]
    return chain, frame, grid, h, np.concatenate(([0.0], np.cumsum((h / d_on_grid)[:-1] * 300.0)))


def true_gamma(chain, grid, weighted, s_rounds, w_days):
    """
    The value of gamma(s, w) on a simulated chain, on the same grid and with the same weights as the measure.

    Args:
    - chain (Chain): The chain.
    - grid (numpy.ndarray): The fine time grid.
    - weighted (numpy.ndarray): The integral of h/D on it.
    - s_rounds (int): The window, in rounds.
    - w_days (float): The sub-windows, in days.

    Returns:
    - float: gamma(s, w).
    """
    w_seconds = w_days * DAY
    positions, _, e = cells(chain, w_seconds)
    mean = (np.interp(positions + w_seconds, grid, weighted) - np.interp(positions, grid, weighted)) / e
    best = 1.0
    for lag in range(CELLS_PER_W, int((s_rounds * ROUND_SECONDS - w_seconds) / (w_seconds / CELLS_PER_W)) + 1):
        ratio = mean[:-lag] / mean[lag:]
        best = max(best, float(ratio.max()), float((1 / ratio).max()))
    return best


def one_simulation(task):
    """
    The three methods on one simulated chain.

    Args:
    - task (tuple): The scenario, the length of the chain in days, the seed, and whether to run the two other methods.

    Returns:
    - dict: What each method returns, and the truth.
    """
    name, days, seed, with_old = task
    chain, frame, grid, h, weighted = simulate_chain(name, days, seed)
    out = {'scenario': name, 'seed': seed, 'blocks': len(chain.times)}
    for s_rounds in (72_000, 105_000):
        width = int(s_rounds * ROUND_SECONDS / 300)
        series = pd.Series(h)
        pointwise = float((series.rolling(width).max() / series.rolling(width).min()).max())
        row = {'definition': pointwise}
        for w_days in (1, 3, 7):
            b = bracket(chain, s_rounds, w_days)
            truth = true_gamma(chain, grid, weighted, s_rounds, w_days)
            row[f'new-w{w_days}'] = {'lower': b['lower'], 'upper': b['upper'], 'point': b['point'], 'truth': truth, 'covers_truth': bool(b['lower'] <= truth <= b['upper']), 'covers_definition': bool(b['lower'] <= pointwise <= b['upper'])}
        if with_old:
            for method, rounds in (('old', smoothed_rounds(frame, K_SMOOTH)), ('difficulty', difficulty_rounds(frame))):
                classic, robust = windowed(rounds, s_rounds)
                row[method] = {'max_min': float(classic.max()), 'q95': float(robust.quantile(0.95))}
        out[str(s_rounds)] = row
    return out


def summarize(results):
    """
    Medians and 10th-90th percentiles of one scenario, and how often the intervals hold the truth.

    Args:
    - results (list): The outputs of one_simulation for one scenario.

    Returns:
    - dict: The summary, by window.
    """
    def spread(values):
        return {'median': float(np.median(values)), 'p10': float(np.percentile(values, 10)), 'p90': float(np.percentile(values, 90))}

    summary = {'runs': len(results), 'blocks': int(np.median([r['blocks'] for r in results]))}
    for s in ('72000', '105000'):
        rows = [r[s] for r in results]
        block = {'definition': spread([r['definition'] for r in rows])}
        for key in rows[0]:
            if key.startswith('new-'):
                block[key] = {'lower': spread([r[key]['lower'] for r in rows]), 'upper': spread([r[key]['upper'] for r in rows]), 'point': spread([r[key]['point'] for r in rows]), 'truth': spread([r[key]['truth'] for r in rows]), 'coverage_truth': float(np.mean([r[key]['covers_truth'] for r in rows])), 'coverage_definition': float(np.mean([r[key]['covers_definition'] for r in rows]))}
            elif key in ('old', 'difficulty'):
                block[key] = {stat: spread([r[key][stat] for r in rows]) for stat in ('max_min', 'q95')}
        summary[s] = block
    return summary



###############################################################################
# Figure

def bracket_figure(rows, old, out):
    """
    The interval against the sub-window, on the period the paper would quote, with the two other methods as references.

    Args:
    - rows (list): The brackets of the period.
    - old (dict): The statistics of the two other methods, by method and window.
    - out (str): The path of the PDF.

    Returns:
    - None
    """
    plt.rcParams.update({
        'font.family': 'serif', 'font.serif': ['STIXGeneral'], 'mathtext.fontset': 'stix',
        'font.size': 8, 'axes.labelsize': 8, 'legend.fontsize': 7, 'xtick.labelsize': 7, 'ytick.labelsize': 7,
        'axes.linewidth': 0.5, 'axes.edgecolor': GRAY, 'xtick.color': GRAY, 'ytick.color': GRAY, 'pdf.fonttype': 42,
    })
    fig, axes = plt.subplots(2, 2, figsize=(3.4, 3.4), sharey=True, sharex=True, layout='constrained')
    for ax, s_rounds in zip(axes.ravel(), S_VALUES):
        here = [row for row in rows if row['s'] == s_rounds]
        x = [W_DAYS.index(row['w_days']) for row in here]
        ax.vlines(x, [row['lower'] for row in here], [row['upper'] for row in here], color=BLUE, linewidth=2, label='New: 95% interval')
        ax.plot(x, [row['point'] for row in here], linestyle='none', marker='o', markersize=4, color=BLUE, markeredgecolor='white', markeredgewidth=0.5, label='New: estimate')
        ax.axhline(old['old'][s_rounds]['q95'], color=ORANGE, linestyle='--', linewidth=1, label='Notebook, q95')
        ax.axhline(old['old'][s_rounds]['max_min'], color=ORANGE, linestyle='-', linewidth=1, label='Notebook, max/min')
        ax.axhline(old['difficulty'][s_rounds]['max_min'], color=GRAY, linestyle=':', linewidth=1, label='D / 10 min, max/min')
        ax.set_title(f's = {s_rounds:,} rounds ({s_rounds * ROUND_SECONDS / DAY:.0f} days)', fontsize=7, loc='left')
        ax.set_xticks(range(len(W_DAYS)), [f'{w}' for w in W_DAYS])
        ax.set_xlim(-0.5, len(W_DAYS) - 0.5)
        ax.set_yscale('log')
        ax.set_ylim(1, None)
        ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda y, _: f'{y:g}'))
        ax.yaxis.set_minor_formatter(matplotlib.ticker.FuncFormatter(lambda y, _: f'{y:g}' if y in (1.5, 2, 3, 5) else ''))
        ax.grid(True, axis='y', which='both', color='#e4e3df', linewidth=0.5)
        ax.set_axisbelow(True)
        for side in ('top', 'right'):
            ax.spines[side].set_visible(False)
    for ax in axes[1]:
        ax.set_xlabel('Sub-window w (days)')
    for ax in axes[:, 0]:
        ax.set_ylabel(r'$\gamma$')
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='outside upper center', ncols=2, frameon=False)
    fig.savefig(out)
    plt.close(fig)



###############################################################################
# Commands

def check():
    """
    Checks the interval, the exposure and the pairs against independent computations.

    Args:
    - None

    Returns:
    - None

    Raises:
    - AssertionError: If a check fails.
    """
    # The interval on pi is the exact one of scipy. With equal exposures, the ratio is pi / (1 - pi).
    for n_a, n_b, alpha in ((10, 30, 0.05), (144, 100, 0.001), (1, 0, 0.05), (0, 7, 0.05), (2000, 2100, 1e-6)):
        ci = binomtest(n_a, n_a + n_b).proportion_ci(1 - alpha, method='exact')
        _, low, high = ratio_bounds(np.array([n_a]), np.array([n_b]), np.array([1.0]), np.array([1.0]), alpha)
        assert abs(low[0] - ci.low / (1 - ci.low)) < 1e-6 * (1 + low[0]), (n_a, n_b, low[0], ci.low)
        if n_b > 0:
            assert abs(high[0] - ci.high / (1 - ci.high)) < 1e-6 * high[0], (n_a, n_b, high[0], ci.high)
    print('interval: same as the exact binomial interval of scipy')

    # By hand: 1 day at difficulty 2, then 1 day at difficulty 4.
    chain = Chain(np.array([0.0, 2.0 * DAY]), np.array([0.0, float(DAY)]), np.array([2.0, 4.0]))
    start = chain.exposure(np.array([0.0]))[0]
    assert abs(chain.exposure(np.array([2.0 * DAY]))[0] - start - (DAY / 2 + DAY / 4)) < 1e-6
    assert abs(chain.exposure(np.array([1.5 * DAY]))[0] - start - (DAY / 2 + DAY / 8)) < 1e-6

    # At the scale of the chain: a day at the difficulty of 2026, after years at difficulty 1.
    day_2026 = 1.5e14
    chain = Chain(np.array([0.0, 400.0 * DAY]), np.array([0.0, 300.0 * DAY]), np.array([1.0, day_2026]))
    measured = np.diff(chain.exposure(np.array([350.0 * DAY, 351.0 * DAY])))[0]
    assert abs(measured / (DAY / day_2026) - 1) < 1e-9, measured

    # By hand: the same hashrate gives half the blocks at twice the difficulty, and the ratio must come out at 1.
    point, _, _ = ratio_bounds(np.array([100]), np.array([50]), np.array([DAY / 2.0]), np.array([DAY / 4.0]), 0.05)
    assert abs(point[0] - 1) < 1e-12
    print('exposure: as computed by hand, difficulty changes included')

    # The pairs counted for Bonferroni are those a brute force finds.
    w_seconds, s_rounds = DAY, int(5 * DAY / ROUND_SECONDS)
    times = np.sort(np.random.default_rng(0).uniform(0, 40 * DAY, 5000))
    chain = Chain(times, np.array([times[0]]), np.array([1.0]))
    positions, _, _ = cells(chain, w_seconds)
    brute = sum(1 for i in range(len(positions)) for j in range(i + 1, len(positions)) if positions[j] >= positions[i] + w_seconds - 1e-6 and positions[j] + w_seconds - positions[i] <= s_rounds * ROUND_SECONDS + 1e-6)
    assert bracket(chain, s_rounds, 1)['pairs'] == brute, (bracket(chain, s_rounds, 1)['pairs'], brute)
    print(f'pairs: {brute}, same as brute force')

    # On a simulated chain, the hashrate comes out.
    chain, _, grid, h, weighted = simulate_chain('dip-14', 150, 1)
    positions, n, e = cells(chain, 3 * DAY)
    estimate = n / e * TARGET_SPACING
    truth = (np.interp(positions + 3 * DAY, grid, weighted) - np.interp(positions, grid, weighted)) / e
    assert np.median(np.abs(estimate / truth - 1)) < 0.05, np.median(np.abs(estimate / truth - 1))
    print(f'hashrate: median error {np.median(np.abs(estimate / truth - 1)):.3f} per 3 days, for about {np.sqrt(1 / (3 * 144)):.3f} expected')
    print('All checks passed.')


def bracket_task(args):
    """
    One cell of the table.

    Args:
    - args (tuple): The name of the period, its start and end, the window and the sub-window.

    Returns:
    - dict: The bracket, with the name of its period, or None if the period cannot hold the pair.
    """
    name, t_from, t_to, s_rounds, w_days = args
    row = bracket(CHAIN, s_rounds, w_days, t_from, t_to)
    return None if row is None else row | {'period': name}


def measure(args):
    """
    The measure on the real chain, and the comparison with the two other methods.

    Args:
    - args (argparse.Namespace): The command line.

    Returns:
    - None
    """
    global CHAIN
    CHAIN, time = chain_from_headers(args.headers)
    spans = {}
    tasks = []
    for name, first, last in PERIODS:
        t_from = float(np.maximum.accumulate(time)[first])
        t_to = float(time[-1] if last is None else np.maximum.accumulate(time)[last - 1])
        spans[name] = (t_from, t_to)
        tasks += [(name, t_from, t_to, s, w) for s in S_VALUES for w in W_DAYS if 2 * w * DAY <= s * ROUND_SECONDS]
    context = mp.get_context('fork')
    with context.Pool(args.workers) as pool:
        rows = [row for row in pool.map(bracket_task, tasks, chunksize=1) if row is not None]
    print(f'{len(rows)} brackets')

    frame = load_blocks(args.headers)
    genesis = frame.attrs['genesis_time']
    round_spans = {name: (int((a - genesis) // ROUND_SECONDS), int((b - genesis) // ROUND_SECONDS)) for name, (a, b) in spans.items()}
    series = {'old': smoothed_rounds(frame, K_SMOOTH), 'difficulty': difficulty_rounds(frame)}
    with context.Pool(min(args.workers, 8)) as pool:
        old = pool.map(old_statistics, [(method, rounds, s, round_spans) for method, rounds in series.items() for s in S_VALUES], chunksize=1)
    print('two other methods done')

    since, until = spans['since-2016']
    attack = {f'w={w}': attack_windows(CHAIN, ATTACK_S, w, since, until, REQUIREMENT_2) for w in (1, 3, 7)}

    # The timestamps of miners against the median time past, on the period the paper would quote.
    CHAIN, _ = chain_from_headers(args.headers, median_time_past=True)
    with context.Pool(args.workers) as pool:
        mtp = [row for row in pool.map(bracket_task, [t for t in tasks if t[0] == 'since-2016'], chunksize=1) if row is not None]

    result = {'n_headers': len(time), 'alpha': ALPHA, 'cells_per_w': CELLS_PER_W, 'spans': spans, 'brackets': rows, 'old': old, 'attack_share_since_2016': {'s': ATTACK_S, 'by_w': attack}, 'median_time_past_since_2016': mtp}
    with open(f'{args.out}.json', 'w') as f:
        json.dump(result, f, indent=1)
    by_method = {method: {row['s']: row['periods']['since-2016'] for row in old if row['method'] == method} for method in series}
    bracket_figure([row for row in rows if row['period'] == 'since-2016'], by_method, f'{args.out}.pdf')
    print(f'{args.out}.json and .pdf written')


def simulate(args):
    """
    The three methods against known hashrate paths, and the coverage of the interval on longer chains.

    Args:
    - args (argparse.Namespace): The command line.

    Returns:
    - None
    """
    scenarios = ['constant', 'dip-1', 'dip-3', 'dip-7', 'dip-14', 'dip-30', 'ramp']
    tasks = [(name, 150, 1000 * i + seed, True) for i, name in enumerate(scenarios) for seed in range(args.runs)]
    with mp.get_context('fork').Pool(args.workers) as pool:
        results = pool.map(one_simulation, tasks, chunksize=1)
        print('scenarios done')
        # Longer chains at a constant hashrate: many more pairs, and only retargeting to depart from the model.
        coverage = pool.map(one_simulation, [('constant', 730, 900_000 + seed, False) for seed in range(args.coverage_runs)], chunksize=1)
    out = {name: summarize([r for r in results if r['scenario'] == name]) for name in scenarios}
    out['coverage-constant-730-days'] = summarize(coverage)
    with open(args.out, 'w') as f:
        json.dump(out, f, indent=1)
    print(f'{args.out} written')


def coverage_run(task):
    """
    Whether the interval holds the truth on one chain at a constant hashrate.

    Args:
    - task (tuple): Whether the chain retargets, and the seed.

    Returns:
    - tuple: Whether the chain retargets, and whether the interval holds gamma = 1, by window and sub-window.
    """
    retargets, seed = task
    if retargets:
        chain = simulate_chain('constant', 730, 5_000_000 + seed)[0]
    else:
        times = np.cumsum(np.random.default_rng(7_000_000 + seed).exponential(TARGET_SPACING, int(730 * 144 * 1.1)))
        chain = Chain(times[times < 730 * DAY], np.array([0.0]), np.array([1.0]))
    return retargets, {f's={s},w={w}': bool(bracket(chain, s, w)['lower'] <= 1.0) for s in (72_000, 105_000) for w in (3, 7)}


def coverage(args):
    """
    The coverage of the interval, precisely enough to see what retargeting changes.

    Args:
    - args (argparse.Namespace): The command line.

    Returns:
    - None
    """
    with mp.get_context('fork').Pool(args.workers) as pool:
        results = pool.map(coverage_run, [(retargets, seed) for retargets in (True, False) for seed in range(args.runs)], chunksize=8)
    out = {'runs': args.runs, 'days': 730}
    for retargets, name in ((True, 'retarget'), (False, 'no-retarget')):
        rows = [row for flag, row in results if flag == retargets]
        out[name] = {key: float(np.mean([row[key] for row in rows])) for key in rows[0]}
    with open(args.out, 'w') as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out, indent=1))


def main():
    """
    Runs one command.

    Args:
    - None

    Returns:
    - None
    """
    parser = argparse.ArgumentParser(description='A measure of gamma that matches its definition: worst case, at a stated resolution, with an exact interval.')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('check', help='Check the computations.')
    p = commands.add_parser('measure', help='Measure on a headers file.')
    p.add_argument('headers')
    p.add_argument('--out', required=True, help='Prefix of the JSON file and of the figure.')
    p.add_argument('--workers', type=int, default=16)
    p = commands.add_parser('simulate', help='Compare the methods on chains with a known hashrate.')
    p.add_argument('--out', required=True, help='JSON file.')
    p.add_argument('--runs', type=int, default=100)
    p.add_argument('--coverage-runs', type=int, default=200)
    p.add_argument('--workers', type=int, default=16)
    p = commands.add_parser('coverage', help='Measure the coverage of the interval at a constant hashrate.')
    p.add_argument('--out', required=True, help='JSON file.')
    p.add_argument('--runs', type=int, default=2000)
    p.add_argument('--workers', type=int, default=16)
    args = parser.parse_args()
    if args.command == 'check':
        check()
    elif args.command == 'measure':
        measure(args)
    elif args.command == 'simulate':
        simulate(args)
    else:
        coverage(args)


if __name__ == '__main__':
    main()
