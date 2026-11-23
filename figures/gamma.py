"""Figures of the hashrate fluctuation gamma.

    python -m figures.gamma evolution --headers headers/headers.zip --out out/gamma-evolution-over-time.pdf
    python -m figures.gamma bound --run results/gamma-bound.json --out out/gamma-bound.pdf
"""

import argparse
import json

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import FuncFormatter

from vmls import gamma, style
from vmls.chain import load_headers

W_DAYS = [1, 3, 7, 14]
S_VALUES = [72_000, 105_000, 145_000, 271_000]


def evolution(args: argparse.Namespace) -> None:
    """The figure of the draft: the notebook's classic gamma over windows of s rounds, by the height at which each
    window ends.

    Args:
        args: The command line.
    """
    headers = load_headers(args.headers)
    blocks = gamma.load_blocks(headers)
    over_time = gamma.gamma_over_time(blocks, gamma.smoothed_rounds(blocks), args.s)
    step = max(1, len(over_time) // 4000)
    picks = over_time.iloc[::step]
    fig, ax = plt.subplots(figsize=(style.IEEE_COLUMN, 2.0), layout='constrained')
    ax.plot(picks['height'], picks['gamma'], color=style.BLUE, linewidth=0.8)
    ax.set_yscale('log')
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f'{y:g}'))
    ax.set_ylabel(rf'$\gamma$ (s = {args.s:,} rounds)')
    style.height_axis(ax, [h['time'] for h in headers], [0, 200_000, 400_000, 600_000, 800_000])
    fig.savefig(args.out)
    plt.close(fig)


def bound(args: argparse.Namespace) -> None:
    """The interval on gamma(s, w) against the sub-window w, since 2016, with the notebook's estimators as references.

    Args:
        args: The command line.
    """
    with open(args.run) as f:
        result = json.load(f)
    rows = [row for row in result['brackets'] if row['period'] == 'since-2016']
    old = {(row['method'], row['s']): row['periods']['since-2016'] for row in result['old']}
    fig, axes = plt.subplots(2, 2, figsize=(style.IEEE_COLUMN, 3.4), sharey=True, sharex=True, layout='constrained')
    for ax, s in zip(axes.ravel(), S_VALUES):
        here = [row for row in rows if row['s'] == s]
        x = [W_DAYS.index(row['w_days']) for row in here]
        ax.vlines(x, [row['lower'] for row in here], [row['upper'] for row in here], color=style.BLUE, linewidth=2,
                  label='95% interval')
        ax.plot(x, [row['point'] for row in here], linestyle='none', marker='o', markersize=4, color=style.BLUE,
                markeredgecolor='white', markeredgewidth=0.5, label='Estimate')
        ax.axhline(old['old', s]['q95'], color=style.ORANGE, linestyle='--', linewidth=1, label='Notebook, q95')
        ax.axhline(old['old', s]['max_min'], color=style.ORANGE, linewidth=1, label='Notebook, max/min')
        ax.axhline(old['difficulty', s]['max_min'], color=style.GRAY, linestyle=':', linewidth=1, label='D / 10 min, max/min')
        ax.set_title(f's = {s:,} rounds ({s * gamma.ROUND_SECONDS / 86400:.0f} days)', loc='left', fontsize=7)
        ax.set_xticks(range(len(W_DAYS)), [str(w) for w in W_DAYS])
        ax.set_xlim(-0.5, len(W_DAYS) - 0.5)
        ax.set_yscale('log')
        ax.set_ylim(1, None)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f'{y:g}'))
        ax.yaxis.set_minor_formatter(FuncFormatter(lambda y, _: f'{y:g}' if np.isclose(y, [1.5, 2, 3, 5]).any() else ''))
        ax.grid(True, axis='y', which='both')
        ax.set_axisbelow(True)
    for ax in axes[1]:
        ax.set_xlabel('Sub-window w (days)')
    for ax in axes[:, 0]:
        ax.set_ylabel(r'$\gamma$')
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='outside upper center', ncols=2)
    fig.savefig(args.out)
    plt.close(fig)


def main() -> None:
    """Draws one figure."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    commands = parser.add_subparsers(dest='command', required=True)
    command = commands.add_parser('evolution')
    command.add_argument('--headers', required=True, help='Exported headers.')
    command.add_argument('-s', type=int, default=271_000, help='Window, in rounds.')
    command.add_argument('--out', required=True, help='PDF file.')
    command = commands.add_parser('bound')
    command.add_argument('--run', required=True, help='JSON of experiments.gamma bound.')
    command.add_argument('--out', required=True, help='PDF file.')
    args = parser.parse_args()
    style.use()
    {'evolution': evolution, 'bound': bound}[args.command](args)
    print(f'{args.out} written')


if __name__ == '__main__':
    main()
