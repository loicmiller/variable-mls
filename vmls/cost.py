"""The hashing work of a prover and a verifier, to measure their time.

Historical headers carry neither the commitment nor the pointers of the schemes measured. The hash calls are real and
have the right input length, but their input is a stand-in; only the checks on block hashes, targets and commitments
compare real values.
"""

import hashlib
import random
import statistics
import time

from vmls.chain import Block, blind_level, sha256
from vmls.nipopow import Params, compare_blind, compare_published
from vmls.sizes import HASH, draft_leaves, header_size, merkle_path, n_levels

HASH_BUFFER = random.Random(0).randbytes(20_000)  # Stand-in for serialized headers: only its length matters to SHA-256.


def sha256d(data: bytes) -> bytes:
    """Double SHA-256, as Bitcoin hashes its headers.

    Args:
        data: The data to hash.

    Returns:
        The digest.
    """
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def validate_proof(proof: list[Block], scheme: str, p: Params) -> None:
    """What a verifier hashes and checks to accept a proof.

    Args:
        proof: The proof.
        scheme: One of vmls.sizes.SCHEMES.
        p: The parameters.

    Raises:
        ValueError: If a block does not satisfy its target or does not open its commitment.
    """
    n_compressed = len(proof) - p.k - p.chi
    n_revealed = len(proof) - p.k
    blind = scheme.startswith('draft')
    for i, block in enumerate(proof):
        sha256d(HASH_BUFFER[:header_size(scheme, block.height, p.k)])
        if block.block_hash > block.target:
            raise ValueError(f'block {block.height} does not satisfy its target')
        if blind and i < n_revealed:
            if sha256(block.ctr) != block.commitment:
                raise ValueError(f'block {block.height} does not open its commitment')
            blind_level(block.ctr, block.block_hash.to_bytes(32, 'big'))
        if scheme == 'ccs-merkle' and i < n_compressed:
            for _ in range(merkle_path(n_levels(block.height)) // HASH):
                sha256(HASH_BUFFER[:64])
        if scheme == 'draft-merkle' and i < n_revealed:
            depth = merkle_path(draft_leaves(block.height, p.k)) // HASH
            for _ in range(2 * depth if i < n_compressed else depth):
                sha256(HASH_BUFFER[:64])


def time_verifier(proof_1: list[Block], proof_2: list[Block], scheme: str, p: Params, v: float,
                  repetitions: int = 5) -> tuple[float, int | None, str]:
    """CPU time of a verifier that validates two proofs, dissolves them and compares them.

    Args:
        proof_1: The first proof.
        proof_2: The second proof.
        scheme: One of vmls.sizes.SCHEMES.
        p: The parameters.
        v: The factor v_mu of the Score.
        repetitions: Number of runs.

    Returns:
        The median time in milliseconds, the winner and the branch taken by the comparison.
    """
    timings = []
    for _ in range(repetitions):
        start = time.perf_counter_ns()
        validate_proof(proof_1, scheme, p)
        validate_proof(proof_2, scheme, p)
        if scheme.startswith('draft'):
            winner, path = compare_blind(proof_1, proof_2, p, v)
        else:
            winner, path = compare_published(proof_1, proof_2, p)
        timings.append(time.perf_counter_ns() - start)
    return statistics.median(timings) / 1e6, winner, path
