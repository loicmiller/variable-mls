"""The prover: Dissolve and Compress (Algorithm 1 of the papers), the same for both constructions.

A proof keeps three parts of a chain C:

- Omega, the unstable subchain: the last k blocks, kept whole;
- X, the uncompressed subchain: the chi = 2m headers before them, so that a miner can recompute the next target;
- D, the abridged subchain, sampled from the rest C': at the proof level l, every l-block of C'; at each level mu
  below, the last 2K mu-blocks and every mu-block after the K-th last (mu+1)-block.

A proof is itself a chain, so Compress applies to a proof extended by new blocks: that is how a prover updates it.

    proof = compress(chain, Params(K=208, k=6))
"""

from dataclasses import dataclass

from vmls.chain import Block


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


def split(proof: list[Block], p: Params) -> tuple[dict[int, list[Block]], list[Block], list[Block]]:
    """The rows of D, X and Omega of a proof, as the verifier reads them (Algorithm 3, lines 2-3)."""
    D, _, x, omega = dissolve(proof, p)
    return D, x, omega
