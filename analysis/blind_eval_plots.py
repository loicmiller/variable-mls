###############################################################################
# Imports

import glob
import json
import os
import sys

import matplotlib
matplotlib.use('pdf')
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime, timezone
from matplotlib.ticker import FixedLocator, FuncFormatter



###############################################################################
# Constants

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'analysis', 'blind-eval')
K = sys.argv[2] if len(sys.argv) > 2 else '208'
HEADERS = next((arg for arg in sys.argv[3:] if arg.endswith('.json')), os.path.join(ROOT, 'headers', 'headers.json'))

# Hue = scheme, line style = where the pointers live. Validated with the dataviz palette checker (light surface).
BLUE, ORANGE, GRAY = '#2a78d6', '#eb6834', '#52514e'
STYLE = {
    'ccs': {'color': BLUE, 'linestyle': '-', 'label': 'CCS'},
    'ccs-merkle': {'color': BLUE, 'linestyle': '--', 'label': 'CCS, Merkle'},
    'draft': {'color': ORANGE, 'linestyle': '-', 'label': 'This work, as written'},
    'draft-merkle': {'color': ORANGE, 'linestyle': '--', 'label': 'This work, Merkle'},
}

# Once the Merkle commitment is adopted, the figures leave out the header as written in the draft.
if 'merkle-only' in sys.argv:
    STYLE.pop('draft')

plt.rcParams.update({
    'font.family': 'serif', 'font.serif': ['STIXGeneral'], 'mathtext.fontset': 'stix',
    'font.size': 8, 'axes.labelsize': 8, 'legend.fontsize': 7, 'xtick.labelsize': 7, 'ytick.labelsize': 7,
    'axes.linewidth': 0.5, 'axes.edgecolor': GRAY, 'xtick.color': GRAY, 'ytick.color': GRAY,
    'grid.color': '#e4e3df', 'grid.linewidth': 0.5, 'lines.linewidth': 1.2,
    'pdf.fonttype': 42,
})



###############################################################################
# Data

def latest(mode, extension):
    """
    Finds the most recent run of a mode.

    Args:
    - mode (str): 'ccs' or 'blind'.
    - extension (str): 'npz' or 'json'.

    Returns:
    - str: The path to the file.
    """
    return sorted(glob.glob(os.path.join(ROOT, 'data', f'*-blind-eval-{mode}-up-to-*-K-{K}-chi-4032-k-323.{extension}')))[-1]


def epochs(values, width=2016):
    """
    Summarizes a per-block series per epoch, to avoid a PDF of 865,000 points.

    Args:
    - values (numpy.ndarray): One value per block.
    - width (int): The number of blocks per bin.

    Returns:
    - x, median, low, high (tuple): The centers of the bins, and the median, 5th and 95th percentiles of each bin.
    """
    n = len(values) // width
    blocks = values[:n * width].reshape(n, width)
    x = (np.arange(n) + 0.5) * width
    return x, np.median(blocks, axis=1), np.percentile(blocks, 5, axis=1), np.percentile(blocks, 95, axis=1)


def level_changes(block_level):
    """
    Heights at which the level of the proof changes, as the CCS data defines it: the highest level with 2K blocks in the proof.

    Args:
    - block_level (numpy.ndarray): The level of each block.

    Returns:
    - list: The height of each change, by increasing level.

    Notes:
    - Every block of the highest level is in the proof, so counting them over the chain is enough. This gives the proof_level
      field of the CCS data at K=104 on all 865,043 blocks.
    """
    changes = []
    for mu in range(1, int(block_level[1:].max()) + 1):
        height = int(np.searchsorted(np.cumsum(block_level >= mu), 2 * int(K)))
        if height < len(block_level):
            changes.append(height)
    return changes


def height_axis(ax, times, label=True):
    """
    Same abscissa as the figures of the CCS paper: the block height and its date.

    Args:
    - ax (matplotlib.axes.Axes): The axes.
    - times (list): The timestamp of each block.
    - label (bool): Whether to write the ticks and the axis label.

    Returns:
    - None
    """
    ticks = [0, 200_000, 400_000, 600_000, 800_000]
    ax.xaxis.set_major_locator(FixedLocator(ticks))
    ax.set_xlim(0, len(times))
    if label:
        dates = {t: datetime.fromtimestamp(times[t], tz=timezone.utc).strftime('%Y-%m') for t in ticks}
        ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f'{int(x / 1000)}k\n{dates.get(int(x), "")}' if x else f'0\n{dates[0]}'))
        ax.set_xlabel('Block height (date)')
    else:
        ax.tick_params(labelbottom=False)
    ax.grid(True)
    ax.set_axisbelow(True)
    for side in ('top', 'right'):
        ax.spines[side].set_visible(False)



###############################################################################
# Figures

def latency_figure(ccs, blind, verifier, times):
    """
    Figure A: prover update latency and verifier CPU time.

    Args:
    - ccs (numpy.lib.npyio.NpzFile): The per-block measurements of the ccs run.
    - blind (numpy.lib.npyio.NpzFile): The per-block measurements of the blind run.
    - verifier (list): The verifier samples of both runs.
    - times (list): The timestamp of each block.

    Returns:
    - None
    """
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(3.4, 3.5), height_ratios=[1, 1], layout='constrained')

    series = {
        'ccs': ccs['latency_base'],
        'ccs-merkle': ccs['latency_base'] + ccs['latency_merkle'],
        'draft': blind['latency_base'],
        'draft-merkle': blind['latency_base'] + blind['latency_merkle'],
    }
    for scheme, values in series.items():
        if scheme not in STYLE:
            continue
        x, median, low, high = epochs(values / 1000)
        if not scheme.endswith('merkle'):
            top.fill_between(x, low, high, color=STYLE[scheme]['color'], alpha=0.15, linewidth=0)
        top.plot(x, median, **STYLE[scheme])
    top.set_ylabel('Prover update (ms)')
    top.set_ylim(bottom=0)
    height_axis(top, times, label=False)
    top.text(0.015, 0.97, '(a)', transform=top.transAxes, va='top')

    for scheme in STYLE:
        samples = [s for s in verifier if s['fork'] == 'deep' and s['scheme'] == scheme]
        bottom.plot([s['height'] for s in samples], [s['ms'] for s in samples], **STYLE[scheme])
    bottom.set_ylabel('Verifier CPU time (ms)')
    bottom.set_ylim(bottom=0)
    height_axis(bottom, times)
    bottom.text(0.015, 0.97, '(b)', transform=bottom.transAxes, va='top')

    handles, labels = bottom.get_legend_handles_labels()
    fig.legend(handles, labels, loc='outside upper center', ncols=2, frameon=False)
    fig.savefig(f'{OUT}-latency.pdf')
    plt.close(fig)


def size_figure(byte_samples, times):
    """
    Figure B: size of the proof, against the headers an SPV client stores.

    Args:
    - byte_samples (list): The proof size samples of both runs.
    - times (list): The timestamp of each block.

    Returns:
    - None
    """
    fig, ax = plt.subplots(figsize=(3.4, 2.5), layout='constrained')
    heights = np.array([s['height'] for s in byte_samples if 'ccs' in s])
    ax.plot(heights, 80 * (heights + 1) / 1e6, color=GRAY, linestyle=':', label='SPV (all headers)')
    for scheme in STYLE:
        samples = [s for s in byte_samples if scheme in s]
        ax.plot([s['height'] for s in samples], [s[scheme] / 1e6 for s in samples], **STYLE[scheme])
    ax.set_yscale('log')
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f'{y:g}'))
    ax.set_ylabel('Proof size (MB)')
    height_axis(ax, times)
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, loc='outside upper center', ncols=2, frameon=False)
    fig.savefig(f'{OUT}-size.pdf')
    plt.close(fig)


def ccs_latency_figure(runs, times):
    """
    Figure C: latency of each update, with the level changes, as in the CCS paper.

    Args:
    - runs (list): For each panel, the scheme, the latency of each block in ms, and the heights of the level changes.
    - times (list): The timestamp of each block.

    Returns:
    - float: The top of the shared ordinate, where outliers are cut.
    """
    top = float(np.ceil(max(np.percentile(values, 99.99) for _, values, _ in runs)))
    fig, axes = plt.subplots(len(runs), 1, figsize=(3.4, 3.5), sharex=True, layout='constrained')
    for ax, (scheme, values, changes), last in zip(axes, runs, [False] * (len(runs) - 1) + [True]):
        ax.plot(np.arange(len(values)), values, color=STYLE[scheme]['color'], linewidth=0.3, rasterized=True)
        for height in changes:
            ax.axvline(height, color=GRAY, linestyle='--', linewidth=0.5)
        ax.set_ylim(0, top)
        ax.set_ylabel('Latency (ms)')
        ax.set_title(STYLE[scheme]['label'], loc='left', fontsize=8)
        height_axis(ax, times, label=last)
    fig.savefig(f'{OUT}-ccs-latency.pdf', dpi=300)
    plt.close(fig)
    return top


def ccs_count_figure(ccs, blind, times):
    """
    Figure D: number of blocks in the proof, against the curves of the CCS paper.

    Args:
    - ccs (numpy.lib.npyio.NpzFile): The per-block measurements of the ccs run.
    - blind (numpy.lib.npyio.NpzFile): The per-block measurements of the blind run.
    - times (list): The timestamp of each block.

    Returns:
    - None
    """
    fig, ax = plt.subplots(figsize=(3.4, 2.5), layout='constrained')
    heights = np.arange(1, len(times))
    ax.plot(heights, 2 * int(K) * np.log(heights), color=GRAY, linestyle='--', linewidth=0.8, label=r'$2K\ln h$')
    ax.plot(heights, 3 * int(K) * np.log(heights), color=GRAY, linestyle=':', linewidth=0.8, label=r'$3K\ln h$')
    for run, scheme in ((ccs, 'ccs'), (blind, 'draft' if 'draft' in STYLE else 'draft-merkle')):
        ax.plot(np.arange(len(run['proof_size'])), run['proof_size'], color=STYLE[scheme]['color'], linewidth=0.6, rasterized=True, label='CCS' if scheme == 'ccs' else 'This work')
    ax.set_ylim(bottom=0)
    ax.set_ylabel('Blocks in the proof')
    height_axis(ax, times)
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, loc='outside upper center', ncols=4, frameon=False)
    fig.savefig(f'{OUT}-ccs-count.pdf', dpi=300)
    plt.close(fig)



###############################################################################
# Main

if __name__ == '__main__':
    ccs = np.load(latest('ccs', 'npz'))
    blind = np.load(latest('blind', 'npz'))
    with open(latest('ccs', 'json')) as f:
        ccs_json = json.load(f)
    with open(latest('blind', 'json')) as f:
        blind_json = json.load(f)
    with open(HEADERS) as f:
        times = [header['time'] for header in json.load(f)]

    byte_samples = ccs_json['bytes'] + blind_json['bytes']
    verifier = ccs_json['verifier'] + blind_json['verifier']
    latency_figure(ccs, blind, verifier, times)
    size_figure(byte_samples, times)
    this_work = 'draft' if 'draft' in STYLE else 'draft-merkle'
    runs = [
        ('ccs', ccs['latency_base'] / 1000, level_changes(ccs['block_level'])),
        (this_work, (blind['latency_base'] + (blind['latency_merkle'] if this_work == 'draft-merkle' else 0)) / 1000, level_changes(blind['block_level'])),
    ]
    latency_top = ccs_latency_figure(runs, times)
    ccs_count_figure(ccs, blind, times)

    # The numbers the text quotes.
    summary = {}
    summary['ccs_figure_latency'] = {scheme: {'level_changes': changes, 'median_ms': float(np.median(values)), 'above_ordinate': int((values > latency_top).sum()), 'max_ms': float(values.max())} for scheme, values, changes in runs}
    summary['ccs_figure_latency_top_ms'] = latency_top
    summary['ccs_figure_count'] = {name: {'last': int(run['proof_size'][-1]), 'max_after_100k': int(run['proof_size'][100_000:].max())} for name, run in (('ccs', ccs), ('blind', blind))}
    summary['ccs_figure_curves_at_tip'] = {'2K ln h': 2 * int(K) * float(np.log(len(times) - 1)), '3K ln h': 3 * int(K) * float(np.log(len(times) - 1))}
    last = -10_000
    for name, values in (('ccs', ccs['latency_base']), ('ccs-merkle', ccs['latency_base'] + ccs['latency_merkle']), ('draft', blind['latency_base']), ('draft-merkle', blind['latency_base'] + blind['latency_merkle']), ('compress-only-ccs', ccs['latency_compress']), ('compress-only-blind', blind['latency_compress'])):
        summary[f'prover_ms_median_all[{name}]'] = float(np.median(values)) / 1000
        summary[f'prover_ms_median_last10k[{name}]'] = float(np.median(values[last:])) / 1000
        summary[f'prover_ms_p99_last10k[{name}]'] = float(np.percentile(values[last:], 99)) / 1000
    for run_json in (ccs_json, blind_json):
        tip = run_json['bytes'][-1]
        summary[f'bytes_tip[{tip["height"]}]' + ('[blind]' if 'draft' in tip else '[ccs]')] = tip
    top_height = max(s['height'] for s in verifier)
    summary['verifier_tip'] = [s for s in verifier if s['height'] == top_height]
    summary['verifier_paths'] = {}
    for s in verifier:
        key = f"{s['scheme']}/{s['fork']}/{s['path']}/winner={s['winner']}"
        summary['verifier_paths'][key] = summary['verifier_paths'].get(key, 0) + 1
    with open(f'{OUT}-summary.json', 'w') as f:
        json.dump(summary, f, indent=1)
    print(json.dumps(summary, indent=1))
