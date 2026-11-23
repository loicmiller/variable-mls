"""The byte model of headers, proofs and Merkle paths.

Four schemes: 'ccs' (CCS 2025: one pointer per level in the header), 'draft' (blind mining as the draft writes it: a
commitment, k pointers and one tuple (H(b1), ctr1, H(b2), ctr2) per level), and their '-merkle' variants, where pointers
and tuples go under a single root and each opened value carries its Merkle path.
"""

import math

from vmls.chain import sha256

BITCOIN_HEADER = 80  # Bytes of a Bitcoin block header.
HASH = 32  # Bytes of a hash, hence of a pointer or of a revealed nonce (a 32-bit nonce would not hide the level).
COMMITMENT_OVERHEAD = HASH - 4  # H(ctr) replaces the 4-byte nonce of the header.
SCHEMES = ('ccs', 'ccs-merkle', 'draft', 'draft-merkle')


def n_levels(height: int) -> int:
    """Number of levels a header at this height keeps pointers for, the 'up to log(#C)' of the papers.

    Args:
        height: Height of the block.

    Returns:
        The number of levels.
    """
    return max(1, math.ceil(math.log2(height + 2)))


def merkle_path(n_leaves: int) -> int:
    """Size of a Merkle inclusion path.

    Args:
        n_leaves: Number of leaves of the tree.

    Returns:
        The size in bytes.
    """
    return math.ceil(math.log2(max(n_leaves, 2))) * HASH


def draft_leaves(height: int, k: int) -> int:
    """Number of leaves under the root of a 'draft-merkle' header: k pointers and 4 entries per level.

    Args:
        height: Height of the block.
        k: The common prefix parameter.

    Returns:
        The number of leaves.
    """
    return k + 4 * n_levels(height)


def header_size(scheme: str, height: int, k: int) -> int:
    """Size of a header. The block height the draft also requires (4 bytes) is left out of every scheme.

    Args:
        scheme: One of SCHEMES.
        height: Height of the block.
        k: The common prefix parameter.

    Returns:
        The size in bytes.

    Raises:
        ValueError: If the scheme is unknown.
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


def proof_size(scheme: str, D: list[int], X: list[int], Omega: list[int], k: int) -> int:
    """Size of the headers of a proof and of the Merkle paths it carries.

    D is a merged chain, so each of its blocks carries one link to its predecessor in the proof; X and Omega are
    consecutive blocks, linked by the previous-block hash. With 'draft-merkle', a block of D also carries its nonce,
    opened from the block that reveals it, and a block of X only its nonce; the blocks of Omega are not revealed yet.

    Args:
        scheme: One of SCHEMES.
        D: Heights of the blocks of the abridged subchain.
        X: Heights of the blocks of the uncompressed subchain.
        Omega: Heights of the blocks of the unstable subchain.
        k: The common prefix parameter.

    Returns:
        The size in bytes.
    """
    size = sum(header_size(scheme, h, k) for h in D + X + Omega)
    if scheme == 'ccs-merkle':
        size += sum(HASH + merkle_path(n_levels(h)) for h in D)
    if scheme == 'draft-merkle':
        size += sum(2 * (HASH + merkle_path(draft_leaves(h, k))) for h in D)
        size += sum(HASH + merkle_path(draft_leaves(h, k)) for h in X)
    return size


def spv_size(height: int) -> int:
    """Size of all the headers of the chain, what an SPV client stores.

    Args:
        height: Height of the tip.

    Returns:
        The size in bytes.
    """
    return BITCOIN_HEADER * (height + 1)


def merkle_root(leaves: list[bytes]) -> bytes:
    """Root of a Merkle tree rebuilt from its leaves.

    Args:
        leaves: The leaves.

    Returns:
        The root.
    """
    nodes = leaves
    while len(nodes) > 1:
        nodes = [sha256(b''.join(nodes[i:i + 2])) for i in range(0, len(nodes), 2)]
    return nodes[0]
