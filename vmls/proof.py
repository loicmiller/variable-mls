"""The prover: Dissolve and Compress (Algorithm 1 of the papers), the same for both constructions.

A proof keeps three parts of a chain C:

- Omega, the unstable subchain: the last k blocks, kept whole;
- X, the uncompressed subchain: the chi = 2m headers before them, so that a miner can recompute the next target;
- D, the abridged subchain, sampled from the rest C': at the proof level l, every l-block of C'; at each level mu
  below, the last 2K mu-blocks and every mu-block after the K-th last (mu+1)-block.

A proof is itself a chain, so Compress applies to a proof extended by new blocks: that is how a prover updates it.
A prover that starts from the headers can instead fill D while it computes the levels, in one pass over the chain
(compress_in_one_pass): the same proof, without holding the chain.

    proof = compress(chain, Params(K=208, k=6))
"""

import bisect
from collections.abc import Iterable
from dataclasses import dataclass

from vmls.chain import Block

_BATCH = 4096  # Blocks entering C' at a time in compress_in_one_pass.


@dataclass(frozen=True)
class Params:
    """Parameters of a NIPoPoW.

    Attributes:
        K: Security parameter (K* in the papers): a level enters the proof once it holds 2K blocks.
        k: Common prefix parameter, the length of the unstable subchain Omega; 6 for Bitcoin.
        chi: Length of the uncompressed subchain X, 2m = 4032 for Bitcoin.
    """

    K: int = 208
    k: int = 6
    chi: int = 4032


def upward(blocks: list[Block], mu: int) -> list[Block]:
    """The mu-blocks of a chain, C↑mu in the papers: the blocks of level at least mu, in order."""
    return [block for block in blocks if block.level >= mu]


def proof_level(blocks: list[Block], K: int) -> int:
    """The highest level mu such that the blocks hold at least 2K mu-blocks, 0 if there is none.

    Args:
        blocks: The blocks.
        K: The security parameter.

    Returns:
        The level.
    """
    counts = {}
    for block in blocks:
        counts[block.level] = counts.get(block.level, 0) + 1
    total = 0
    for mu in sorted(counts, reverse=True):
        total += counts[mu]
        if total >= 2 * K:
            return mu
    return 0


def _row(prefix: list[Block], mu: int, count: int, start: Block | None) -> list[Block]:
    """The last mu-blocks of a prefix: at least count of them, and all of them from start on.

    Args:
        prefix: The compressible blocks.
        mu: The level.
        count: The number of most recent mu-blocks to keep.
        start: The block from which every mu-block is kept too, if any.

    Returns:
        The blocks, in order.
    """
    row = []
    for block in reversed(prefix):
        if block.level >= mu:
            row.append(block)
            if len(row) >= count and (start is None or block.height <= start.height):
                break
    return row[::-1]


def dissolve(chain: list[Block], p: Params) -> tuple[dict[int, list[Block]], int, list[Block], list[Block]]:
    """Splits a chain, or a proof, into the rows of D, its level, X and Omega.

    Args:
        chain: The chain or a proof of it.
        p: The parameters.

    Returns:
        The rows D[mu], the proof level, X and Omega.
    """
    n = len(chain)
    omega = chain[max(n - p.k, 0):]
    x = chain[max(n - p.k - p.chi, 0):max(n - p.k, 0)]
    prefix = chain[:max(n - p.k - p.chi, 0)]
    if len(prefix) < 2 * p.K:
        return {0: prefix}, 0, x, omega
    level = proof_level(prefix, p.K)
    D = {level: upward(prefix, level)}
    for mu in range(level - 1, -1, -1):
        D[mu] = _row(prefix, mu, 2 * p.K, D[mu + 1][-p.K])
    return D, level, x, omega


def compress(chain: list[Block], p: Params) -> list[Block]:
    """The proof of a chain: the blocks of D in height order, then X and Omega.

    Args:
        chain: The chain or a proof of it.
        p: The parameters.

    Returns:
        The proof.
    """
    D, _, x, omega = dissolve(chain, p)
    kept = {block.height: block for row in D.values() for block in row}
    return [kept[height] for height in sorted(kept)] + x + omega


def compress_in_one_pass(blocks: Iterable[Block], p: Params) -> list[Block]:
    """The proof of a chain read once, from the genesis block, each block with its level: compress(chain, p).

    The last chi + k blocks wait in X and Omega; the blocks that leave them enter C' and the rows of their levels, a
    batch at a time. Since the counts of mu-blocks only grow, once level mu + 1 holds 2K blocks, level mu is below the
    proof level for good, and its row needs nothing before the K-th last (mu+1)-block (b† of Algorithm 1) and the
    2K-th last mu-block: the rest is dropped after each batch, so the prover holds O(K) blocks per level.

    Args:
        blocks: The blocks of the chain in height order, levels computed.
        p: The parameters.

    Returns:
        The proof, as compress returns it.
    """
    wait, batch, need = p.chi + p.k, max(p.chi + p.k, _BATCH), 2 * p.K
    rows, dropped = [[]], [0]  # The mu-blocks of C' still needed, and how many were dropped, by level mu.
    appends = [rows[0].append]

    def enter(chunk: list[Block]) -> None:
        for b in chunk:
            level = b.level
            if level == 0:
                appends[0](b)
                continue
            while len(rows) <= level:
                rows.append([])
                dropped.append(0)
                appends.append(rows[-1].append)
            for mu in range(level + 1):
                appends[mu](b)
        for mu in range(len(rows) - 1):
            row, upper = rows[mu], rows[mu + 1]
            if dropped[mu + 1] + len(upper) >= need and len(row) > 4 * need:
                cut = min(bisect.bisect_left(row, upper[-p.K].height, key=lambda x: x.height), len(row) - need)
                del row[:cut]
                dropped[mu] += cut

    tail = []
    for block in blocks:
        tail.append(block)
        if len(tail) >= wait + batch:
            enter(tail[:-wait] if wait else tail)
            tail = tail[-wait:] if wait else []
    enter(tail[:len(tail) - wait] if len(tail) > wait else [])
    tail = tail[-wait:] if wait else []
    x, omega = tail[:max(len(tail) - p.k, 0)], tail[max(len(tail) - p.k, 0):]
    counts = [d + len(row) for d, row in zip(dropped, rows)]
    if counts[0] < need:
        return rows[0] + x + omega
    level = max(mu for mu, count in enumerate(counts) if count >= need)
    D = {level: rows[level]}
    for mu in range(level - 1, -1, -1):
        D[mu] = _row(rows[mu], mu, need, D[mu + 1][-p.K])
    kept = {block.height: block for row in D.values() for block in row}
    return [kept[height] for height in sorted(kept)] + x + omega


def split(proof: list[Block], p: Params) -> tuple[dict[int, list[Block]], list[Block], list[Block]]:
    """The rows of D, X and Omega of a proof, as the verifier reads them (Algorithm 3, lines 2-3)."""
    D, _, x, omega = dissolve(proof, p)
    return D, x, omega
