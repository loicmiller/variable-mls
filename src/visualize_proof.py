###############################################################################
# Imports

import matplotlib.pyplot as plt
from typing import Dict, List, Optional
import seaborn as sns



###############################################################################
# Visualization

# Color palette (discrete)
palette = sns.color_palette("deep", 5)

def block_color(b):
    """
    Assign a stable color to a block using its height.

    Args:
        b (Block): The block.

    Returns:
        color (tuple): The RGBA color tuple.
    """
    return palette[b.height % len(palette)]

def visualize_proof(full_chain: List, proof: List, dissolved_chain: Dict[int, List], k_args, chi_args, K_args, title: Optional[str] = None, square_size: float = 0.8, bar_width: float = 0.6) -> None:
    """
    Visualize an MLS proof with two side-by-side views:

    (a) Original chain (left): each block is drawn as a vertical rectangle
        from level 0 up to its block level, indexed by block height.
    (b) Dissolved chain (right): for each level μ, blocks are drawn as squares
        indexed by their position in the dissolved chain at that level,
        annotated with their block height.

    Args:
        full_chain (List): Full chain of blocks.
        proof (List): Compressed proof.
        dissolved_chain (Dict[int, List]): Output of Dissolve(proof).
        k_args (int): Parameter k.
        chi_args (int): Parameter chi.
        K_args (int): Parameter K.
        title (Optional[str]): Title of the figure.
        square_size (float): Size of squares.
        bar_width (float): Width of bars in original chain view.

    Returns:
        The visualization is displayed using matplotlib.
    """
    if not dissolved_chain:
        raise ValueError("Dissolved chain is empty")
    if not proof:
        raise ValueError("Proof is empty")

    levels = sorted(dissolved_chain.keys())
    max_level = max(b.level for b in proof[1:])  # Exclude genesis block
    max_len = max(len(dissolved_chain[mu]) for mu in levels)
    heights = [b.height for b in proof]

    # ------------------------------------------------------------------
    # Create figure with two subplots
    # ------------------------------------------------------------------

    fig, (ax_full, ax_proof, ax_levels) = plt.subplots(
        1, 3, figsize=(22, 6), sharey=False
    )

    # ==============================================================
    # (a) Full chain
    # ==============================================================

    for b in full_chain:
        visual_height = b.level + 1  # Ensure level 0 blocks are visible
        if b.height == 0:
            visual_height = max_level + 1  # Special case for genesis block

        ax_full.add_patch(
            plt.Rectangle(
                (b.height - bar_width / 2, -1),
                bar_width,
                visual_height,
                edgecolor="black",
                facecolor=block_color(b),
                linewidth=0.5
            )
        )

    ax_full.set_xlabel("Block height")
    ax_full.set_ylabel("Level")
    ax_full.set_title("(a) Full chain")
    ax_full.set_xlim(min([b.height for b in full_chain]) - 1, max([b.height for b in full_chain]) + 1)
    ax_full.set_ylim(-1, max_level + 1)
    ax_full.set_xticks([b.height for b in full_chain])

    # ==============================================================
    # (b) Original chain (proof)
    # ==============================================================

    for b in proof:
        visual_height = b.level + 1  # Ensure level 0 blocks are visible
        if b.height == 0:
            visual_height = max_level + 1  # Special case for genesis block

        ax_proof.add_patch(
            plt.Rectangle(
                (b.height - bar_width / 2, -1),
                bar_width,
                visual_height,
                edgecolor="black",
                facecolor=block_color(b),
                linewidth=0.5
            )
        )

    ax_proof.set_xlabel("Block height")
    ax_proof.set_ylabel("Level")
    ax_proof.set_title("(b) Proof blocks in original chain")
    ax_proof.set_xlim(min(heights) - 1, max(heights) + 1)
    ax_proof.set_ylim(-1, max_level + 1)
    ax_proof.set_xticks(heights)

    # ==============================================================
    # (c) Dissolved chain
    # ==============================================================

    for mu in levels:
        blocks = dissolved_chain[mu]
        for idx, b in enumerate(blocks):
            # Draw square
            x = max_len - len(blocks) + idx

            ax_levels.add_patch(
                plt.Rectangle(
                    (x - square_size / 2, mu - square_size / 2),
                    square_size,
                    square_size,
                    edgecolor="black",
                    facecolor=block_color(b),
                    linewidth=0.8
                )
            )

            # Annotate with block height
            ax_levels.text(
                x,
                mu,
                str(b.height),
                ha="center",
                va="center",
                fontsize=8,
                color="white"
            )


    ax_levels.set_xlabel("Index in level")
    ax_levels.set_ylabel("Level")
    ax_levels.set_yticks(levels)
    ax_levels.set_xlim(-1, max_len)
    ax_levels.set_ylim(min(levels) - 1, max(levels) + 1)
    ax_levels.set_title(title or "Dissolved MLS Proof Structure")

    # ------------------------------------------------------------------
    # Global formatting
    # ------------------------------------------------------------------

    params_str = f"k = {k_args}, χ = {chi_args}, K = {K_args}"

    if title:
        fig.suptitle(f"{title} - {params_str}", fontsize=14)
    else:
        fig.suptitle(f"MLS Proof ({params_str})", fontsize=14)

    plt.tight_layout()
    plt.show()
