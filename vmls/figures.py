"""The figures, drawn from the JSON and NPZ files of results/, at the width of a paper column.

Fonts are at their printed size (8 pt labels, 7 pt ticks and legends), in a serif family. Colour names the construction
(blue CCS 2025, orange ours) and line style the value of K (dotted 104, solid 208, dashed 416), in every figure, so
that each also reads in black and white; markers sit only on sparse measured points. The parts of a proof (D, X, Omega)
take three other hues, and never share a figure with the two of the constructions, which are then split into panels. draw_all draws whatever the results allow and writes numbers.json, the figures'
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
# Violet, aqua, yellow. Each palette passes the dataviz validator alone (--pairs all, light surface): the constructions
# with CVD ΔE 24.7, the parts with 9.1; together they would not, so they never share a figure.
PART_COLOURS = {'D': '#6250d6', 'X': '#1baf7a', 'Omega': '#eda100'}
PART_NAMES = {'D': 'D (sampled headers)', 'X': 'X ($\\chi$ headers)', 'Omega': '$\\Omega$ ($k$ full blocks)'}
PART_INK = {'D': 'white', 'X': '#1a1a19', 'Omega': '#1a1a19'}  # Label inside each band.
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
            left.plot([r['height'] for r in rows], [r.get('one_pass_s', r['total_s']) for r in rows],
                      color=COLOURS[construction], linewidth=1.0, marker='o', markersize=3,
                      markeredgewidth=0)  # The measured heights; a ring would cut the line into dashes (K = 416).
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
    """The number of blocks in the proof against the height (median over each epoch), for each construction and K."""
    fig, ax = plt.subplots(figsize=(COLUMN, 1.8), layout='constrained')
    for (construction, K), (_, series) in sorted(runs.items()):
        if construction == 'ccs2025' and K != 208 and ('ours', K) in runs:
            continue  # CCS 2025 coincides with ours at every K: one value of K shows it (the caption says so).
        blocks = series['proof_blocks'].astype(float)
        epochs = len(blocks) // EPOCH  # Per block, the jitter would hide the line styles.
        ax.plot(np.arange(epochs) * EPOCH, np.median(blocks[:epochs * EPOCH].reshape(epochs, EPOCH), axis=1),
                color=COLOURS[construction], linestyle=K_STYLE.get(K, '-'), linewidth=0.9)
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
        K: The value of K drawn, or the smallest one measured if it was not.
        log: Draw each part as a line on a log axis instead of stacked bands, so that small parts stay visible.

    Returns:
        The path written.
    """
    measured = {r['K'] for r in sections['rows']}
    K = K if K in measured else min(measured)  # A run without K = 208 (tests, other chains) draws its smallest K.
    fig, axes = plt.subplots(1, 2, figsize=(COLUMN, 1.9), layout='constrained', sharey=True)
    bands = {}
    for ax, construction in zip(axes, NAMES):
        rows = sorted((r for r in sections['rows'] if r['construction'] == construction and r['K'] == K),
                      key=lambda r: r['height'])
        x = np.array([r['height'] for r in rows])
        ys = {part: np.array([r['bytes'][part] / 1e6 for r in rows]) for part in PART_COLOURS}
        if log:
            for part, y in ys.items():
                ax.plot(x, y, color=PART_COLOURS[part], label=PART_NAMES[part])
            ax.set_yscale('log')
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f'{y:g}'))
        else:
            ax.stackplot(x, *ys.values(), colors=list(PART_COLOURS.values()), edgecolor='white', linewidth=0.5,
                         labels=[PART_NAMES[part] for part in PART_COLOURS])
            bands[ax] = (x, ys)
        ax.set_title(f'{NAMES[construction]} ({sum(y[-1] for y in ys.values()):.1f} MB)', fontsize=8)
        _height_axis(ax)
    top = axes[0].get_ylim()[1]
    for ax, (x, ys) in bands.items():  # Each band tall enough for its name gets it, at three quarters of the height.
        i, base = int(0.75 * (len(x) - 1)), 0.0
        for part, y in ys.items():
            if y[i] >= 0.12 * top:
                ax.text(x[i], base + y[i] / 2, part.replace('Omega', '$\\Omega$'), ha='center', va='center',
                        fontsize=7, color=PART_INK[part])
            base += y[i]
    axes[0].set_ylabel(f'Proof size, $K^\\star$={K} (MB)')
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='outside upper center', ncols=3, handlelength=1.2, columnspacing=0.8)
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
            row = out.setdefault(f'{r["construction"]}-K{r["K"]}', {})
            row['build_s'] = r.get('one_pass_s', r['total_s'])  # The one-pass prover, when measured.
            row['build_levels_then_compress_s'] = r['total_s']
    if sections:
        top = max(r['height'] for r in sections['rows'])
        for r in sections['rows']:
            if r['height'] == top:
                out.setdefault(f'{r["construction"]}-K{r["K"]}', {})['bytes'] = r['bytes']
    return out


def draw_all(results: Path, out: Path, timings: Path | None = None) -> list[Path]:
    """Draws every figure the results allow and writes numbers.json.

    Args:
        results: Directory of the results (build-time.json, replay-*.json/.npz, sections.json, attack.json).
        out: Directory of the figures.
        timings: Directory of replays (with or without verifier) and build-time.json measured alone, whose update
            series and build times replace those of results; the proofs must be the same.

    Returns:
        The paths written.
    """
    plt.rcParams.update(STYLE)
    out.mkdir(parents=True, exist_ok=True)
    build = _result(results / 'build-time.json') if (results / 'build-time.json').exists() else None
    sections = _result(results / 'sections.json') if (results / 'sections.json').exists() else None
    runs = _replays(results)
    if timings:
        if (timings / 'build-time.json').exists():
            build = _result(timings / 'build-time.json')
        for key, (_, series) in _replays(timings).items():
            if key in runs:
                if not np.array_equal(series['proof_blocks'], runs[key][1]['proof_blocks']):
                    raise ValueError(f'the replays of {key} do not give the same proofs')
                runs[key][1]['update_us'] = series['update_us']
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
