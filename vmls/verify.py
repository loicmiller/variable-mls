"""The verifier: checking a proof, then comparing two (Algorithms 2 and 3 of the papers).

check reads the headers of a proof as encoding writes them: the proof starts at the genesis block the verifier knows;
each header is hashed and its proof of work checked against the target in its bits; each block is linked to the one
before it in the proof (by its previous hash in X and Omega, which are contiguous, and in D by its previous hash, a
pointer, an interlink or a tuple); each level is the one the construction gives, from the hash and the target under
ccs2025 and from the revealed nonce, which must open its commitment, under ours. check_model does the same work by
formula, hashing a buffer of the right length, without reading any field: it is what measurements did before real
headers, kept to compare the two.

The online test of Algorithm 3 waits for blocks to come; the comparisons here stop where it would start and say so.

    winner, branch = compare_ours(proof_1, proof_2, Params(), v=[2.4, 2.4, 2.4, 2.6])
"""

import random
import statistics
from collections.abc import Sequence

from vmls.chain import Block, bits_to_target, ccs_level, committed_level, sha256, sha256d
from vmls.encoding import HASH, decode, header_size
from vmls.proof import Params, split, upward

STAND_IN = random.Random(0).randbytes(20_000)  # Stand-in for header bytes in check_model: only its length matters.


def check(proof: list[Block], headers: list[bytes], construction: str, p: Params, genesis: int) -> None:
    """Checks a proof from its headers.

    Args:
        proof: The blocks of the proof, for their hash (exported headers lack the fields it is computed from), the
            level they claim and, under ours, their revealed nonce.
        headers: The bytes of each header, as encoding.encode writes them.
        construction: 'ccs2025' or 'ours'.
        p: The parameters.
        genesis: The hash of the genesis block, which the verifier knows.

    Raises:
        ValueError: If the proof does not start at the genesis block, or if a block misses its target, is not linked
            to the previous block of the proof, claims a level it does not have or does not open its commitment.
    """
    if not proof or proof[0].hash != genesis:
        raise ValueError('the proof does not start at the genesis block')
    revealed = len(proof) - p.k
    contiguous = len(proof) - p.k - p.chi  # X and Omega start here: each of their blocks follows the one before it.
    for i, (block, data) in enumerate(zip(proof, headers, strict=True)):
        sha256d(data)  # The header id a verifier computes; its value is the block hash here, see the docstring.
        header = decode(data, construction, p.k)
        target = bits_to_target(header.bits)
        if block.hash > target:
            raise ValueError(f'block {block.height} misses its target')
        previous = proof[i - 1].hash.to_bytes(HASH, 'big') if i else header.previous
        if previous != header.previous and (i >= contiguous or previous not in header.pointers):
            raise ValueError(f'block {block.height} is not linked to block {proof[i - 1].height}')
        if construction == 'ccs2025' and i and ccs_level(block.hash, target) != block.level:
            raise ValueError(f'block {block.height} claims level {block.level}')
        if construction == 'ours' and block.ctr is None and block.height and block.level:
            raise ValueError(f'block {block.height} claims level {block.level} without a revealed nonce')
        if construction == 'ours' and i < revealed and block.height and block.ctr is not None:
            if sha256(block.ctr) != header.commitment:
                raise ValueError(f'block {block.height} does not open its commitment')
            if committed_level(block.ctr, block.hash) != block.level:
                raise ValueError(f'block {block.height} claims level {block.level}')


def check_model(proof: list[Block], construction: str, p: Params) -> None:
    """The work of check by formula: one hash of a stand-in of each header's length, no field read.

    Args:
        proof: The blocks of the proof.
        construction: 'ccs2025' or 'ours'.
        p: The parameters.

    Raises:
        ValueError: If a block misses its target or does not open its commitment.
    """
    revealed = len(proof) - p.k
    for i, block in enumerate(proof):
        sha256d(STAND_IN[:header_size(construction, block.height, p.k)])
        if block.hash > block.target:
            raise ValueError(f'block {block.height} misses its target')
        if construction == 'ccs2025' and i:
            ccs_level(block.hash, block.target)
        if construction == 'ours' and i < revealed and block.height and block.ctr is not None:
            sha256(block.ctr)
            committed_level(block.ctr, block.hash)


def reveal_coverage(proof: list[Block], headers: list[bytes], p: Params) -> float:
    """Under ours, the share of revealed blocks of D whose nonce a later header of the proof carries.

    The papers keep a nonce alive through the tuples of later headers; this measures how often a proof carries the
    nonce of each of its own blocks.

    Args:
        proof: The blocks of the proof.
        headers: Their headers.
        p: The parameters.

    Returns:
        The share, 1.0 when every block of D is covered.
    """
    D, _, _ = split(proof, p)
    blocks = {b.height: b for row in D.values() for b in row if b.height and b.level > 0}
    carried = {h for data in headers for h, ctr in decode(data, 'ours', p.k).nonces if ctr != bytes(HASH)}
    covered = sum(b.hash.to_bytes(HASH, 'big') in carried for b in blocks.values())
    return covered / len(blocks) if blocks else 1.0


def lowest_common_ancestor(D_1: dict[int, list[Block]], D_2: dict[int, list[Block]]) -> tuple[int | None, Block | None]:
    """The lowest level at which two proofs share a block, and the last block they share there (matched by hash).

    Args:
        D_1: The rows of the first proof.
        D_2: The rows of the second proof.

    Returns:
        The level and the block, or (None, None) if the proofs share no block.
    """
    for mu in sorted(D_1.keys() & D_2.keys()):
        hashes = {block.hash for block in D_2[mu]}
        shared = [block for block in D_1[mu] if block.hash in hashes]
        if shared:
            return mu, shared[-1]
    return None, None


def after(row: list[Block], b: Block) -> list[Block]:
    """The blocks of a row from b on, D{b:} in the papers."""
    return row[next(i for i, block in enumerate(row) if block.hash == b.hash):]


def work(blocks: list[Block]) -> int:
    """The accumulated work of blocks, ||B|| in the papers."""
    return sum(block.work for block in blocks)


def score(blocks: list[Block], v: float) -> float:
    """Score (Algorithm 4): each block's work capped at v times the median work of the blocks.

    Args:
        blocks: Blocks of a single level.
        v: The factor v_mu.

    Returns:
        The capped accumulated work.
    """
    cap = v * statistics.median(block.work for block in blocks)
    return sum(min(block.work, cap) for block in blocks)


def compare_ccs(proof_1: list[Block], proof_2: list[Block], p: Params) -> tuple[int | None, str]:
    """The verifier of CCS 2025 (Algorithm 2): the work of the mu-blocks after the lowest common ancestor.

    Args:
        proof_1: The first proof.
        proof_2: The second proof.
        p: The parameters.

    Returns:
        The winner (1 or 2, None when the online test decides) and the branch: 'level-0', 'level-mu' or 'online'.
    """
    D_1, X_1, Omega_1 = split(proof_1, p)
    D_2, X_2, Omega_2 = split(proof_2, p)
    mu, b = lowest_common_ancestor(D_1, D_2)
    if mu is None:
        return None, 'online'
    work_1 = work(after(D_1[mu], b) + upward(X_1 + Omega_1, mu))
    work_2 = work(after(D_2[mu], b) + upward(X_2 + Omega_2, mu))
    return (2 if work_2 > work_1 else 1), ('level-0' if mu == 0 else 'level-mu')


def compare_ours(proof_1: list[Block], proof_2: list[Block], p: Params, v: Sequence[float]) -> tuple[int | None, str]:
    """Our verifier (Algorithm 3), up to its online test.

    The blocks of Omega are not revealed yet, so they have level 0: they count at level 0 and not above.

    Args:
        proof_1: The first proof.
        proof_2: The second proof.
        p: The parameters.
        v: The factor v_mu of Score for each level mu (measure.v_by_level); the last one serves the levels above.

    Returns:
        The winner (1 or 2, None when the online test decides) and the branch: 'level-0', 'score' or 'online'.
    """
    D_1, X_1, Omega_1 = split(proof_1, p)
    D_2, X_2, Omega_2 = split(proof_2, p)
    mu, b = lowest_common_ancestor(D_1, D_2)
    if mu is None:
        return None, 'online'
    row_1, row_2 = after(D_1[mu], b), after(D_2[mu], b)
    if mu == 0:
        return (1 if work(row_1 + X_1 + Omega_1) >= work(row_2 + X_2 + Omega_2) else 2), 'level-0'
    if len(row_1) >= p.K and len(row_2) >= p.K:
        v_mu = v[min(mu, len(v) - 1)]
        return (1 if score(row_1 + upward(X_1, mu), v_mu) > score(row_2 + upward(X_2, mu), v_mu) else 2), 'score'
    return None, 'online'
