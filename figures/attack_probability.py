"""Figures of the success probability of the zero-difficulty attack over the life of Bitcoin.

    python -m figures.attack_probability --run results/attack.json --out-dir out
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import FuncFormatter

from vmls import style

YEAR = 365.25 * 86400


def main() -> None:
    """Draws the probability over time and the time to reach each level."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--run', required=True, help='JSON of experiments.attack_probability.')
    parser.add_argument('--out-dir', default='out', help='Directory of the PDFs.')
    args = parser.parse_args()
    with open(args.run) as f:
        run = json.load(f)
    p = {int(mu): value for mu, value in run['p'].items()}
    observed = run['transitions']
    last_level, last_height = observed[-1]['level'], run['last_height']
    next_ = run['expected'][-1]
    x_max = int(1.15 * next_['height'])
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    style.use()

    # Probability over time: observed steps, then the extrapolated transition to the next level.
    fig, ax = plt.subplots(figsize=(style.IEEE_COLUMN, 2.2), layout='constrained')
    x = [0] + [t['height'] for t in observed] + [last_height]
    y = [p[0]] + [p[t['level']] for t in observed] + [p[last_level]]
    ax.step(x, y, where='post', color=style.BLUE, label='Observed')
    ax.step([last_height, next_['height'], x_max], [p[last_level], p[next_['level']], p[next_['level']]], where='post',
            color=style.BLUE, linestyle='--', label='Extrapolated')
    marks = [(t['level'], t['height']) for t in observed if t['level'] >= 10] + [(next_['level'], next_['height'])]
    for i, (mu, h) in enumerate(marks):
        ax.axvline(h, color=style.GRAY, linestyle=':', linewidth=0.8, label='Level transition' if i == 0 else None)
        end = marks[i + 1][1] if i + 1 < len(marks) else x_max
        ax.text((h + end) / 2, p[mu] + 0.02, rf'$\mu = {mu}$', ha='center', va='bottom', fontsize=7)
    ticks = list(range(0, x_max + 1, 250_000))
    ax.set_xticks(ticks, [f'{t // 1000}k' for t in ticks])
    ax.set_xlim(0, x_max)
    ax.set_ylim(0, 0.65)
    ax.set_xlabel('Block height')
    ax.set_ylabel('Attack success probability')
    ax.grid(True)
    ax.legend(loc='upper left')
    fig.savefig(out / 'attack-success-probability-over-time.pdf')
    plt.close(fig)

    # Time to reach each level, expected at 10 minutes per block against observed.
    levels = np.array([e['level'] for e in run['expected']])
    expected = np.array([(e['time'] - run['genesis_time']) / YEAR for e in run['expected']])
    actual = np.array([(t['time'] - run['genesis_time']) / YEAR for t in observed])
    spread = 2 / np.sqrt(2 * run['K'])  # The 2K-th block of a level arrives with relative spread 1/sqrt(2K).
    fig, ax = plt.subplots(figsize=(style.IEEE_COLUMN, 2.2), layout='constrained')
    ax.fill_between(levels, expected * (1 - spread), expected * (1 + spread), color=style.ORANGE, alpha=0.2, linewidth=0,
                    label=r'Expected $\pm 2\sigma$')
    ax.plot(levels, expected, color=style.ORANGE, linestyle='--', marker='x', markersize=4, label='Expected (10 min/block)')
    ax.plot([t['level'] for t in observed], actual, color=style.BLUE, marker='o', markersize=3, label='Observed')
    ax.set_yscale('log')
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f'{y:g}'))
    ax.set_xticks(levels)
    ax.set_xlabel(r'Proof level $\mu$')
    ax.set_ylabel('Years to reach the level')
    ax.annotate(datetime.fromtimestamp(next_['time'], tz=timezone.utc).strftime('%Y-%m'), (levels[-1], expected[-1]),
                xytext=(-6, -2), textcoords='offset points', ha='right', fontsize=7)
    ax.grid(True)
    ax.legend(loc='upper left')
    fig.savefig(out / 'proof-level-time-expected-vs-actual.pdf')
    plt.close(fig)
    print(f'Two figures in {out}')


if __name__ == '__main__':
    main()
