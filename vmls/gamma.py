"""The hashrate fluctuation gamma, as the gamma notebook of the project estimates it.

The (gamma, s)-respecting property bounds the ratio of the largest to the smallest hashrate within any s rounds.
The notebook estimates the hashrate from the work of the last K_SMOOTH blocks, on a grid of 18-second rounds, then
takes ratios over windows of s rounds: the classic gamma is the worst max/min; the robust one is the q95 or q99, over
the windows, of the 1%-99% ratio inside each window. vmls.gamma_bound measures what the definition asks instead.
"""

import numpy as np
import pandas as pd

from vmls.chain import GENESIS_TARGET, bits_to_target

ROUND_SECONDS = 18
K_SMOOTH = 1008  # Blocks of the smoothing window, at the knee of the notebook's sweep.
K_GRID = [144, 432, 1008, 2016, 4032, 8064]
ALPHA_INNER = 0.01


def load_blocks(headers: list[dict]) -> pd.DataFrame:
    """The blocks the estimator can use: those with a positive time since the previous block.

    Args:
        headers: The headers, one per height.

    Returns:
        The height, time and difficulty of each block; the time of the genesis block and the number of headers are
        in the attrs.
    """
    df = pd.DataFrame({'time': [header['time'] for header in headers]})
    df['difficulty'] = [GENESIS_TARGET / bits_to_target(header['bits']) for header in headers]
    genesis_time = int(df['time'].iloc[0])
    df['height'] = df.index
    df = df[df['time'].diff() > 0].copy()
    df.attrs['genesis_time'] = genesis_time
    df.attrs['n_headers'] = len(headers)
    return df


def smoothed_rounds(blocks: pd.DataFrame, k_smooth: int = K_SMOOTH) -> pd.DataFrame:
    """Hashrate per round, from the work and time of the last k_smooth blocks, empty rounds interpolated.

    Blocks are sorted by time, as in the notebook. Bitcoin timestamps are not monotonic, so this is not the height order.

    Args:
        blocks: The output of load_blocks.
        k_smooth: Blocks of the smoothing window.

    Returns:
        The columns round_idx and hashrate, without gaps.
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


def classic_gamma(h: pd.Series, s: int) -> float:
    """Worst max/min over the windows of s rounds.

    Args:
        h: The hashrate per round.
        s: The window, in rounds.

    Returns:
        The ratio.
    """
    window = h.rolling(window=s, min_periods=s)
    return float((window.max() / window.min()).max())


def gamma_row(h: pd.Series, s: int) -> dict:
    """All the gammas of one window.

    Args:
        h: The hashrate per round.
        s: The window, in rounds.

    Returns:
        The classic gamma, and the robust one with its maximum, q95 and q99 over the windows.
    """
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


def knee(gammas: dict[int, float]) -> int:
    """The smoothing window at the knee of the log-log curve, as the notebook chooses it.

    Args:
        gammas: The classic gamma per smoothing window.

    Returns:
        The smoothing window farthest from the chord between the two ends.
    """
    x = np.log10(list(gammas.keys()))
    y = np.log10(list(gammas.values()))
    distance = np.abs((y[-1] - y[0]) * x - (x[-1] - x[0]) * y + x[-1] * y[0] - y[-1] * x[0]) / np.hypot(y[-1] - y[0], x[-1] - x[0])
    return list(gammas.keys())[int(distance.argmax())]


def gamma_over_time(blocks: pd.DataFrame, rounds: pd.DataFrame, s: int) -> pd.DataFrame:
    """Classic gamma of each window of s rounds, by the height and time at which the window ends.

    Args:
        blocks: The output of load_blocks.
        rounds: The output of smoothed_rounds.
        s: The window, in rounds.

    Returns:
        The columns height, time and gamma, one row per window.
    """
    window = rounds['hashrate'].rolling(window=s, min_periods=s)
    gamma_t = (window.max() / window.min()).dropna()
    meta = (blocks.assign(round_idx=(blocks['time'] - blocks.attrs['genesis_time']) // ROUND_SECONDS)
            .groupby('round_idx').agg(height=('height', 'max'), time=('time', 'max')))
    aligned = meta.reindex(rounds['round_idx']).ffill().bfill().astype(int).reset_index()
    return pd.DataFrame({'height': aligned.loc[gamma_t.index, 'height'].to_numpy(),
                         'time': aligned.loc[gamma_t.index, 'time'].to_numpy(),
                         'gamma': gamma_t.to_numpy()})
