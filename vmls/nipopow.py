"""The prover (Dissolve, Compress) and the verifier rules.

A proof is the list of blocks it keeps: the abridged subchain D, sampled level by level from the prefix of the chain,
then the uncompressed subchain X of chi blocks and the unstable subchain Omega of the last k blocks.
"""

import statistics
from dataclasses import dataclass

import numpy as np

from vmls.chain import Block


@dataclass(frozen=True)
class Params:
    """Parameters of a NIPoPoW.

    Attributes:
        K: Security parameter: a level enters the proof once it has 2K blocks.
        k: Common prefix parameter, the length of the unstable subchain Omega.
        chi: Length of the uncompressed subchain X.
    """

    K: int = 208
    k: int = 323
    chi: int = 4032


def upward(chain: list[Block], mu: int) -> list[Block]:
    """The blocks of level mu or above, the C↑mu of the papers.

    Args:
        chain: The blocks.
        mu: The level.

    Returns:
        The blocks of level at least mu, in order.
    """
    return [block for block in chain if block.level >= mu]


def proof_level(blocks: list[Block], K: int) -> int:
    """Highest level with at least 2K blocks, counting a block at its level and every level below.

    Args:
        blocks: The blocks.
        K: The security parameter.

    Returns:
        The level, 0 if no level has 2K blocks.
    """
    counts = {}
    for block in blocks:
        counts[block.level] = counts.get(block.level, 0) + 1
    cumulative = 0
    for mu in sorted(counts, reverse=True):
        cumulative += counts[mu]
        if cumulative >= 2 * K:
            return mu
    return 0


def dissolve(chain: list[Block], p: Params) -> tuple[dict[int, list[Block]], int, list[Block]]:
    """Samples the prefix of a chain level by level, as the prover of the papers.

    Args:
        chain: The chain or a proof of it.
        p: The parameters.

    Returns:
        The rows D[mu] of the abridged subchain, the level of the proof, and the last chi + k blocks.
    """
    prefix = chain[:-p.k - p.chi]
    D = {}
    if len(prefix) >= 2 * p.K:
        top = proof_level(prefix, p.K)
        above = upward(prefix, top)
        D[top] = above
        for mu in range(top - 1, -1, -1):
            b = above[-p.K]
            row = upward(prefix, mu)
            index = next(i for i, block in enumerate(row) if block.height == b.height)
            D[mu] = row[min(len(row) - 2 * p.K, index):]
            above = row
    else:
        top = 0
        D[0] = prefix
    return D, top, chain[-p.k - p.chi:]


def compress(chain: list[Block], p: Params) -> list[Block]:
    """The proof of a chain: the blocks of D in height order, then the last chi + k blocks.

    Args:
        chain: The chain or a proof of it.
        p: The parameters.

    Returns:
        The proof.
    """
    D, _, suffix = dissolve(chain, p)
    kept = {block.height: block for row in D.values() for block in row}
    return [kept[height] for height in sorted(kept)] + suffix


def split(proof: list[Block], p: Params) -> tuple[dict[int, list[Block]], list[Block], list[Block]]:
    """Dissolves a proof and separates its uncompressed and unstable subchains.

    Args:
        proof: The proof.
        p: The parameters.

    Returns:
        D, X and Omega.
    """
    D, _, suffix = dissolve(proof, p)
    return D, suffix[:-p.k], suffix[-p.k:]


def lowest_common_ancestor(D_1: dict, D_2: dict) -> tuple[int | None, Block | None]:
    """Lowest level at which two proofs share a block, and their last shared block at that level.

    Blocks are matched by hash, since two proofs of different chains can hold different blocks at one height.

    Args:
        D_1: The rows of the first proof.
        D_2: The rows of the second proof.

    Returns:
        The level and the block, or (None, None) if the proofs share no block.
    """
    common = {}
    for mu in D_1.keys() & D_2.keys():
        hashes = {block.block_hash for block in D_2[mu]}
        shared = [block for block in D_1[mu] if block.block_hash in hashes]
        if shared:
            common[mu] = shared
    if not common:
        return None, None
    mu = min(common)
    return mu, common[mu][-1]


def from_block(row: list[Block], b: Block) -> list[Block]:
    """The blocks of a row from a given block on, the D{b:} of the papers.

    Args:
        row: A row of D.
        b: The block, included.

    Returns:
        The blocks from b on.
    """
    return row[next(i for i, block in enumerate(row) if block.block_hash == b.block_hash):]


def difficulty_sum(blocks: list[Block]) -> int:
    """Accumulated difficulty of blocks.

    Args:
        blocks: The blocks.

    Returns:
        The sum of their difficulties.
    """
    return sum(block.diff for block in blocks)


def score(blocks: list[Block], v: float) -> float:
    """The Score of the new construction: each difficulty capped at v times the median difficulty.

    Args:
        blocks: Blocks of a single level.
        v: The factor v_mu.

    Returns:
        The capped accumulated difficulty.
    """
    cap = v * statistics.median(block.diff for block in blocks)
    return sum(min(block.diff, cap) for block in blocks)


def compare_published(proof_1: list[Block], proof_2: list[Block], p: Params) -> tuple[int | None, str]:
    """The verifier of the CCS 2025 paper (Algorithm 2): accumulated difficulty of the mu-blocks after the ancestor.

    The code tagged ccs-2025 counts X and Omega whatever their level; the paper counts their mu-blocks only, and that
    is the verifier the zero-difficulty attack defeats.

    Args:
        proof_1: The first proof.
        proof_2: The second proof.
        p: The parameters.

    Returns:
        The winner (1 or 2, None for the online test) and the branch taken: 'level-0', 'level-mu' or 'online'.
    """
    D_1, X_1, Omega_1 = split(proof_1, p)
    D_2, X_2, Omega_2 = split(proof_2, p)
    mu, b = lowest_common_ancestor(D_1, D_2)
    if mu is None:
        return None, 'online'
    score_1 = difficulty_sum(from_block(D_1[mu], b) + upward(X_1 + Omega_1, mu))
    score_2 = difficulty_sum(from_block(D_2[mu], b) + upward(X_2 + Omega_2, mu))
    return (2 if score_2 > score_1 else 1), ('level-0' if mu == 0 else 'level-mu')


def compare_blind(proof_1: list[Block], proof_2: list[Block], p: Params, v: float) -> tuple[int | None, str]:
    """The verifier of the new construction, without the wait of its online test.

    The blocks of Omega are left out of the Score, since an honest prover has not revealed them yet.

    Args:
        proof_1: The first proof.
        proof_2: The second proof.
        p: The parameters.
        v: The factor v_mu.

    Returns:
        The winner (1 or 2, None for the online test) and the branch taken: 'level-0', 'score' or 'online'.
    """
    D_1, X_1, Omega_1 = split(proof_1, p)
    D_2, X_2, Omega_2 = split(proof_2, p)
    mu, b = lowest_common_ancestor(D_1, D_2)
    if mu is None:
        return None, 'online'
    row_1, row_2 = from_block(D_1[mu], b), from_block(D_2[mu], b)
    if mu == 0:
        return (1 if difficulty_sum(row_1 + X_1 + Omega_1) >= difficulty_sum(row_2 + X_2 + Omega_2) else 2), 'level-0'
    if len(row_1) >= p.K and len(row_2) >= p.K:
        return (1 if score(row_1 + upward(X_1, mu), v) > score(row_2 + upward(X_2, mu), v) else 2), 'score'
    return None, 'online'


def level_changes(block_levels: np.ndarray, K: int) -> list[int]:
    """Heights at which the level of the whole proof grows, from the level of each block.

    This is the proof_level of the CCS 2025 data: the highest level with 2K blocks in the whole proof. Every block of
    that level is in the proof, so counting them over the chain is enough.

    Args:
        block_levels: The level of each block, the genesis block included.
        K: The security parameter.

    Returns:
        The height of each change, by increasing level.
    """
    changes = []
    for mu in range(1, int(block_levels[1:].max()) + 1):
        height = int(np.searchsorted(np.cumsum(block_levels >= mu), 2 * K))
        if height < len(block_levels):
            changes.append(height)
    return changes


def proof_levels(block_levels: np.ndarray, K: int) -> np.ndarray:
    """Level of the whole proof at each height, with the convention of level_changes.

    Args:
        block_levels: The level of each block, the genesis block included.
        K: The security parameter.

    Returns:
        One level per height.
    """
    levels = np.zeros(len(block_levels), dtype=np.uint16)
    for mu, height in enumerate(level_changes(block_levels, K), start=1):
        levels[height:] = mu
    return levels
