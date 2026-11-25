"""The figures, drawn from the JSON and NPZ files of results/, at the width of a paper column.

Fonts are at their printed size (8 pt labels, 7 pt ticks and legends), in a serif family. Blue is CCS 2025, orange
our construction (a pair validated for colour vision deficiencies); line styles tell the values of K apart, so every
figure also reads in black and white. draw_all draws whatever the results allow and writes numbers.json, the figures'
numbers that a text quotes.

    vmls figures --results results --out-dir out
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use('pdf')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

COLUMN = 3.5  # Inches: one IEEE column.
BLUE, ORANGE, GRAY = '#2a78d6', '#eb6834', '#52514e'
PART_COLOURS = {'D': '#8f6fd1', 'X': '#4fb3bf', 'Omega': '#e3b23c'}  # Violet, aqua, yellow; each band also labelled.
NAMES = {'ccs2025': 'CCS 2025', 'ours': 'Our construction'}
COLOURS = {'ccs2025': BLUE, 'ours': ORANGE}
K_STYLE = {104: ':', 208: '-', 416: '--'}
EPOCH = 2016
STYLE = {
    'font.family': 'serif', 'font.serif': ['STIXGeneral', 'Times New Roman', 'DejaVu Serif'], 'mathtext.fontset': 'stix',
    'font.size': 8, 'axes.labelsize': 8, 'legend.fontsize': 7, 'xtick.labelsize': 7, 'ytick.labelsize': 7,
    'axes.linewidth': 0.5, 'axes.edgecolor': GRAY, 'xtick.color': GRAY, 'ytick.color': GRAY,
    'grid.color': '#e4e3df', 'grid.linewidth': 0.5, 'lines.linewidth': 1.2, 'legend.frameon': False,
    'axes.spines.top': False, 'axes.spines.right': False, 'pdf.fonttype': 42, 'savefig.dpi': 300,
}


def _result(path: Path) -> object:
    """The result part of a file written by the command line."""
    return json.loads(path.read_text())['result']


def _height_axis(ax: plt.Axes) -> None:
    """Block heights in thousands on the x axis, with a light grid."""
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x / 1000:.0f}k'))
    ax.set_xlabel('Block height')
    ax.grid(True)
    ax.set_axisbelow(True)


def _legend(fig: plt.Figure, Ks: list[int]) -> None:
    """One legend above the figure: a colour per construction, then a line style per K (in grey)."""
    handles = [plt.Line2D([], [], color=COLOURS[c], label=NAMES[c]) for c in NAMES]
    handles += [plt.Line2D([], [], color=GRAY, linestyle=K_STYLE[K], linewidth=0.9, label=f'$K^\\star$={K}') for K in Ks]
    fig.legend(handles=handles, loc='outside upper center', ncols=len(handles), handlelength=1.3,
               handletextpad=0.4, columnspacing=0.7)


def _replays(results: Path) -> dict[tuple[str, int], tuple[dict, dict]]:
    """Every replay of a results directory, by construction and K: its samples and per-block series."""
    runs = {}
    for path in sorted(results.glob('replay-*.json')):
        samples = _result(path)
        series = dict(np.load(path.with_suffix('.npz')))
        runs[(samples['construction'], samples['params']['K'])] = (samples, series)
    return runs


def time_figure(build: list[dict], runs: dict, out: Path) -> Path:
    """Left: building a proof from scratch against the height. Right: the median update per epoch.

    Args:
        build: The rows of vmls build-time.
        runs: The replays.
        out: Directory of the PDF.

    Returns:
        The path written.
    """
    fig, (left, right) = plt.subplots(1, 2, figsize=(COLUMN, 1.7), layout='constrained')
    for construction in NAMES:
        rows = sorted((r for r in build if r['construction'] == construction and r['K'] == 208), key=lambda r: r['height'])
        if rows:
            left.plot([r['height'] for r in rows], [r['total_s'] for r in rows], color=COLOURS[construction])
        for (c, K), (_, series) in sorted(runs.items()):
            if c == construction and K in K_STYLE:
                us = series['update_us'].astype(float)
                epochs = len(us) // EPOCH
                medians = np.median(us[:epochs * EPOCH].reshape(epochs, EPOCH), axis=1) / 1000
                right.plot(np.arange(epochs) * EPOCH, medians, color=COLOURS[c], linestyle=K_STYLE[K], linewidth=0.9)
    left.set_ylabel('Build from scratch (s)')
    right.set_ylabel('Update per block (ms)')
    for ax in (left, right):
        _height_axis(ax)
        ax.set_xlim(left=0)
        ax.set_ylim(bottom=0)
    _legend(fig, sorted({K for _, K in runs if K in K_STYLE}))
    path = out / 'time.pdf'
    fig.savefig(path)
    plt.close(fig)
    return path


def size_figure(runs: dict, out: Path) -> Path:
    """The number of blocks in the proof against the height, for each construction and K."""
    fig, ax = plt.subplots(figsize=(COLUMN, 1.8), layout='constrained')
    for (construction, K), (_, series) in sorted(runs.items()):
        ax.plot(series['proof_blocks'], color=COLOURS[construction], linestyle=K_STYLE.get(K, '-'), linewidth=0.9)
    ax.set_ylabel('Blocks in the proof')
    _height_axis(ax)
    _legend(fig, sorted({K for _, K in runs if K in K_STYLE}))
    path = out / 'proof-blocks.pdf'
    fig.savefig(path)
    plt.close(fig)
    return path


def sections_figure(sections: dict, out: Path, K: int = 208, log: bool = False) -> Path:
    """The size of D, X and Omega against the height, CCS 2025 (left) and ours (right), on a shared axis.

    Args:
        sections: The result of vmls sections.
        out: Directory of the PDF.
        K: The value of K drawn.
        log: Draw each part as a line on a log axis instead of stacked bands, so that small parts stay visible.

    Returns:
        The path written.
    """
    fig, axes = plt.subplots(1, 2, figsize=(COLUMN, 1.8), layout='constrained', sharey=True)
    for ax, construction in zip(axes, NAMES):
        rows = sorted((r for r in sections['rows'] if r['construction'] == construction and r['K'] == K),
                      key=lambda r: r['height'])
        x = [r['height'] for r in rows]
        ys = {part: np.array([r['bytes'][part] / 1e6 for r in rows]) for part in PART_COLOURS}
        if log:
            for part, y in ys.items():
                ax.plot(x, y, color=PART_COLOURS[part], label=part.replace('Omega', '$\\Omega$'))
            ax.set_yscale('log')
        else:
            ax.stackplot(x, *ys.values(), colors=list(PART_COLOURS.values()), linewidth=0,
                         labels=[p.replace('Omega', '$\\Omega$') for p in PART_COLOURS])
        ax.set_title(NAMES[construction], fontsize=8)
        _height_axis(ax)
    axes[0].set_ylabel('Proof size (MB)')
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='outside upper center', ncols=3)
    path = out / f'proof-sections{"-log" if log else ""}.pdf'
    fig.savefig(path)
    plt.close(fig)
    return path


def attack_figure(attack: dict, out: Path) -> Path:
    """The proof level of Bitcoin over time, and the success probability of the attack at each level."""
    fig, ax = plt.subplots(figsize=(COLUMN, 1.8), layout='constrained')
    rises = attack['rises']
    heights = [0] + [r['height'] for r in rises] + [attack['last_height']]
    levels = [0] + [r['level'] for r in rises] + [rises[-1]['level'] if rises else 0]
    ax.step(heights, levels, where='post', color=GRAY)
    for r in rises[-4:]:
        p = attack['p'][str(r['level'])] if isinstance(next(iter(attack['p'])), str) else attack['p'][r['level']]
        ax.annotate(f'p = {p:.2g}', (r['height'], r['level']), textcoords='offset points', xytext=(3, -9), fontsize=7)
    ax.set_ylabel('Proof level')
    ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
    _height_axis(ax)
    path = out / 'attack.pdf'
    fig.savefig(path)
    plt.close(fig)
    return path


def numbers(build: list[dict] | None, runs: dict, sections: dict | None) -> dict:
    """The numbers a text quotes: at the tip, build time, update, size by part and verifier, per construction and K."""
    out = {}
    for (construction, K), (samples, series) in sorted(runs.items()):
        us = series['update_us'].astype(float)
        row = {'update_ms_last_epoch': float(np.median(us[-EPOCH:]) / 1000), 'proof_blocks': int(series['proof_blocks'][-1])}
        verifier = samples['verifier']
        if verifier:
            row['verifier_ms_headers'] = float(np.median([v['ms_headers'] for v in verifier]))
            row['verifier_ms_model'] = float(np.median([v['ms_model'] for v in verifier]))
            row['verifier_ms_headers_tip'] = [v['ms_headers'] for v in verifier if v['height'] == samples['height']]
            row['branches'] = sorted({v['branch'] for v in verifier})
            if construction == 'ours':
                row['reveal_coverage_min'] = min(v['reveal_coverage'] for v in verifier)
        out[f'{construction}-K{K}'] = row
    for r in build or []:
        if r['height'] == max(b['height'] for b in build):
            out.setdefault(f'{r["construction"]}-K{r["K"]}', {})['build_s'] = r['total_s']
    if sections:
        top = max(r['height'] for r in sections['rows'])
        for r in sections['rows']:
            if r['height'] == top:
                out.setdefault(f'{r["construction"]}-K{r["K"]}', {})['bytes'] = r['bytes']
    return out


def draw_all(results: Path, out: Path) -> list[Path]:
    """Draws every figure the results allow and writes numbers.json.

    Args:
        results: Directory of the results (build-time.json, replay-*.json/.npz, sections.json, attack.json).
        out: Directory of the figures.

    Returns:
        The paths written.
    """
    plt.rcParams.update(STYLE)
    out.mkdir(parents=True, exist_ok=True)
    build = _result(results / 'build-time.json') if (results / 'build-time.json').exists() else None
    sections = _result(results / 'sections.json') if (results / 'sections.json').exists() else None
    runs = _replays(results)
    written = []
    if build and runs:
        written.append(time_figure(build, runs, out))
    if runs:
        written.append(size_figure(runs, out))
    if sections:
        written += [sections_figure(sections, out), sections_figure(sections, out, log=True)]
    if (results / 'attack.json').exists():
        written.append(attack_figure(_result(results / 'attack.json'), out))
    path = out / 'numbers.json'
    path.write_text(json.dumps(numbers(build, runs, sections), indent=1))
    written.append(path)
    return written
