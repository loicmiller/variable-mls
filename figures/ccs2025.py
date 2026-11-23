"""Regenerates the five figures of the CCS 2025 paper, with today's code and style.

The published PDFs are kept as they are in paper-figures/ccs-2025/; these show the same data at the width of an ACM
column. Latencies are those of this machine.

    python -m experiments.proof_over_chain --mode ccs --headers headers/headers.zip -K 208 --stop 865043 --no-verifier
    python -m figures.ccs2025 --headers headers/headers.zip --run results/<stamp>-proof-over-chain-ccs-up-to-865042-K-208-chi-4032-k-323
"""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from vmls import style
from vmls.chain import GENESIS_LEVEL, blocks_from_headers, load_headers
from vmls.nipopow import level_changes

TICKS = [0, 200_000, 400_000, 600_000, 800_000]


def main() -> None:
    """Draws the figures into the output directory."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--headers', required=True, help='Exported headers, up to height 865,042 for the paper.')
    parser.add_argument('--run', required=True, help='Prefix of a ccs run of experiments.proof_over_chain.')
    parser.add_argument('--out-dir', default='out/ccs-2025', help='Directory of the PDFs.')
    args = parser.parse_args()

    run = np.load(f'{args.run}.npz')
    with open(f'{args.run}.json') as f:
        meta = json.load(f)
    K = meta['args']['K']
    n = len(run['proof_size'])
    chain = blocks_from_headers(load_headers(args.headers), stop=n)
    times = [block.timestamp for block in chain]
    heights = np.arange(n)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    style.use()
    size = (style.ACM_COLUMN, 2.2)

    # Difficulty, with a dotted line at each decrease.
    difficulty = np.array([block.diff for block in chain], dtype=float)
    fig, ax = plt.subplots(figsize=size, layout='constrained')
    for h in np.flatnonzero(np.diff(difficulty) < 0) + 1:
        ax.axvline(h, color=style.ORANGE, linestyle=':', linewidth=0.4)
    ax.plot(heights, difficulty, color=style.BLUE)
    ax.set_yscale('log')
    ax.set_ylabel('Difficulty')
    style.height_axis(ax, times, TICKS)
    fig.savefig(out / 'difficulty-variation-over-time-with-drops.pdf')
    plt.close(fig)

    # Number of blocks in the proof, against 2K ln h and 3K ln h.
    fig, ax = plt.subplots(figsize=size, layout='constrained')
    h = heights[1:]
    ax.plot(h, 3 * K * np.log(h), color=style.GRAY, linestyle=':', linewidth=0.8, label=r'$3K\ln h$')
    ax.plot(heights, run['proof_size'], color=style.BLUE, linewidth=0.6, rasterized=True, label='NIPoPoW')
    ax.plot(h, 2 * K * np.log(h), color=style.GRAY, linestyle='--', linewidth=0.8, label=r'$2K\ln h$')
    ax.set_ylim(bottom=0)
    ax.set_ylabel('Blocks in the proof')
    style.height_axis(ax, times, TICKS)
    ax.legend(loc='lower right')
    fig.savefig(out / 'proof-size-variation-over-time.pdf')
    plt.close(fig)

    # Latency of each update, with a dashed line where the level of the proof grows.
    latency = run['latency_compress'] / 1000
    fig, ax = plt.subplots(figsize=size, layout='constrained')
    for change in level_changes(run['block_level'], K):
        ax.axvline(change, color=style.GRAY, linestyle='--', linewidth=0.5)
    ax.plot(heights, latency, color=style.BLUE, linewidth=0.3, rasterized=True)
    ax.set_ylim(0, float(np.ceil(np.percentile(latency, 99.99))))
    ax.set_ylabel('Latency (ms)')
    style.height_axis(ax, times, TICKS)
    fig.savefig(out / 'proof-generation-latency-over-time-with-level-changes.pdf')
    plt.close(fig)

    # Difficulty of the last K blocks of each row, against the bound D_min^A(l) = D_0 / 2^l.
    last = {int(mu): value for mu, value in meta['last_K_difficulty'].items()}
    levels = sorted(last)
    fig, ax = plt.subplots(figsize=size, layout='constrained')
    ax.plot(levels, [last[mu] for mu in levels], color=style.BLUE, marker='o', markersize=3, label='Last K blocks')
    ax.plot(levels, [last[0] / 2 ** mu for mu in levels], color=style.ORANGE, linestyle='--', marker='x', markersize=3,
            label=r'Bound $D^{\mathcal{A}}_{\min}(\ell)$')
    ax.set_yscale('log')
    ax.set_xticks(levels)
    ax.set_xlabel(r'Level $\ell$')
    ax.set_ylabel('Difficulty')
    ax.grid(True)
    ax.legend(loc='lower left')
    fig.savefig(out / 'difficulty-vs-required-last-row-logscale.pdf')
    plt.close(fig)

    # Number of blocks of level mu or more.
    block_levels = run['block_level'][1:]
    top = int(block_levels[block_levels < GENESIS_LEVEL].max())
    counts = [int((block_levels >= mu).sum()) for mu in range(top + 1)]
    fig, ax = plt.subplots(figsize=size, layout='constrained')
    ax.plot(range(top + 1), counts, color=style.BLUE, marker='o', markersize=3)
    ax.set_yscale('log')
    ax.set_xticks(range(top + 1))
    ax.set_xlabel(r'Block level $\mu$')
    ax.set_ylabel(r'Blocks of level $\geq \mu$')
    ax.grid(True)
    fig.savefig(out / 'BitcoinMainNetLevels-Log.pdf')
    plt.close(fig)
    print(f'Five figures in {out}')


if __name__ == '__main__':
    main()
