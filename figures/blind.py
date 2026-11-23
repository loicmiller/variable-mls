"""Figures of the blind-mining paper: proof size, construction from scratch and update per block, against CCS 2025.

Two figures at the width of an IEEE column, two panels each. Blue is the construction of CCS 2025, orange the blind
one; line styles tell the values of K apart, so the figures also read in black and white.

    python -m figures.blind --build results/build-time-974505.json --runs results/blind
"""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from vmls import style

TICKS = [0, 200_000, 400_000, 600_000, 800_000]
K_STYLE = {104: ':', 208: '-', 416: '--'}
SCHEME_COLOUR = {'ccs': style.BLUE, 'blind': style.ORANGE}
SCHEME_NAME = {'ccs': 'CCS 2025', 'blind': 'Blind'}
LABEL_AT = 500_000  # Height of the direct labels.


def load_runs(directory: Path) -> dict[tuple[str, int], tuple[dict, dict]]:
    """Reads every run of experiments.proof_over_chain in a directory.

    Args:
        directory: Where the runs were written.

    Returns:
        For each (mode, K): the per-block arrays and the JSON summary.
    """
    runs = {}
    for meta_path in sorted(directory.glob('*-proof-over-chain-*.json')):
        meta = json.loads(meta_path.read_text())
        arrays = np.load(meta_path.with_suffix('.npz'))
        runs[meta['args']['mode'], meta['args']['K']] = {name: arrays[name] for name in arrays.files}, meta
    return runs


def rolling_median(values: np.ndarray, window: int) -> np.ndarray:
    """Median of each block of `window` consecutive values, one value per block.

    Args:
        values: The series.
        window: Values per block.

    Returns:
        The medians.
    """
    n = len(values) // window * window
    return np.median(values[:n].reshape(-1, window), axis=1)


def height_ticks(ax: plt.Axes, n: int | None = None) -> None:
    """Block heights on the x axis, in thousands, with a grid.

    Args:
        ax: The axes.
        n: Number of blocks, to fit the axis to the chain; None leaves the limits alone.
    """
    if n is not None:
        ax.set_xlim(0, n - 1)
    ax.set_xticks(TICKS[::2], [f'{t // 1000}k' if t else '0' for t in TICKS[::2]])
    ax.set_xlabel('Block height')
    ax.grid(True)


def size_figure(runs: dict, n: int, out: Path) -> None:
    """Draws the proof size: blocks by K (left) and bytes at K = 208 against all SPV headers (right)."""
    fig, (left, right) = plt.subplots(1, 2, figsize=(style.IEEE_COLUMN, 1.7), layout='constrained')
    for (mode, K), (arrays, _) in sorted(runs.items()):
        if mode == 'blind' or K == 208:
            left.plot(np.arange(len(arrays['proof_size'])), arrays['proof_size'] / 1000, color=SCHEME_COLOUR[mode],
                      linestyle=K_STYLE[K], linewidth=0.8, rasterized=True,
                      label=f'{SCHEME_NAME[mode]}, $K^\\star$={K}')
    left.set_ylim(bottom=0)
    left.set_ylabel('Blocks in the proof (thousands)')
    height_ticks(left, n)

    # Bytes at K* = 208, each line labelled at its end: the legend above is about K*.
    lines = [('ccs-merkle', style.BLUE, '-', 'CCS 2025'), ('draft-merkle', style.ORANGE, '-', 'Blind'),
             ('draft', style.ORANGE, '--', 'Blind, no Merkle')]
    for scheme, colour, line, name in lines:
        mode = 'ccs' if scheme.startswith('ccs') else 'blind'
        if (mode, 208) not in runs:
            continue
        samples = runs[mode, 208][1]['bytes']
        y = [s[scheme] / 1e6 for s in samples]
        right.plot([s['height'] for s in samples], y, color=colour, linestyle=line, linewidth=0.9)
        right.annotate(name, (LABEL_AT, np.interp(LABEL_AT, [s['height'] for s in samples], y)), xytext=(0, 2),
                       textcoords='offset points', ha='center', va='bottom', fontsize=6.5)
    heights = np.arange(n)
    right.plot(heights, 80 * heights / 1e6, color=style.GRAY, linestyle=':', linewidth=0.9)
    right.annotate('All headers', (LABEL_AT, 80 * LABEL_AT / 1e6), xytext=(0, -2), textcoords='offset points',
                   ha='center', va='top', fontsize=6.5, color=style.GRAY)
    right.set_yscale('log')
    right.set_ylim(0.5, 300)
    right.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f'{y:g}'))
    right.set_ylabel(r'Proof size, $K^\star$=208 (MB)')
    height_ticks(right, n)
    fig.legend(*_merged_legend(left), loc='outside upper center', ncols=2, handlelength=2.2)
    fig.savefig(out / 'blind-proof-size.pdf')
    plt.close(fig)


def _merged_legend(*axes: plt.Axes) -> tuple[list, list]:
    """Handles and labels of several axes, each label once."""
    handles, labels = [], []
    for ax in axes:
        for handle, label in zip(*ax.get_legend_handles_labels()):
            if label not in labels:
                handles.append(handle)
                labels.append(label)
    return handles, labels


def time_figure(build: dict, runs: dict, out: Path) -> None:
    """Draws the construction from scratch against the height (left) and the update per block (right)."""
    fig, (left, right) = plt.subplots(1, 2, figsize=(style.IEEE_COLUMN, 1.7), layout='constrained')
    for scheme, mode in (('ccs', 'ccs'), ('draft', 'blind')):
        for K in sorted(K_STYLE):
            rows = [r for r in build['rows'] if r['scheme'] == scheme and r['K'] == K]
            if not rows or (mode == 'ccs' and K != 208):
                continue
            total = [r['blocks_s'] + r['compress_s'] + r.get('merkle_s', 0) for r in rows]
            left.plot([r['height'] for r in rows], total, color=SCHEME_COLOUR[mode], linestyle=K_STYLE[K],
                      linewidth=0.9, marker='o' if K == 208 else None, markersize=2,
                      label=f'{SCHEME_NAME[mode]}, $K^\\star$={K}')
    left.set_ylim(bottom=0)
    left.set_ylabel('Build from scratch (s)')
    height_ticks(left)

    window = 2016
    for mode in ('ccs', 'blind'):
        if (mode, 208) not in runs:
            continue
        arrays = runs[mode, 208][0]
        update = (arrays['latency_base'] + arrays['latency_compress']).astype(float)
        if mode == 'blind':
            update += arrays['latency_merkle']
        medians = rolling_median(update / 1000, window)
        right.plot(np.arange(len(medians)) * window, medians, color=SCHEME_COLOUR[mode], linewidth=0.9)
    right.set_ylim(bottom=0)
    right.set_ylabel('Update per block (ms)')
    height_ticks(right)
    fig.legend(*_merged_legend(left), loc='outside upper center', ncols=2, handlelength=2.2)
    fig.savefig(out / 'blind-time.pdf')
    plt.close(fig)


def numbers(build: dict, runs: dict) -> dict:
    """The numbers quoted in the text, at the last height measured.

    Args:
        build: Output of experiments.build_time.
        runs: Output of load_runs.

    Returns:
        Build time and proof blocks by scheme and K; update time, bytes and verifier time by mode and K.
    """
    top = max(r['height'] for r in build['rows'])
    result = {'height': top, 'read_s': build.get('read_s'), 'build': {}, 'runs': {}}
    for r in build['rows']:
        if r['height'] == top:
            result['build'][f"{r['scheme']}-K{r['K']}"] = {
                'total_s': r['blocks_s'] + r['compress_s'] + r.get('merkle_s', 0), 'levels_s': r['blocks_s'],
                'compress_s': r['compress_s'], 'merkle_s': r.get('merkle_s'), 'proof_blocks': r['proof_blocks']}
    for (mode, K), (arrays, meta) in sorted(runs.items()):
        update = (arrays['latency_base'] + arrays['latency_compress']).astype(float) / 1000
        verifier = {}
        for sample in meta['verifier']:
            verifier.setdefault(f"{sample['fork']}-{sample['scheme']}-{sample['path']}", []).append(sample['ms'])
        result['runs'][f'{mode}-K{K}'] = {
            'blocks': int(arrays['proof_size'][-1]),
            'update_ms_median_last_epoch': float(np.median(update[-2016:])),
            'update_ms_p99_last_epoch': float(np.percentile(update[-2016:], 99)),
            'merkle_ms_median_last_epoch': float(np.median(arrays['latency_merkle'][-2016:] / 1000)),
            'bytes_last': meta['bytes'][-1] if meta['bytes'] else None,
            'verifier_ms': {key: {'n': len(v), 'median': float(np.median(v)), 'max': float(np.max(v))}
                            for key, v in sorted(verifier.items())}}
    return result


def main() -> None:
    """Draws the figures into the output directory and writes the numbers quoted in the text."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--build', required=True, help='Output of experiments.build_time.')
    parser.add_argument('--runs', required=True, help='Directory of the runs of experiments.proof_over_chain.')
    parser.add_argument('--out-dir', default='out/blind', help='Directory of the PDFs.')
    args = parser.parse_args()

    runs = load_runs(Path(args.runs))
    build = json.loads(Path(args.build).read_text())
    n = max(len(arrays['proof_size']) for arrays, _ in runs.values())
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    style.use()
    size_figure(runs, n, out)
    time_figure(build, runs, out)
    (out / 'blind-numbers.json').write_text(json.dumps(numbers(build, runs), indent=1))
    print(f'Two figures and the numbers of the text in {out}')


if __name__ == '__main__':
    main()
