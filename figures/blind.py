"""Figures of the blind-mining paper: proof size, construction from scratch and update per block, against CCS 2025.

Figures at the width of an IEEE column. Blue is the construction of CCS 2025, orange the blind one; line styles
tell the values of K apart, so the figures also read in black and white. Headers are the ones the papers write (no
Merkle root over the pointers). With --sections, two more figures give the size of the proof split into D, X and
Omega (violet, aqua and yellow, each band also labelled): headers of D and X, full blocks of Omega, as both papers
define it when proof_sections had the block sizes, headers only otherwise (files suffixed -headers).

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
SECTIONS = (('D', 'D (sampled headers)', '#6250d6'), ('X', r'X ($\chi$ headers)', '#1baf7a'),
            ('Omega', r'$\Omega$ ($k$ headers)', '#eda100'))  # Validated with the dataviz script.
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
    """Draws the number of blocks in the proof against the height, by K; its size is in the figures of its parts."""
    fig, ax = plt.subplots(figsize=(style.IEEE_COLUMN, 1.9), layout='constrained')
    for (mode, K), (arrays, _) in sorted(runs.items()):
        if mode == 'blind' or K == 208:
            medians = rolling_median(arrays['proof_size'] / 1000, EPOCH)
            ax.plot(np.arange(len(medians)) * EPOCH, medians, color=SCHEME_COLOUR[mode], linestyle=K_STYLE[K],
                    linewidth=0.9, label=f'{SCHEME_NAME[mode]}, $K^\\star$={K}')
    ax.set_ylim(bottom=0)
    ax.set_ylabel('Blocks in the proof (thousands)')
    height_ticks(ax, n)
    fig.legend(*_merged_legend(ax), loc='outside upper center', ncols=2, handlelength=2.2)
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


VARIANTS = {  # Field of experiments.proof_sections: file suffix, label of Omega, unit, scale.
    'bytes_full': ('', r'$\Omega$ ($k$ full blocks)', 'MB', 1e6),  # The proof, as both papers define it.
    'bytes': ('-headers', r'$\Omega$ ($k$ headers)', 'MB', 1e6),  # Fallback without block sizes: headers only.
}


def _sections(field: str) -> list[tuple[str, str, str]]:
    """The parts of a proof with the labels of one variant."""
    labels = {'D': 'D (sampled headers)', 'X': r'X ($\chi$ headers)', 'Omega': VARIANTS[field][1]}
    return [(key, labels[key], colour) for key, _, colour in SECTIONS]


def sections_bars(sections: dict, out: Path, field: str = 'bytes') -> None:
    """Draws the parts of the proof at the last height: blocks (left) and size (right), one bar per scheme and K."""
    suffix, _, unit, scale = VARIANTS[field]
    top = max(r['height'] for r in sections['rows'])
    rows = _section_rows(sections, top)
    bars = [(scheme, K) for scheme in ('draft', 'ccs') for K in (416, 208, 104) if (scheme, K) in rows]
    names = [f"{SCHEME_NAME['ccs' if scheme == 'ccs' else 'blind']}, {K}" for scheme, K in bars]
    fig, (left, right) = plt.subplots(1, 2, figsize=(style.IEEE_COLUMN, 1.75), layout='constrained', sharey=True)
    for ax, key_field, divisor in ((left, 'blocks', 1000), (right, field, scale)):
        start = np.zeros(len(bars))
        for key, label, colour in _sections(field):
            values = np.array([rows[bar][key_field][key] / divisor for bar in bars])
            ax.barh(range(len(bars)), values, left=start, height=0.7, color=colour, edgecolor='white',
                    linewidth=0.5, label=label)
            start += values
        for y, total in enumerate(start):
            text = f'{total:.1f}' if key_field == 'blocks' or unit == 'GB' else f'{total:.0f}'
            ax.annotate(text, (total, y), xytext=(2, 0), textcoords='offset points', va='center', fontsize=6.5,
                        color=style.GRAY)
        ax.set_xlim(0, start.max() * 1.22)
        ax.grid(True, axis='x')
        ax.set_axisbelow(True)
        ax.tick_params(axis='y', length=0)
    left.set_yticks(range(len(bars)), names)
    left.set_xlabel('Blocks (thousands)')
    right.set_xlabel(f'Size ({unit})')
    fig.legend(*left.get_legend_handles_labels(), loc='outside upper center', ncols=3, handlelength=1.2,
               columnspacing=0.8)
    fig.savefig(out / f'blind-proof-sections{suffix}.pdf')
    plt.close(fig)


def _stack(ax: plt.Axes, rows: list[dict], field: str, labels: bool, names: bool = True,
           fontsize: float = 7) -> None:
    """Stacks the size of D, X and Omega against the height, the tall bands labelled inside."""
    scale = VARIANTS[field][3]
    heights = [r['height'] for r in rows]
    stack = [[r[field][key] / scale for r in rows] for key, _, _ in SECTIONS]
    ax.stackplot(heights, stack, colors=[colour for _, _, colour in SECTIONS], edgecolor='white', linewidth=0.5,
                 labels=[label for _, label, _ in _sections(field)] if labels else ())
    total = sum(values[-1] for values in stack)
    base = 0.0
    for (key, _, _), values in zip(SECTIONS, stack):
        size = np.interp(LABEL_AT, heights, values)
        if names and values[-1] > 0.15 * total:  # Thin bands are named by the legend only.
            ax.annotate(key if key != 'Omega' else r'$\Omega$', (LABEL_AT, base + size / 2), ha='center',
                        va='center', fontsize=fontsize, color='white' if key == 'D' else '#1a1a19')
        base += size
    ax.set_xlim(0, heights[-1])


def sections_areas(sections: dict, out: Path, field: str = 'bytes', K: int = 208) -> None:
    """Draws the size of each part of the proof against the height, CCS 2025 (left) and blind (right), at one K.

    Both panels share the y axis, so that the heavier proof shows as heavier; an inset with its own axis zooms on
    the lighter one when it is too thin to read at that scale.
    """
    suffix, _, unit, scale = VARIANTS[field]
    fig, axes = plt.subplots(1, 2, figsize=(style.IEEE_COLUMN, 1.8), layout='constrained', sharey=True)
    by_scheme = {scheme: sorted((r for r in sections['rows'] if r['scheme'] == scheme and r['K'] == K),
                                key=lambda r: r['height']) for scheme in ('ccs', 'draft')}
    totals = {scheme: sum(rows[-1][field].values()) / scale for scheme, rows in by_scheme.items()}
    light = min(totals, key=totals.get) if max(totals.values()) > 4 * min(totals.values()) else None
    for ax, (scheme, rows) in zip(axes, by_scheme.items()):
        _stack(ax, rows, field, labels=scheme == 'ccs', names=scheme != light)  # The zoom names the light bands.
        name = SCHEME_NAME['ccs' if scheme == 'ccs' else 'blind']
        total = totals[scheme]
        ax.set_title(f'{name}: {total:.2f} {unit} at the tip' if unit == 'GB' else f'{name}: {total:.0f} {unit} at the tip',
                     fontsize=7)
        height_ticks(ax)
        ax.set_axisbelow(True)
        if scheme == light:
            zoom = ax.inset_axes([0.2, 0.3, 0.75, 0.55])
            _stack(zoom, rows, field, labels=False, fontsize=6)
            zoom.set_ylim(0, total * 1.15)
            zoom.set_xticks([])
            zoom.tick_params(axis='y', labelsize=6, length=2, pad=1)
            zoom.set_title(f'zoom, {unit}', fontsize=6, pad=2, color=style.GRAY)
            for spine in zoom.spines.values():
                spine.set_visible(True)
                spine.set_linewidth(0.5)
                spine.set_color(style.GRAY)
    axes[0].set_ylim(bottom=0)
    axes[0].set_ylabel(f'Proof size, $K^\\star$={K} ({unit})')
    fig.legend(*axes[0].get_legend_handles_labels(), loc='outside upper center', ncols=3, handlelength=1.2,
               columnspacing=0.8)
    fig.savefig(out / f'blind-proof-sections-height{suffix}.pdf')
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
        field = next(f for f in VARIANTS if all(f in r for r in sections['rows']))
        sections_bars(sections, out, field)
        sections_areas(sections, out, field)
        top = max(r['height'] for r in sections['rows'])
        result['sections'] = [r for r in sections['rows'] if r['height'] == top]
    (out / 'blind-numbers.json').write_text(json.dumps(result, indent=1))
    print(f'Figures and the numbers of the text in {out}')


if __name__ == '__main__':
    main()
