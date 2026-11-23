"""The look of the figures: sizes at print scale, colours and the height axis.

Figures are drawn at the width they are printed, so that fonts keep their size: 3.5 in for an IEEE column, 3.33 in
for an ACM one. Text is 8 pt for axis labels and 7 pt for ticks and legends, in the serif family of the papers.
Colours: blue for the construction of CCS 2025, orange for the new one, grey for references (validated for colour
vision deficiencies); identity is doubled by line style, so figures also read in black and white.
"""

from datetime import datetime, timezone

import matplotlib

matplotlib.use('pdf')

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FixedLocator, FuncFormatter  # noqa: E402

IEEE_COLUMN = 3.5  # Inches.
IEEE_PAGE = 7.16
ACM_COLUMN = 3.33
BLUE, ORANGE, GRAY = '#2a78d6', '#eb6834', '#52514e'
GRID = '#e4e3df'

RC = {
    'font.family': 'serif', 'font.serif': ['STIXGeneral', 'Times New Roman', 'DejaVu Serif'], 'mathtext.fontset': 'stix',
    'font.size': 8, 'axes.labelsize': 8, 'axes.titlesize': 8, 'legend.fontsize': 7,
    'xtick.labelsize': 7, 'ytick.labelsize': 7,
    'axes.linewidth': 0.5, 'axes.edgecolor': GRAY, 'xtick.color': GRAY, 'ytick.color': GRAY,
    'xtick.major.width': 0.5, 'ytick.major.width': 0.5,
    'grid.color': GRID, 'grid.linewidth': 0.5, 'lines.linewidth': 1.2,
    'legend.frameon': False, 'axes.spines.top': False, 'axes.spines.right': False,
    'pdf.fonttype': 42, 'savefig.dpi': 300,
}


def use() -> None:
    """Applies the look to every figure drawn afterwards."""
    plt.rcParams.update(RC)


def height_axis(ax: plt.Axes, times: list[int], ticks: list[int], label: bool = True) -> None:
    """Block heights on the x axis, each tick with the month it was mined.

    Args:
        ax: The axes.
        times: Timestamp of each block.
        ticks: Heights to mark.
        label: Whether to write the tick labels and the axis title.
    """
    ax.xaxis.set_major_locator(FixedLocator(ticks))
    ax.set_xlim(0, len(times) - 1)
    if label:
        months = {t: datetime.fromtimestamp(times[t], tz=timezone.utc).strftime('%Y-%m') for t in ticks}
        ax.xaxis.set_major_formatter(FuncFormatter(
            lambda x, _: f'{int(x) // 1000}k\n{months.get(int(x), "")}' if x else f'0\n{months[0]}'))
        ax.set_xlabel('Block height (month)')
    else:
        ax.tick_params(labelbottom=False)
    ax.grid(True)
    ax.set_axisbelow(True)
