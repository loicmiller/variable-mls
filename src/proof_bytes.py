###############################################################################
# Imports

import math



###############################################################################
# Constants

BITCOIN_HEADER = 80 # Bytes of a Bitcoin block header.
HASH = 32 # Bytes of a hash, hence of a pointer or of a revealed nonce (a 32-bit nonce would not hide the level).
COMMITMENT_OVERHEAD = HASH - 4 # H(ctr) replaces the 4-byte nonce of the header.



###############################################################################
# Model

def n_levels(height):
    """
    Number of levels a header at this height keeps pointers for.

    Args:
    - height (int): The height of the block.

    Returns:
    - int: log2 of the chain length, the "up to log(#C)" of the paper.
    """
    return max(1, math.ceil(math.log2(height + 2)))


def merkle_path(n_leaves):
    """
    Size of a Merkle inclusion path.

    Args:
    - n_leaves (int): The number of leaves of the tree.

    Returns:
    - int: The size of the path, in bytes.
    """
    return math.ceil(math.log2(max(n_leaves, 2))) * HASH


def header_size(scheme, height, k):
    """
    Size of a block header in each scheme.

    Args:
    - scheme (str): One of 'ccs', 'ccs-merkle', 'draft', 'draft-merkle'.
    - height (int): The height of the block.
    - k (int): The common prefix parameter.

    Returns:
    - int: The size of the header, in bytes.

    Notes:
    - ccs: one pointer per level.
    - draft: the commitment, k pointers and one tuple (H(b1), ctr1, H(b2), ctr2) per level, as written in the draft.
    - *-merkle: pointers and tuples are moved under a single root in the header.
    - The block height the draft requires in the header (4 bytes) is left out of every scheme.
    """
    if scheme == 'ccs':
        return BITCOIN_HEADER + HASH * n_levels(height)
    if scheme == 'ccs-merkle':
        return BITCOIN_HEADER + HASH
    if scheme == 'draft':
        return BITCOIN_HEADER + COMMITMENT_OVERHEAD + HASH * k + 4 * HASH * n_levels(height)
    if scheme == 'draft-merkle':
        return BITCOIN_HEADER + COMMITMENT_OVERHEAD + HASH
    raise ValueError(scheme)


def draft_leaves(height, k):
    """
    Number of leaves under the root of a 'draft-merkle' header.

    Args:
    - height (int): The height of the block.
    - k (int): The common prefix parameter.

    Returns:
    - int: The k pointers and the 4 entries of each level's tuple.
    """
    return k + 4 * n_levels(height)


def proof_size(scheme, D_heights, X_heights, Omega_heights, k):
    """
    Size of a NIPoPoW in each scheme.

    Args:
    - scheme (str): One of 'ccs', 'ccs-merkle', 'draft', 'draft-merkle'.
    - D_heights (list): The heights of the blocks of the abridged subchain D.
    - X_heights (list): The heights of the blocks of the uncompressed subchain X.
    - Omega_heights (list): The heights of the blocks of the unstable subchain Omega.
    - k (int): The common prefix parameter.

    Returns:
    - int: The size of the proof, in bytes.

    Notes:
    - D is a merged chain, so each of its blocks carries one link to its predecessor in the proof.
    - X and Omega are consecutive blocks: the previous-block hash of the header links them.
    - draft-merkle: a block of D also carries its nonce, opened from the block that reveals it; a block of X only
      needs its nonce, since its level enters the score; the blocks of Omega are not revealed yet.
    """
    size = sum(header_size(scheme, h, k) for h in D_heights)
    size += sum(header_size(scheme, h, k) for h in X_heights)
    size += sum(header_size(scheme, h, k) for h in Omega_heights)
    if scheme == 'ccs-merkle':
        size += sum(HASH + merkle_path(n_levels(h)) for h in D_heights)
    if scheme == 'draft-merkle':
        size += sum(2 * (HASH + merkle_path(draft_leaves(h, k))) for h in D_heights)
        size += sum(HASH + merkle_path(draft_leaves(h, k)) for h in X_heights)
    return size


def spv_size(height):
    """
    Size of all the headers of the chain, what an SPV client stores.

    Args:
    - height (int): The height of the tip.

    Returns:
    - int: The size, in bytes.
    """
    return BITCOIN_HEADER * (height + 1)
