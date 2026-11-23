###############################################################################
# Imports

import argparse
import json
from multiprocessing import Pool

import matplotlib
matplotlib.use('pdf')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd



###############################################################################
# Constants

# The estimator of bitcoin-gamma-estimation.ipynb, as a script: the notebook reads a fixed headers file.
GENESIS_TARGET = 0xffff << 208
ROUND_SECONDS = 18
K_SMOOTH = 1008
K_GRID = [144, 432, 1008, 2016, 4032, 8064]
ALPHA_INNER = 0.01
S_VALUES = [72_000, 105_000, 145_000, 271_000]

# What the notebook printed on the 865,043 blocks of headers.json.
NOTEBOOK = {
    72_000: {'classic': 9.481139, 'robust_max': 9.287758, 'q95': 1.539881, 'q99': 1.968455},
    271_000: {'classic': 34.961995, 'robust_max': 33.342730, 'q95': 3.888302, 'q99': 12.419624},
}
NOTEBOOK_K_GAMMA = {144: 52.964829, 432: 41.930867, 1008: 34.961995, 2016: 31.909972, 4032: 30.481528, 8064: 27.083362}



###############################################################################
# Estimator

def load_blocks(path):
    """
    Loads the blocks the estimator can use: those with a positive time since the previous block.

    Args:
    - path (str): The headers file.

    Returns:
    - pd.DataFrame: The height, time and difficulty of each block, and the time of the genesis block in the attrs.
    """
    with open(path) as f:
        headers = json.load(f)
    df = pd.DataFrame({'time': [header['time'] for header in headers]})
    df['difficulty'] = [GENESIS_TARGET / ((int(header['bits'], 16) & 0xffffff) << (8 * ((int(header['bits'], 16) >> 24) - 3))) for header in headers]
    genesis_time = int(df['time'].iloc[0])
    df['height'] = df.index
    df = df[df['time'].diff() > 0].copy()
    df.attrs['genesis_time'] = genesis_time
    df.attrs['n_headers'] = len(headers)
    return df


def smoothed_rounds(blocks, k_smooth):
    """
    Hashrate per round, from the work and time of the last k_smooth blocks, with empty rounds interpolated.

    Args:
    - blocks (pd.DataFrame): The output of load_blocks.
    - k_smooth (int): The number of blocks of the smoothing window.

    Returns:
    - pd.DataFrame: The columns round_idx and hashrate, without gaps.

    Notes:
    - Sorting by time mirrors the notebook. Bitcoin timestamps are not monotonic, so this is not the order by height.
    """
    tmp = blocks[['time', 'difficulty']].sort_values('time').reset_index(drop=True)
    work = tmp['difficulty'].rolling(window=k_smooth, min_periods=k_smooth).sum() * (2 ** 256 / GENESIS_TARGET)
    elapsed = tmp['time'] - tmp['time'].shift(k_smooth)
    tmp['hashrate'] = work / elapsed
    tmp = tmp.dropna(subset=['hashrate'])
    tmp = tmp[elapsed.loc[tmp.index] > 0]
    tmp['round_idx'] = (tmp['time'] - blocks.attrs['genesis_time']) // ROUND_SECONDS
    observed = tmp.groupby('round_idx')['hashrate'].mean()
    full = observed.reindex(pd.RangeIndex(int(observed.index.min()), int(observed.index.max()) + 1, name='round_idx'))
    return full.interpolate(method='linear').ffill().bfill().reset_index()


def classic_gamma(h, s):
    """
    Worst max/min over the windows of s rounds.

    Args:
    - h (pd.Series): The hashrate per round.
    - s (int): The window, in rounds.

    Returns:
    - float: The ratio.
    """
    window = h.rolling(window=s, min_periods=s)
    return float((window.max() / window.min()).max())


def row_for_s(args):
    """
    All the gammas of one window.

    Args:
    - args (tuple): The hashrate per round and the window, in rounds.

    Returns:
    - dict: The classic gamma, and the robust one with its maximum, q95 and q99 over the windows.
    """
    h, s = args
    window = h.rolling(window=s, min_periods=s)
    ratios = (window.quantile(1.0 - ALPHA_INNER) / window.quantile(ALPHA_INNER)).dropna()
    return {
        's': s,
        'days': s * ROUND_SECONDS / 86400,
        'n_windows': len(ratios),
        'classic': classic_gamma(h, s),
        'robust_max': float(ratios.max()),
        'q95': float(ratios.quantile(0.95)),
        'q99': float(ratios.quantile(0.99)),
    }


def knee(gammas):
    """
    The smoothing window at the knee of the log-log curve, as chosen in the notebook.

    Args:
    - gammas (dict): The classic gamma per smoothing window.

    Returns:
    - int: The smoothing window at the largest distance to the chord between the two ends.
    """
    x = np.log10(list(gammas.keys()))
    y = np.log10(list(gammas.values()))
    distance = np.abs((y[-1] - y[0]) * x - (x[-1] - x[0]) * y + x[-1] * y[0] - y[-1] * x[0]) / np.hypot(y[-1] - y[0], x[-1] - x[0])
    return list(gammas.keys())[int(distance.argmax())]



###############################################################################
# Figure

def evolution_figure(blocks, rounds, s, out):
    """
    The figure of the draft: max/min over the windows of s rounds, by the height at which each window ends.

    Args:
    - blocks (pd.DataFrame): The output of load_blocks.
    - rounds (pd.DataFrame): The hashrate per round.
    - s (int): The window, in rounds.
    - out (str): The path of the PDF.

    Returns:
    - dict: The last value and the largest one of the last s rounds.
    """
    window = rounds['hashrate'].rolling(window=s, min_periods=s)
    gamma_t = (window.max() / window.min()).dropna()
    meta = blocks.assign(round_idx=(blocks['time'] - blocks.attrs['genesis_time']) // ROUND_SECONDS).groupby('round_idx').agg(height=('height', 'max'), time=('time', 'max'))
    aligned = meta.reindex(rounds['round_idx']).ffill().bfill().astype(int).reset_index()
    step = max(1, len(gamma_t) // 4000)
    picks = gamma_t.index[::step]
    heights = aligned.loc[picks, 'height'].to_numpy()

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(heights, gamma_t.loc[picks].to_numpy(), linewidth=1.2)
    ax.set_xlabel('Block height (date)', fontsize=20)
    ax.set_ylabel('gamma(t)', fontsize=20)
    ax.grid(True, alpha=0.3)
    ax.tick_params(labelsize=16)
    ticks = [int(tick) for tick in np.linspace(heights.min(), heights.max(), max(4, len(ax.get_xticks())) + 2)]
    nearest = [int(np.abs(heights - tick).argmin()) for tick in ticks]
    dates = pd.to_datetime(aligned.loc[picks, 'time'].to_numpy(), unit='s', utc=True)
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{int(heights[i])} ({dates[i].strftime('%Y-%m')})" for i in nearest], rotation=45, ha='right', fontsize=16)
    fig.tight_layout()
    fig.savefig(out, format='pdf', bbox_inches='tight')
    plt.close(fig)
    return {'last': float(gamma_t.iloc[-1]), 'peak_after_2015': float(gamma_t[aligned.loc[gamma_t.index, 'height'] > 340_000].max())}



###############################################################################
# Main

def main():
    """
    Computes the gammas of one headers file, and checks them against the notebook if it is the same file.

    Args:
    - None

    Returns:
    - None

    Raises:
    - AssertionError: If --check is given and a value differs from what the notebook printed.
    """
    parser = argparse.ArgumentParser(description='Gamma of the (gamma, s)-respecting property, from block headers.')
    parser.add_argument('headers', help='Headers file.')
    parser.add_argument('--out', required=True, help='Prefix of the JSON file and of the figure.')
    parser.add_argument('--check', action='store_true', help='Compare with the values the notebook printed on headers.json.')
    args = parser.parse_args()

    blocks = load_blocks(args.headers)
    rounds = smoothed_rounds(blocks, K_SMOOTH)
    h = rounds['hashrate'].astype(float)
    h = h[h > 0].reset_index(drop=True)
    print(f'{blocks.attrs["n_headers"]} headers, {len(blocks)} with a positive interval, {len(h)} rounds')

    with Pool(len(S_VALUES)) as pool:
        rows = pool.map(row_for_s, [(h, s) for s in S_VALUES])
    k_gammas = {k: classic_gamma(smoothed_rounds(blocks, k)['hashrate'].astype(float), 271_000) for k in K_GRID}
    result = {
        'n_headers': blocks.attrs['n_headers'],
        'rounds': len(h),
        'rows': rows,
        'k_gammas_s_271000': k_gammas,
        'knee': knee(k_gammas),
        'evolution_s_271000': evolution_figure(blocks, rounds, 271_000, f'{args.out}-evolution-over-time.pdf'),
    }
    print(json.dumps(result, indent=1))

    if args.check:
        for row in rows:
            for key, value in NOTEBOOK.get(row['s'], {}).items():
                assert abs(row[key] - value) < 1e-5, (row['s'], key, row[key], value)
        for k, value in NOTEBOOK_K_GAMMA.items():
            assert abs(k_gammas[k] - value) < 1e-5, (k, k_gammas[k], value)
        assert result['knee'] == K_SMOOTH
        print('Same values as the notebook.')

    with open(f'{args.out}.json', 'w') as f:
        json.dump(result, f, indent=1)


if __name__ == '__main__':
    main()
