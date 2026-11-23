"""Figures of the blind-mining paper: proof size, construction from scratch and update per block, against CCS 2025.

Figures at the width of an IEEE column, two panels each. Blue is the construction of CCS 2025, orange the blind
one; line styles tell the values of K apart, so the figures also read in black and white. Headers are the ones the
papers write (no Merkle root over the pointers). With --sections, two more figures split the proof into D, X and
Omega: violet, aqua and yellow, each band also labelled.

    python -m figures.blind --build results/build-time.json --runs results/blind --sections results/proof-sections.json
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
SECTIONS = (('D', 'D (compressed)', '#6250d6'), ('X', r'X ($\chi$ blocks)', '#1baf7a'),
            ('Omega', r'$\Omega$ (headers only)', '#eda100'))  # Validated with the dataviz script.
EPOCH = 2016  # Blocks per median on the per-block curves.


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
            medians = rolling_median(arrays['proof_size'] / 1000, EPOCH)
            left.plot(np.arange(len(medians)) * EPOCH, medians, color=SCHEME_COLOUR[mode], linestyle=K_STYLE[K],
                      linewidth=0.9, label=f'{SCHEME_NAME[mode]}, $K^\\star$={K}')
    left.set_ylim(bottom=0)
    left.set_ylabel('Blocks in the proof (thousands)')
    height_ticks(left, n)

    # Bytes at K* = 208, each line labelled at its end: the legend above is about K*.
    lines = [('ccs', style.BLUE, '-', 'CCS 2025'), ('draft', style.ORANGE, '-', 'Blind')]
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
    spv_at = 540_000  # The label starts here, under the line, which rises away from it.
    right.annotate('All headers (SPV)', (spv_at, 80 * spv_at / 1e6), xytext=(0, -6), textcoords='offset points',
                   ha='left', va='top', fontsize=6.5, color=style.GRAY)
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
            if not rows or K != 208:  # Without Merkle trees, K barely changes the build time.
                continue
            total = [r['blocks_s'] + r['compress_s'] for r in rows]
            left.plot([r['height'] for r in rows], total, color=SCHEME_COLOUR[mode], linestyle=K_STYLE[K],
                      linewidth=0.9, marker='o', markersize=2,
                      label=f'{SCHEME_NAME[mode]}, $K^\\star$={K}')
    left.set_ylim(bottom=0)
    left.set_ylabel('Build from scratch (s)')
    height_ticks(left)

    for mode in ('ccs', 'blind'):
        if (mode, 208) not in runs:
            continue
        arrays = runs[mode, 208][0]
        update = (arrays['latency_base'] + arrays['latency_compress']).astype(float)
        medians = rolling_median(update / 1000, EPOCH)
        right.plot(np.arange(len(medians)) * EPOCH, medians, color=SCHEME_COLOUR[mode], linewidth=0.9)
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
                'total_s': r['blocks_s'] + r['compress_s'], 'levels_s': r['blocks_s'],
                'compress_s': r['compress_s'], 'proof_blocks': r['proof_blocks']}
    for (mode, K), (arrays, meta) in sorted(runs.items()):
        update = (arrays['latency_base'] + arrays['latency_compress']).astype(float) / 1000
        verifier = {}
        for sample in meta['verifier']:
            verifier.setdefault(f"{sample['fork']}-{sample['scheme']}-{sample['path']}", []).append(sample['ms'])
        result['runs'][f'{mode}-K{K}'] = {
            'blocks': int(arrays['proof_size'][-1]),
            'update_ms_median_last_epoch': float(np.median(update[-2016:])),
            'update_ms_p99_last_epoch': float(np.percentile(update[-2016:], 99)),
            'bytes_last': ({key: v for key, v in meta['bytes'][-1].items() if 'merkle' not in key}
                           if meta['bytes'] else None),
            'verifier_ms': {key: {'n': len(v), 'median': float(np.median(v)), 'max': float(np.max(v))}
                            for key, v in sorted(verifier.items()) if 'merkle' not in key}}
    return result


def _section_rows(sections: dict, height: int) -> dict[tuple[str, int], dict]:
    """The rows of experiments.proof_sections at one height, by (scheme, K)."""
    return {(r['scheme'], r['K']): r for r in sections['rows'] if r['height'] == height}


def sections_bars(sections: dict, out: Path) -> None:
    """Draws the parts of the proof at the last height: blocks (left) and megabytes (right), one bar per scheme and K."""
    top = max(r['height'] for r in sections['rows'])
    rows = _section_rows(sections, top)
    bars = [(scheme, K) for scheme in ('draft', 'ccs') for K in (416, 208, 104) if (scheme, K) in rows]
    names = [f"{SCHEME_NAME['ccs' if scheme == 'ccs' else 'blind']}, {K}" for scheme, K in bars]
    fig, (left, right) = plt.subplots(1, 2, figsize=(style.IEEE_COLUMN, 1.75), layout='constrained', sharey=True)
    for ax, unit, scale in ((left, 'blocks', 1000), (right, 'bytes', 1e6)):
        start = np.zeros(len(bars))
        for key, label, colour in SECTIONS:
            values = np.array([rows[bar][unit][key] / scale for bar in bars])
            ax.barh(range(len(bars)), values, left=start, height=0.7, color=colour, edgecolor='white',
                    linewidth=0.5, label=label)
            start += values
        for y, total in enumerate(start):
            ax.annotate(f'{total:.1f}' if unit == 'blocks' else f'{total:.0f}', (total, y), xytext=(2, 0),
                        textcoords='offset points', va='center', fontsize=6.5, color=style.GRAY)
        ax.set_xlim(0, start.max() * 1.22)
        ax.grid(True, axis='x')
        ax.set_axisbelow(True)
        ax.tick_params(axis='y', length=0)
    left.set_yticks(range(len(bars)), names)
    left.set_xlabel('Blocks (thousands)')
    right.set_xlabel('Size (MB)')
    fig.legend(*left.get_legend_handles_labels(), loc='outside upper center', ncols=3, handlelength=1.2,
               columnspacing=1.0)
    fig.savefig(out / 'blind-proof-sections.pdf')
    plt.close(fig)


def _stack(ax: plt.Axes, rows: list[dict], labels: bool, names: bool = True, fontsize: float = 7) -> None:
    """Stacks the megabytes of D, X and Omega against the height, D and X labelled inside their band."""
    heights = [r['height'] for r in rows]
    stack = [[r['bytes'][key] / 1e6 for r in rows] for key, _, _ in SECTIONS]
    ax.stackplot(heights, stack, colors=[colour for _, _, colour in SECTIONS], edgecolor='white', linewidth=0.5,
                 labels=[label for _, label, _ in SECTIONS] if labels else ())
    base = 0.0
    for (key, _, _), values in zip(SECTIONS, stack):
        size = np.interp(LABEL_AT, heights, values)
        if names and key != 'Omega':  # Omega is a thin band, named by the legend only.
            ax.annotate(key, (LABEL_AT, base + size / 2), ha='center', va='center', fontsize=fontsize,
                        color='white' if key == 'D' else '#1a1a19')
        base += size
    ax.set_xlim(0, heights[-1])


def sections_areas(sections: dict, out: Path, K: int = 208) -> None:
    """Draws the megabytes of each part of the proof against the height, CCS 2025 (left) and blind (right), at one K.

    Both panels share the y axis, so that the blind proof shows as the 18 times heavier one it is; an inset with
    its own axis zooms on CCS 2025, whose band is too thin to read at that scale.
    """
    fig, axes = plt.subplots(1, 2, figsize=(style.IEEE_COLUMN, 1.8), layout='constrained', sharey=True)
    for ax, scheme in zip(axes, ('ccs', 'draft')):
        rows = sorted((r for r in sections['rows'] if r['scheme'] == scheme and r['K'] == K), key=lambda r: r['height'])
        _stack(ax, rows, labels=scheme == 'ccs', names=scheme != 'ccs')  # The zoom names the CCS bands.
        total = sum(rows[-1]['bytes'].values()) / 1e6
        ax.set_title(f"{SCHEME_NAME['ccs' if scheme == 'ccs' else 'blind']}: {total:.0f} MB at the tip", fontsize=7)
        height_ticks(ax)
        ax.set_axisbelow(True)
        if scheme == 'ccs':
            zoom = ax.inset_axes([0.2, 0.3, 0.75, 0.55])
            _stack(zoom, rows, labels=False, fontsize=6)
            zoom.set_ylim(0, total * 1.15)
            zoom.set_xticks([])
            zoom.tick_params(axis='y', labelsize=6, length=2, pad=1)
            zoom.set_title('zoom, MB', fontsize=6, pad=2, color=style.GRAY)
            for spine in zoom.spines.values():
                spine.set_visible(True)
                spine.set_linewidth(0.5)
                spine.set_color(style.GRAY)
    axes[0].set_ylim(bottom=0)
    axes[0].set_ylabel(f'Proof size, $K^\\star$={K} (MB)')
    fig.legend(*axes[0].get_legend_handles_labels(), loc='outside upper center', ncols=3, handlelength=1.2,
               columnspacing=1.0)
    fig.savefig(out / 'blind-proof-sections-height.pdf')
    plt.close(fig)

def main() -> None:
    """Draws the figures into the output directory and writes the numbers quoted in the text."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--build', required=True, help='Output of experiments.build_time.')
    parser.add_argument('--runs', required=True, help='Directory of the runs of experiments.proof_over_chain.')
    parser.add_argument('--sections', default=None, help='Output of experiments.proof_sections (optional).')
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
    result = numbers(build, runs)
    if args.sections:
        sections = json.loads(Path(args.sections).read_text())
        sections_bars(sections, out)
        sections_areas(sections, out)
        top = max(r['height'] for r in sections['rows'])
        result['sections'] = [r for r in sections['rows'] if r['height'] == top]
    (out / 'blind-numbers.json').write_text(json.dumps(result, indent=1))
    print(f'Figures and the numbers of the text in {out}')


if __name__ == '__main__':
    main()
