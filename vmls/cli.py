"""The command line: one subcommand per measurement, each writing JSON (and NPZ for per-block series) to results/.

    vmls export --datadir ~/.bitcoin --reference headers/headers.zip      headers of a synced node
    vmls block-sizes --datadir ~/.bitcoin --headers H                    size of every block (stopped node)
    vmls utxo --datadir ~/.bitcoin                                       size of the UTXO set at the tip
    vmls replay --construction ours --headers H -K 208                   proof grown block by block
    vmls build-time --headers H                                          proof built from the headers
    vmls verifier --headers H                                            two proofs checked and compared
    vmls sections --headers H --block-sizes S                            size of D, X and Omega
    vmls gamma classic --headers H --since 2020-01-01                    hashrate fluctuation
    vmls kstar --headers H                                               K* the security bound asks for
    vmls attack --headers H                                              zero-difficulty attack over time
    vmls figures --results results --out-dir out                         every figure the results allow

Headers are .json, .json.xz or the .zip of the repository. Nothing leaves the machine but RPC calls to the local node.
"""

import argparse
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from vmls import __version__
from vmls.chain import CONSTRUCTIONS, load_headers
from vmls.proof import Params

K_VALUES = [104, 208, 416]


def unix_time(day: str | None) -> int | None:
    """A date YYYY-MM-DD as a Unix time at 00:00 UTC, or None."""
    return None if day is None else int(datetime.strptime(day, '%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp())


def write(result: object, path: Path, args: argparse.Namespace) -> Path:
    """Writes a result with what produced it (command, version, Python, processor), never over an existing file.

    Args:
        result: The measurement.
        path: The JSON file.
        args: The command line, recorded with the result.

    Returns:
        The path written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {'command': ' '.join(sys.argv[1:]), 'args': {k: v for k, v in vars(args).items() if k != 'func'},
            'version': __version__, 'python': platform.python_version(), 'processor': platform.processor(),
            'date': datetime.now(timezone.utc).isoformat(timespec='seconds')}
    with open(path, 'x', encoding='utf-8') as f:
        json.dump({'meta': meta, 'result': result}, f, indent=1, default=str)
    print(f'Results in {path}')
    return path


def heights(n: int, step: int) -> list[int]:
    """Heights every step blocks, and the tip."""
    return list(range(step, n - 1, step)) + [n - 1]


def cmd_export(args: argparse.Namespace) -> None:
    """Exports the headers of a synced node, checked down to the genesis block and against an earlier export."""
    from vmls.node import Node, export_headers, extends, save_headers
    headers = export_headers(Node(args.url, args.datadir), args.margin)
    if args.reference and not extends(headers, load_headers(args.reference)):
        sys.exit(f'The export does not extend {args.reference}.')
    print(f'{len(headers)} headers in {save_headers(headers, args.out_dir)}')


def cmd_block_sizes(args: argparse.Namespace) -> None:
    """Reads the size of every block from the files of a stopped node."""
    from vmls.node import block_sizes
    sizes = block_sizes(args.datadir, load_headers(args.headers), args.threads)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    np.save(args.out, sizes)
    print(f'{args.out}: {len(sizes)} blocks, {sizes[sizes > 0].sum() / 1e9:.1f} GB, {int((sizes < 0).sum())} not found')


def cmd_utxo(args: argparse.Namespace) -> None:
    """Counts the UTXO set at the tip of a running node."""
    from vmls.node import Node, utxo_set
    write(utxo_set(Node(args.url, args.datadir)), Path(args.out), args)


def cmd_replay(args: argparse.Namespace) -> None:
    """Grows a proof over the chain and writes its samples (JSON) and per-block series (NPZ)."""
    from vmls.measure import replay
    p = Params(args.K, args.k, args.chi)
    headers = load_headers(args.headers)[:args.stop]
    stem = Path(args.out_dir) / f'replay-{args.construction}-up-to-{len(headers) - 1}-K-{p.K}-k-{p.k}'
    if stem.with_suffix('.json').exists():  # Before the run, which takes minutes.
        sys.exit(f'{stem.with_suffix(".json")} exists: results are never overwritten.')
    samples, series = replay(headers, args.construction, p)
    write(samples, stem.with_suffix('.json'), args)
    np.savez_compressed(stem.with_suffix('.npz'), **series)


def cmd_build_time(args: argparse.Namespace) -> None:
    """Times building a proof from scratch at several heights, for each construction and K."""
    from vmls.measure import build_time
    headers = load_headers(args.headers)
    rows = []
    for construction in args.construction:
        for K in args.K:
            rows += build_time(headers, construction, Params(K, args.k), heights(len(headers), args.step), args.repetitions)
            print(f'{construction} K={K}: {rows[-1]["one_pass_s"]:.2f} s at height {rows[-1]["height"]}')
    write(rows, Path(args.out), args)


def cmd_verifier(args: argparse.Namespace) -> None:
    """Times the verifier at several heights, against a fork near the tip and a fork deep in the chain."""
    from vmls.measure import verifier
    headers = load_headers(args.headers)
    rows = []
    for construction in args.construction:
        rows += verifier(headers, construction, args.K, args.k, heights(len(headers), args.step), args.v,
                         args.repetitions)
        for row in rows[-2:]:
            print(f'{construction} K={row["K"]}, {row["fork"]} fork at height {row["height"]}: '
                  f'{row["ms_headers"]:.1f} ms, {row["branch"]}')
    write(rows, Path(args.out), args)


def cmd_sections(args: argparse.Namespace) -> None:
    """Measures the size of D, X and Omega at several heights."""
    from vmls.measure import sections
    headers = load_headers(args.headers)
    sizes = np.load(args.block_sizes) if args.block_sizes else None
    rows = []
    for construction in args.construction:
        rows += sections(headers, construction, args.K, args.k, heights(len(headers), args.step), sizes)
    write({'n_headers': len(headers), 'full_blocks': sizes is not None, 'rows': rows}, Path(args.out), args)


def cmd_gamma(args: argparse.Namespace) -> None:
    """Measures the hashrate fluctuation gamma, classic or bounded."""
    from vmls import gamma
    headers = load_headers(args.headers)
    since = unix_time(args.since)
    result = gamma.classic(headers, since) if args.method == 'classic' else gamma.bound(headers, since, args.workers)
    write(result, Path(args.out), args)


def cmd_kstar(args: argparse.Namespace) -> None:
    """Measures what Bitcoin asks of v_mu and K*."""
    from vmls.measure import k_star
    result = k_star(load_headers(args.headers), args.K, since=unix_time(args.since))
    for row in result['levels']:
        print(f'mu {row["mu"]:2d}: spread {row["spread_recent"]:.3g}, K* >= {row["k_star"]:,.0f}')
    write(result, Path(args.out), args)


def cmd_attack(args: argparse.Namespace) -> None:
    """Dates the rises of the proof level and the attack probability at each."""
    from vmls.measure import attack
    write(attack(load_headers(args.headers), args.K, args.k, args.chi), Path(args.out), args)


def cmd_figures(args: argparse.Namespace) -> None:
    """Draws every figure the results directory allows."""
    from vmls import figures
    for path in figures.draw_all(Path(args.results), Path(args.out_dir), Path(args.timings) if args.timings else None):
        print(path)


def parser() -> argparse.ArgumentParser:
    """The command line."""
    top = argparse.ArgumentParser(prog='vmls', description=__doc__.split('\n\n')[0])
    top.add_argument('--version', action='version', version=__version__)
    sub = top.add_subparsers(required=True)

    def command(name: str, func, help_text: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_text, description=help_text)
        p.set_defaults(func=func)
        return p

    def node_options(p: argparse.ArgumentParser) -> None:
        p.add_argument('--datadir', default=None, help='Data directory of the node, for its cookie.')
        p.add_argument('--url', default='http://127.0.0.1:8332', help='RPC URL of the node.')

    def chain_options(p: argparse.ArgumentParser, many: bool = False) -> None:
        p.add_argument('--headers', required=True, help='Exported headers.')
        if many:
            p.add_argument('--construction', nargs='+', choices=CONSTRUCTIONS, default=list(CONSTRUCTIONS))
            p.add_argument('-K', type=int, nargs='+', default=K_VALUES, help='Values of the security parameter.')
        p.add_argument('-k', type=int, default=6, help='Common prefix parameter.')

    p = command('export', cmd_export, cmd_export.__doc__)
    node_options(p)
    p.add_argument('--reference', default=None, help='Earlier export the new one must extend.')
    p.add_argument('--margin', type=int, default=6, help='Blocks left out below the tip.')
    p.add_argument('--out-dir', default='headers')

    p = command('block-sizes', cmd_block_sizes, cmd_block_sizes.__doc__)
    p.add_argument('--datadir', required=True, help='Data directory of the stopped node.')
    p.add_argument('--headers', required=True, help='Exported headers, which fix heights.')
    p.add_argument('--threads', type=int, default=16)
    p.add_argument('--out', default='results/block-sizes.npy')

    p = command('utxo', cmd_utxo, cmd_utxo.__doc__)
    node_options(p)
    p.add_argument('--out', default='results/utxo.json')

    p = command('replay', cmd_replay, cmd_replay.__doc__)
    chain_options(p)
    p.add_argument('--construction', choices=CONSTRUCTIONS, required=True)
    p.add_argument('-K', type=int, default=208, help='Security parameter.')
    p.add_argument('-chi', type=int, default=4032, help='Length of X.')
    p.add_argument('--stop', type=int, default=None, help='Height to stop before.')
    p.add_argument('--out-dir', default='results')

    p = command('build-time', cmd_build_time, cmd_build_time.__doc__)
    chain_options(p, many=True)
    p.add_argument('--step', type=int, default=50_000, help='Blocks between two heights.')
    p.add_argument('--repetitions', type=int, default=5)
    p.add_argument('--out', default='results/build-time.json')

    p = command('verifier', cmd_verifier, cmd_verifier.__doc__)
    chain_options(p, many=True)
    p.add_argument('--step', type=int, default=8 * 2016, help='Blocks between two heights.')
    p.add_argument('-v', type=float, default=None, help='A constant factor v_mu of Score, instead of the one of each '
                                                        'level by the formula of Algorithm 4.')
    p.add_argument('--repetitions', type=int, default=5)
    p.add_argument('--out', default='results/verifier.json')

    p = command('sections', cmd_sections, cmd_sections.__doc__)
    chain_options(p, many=True)
    p.add_argument('--step', type=int, default=25_000)
    p.add_argument('--block-sizes', default=None, help='.npy from block-sizes, for the full blocks of Omega.')
    p.add_argument('--out', default='results/sections.json')

    p = command('gamma', cmd_gamma, cmd_gamma.__doc__)
    p.add_argument('method', choices=['classic', 'bound'])
    p.add_argument('--headers', required=True)
    p.add_argument('--since', default=None, help='Only blocks from this day on, YYYY-MM-DD.')
    p.add_argument('--workers', type=int, default=16)
    p.add_argument('--out', default='results/gamma.json')

    p = command('kstar', cmd_kstar, cmd_kstar.__doc__)
    p.add_argument('--headers', required=True)
    p.add_argument('-K', type=int, default=208)
    p.add_argument('--since', default='2020-01-01', help='Start of the recent period, YYYY-MM-DD.')
    p.add_argument('--out', default='results/kstar.json')

    p = command('attack', cmd_attack, cmd_attack.__doc__)
    p.add_argument('--headers', required=True)
    p.add_argument('-K', type=int, default=208)
    p.add_argument('-k', type=int, default=6)
    p.add_argument('-chi', type=int, default=4032)
    p.add_argument('--out', default='results/attack.json')

    p = command('figures', cmd_figures, cmd_figures.__doc__)
    p.add_argument('--results', default='results')
    p.add_argument('--out-dir', default='out')
    p.add_argument('--timings', help='Directory of replays and build-time run alone, whose timings replace those of '
                                     '--results.')
    return top


def main(argv: list[str] | None = None) -> None:
    """Runs one subcommand."""
    args = parser().parse_args(argv)
    args.func(args)
