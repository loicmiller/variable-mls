"""Measures of the hashrate fluctuation gamma on the Bitcoin header chain.

    python -m experiments.gamma estimate HEADERS --out PREFIX     # the gamma notebook's estimator
    python -m experiments.gamma bound HEADERS --out PREFIX        # gamma(s, w) with exact intervals, by period
    python -m experiments.gamma simulate --out FILE               # all estimators against known hashrate paths
    python -m experiments.gamma coverage --out FILE               # coverage of the intervals at a constant hashrate

Each command writes a JSON file; figures.gamma draws them.
"""

import argparse
import json
import multiprocessing as mp

import numpy as np

from vmls import gamma, gamma_bound
from vmls.chain import load_headers

S_VALUES = [72_000, 105_000, 145_000, 271_000]
W_DAYS = [1, 3, 7, 14]
# By height; the last period ends at the tip.
PERIODS = [('2009-2012', 1, 210_000), ('2012-2016', 210_000, 420_000), ('2016-2020', 420_000, 630_000),
           ('2020-2024', 630_000, 840_000), ('2024-2026', 840_000, None), ('since-2016', 420_000, None), ('all', 1, None)]
# Requirement 2 of the draft, gamma < (a (tau-1) (2m+k) lambda / (c m theta) - zeta) / 2 at lambda = 1.4, zeta -> 0.
REQUIREMENT_2 = {'a=0.9, c=1.35': 1.516, 'a=0.99, c=1.05': 2.144, 'a, c -> 1': 2.274}
ATTACK_S = 105_000
SCENARIOS = ['constant', 'dip-1', 'dip-3', 'dip-7', 'dip-14', 'dip-30', 'ramp']
# What the notebook printed on the 865,043 blocks of headers.json.
NOTEBOOK = {72_000: {'classic': 9.481139, 'robust_max': 9.287758, 'q95': 1.539881, 'q99': 1.968455},
            271_000: {'classic': 34.961995, 'robust_max': 33.342730, 'q95': 3.888302, 'q99': 12.419624}}
NOTEBOOK_K_GAMMA = {144: 52.964829, 432: 41.930867, 1008: 34.961995, 2016: 31.909972, 4032: 30.481528, 8064: 27.083362}

CHAIN = None  # The chain the bound workers share, set before the pool forks.


def estimate(args: argparse.Namespace) -> dict:
    """The gamma notebook's estimator on one headers file.

    Args:
        args: The command line.

    Returns:
        The gammas by window, by smoothing window, the knee, and the end of the curve over time.

    Raises:
        AssertionError: With --check-notebook, if a value differs from what the notebook printed.
    """
    blocks = gamma.load_blocks(load_headers(args.headers))
    rounds = gamma.smoothed_rounds(blocks, gamma.K_SMOOTH)
    h = rounds['hashrate'].astype(float)
    h = h[h > 0].reset_index(drop=True)
    with mp.get_context('fork').Pool(len(S_VALUES)) as pool:
        rows = pool.starmap(gamma.gamma_row, [(h, s) for s in S_VALUES])
    k_gammas = {k: gamma.classic_gamma(gamma.smoothed_rounds(blocks, k)['hashrate'].astype(float), 271_000)
                for k in gamma.K_GRID}
    over_time = gamma.gamma_over_time(blocks, rounds, 271_000)
    result = {'n_headers': blocks.attrs['n_headers'], 'rounds': len(h), 'rows': rows, 'k_gammas_s_271000': k_gammas,
              'knee': gamma.knee(k_gammas),
              'evolution_s_271000': {'last': float(over_time['gamma'].iloc[-1]),
                                     'peak_after_2015': float(over_time.loc[over_time['height'] > 340_000, 'gamma'].max())}}
    if args.check_notebook:
        for row in rows:
            for key, value in NOTEBOOK.get(row['s'], {}).items():
                assert abs(row[key] - value) < 1e-5, (row['s'], key, row[key], value)
        for k, value in NOTEBOOK_K_GAMMA.items():
            assert abs(k_gammas[k] - value) < 1e-5, (k, k_gammas[k], value)
        assert result['knee'] == gamma.K_SMOOTH
        print('Same values as the notebook.')
    return result


def bracket_task(name: str, t_from: float, t_to: float, s_rounds: int, w_days: float) -> dict | None:
    """One cell of the table of brackets, on the shared chain.

    Args:
        name: Name of the period.
        t_from: Start of the period.
        t_to: End of the period.
        s_rounds: The window, in rounds.
        w_days: The sub-windows, in days.

    Returns:
        The bracket with its period, or None if the period cannot hold a pair.
    """
    row = gamma_bound.bracket(CHAIN, s_rounds, w_days, t_from, t_to)
    return None if row is None else row | {'period': name}


def notebook_statistics(method: str, rounds, s_rounds: int, spans: dict) -> dict:
    """The statistics of the notebook on each period.

    Args:
        method: 'old' (the notebook's estimator) or 'difficulty' (D / 10 minutes).
        rounds: Its hashrate per round.
        s_rounds: The window, in rounds.
        spans: First and last round of each period.

    Returns:
        For each period, the worst max/min and the q95 of the 1%-99% ratio.
    """
    classic, robust = gamma_bound.windowed(rounds, s_rounds)
    periods = {}
    for name, (r_from, r_to) in spans.items():
        c, q = classic.loc[r_from + s_rounds:r_to], robust.loc[r_from + s_rounds:r_to]
        periods[name] = {'max_min': float(c.max()), 'q95': float(q.quantile(0.95))}
    return {'method': method, 's': s_rounds, 'periods': periods}


def bound(args: argparse.Namespace) -> dict:
    """gamma(s, w) by period, the notebook's two estimators on the same periods, the share of windows open to the
    attack, and the same brackets with the median time past.

    Args:
        args: The command line.

    Returns:
        The results.
    """
    global CHAIN
    headers = load_headers(args.headers)
    CHAIN, time = gamma_bound.chain_from_headers(headers)
    monotonic = np.maximum.accumulate(time)
    spans, tasks = {}, []
    for name, first, last in PERIODS:
        t_from = float(monotonic[first])
        t_to = float(time[-1] if last is None else monotonic[last - 1])
        spans[name] = (t_from, t_to)
        tasks += [(name, t_from, t_to, s, w) for s in S_VALUES for w in W_DAYS
                  if 2 * w * gamma_bound.DAY <= s * gamma.ROUND_SECONDS]
    context = mp.get_context('fork')
    with context.Pool(args.workers) as pool:
        rows = [row for row in pool.starmap(bracket_task, tasks, chunksize=1) if row is not None]

    blocks = gamma.load_blocks(headers)
    genesis = blocks.attrs['genesis_time']
    round_spans = {name: (int((a - genesis) // gamma.ROUND_SECONDS), int((b - genesis) // gamma.ROUND_SECONDS))
                   for name, (a, b) in spans.items()}
    series = {'old': gamma.smoothed_rounds(blocks, gamma.K_SMOOTH), 'difficulty': gamma_bound.difficulty_rounds(blocks)}
    with context.Pool(min(args.workers, 8)) as pool:
        old = pool.starmap(notebook_statistics, [(method, rounds, s, round_spans) for method, rounds in series.items()
                                                 for s in S_VALUES], chunksize=1)

    since, until = spans['since-2016']
    attack = {f'w={w}': gamma_bound.attack_windows(CHAIN, ATTACK_S, w, since, until, REQUIREMENT_2) for w in (1, 3, 7)}

    CHAIN, _ = gamma_bound.chain_from_headers(headers, median_time_past=True)
    with context.Pool(args.workers) as pool:
        mtp = [row for row in pool.starmap(bracket_task, [t for t in tasks if t[0] == 'since-2016'], chunksize=1) if row]
    return {'n_headers': len(time), 'alpha': gamma_bound.ALPHA, 'cells_per_w': gamma_bound.CELLS_PER_W, 'spans': spans,
            'brackets': rows, 'old': old, 'attack_share_since_2016': {'s': ATTACK_S, 'by_w': attack},
            'median_time_past_since_2016': mtp}


def simulate(args: argparse.Namespace) -> dict:
    """All estimators against known hashrate paths, and the coverage of the interval on longer chains.

    Args:
        args: The command line.

    Returns:
        The summary of each scenario, and of the two-year chains at a constant hashrate.
    """
    tasks = [(name, 150, 1000 * i + seed, True) for i, name in enumerate(SCENARIOS) for seed in range(args.runs)]
    with mp.get_context('fork').Pool(args.workers) as pool:
        results = pool.starmap(gamma_bound.simulation, tasks, chunksize=1)
        coverage = pool.starmap(gamma_bound.simulation,
                                [('constant', 730, 900_000 + seed, False) for seed in range(args.coverage_runs)], chunksize=1)
    out = {name: gamma_bound.summarize([r for r in results if r['scenario'] == name]) for name in SCENARIOS}
    out['coverage-constant-730-days'] = gamma_bound.summarize(coverage)
    return out


def coverage(args: argparse.Namespace) -> dict:
    """Coverage of the intervals at a constant hashrate, with and without retargeting.

    Args:
        args: The command line.

    Returns:
        The share of runs whose interval holds gamma = 1, by window and sub-window.
    """
    with mp.get_context('fork').Pool(args.workers) as pool:
        results = pool.starmap(gamma_bound.coverage_run,
                               [(retargets, seed) for retargets in (True, False) for seed in range(args.runs)], chunksize=8)
    out = {'runs': args.runs, 'days': 730}
    for i, name in ((0, 'retarget'), (1, 'no-retarget')):
        rows = results[i * args.runs:(i + 1) * args.runs]
        out[name] = {key: float(np.mean([row[key] for row in rows])) for key in rows[0]}
    return out


def main() -> None:
    """Runs one command and writes its JSON file."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    commands = parser.add_subparsers(dest='command', required=True)
    for name, needs_headers in (('estimate', True), ('bound', True), ('simulate', False), ('coverage', False)):
        command = commands.add_parser(name)
        if needs_headers:
            command.add_argument('headers', help='Exported headers.')
        command.add_argument('--out', required=True, help='JSON file, or prefix for estimate and bound.')
        command.add_argument('--workers', type=int, default=16)
    commands.choices['estimate'].add_argument('--check-notebook', action='store_true',
                                              help='Compare with what the notebook printed on headers.json.')
    commands.choices['simulate'].add_argument('--runs', type=int, default=100)
    commands.choices['simulate'].add_argument('--coverage-runs', type=int, default=200)
    commands.choices['coverage'].add_argument('--runs', type=int, default=2000)
    args = parser.parse_args()
    result = {'estimate': estimate, 'bound': bound, 'simulate': simulate, 'coverage': coverage}[args.command](args)
    out = f'{args.out}.json' if args.command in ('estimate', 'bound') else args.out
    with open(out, 'w') as f:
        json.dump(result, f, indent=1)
    print(f'{out} written')


if __name__ == '__main__':
    main()
