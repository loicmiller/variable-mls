"""The hashrate fluctuation (vmls.gamma): the classic estimator and gamma(s, w), on simulated chains of known hashrate.

The simulation helpers live here: they mine a chain with Bitcoin's retargeting on a known hashrate path, so that
what each measure returns can be held against the truth. The slow tests reproduce, on the Bitcoin headers, the
values printed when gamma = 1.54 was first measured and the brackets of November 2026.
"""

import json

import numpy as np
import pandas as pd
import pytest
from scipy.stats import binomtest

from tests.conftest import HEADERS, REFERENCE, require
from vmls.chain import GENESIS_TARGET, load_headers
from vmls.encoding import target_to_bits
from vmls.gamma import (DAY, K_SMOOTH, ROUND_SECONDS, Chain, bound, bracket, cells, classic, difficulty_rounds,
                        ratio_bounds, smoothed_rounds, windowed)

EPOCH = 2016
TARGET_SPACING = 600
# Printed on the 865,043 headers of the CCS 2025 paper when gamma = 1.54 was first measured.
PRINTED = {72_000: {'classic': 9.481139, 'robust_max': 9.287758, 'q95': 1.539881, 'q99': 1.968455},
           271_000: {'classic': 34.961995, 'robust_max': 33.342730, 'q95': 3.888302, 'q99': 12.419624}}
PRINTED_K_GAMMA = {144: 52.964829, 432: 41.930867, 1008: 34.961995, 2016: 31.909972, 4032: 30.481528,
                   8064: 27.083362}


def _scenario_hashrate(name: str, grid_days: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """A known hashrate path: 'constant', 'dip-<days>' (half the hashrate for that many days, from day 60 to 74) or
    'ramp' (three times more over days 60 to 120)."""
    h = np.ones(len(grid_days))
    if name.startswith('dip-'):
        start = rng.uniform(60, 74)
        h[(grid_days >= start) & (grid_days < start + float(name[4:]))] = 0.5
    elif name == 'ramp':
        h = np.interp(grid_days, [60, 120], [1, 3])
    return h


def _simulate_chain(name: str, days: float, seed: int) -> tuple[Chain, pd.DataFrame, np.ndarray, np.ndarray, np.ndarray]:
    """Mines a chain with the retargeting of Bitcoin on a known hashrate path.

    Args:
        name: The scenario, see _scenario_hashrate.
        days: Length of the chain, in days.
        seed: The seed.

    Returns:
        The chain, its blocks (time, difficulty, height), a fine time grid, the hashrate on it, and the integral of
        h/D on it.
    """
    rng = np.random.default_rng(seed)
    grid = np.arange(0, days * DAY + 300, 300.0)
    h = _scenario_hashrate(name, grid / DAY, rng)
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


def _headers(blocks: pd.DataFrame) -> list[dict]:
    """Exported headers of a simulated chain, after a genesis block at time 0."""
    genesis = {'hash': '00', 'bits': f'{target_to_bits(GENESIS_TARGET):08x}', 'time': 0}
    return [genesis] + [{'hash': '00', 'bits': f'{target_to_bits(int(GENESIS_TARGET / d)):08x}', 'time': int(t)}
                        for t, d in zip(blocks['time'], blocks['difficulty'])]


def _true_gamma(chain: Chain, grid: np.ndarray, weighted: np.ndarray, s_rounds: int, w_days: float) -> float:
    """gamma(s, w) of a simulated chain, on the grid and with the weights of the measure."""
    w_seconds = w_days * DAY
    positions, _, e = cells(chain, w_seconds)
    mean = (np.interp(positions + w_seconds, grid, weighted) - np.interp(positions, grid, weighted)) / e
    best = 1.0
    for lag in range(4, int((s_rounds * ROUND_SECONDS - w_seconds) / (w_seconds / 4)) + 1):
        ratio = mean[:-lag] / mean[lag:]
        best = max(best, float(ratio.max()), float((1 / ratio).max()))
    return best


def _simulation(name: str, days: float, seed: int, with_classic: bool) -> dict:
    """gamma(s, w), and optionally the classic statistics, on one simulated chain, against the truth.

    Args:
        name: The scenario.
        days: Length of the chain, in days.
        seed: The seed.
        with_classic: Whether to also run the classic estimator and D / 10 minutes.

    Returns:
        What each method returns and the truth, for s = 72,000 and 105,000 rounds.
    """
    chain, blocks, grid, h, weighted = _simulate_chain(name, days, seed)
    out = {'scenario': name, 'seed': seed, 'blocks': len(chain.times)}
    for s_rounds in (72_000, 105_000):
        width = int(s_rounds * ROUND_SECONDS / 300)
        series = pd.Series(h)
        pointwise = float((series.rolling(width).max() / series.rolling(width).min()).max())
        row = {'definition': pointwise}
        for w_days in (1, 3, 7):
            b = bracket(chain, s_rounds, w_days)
            truth = _true_gamma(chain, grid, weighted, s_rounds, w_days)
            row[f'new-w{w_days}'] = {'lower': b['lower'], 'upper': b['upper'], 'point': b['point'], 'truth': truth,
                                     'covers_truth': bool(b['lower'] <= truth <= b['upper']),
                                     'covers_definition': bool(b['lower'] <= pointwise <= b['upper'])}
        if with_classic:
            for method, rounds in (('old', smoothed_rounds(blocks, K_SMOOTH)), ('difficulty', difficulty_rounds(blocks))):
                max_mins, robust = windowed(rounds, s_rounds)
                row[method] = {'max_min': float(max_mins.max()), 'q95': float(robust.quantile(0.95))}
        out[str(s_rounds)] = row
    return out


def _summarize(results: list[dict]) -> dict:
    """Medians and 10th-90th percentiles of the runs of one scenario, and how often the intervals hold the truth."""
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


def _coverage_run(retargets: bool, seed: int) -> dict[str, bool]:
    """Whether the interval holds gamma = 1 on a two-year chain at a constant hashrate, for s = 72,000 and 105,000
    rounds and w = 3 and 7 days."""
    if retargets:
        chain = _simulate_chain('constant', 730, 5_000_000 + seed)[0]
    else:
        times = np.cumsum(np.random.default_rng(7_000_000 + seed).exponential(TARGET_SPACING, int(730 * 144 * 1.1)))
        chain = Chain(times[times < 730 * DAY], np.array([0.0]), np.array([1.0]))
    return {f's={s},w={w}': bool(bracket(chain, s, w)['lower'] <= 1.0) for s in (72_000, 105_000) for w in (3, 7)}


def _close(a, b, rel: float = 1e-12) -> bool:
    """Whether two JSON values are equal, floats up to a relative tolerance (parallel sums change the last bits)."""
    if isinstance(a, dict):
        return isinstance(b, dict) and a.keys() == b.keys() and all(_close(a[key], b[key], rel) for key in a)
    if isinstance(a, list):
        return isinstance(b, list) and len(a) == len(b) and all(_close(x, y, rel) for x, y in zip(a, b))
    if isinstance(a, float) or isinstance(b, float):
        return a == pytest.approx(b, rel=rel)
    return a == b


# gamma(s, w).

def test_interval_is_the_exact_binomial_one():
    # With equal exposures, the ratio is pi / (1 - pi).
    for n_a, n_b, alpha in ((10, 30, 0.05), (144, 100, 0.001), (1, 0, 0.05), (0, 7, 0.05), (2000, 2100, 1e-6)):
        ci = binomtest(n_a, n_a + n_b).proportion_ci(1 - alpha, method='exact')
        _, low, high = ratio_bounds(np.array([n_a]), np.array([n_b]), np.array([1.0]), np.array([1.0]), alpha)
        assert abs(low[0] - ci.low / (1 - ci.low)) < 1e-6 * (1 + low[0])
        if n_b > 0:
            assert abs(high[0] - ci.high / (1 - ci.high)) < 1e-6 * high[0]


def test_exposure_by_hand():
    # One day at difficulty 2, then one at difficulty 4.
    chain = Chain(np.array([0.0, 2.0 * DAY]), np.array([0.0, float(DAY)]), np.array([2.0, 4.0]))
    start = chain.exposure(np.array([0.0]))[0]
    assert abs(chain.exposure(np.array([2.0 * DAY]))[0] - start - (DAY / 2 + DAY / 4)) < 1e-6
    assert abs(chain.exposure(np.array([1.5 * DAY]))[0] - start - (DAY / 2 + DAY / 8)) < 1e-6
    # The same hashrate gives half the blocks at twice the difficulty: the ratio is 1.
    point, _, _ = ratio_bounds(np.array([100]), np.array([50]), np.array([DAY / 2.0]), np.array([DAY / 4.0]), 0.05)
    assert abs(point[0] - 1) < 1e-12


def test_exposure_keeps_its_precision_over_the_whole_chain():
    # A day at the difficulty of 2026, after years at difficulty 1.
    day_2026 = 1.5e14
    chain = Chain(np.array([0.0, 400.0 * DAY]), np.array([0.0, 300.0 * DAY]), np.array([1.0, day_2026]))
    measured = np.diff(chain.exposure(np.array([350.0 * DAY, 351.0 * DAY])))[0]
    assert abs(measured / (DAY / day_2026) - 1) < 1e-9


def test_pairs_are_those_a_brute_force_finds():
    w_seconds, s_rounds = DAY, int(5 * DAY / ROUND_SECONDS)
    times = np.sort(np.random.default_rng(0).uniform(0, 40 * DAY, 5000))
    chain = Chain(times, np.array([times[0]]), np.array([1.0]))
    positions, _, _ = cells(chain, w_seconds)
    brute = sum(1 for i in range(len(positions)) for j in range(i + 1, len(positions))
                if positions[j] >= positions[i] + w_seconds - 1e-6
                and positions[j] + w_seconds - positions[i] <= s_rounds * ROUND_SECONDS + 1e-6)
    assert bracket(chain, s_rounds, 1)['pairs'] == brute


def test_simulated_hashrate_comes_out():
    chain, _, grid, _, weighted = _simulate_chain('dip-14', 150, 1)
    positions, n, e = cells(chain, 3 * DAY)
    estimate = n / e * TARGET_SPACING
    truth = (np.interp(positions + 3 * DAY, grid, weighted) - np.interp(positions, grid, weighted)) / e
    assert np.median(np.abs(estimate / truth - 1)) < 0.05


def test_interval_holds_a_known_drop():
    chain, _, _, _, _ = _simulate_chain('dip-7', 150, 2)
    result = bracket(chain, 72_000, 3)
    assert result['lower'] <= 2.0 <= result['upper']


def test_intervals_hold_the_true_gamma_on_known_paths():
    for name in ('dip-3', 'dip-14', 'ramp'):
        summary = _summarize([_simulation(name, 150, 100 * i + seed, with_classic=False)
                              for i, seed in enumerate(range(3))])
        for s in ('72000', '105000'):
            for w in (1, 3, 7):
                assert summary[s][f'new-w{w}']['coverage_truth'] == 1.0, (name, s, w)


def test_intervals_hold_gamma_one_at_a_constant_hashrate():
    for retargets in (True, False):
        for seed in range(3):
            assert all(_coverage_run(retargets, seed).values()), (retargets, seed)


# The classic estimator.

def test_classic_is_close_to_one_at_a_constant_hashrate():
    _, blocks, _, _, _ = _simulate_chain('constant', 150, 3)
    result = classic(_headers(blocks), s_values=(72_000,))
    row = result['rows'][0]
    assert row['s'] == 72_000 and row['q95'] < 1.3 and row['classic'] < 1.5
    assert set(result['k_gamma']) == {144, 432, 1008, 2016, 4032, 8064}


def test_since_cuts_the_period():
    _, blocks, _, _, _ = _simulate_chain('dip-14', 150, 4)  # Half the hashrate for 14 days, starting by day 74.
    headers = _headers(blocks)
    since = 100 * DAY
    whole = classic(headers, s_values=(72_000,))
    recent = classic(headers, since=since, s_values=(72_000,))
    assert recent['from_time'] >= since and whole['from_time'] < since
    assert 'k_gamma' not in recent
    assert whole['rows'][0]['classic'] > 1.6  # The dip, seen through the smoothing.
    assert recent['rows'][0]['classic'] < 1.3 < whole['rows'][0]['classic']
    assert recent['rounds'] < whole['rounds']


def test_classic_statistics_with_the_classic_tools():
    result = _simulation('dip-7', 150, 5, with_classic=True)
    old = result['72000']['old']
    assert old['max_min'] >= old['q95'] >= 1.0


def test_workers_without_fork_give_the_same_results(monkeypatch):
    """Windows has no fork: spawned workers must compute the same statistics and see the same shared chain."""
    from vmls import gamma
    chain, blocks, _, _, _ = _simulate_chain('dip-7', 150, 6)
    headers = _headers(blocks)
    forked = classic(headers, s_values=(72_000,))
    cell = ('all', chain.start, chain.end, 72_000, 1)
    monkeypatch.setattr(gamma.mp, 'get_all_start_methods', lambda: ['spawn'])
    assert classic(headers, s_values=(72_000,)) == forked
    with gamma._pool(2, chain) as pool:
        spawned = pool.starmap(gamma._bracket_task, [cell])[0]
    expected = bracket(chain, 72_000, 1, cell[1], cell[2])
    assert spawned == (None if expected is None else expected | {'period': 'all'})


# Regressions on the Bitcoin headers.

@pytest.mark.slow
def test_classic_reproduces_the_printed_values():
    reference = json.loads(require(REFERENCE / 'gamma-865042.json').read_text())
    headers = load_headers(require(HEADERS.parent / 'headers.json'))
    result = classic(headers, s_values=(72_000, 271_000))
    rows = {row['s']: row for row in result['rows']}
    assert rows[72_000]['q95'] == pytest.approx(reference['rows'][0]['q95'], rel=1e-12)
    for s, printed in PRINTED.items():
        for key, value in printed.items():
            assert abs(rows[s][key] - value) < 1e-5, (s, key)
    for k, value in PRINTED_K_GAMMA.items():
        assert abs(result['k_gamma'][k] - value) < 1e-5, k
    assert result['knee'] == K_SMOOTH


@pytest.mark.slow
def test_bound_reproduces_the_brackets_of_november_2026():
    reference = json.loads(require(REFERENCE / 'gamma-bound-974505.json').read_text())
    headers = load_headers(require(HEADERS))
    if reference['n_headers'] != len(headers):
        pytest.skip('reference measured on another headers file')
    assert _close(json.loads(json.dumps(bound(headers, workers=16))), reference)
