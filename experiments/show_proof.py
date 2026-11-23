"""Draws the proof of a small synthetic chain: the full chain, the blocks the proof keeps, and its rows D[mu].

    python -m experiments.show_proof --levels 0,1,0,2,0,1,0,3,0,1,0,2,0,1,0,4 -K 1 -k 2 -chi 3 --out proof.pdf
    python -m experiments.show_proof --random 60 --seed 1 -K 2 -k 2 -chi 9 --out proof.pdf
"""

import argparse

import matplotlib.pyplot as plt

from vmls import style
from vmls.nipopow import Params, compress, dissolve
from vmls.synthetic import random_chain, scripted_chain


def draw_blocks(ax: plt.Axes, blocks: list, top: int, title: str) -> None:
    """Draws each block as a bar as tall as its level.

    Args:
        ax: The axes.
        blocks: The blocks.
        top: Height of the genesis bar.
        title: Title of the panel.
    """
    for block in blocks:
        height = top + 1 if block.height == 0 else block.level + 1
        ax.bar(block.height, height, bottom=-1, width=0.6, color=style.BLUE, edgecolor='white', linewidth=0.5)
    ax.set_xticks([block.height for block in blocks])
    ax.set_ylim(-1, top + 1)
    ax.set_xlabel('Block height')
    ax.set_ylabel('Level')
    ax.set_title(title, loc='left')


def main() -> None:
    """Builds the chain, compresses it and writes the figure."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--levels', help='Comma-separated level of each block, the genesis block first.')
    source.add_argument('--random', type=int, help='Number of blocks of a chain with geometric levels.')
    parser.add_argument('--seed', type=int, default=0, help='Seed of the random chain.')
    parser.add_argument('-K', type=int, default=1, help='Security parameter.')
    parser.add_argument('-k', type=int, default=2, help='Common prefix parameter.')
    parser.add_argument('-chi', type=int, default=3, help='Length of the uncompressed subchain.')
    parser.add_argument('--out', required=True, help='PDF file.')
    args = parser.parse_args()

    chain = scripted_chain([int(x) for x in args.levels.split(',')]) if args.levels else random_chain(args.random, args.seed)
    p = Params(args.K, args.k, args.chi)
    proof = compress(chain, p)
    D, level, _ = dissolve(proof, p)
    top = max(block.level for block in chain[1:])

    style.use()
    fig, (full, kept, rows) = plt.subplots(1, 3, figsize=(style.IEEE_PAGE, 2.2), layout='constrained')
    draw_blocks(full, chain, top, '(a) Chain')
    draw_blocks(kept, proof, top, f'(b) Proof, {len(proof)} blocks')
    width = max(len(row) for row in D.values())
    for mu, row in D.items():
        for i, block in enumerate(row):
            x = width - len(row) + i
            rows.add_patch(plt.Rectangle((x - 0.4, mu - 0.4), 0.8, 0.8, color=style.BLUE))
            rows.text(x, mu, str(block.height), ha='center', va='center', fontsize=6, color='white')
    rows.set_xlim(-1, width)
    rows.set_ylim(min(D) - 1, max(D) + 1)
    rows.set_yticks(sorted(D))
    rows.set_xlabel('Index in the row')
    rows.set_ylabel(r'Level $\mu$')
    rows.set_title(f'(c) Rows D[mu], proof level {level}', loc='left')
    fig.suptitle(f'K = {p.K}, k = {p.k}, chi = {p.chi}')
    fig.savefig(args.out)
    print(f'{args.out} written')


if __name__ == '__main__':
    main()
