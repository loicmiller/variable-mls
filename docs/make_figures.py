"""Draws the figures of the README from the code itself: architecture, commands, anatomy of a proof, header layout.

Each figure is written as SVG (shown by GitHub) and PDF (for print), in docs/figures/.

    python docs/make_figures.py [out_dir]
"""

import sys
from pathlib import Path

import matplotlib

matplotlib.use('svg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

from vmls.chain import random_chain  # noqa: E402
from vmls.encoding import CORE, HASH, header_size, n_levels  # noqa: E402
from vmls.figures import BLUE, GRAY, ORANGE, PART_COLOURS, STYLE  # noqa: E402
from vmls.proof import Params, dissolve  # noqa: E402

INK, PAPER, LINE = '#22211f', '#f6f5f2', '#c9c7c1'


def box(ax: plt.Axes, x: float, y: float, w: float, h: float, title: str, body: str = '', colour: str = LINE) -> None:
    """A rounded box with a bold title and a smaller body."""
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.02,rounding_size=0.08', facecolor=PAPER,
                                edgecolor=colour, linewidth=1.2))
    ax.text(x + w / 2, y + h - 0.16, title, ha='center', va='top', fontsize=8, weight='bold', color=INK)
    if body:
        ax.text(x + w / 2, y + h - 0.42, body, ha='center', va='top', fontsize=6.5, color=GRAY, linespacing=1.3)


def arrow(ax: plt.Axes, start: tuple[float, float], end: tuple[float, float], label: str = '') -> None:
    """An arrow from start to end, with an optional label at its middle."""
    ax.add_patch(FancyArrowPatch(start, end, arrowstyle='-|>', mutation_scale=8, color=GRAY, linewidth=0.9,
                                 shrinkA=2, shrinkB=2))
    if label:
        ax.text((start[0] + end[0]) / 2, (start[1] + end[1]) / 2 + 0.06, label, ha='center', va='bottom', fontsize=6,
                color=GRAY)


def canvas(width: float, height: float) -> tuple[plt.Figure, plt.Axes]:
    """A blank figure whose axes units are inches."""
    fig, ax = plt.subplots(figsize=(width, height))
    ax.set_xlim(0, width)
    ax.set_ylim(0, height)
    ax.axis('off')
    fig.subplots_adjust(0, 0, 1, 1)
    return fig, ax


def architecture() -> plt.Figure:
    """The modules and what flows between them."""
    fig, ax = canvas(7.0, 3.3)
    box(ax, 0.1, 2.2, 1.6, 0.95, 'node', 'export headers\nblock sizes, UTXO set\n(Bitcoin Core RPC)')
    box(ax, 2.0, 2.2, 1.6, 0.95, 'chain', 'Block, work, level\nccs2025: hash vs target\nours: committed nonce')
    box(ax, 3.9, 2.2, 1.4, 0.95, 'proof', 'Dissolve, Compress\nD, X, Omega', ORANGE)
    box(ax, 5.55, 2.2, 1.35, 0.95, 'encoding', 'header bytes\nsize formula')
    box(ax, 3.9, 0.95, 1.4, 0.95, 'verify', 'check headers, Score\ncompare_ccs, _ours', ORANGE)
    box(ax, 2.0, 0.95, 1.6, 0.95, 'measure', 'replay, build_time\nsections, k_star, attack')
    box(ax, 0.1, 0.95, 1.6, 0.95, 'gamma', 'hashrate fluctuation\nclassic, bound (s, w)')
    box(ax, 5.55, 0.95, 1.35, 0.95, 'figures', 'PDF at column\nwidth, numbers.json')
    box(ax, 2.0, 0.05, 4.9, 0.6, 'cli', 'vmls <command>: results/*.json, *.npz  →  out/*.pdf')
    arrow(ax, (1.7, 2.67), (2.0, 2.67), 'headers')
    arrow(ax, (3.6, 2.67), (3.9, 2.67), 'blocks')
    arrow(ax, (5.3, 2.67), (5.55, 2.67))
    arrow(ax, (4.6, 2.2), (4.6, 1.9), 'proofs')
    arrow(ax, (5.55, 2.35), (5.3, 1.75), 'bytes')
    arrow(ax, (3.9, 1.42), (3.6, 1.42))
    arrow(ax, (2.8, 2.2), (2.8, 1.9))
    arrow(ax, (1.7, 1.42), (2.0, 1.1))
    arrow(ax, (2.8, 0.95), (2.8, 0.65), 'results')
    arrow(ax, (6.2, 0.65), (6.2, 0.95))
    return fig


def usage() -> plt.Figure:
    """The commands in the order a measurement campaign runs them, with what each reads and writes."""
    fig, ax = canvas(7.0, 2.6)
    box(ax, 0.1, 1.45, 1.5, 0.9, 'vmls export', 'synced node\n→ headers/*.json')
    box(ax, 0.1, 0.25, 1.5, 0.9, 'vmls block-sizes', 'stopped node\n→ block-sizes.npy')
    grid = [('replay', 'per block: update,\nsize', ORANGE), ('build-time, verifier', 'by height: prover,\nverifier', ORANGE),
            ('sections', 'D, X, Omega\nby height', ORANGE), ('gamma, kstar, attack', 'Bitcoin\nparameters', LINE)]
    for i, (title, body, colour) in enumerate(grid):
        box(ax, 2.1 + (i % 2) * 1.55, 1.45 - (i // 2) * 1.2, 1.45, 0.9, title, body, colour)
    box(ax, 5.55, 0.85, 1.35, 0.9, 'vmls figures', 'results/ → out/*.pdf\nnumbers.json')
    arrow(ax, (1.6, 1.9), (2.1, 1.9), 'headers')
    arrow(ax, (1.6, 0.7), (2.1, 0.7), 'sizes')
    arrow(ax, (5.15, 1.3), (5.55, 1.3), 'results/')
    ax.text(2.1, 0.05, 'Every result is a JSON file with its command, version and date, never overwritten.',
            fontsize=6.5, color=GRAY)
    return fig


def anatomy() -> plt.Figure:
    """A small chain and its proof: every block by height and level, the blocks kept, the rows of D, X and Omega."""
    p = Params(K=3, k=4, chi=10)
    chain = random_chain(260, seed=4)
    D, top, x, omega = dissolve(chain, p)
    fig, ax = plt.subplots(figsize=(7.0, 2.7), layout='constrained')
    heights = [b.height for b in chain]
    levels = [min(b.level, top + 1) for b in chain]
    ax.scatter(heights, levels, s=6, color=LINE, zorder=1, label='block (not kept)')
    for mu, row in D.items():
        ax.scatter([b.height for b in row], [min(b.level, top + 1) for b in row], s=14, color=PART_COLOURS['D'],
                   zorder=2, label='D' if mu == top else None)
        ax.hlines(mu - 0.35, row[0].height, row[-1].height, color=PART_COLOURS['D'], linewidth=2)
        ax.text(row[-1].height + 3, mu - 0.35, f'D[{mu}]', ha='left', va='center', fontsize=6, color=GRAY)
    for part, blocks in (('X', x), ('Omega', omega)):
        ax.scatter([b.height for b in blocks], [min(b.level, top + 1) for b in blocks], s=14, color=PART_COLOURS[part],
                   zorder=2, label=part.replace('Omega', '$\\Omega$'))
    ax.set_xlabel('Block height')
    ax.set_xlim(-5, len(chain) + 25)
    ax.set_ylabel('Level')
    ax.set_yticks(range(top + 2), [str(mu) for mu in range(top + 1)] + [f'≥{top + 1}'])
    ax.set_title(f'K = {p.K}, χ = {p.chi}, k = {p.k}: the proof keeps {sum(map(len, D.values()))} + {len(x)} + '
                 f'{len(omega)} of {len(chain)} blocks', fontsize=8)
    fig.legend(loc='outside lower center', ncols=4)
    return fig


def header_layout(height: int = 977_192, k: int = 6) -> plt.Figure:
    """One header field by field, to scale, under each construction."""
    levels = n_levels(height)
    rows = {
        'CCS 2025': [('core', CORE, LINE), (f'interlink: {levels} × 32 B', HASH * levels, BLUE)],
        'Our construction': [('core', CORE - 4, LINE), ('H(ctr)', HASH, '#8f6fd1'),
                             (f'{k - 1} pointers', HASH * (k - 1), '#4fb3bf'),
                             (f'{levels} tuples (H(b1), ctr1, H(b2), ctr2): {levels} × 128 B', 4 * HASH * levels, ORANGE)],
    }
    fig, ax = plt.subplots(figsize=(7.0, 1.6), layout='constrained')
    for y, (name, fields) in enumerate(reversed(rows.items())):
        start = 0
        for label, size, colour in fields:
            ax.barh(y, size, left=start, color=colour, edgecolor='white', height=0.6)
            if size > 400:
                ax.text(start + size / 2, y, label, ha='center', va='center', fontsize=6.5, color=INK)
            start += size
        ax.text(start + 30, y, f'{start} B', va='center', fontsize=7, color=GRAY)
    assert header_size('ccs2025', height, k) == CORE + HASH * levels
    assert header_size('ours', height, k) == sum(size for _, size, _ in rows['Our construction'])
    ax.set_yticks(range(2), list(reversed(rows)))

    ax.set_xlabel(f'Bytes of one header at height {height:,}, k = {k}. Grey: the Bitcoin core, 80 B, of which ours '
                  f'replaces the 4-byte nonce with H(ctr), 32 B (violet); aqua: {k - 1} pointers, {HASH * (k - 1)} B.', fontsize=7)
    ax.set_xlim(0, header_size('ours', height, k) * 1.12)
    return fig


def main() -> None:
    """Writes every figure as SVG and PDF."""
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / 'figures'
    out.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update(STYLE)
    for name, draw in (('architecture', architecture), ('usage', usage), ('proof-anatomy', anatomy),
                       ('header-layout', header_layout)):
        fig = draw()
        for suffix in ('svg', 'pdf'):
            fig.savefig(out / f'{name}.{suffix}')
        plt.close(fig)
        print(out / f'{name}.svg')


if __name__ == '__main__':
    main()
