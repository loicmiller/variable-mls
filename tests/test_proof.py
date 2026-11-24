"""The prover on synthetic chains: properties Algorithm 1 promises, checked on hundreds of random chains (vmls.proof)."""

import random

import pytest

from vmls.chain import GENESIS_LEVEL, random_chain, scripted_chain
from vmls.proof import Params, compress, dissolve, proof_level, upward

SMALL = Params(K=4, k=3, chi=8)


def chains(count: int, construction: str = 'ccs2025'):
    """Random chains of varied lengths, reproducible."""
    rng = random.Random(7)
    for seed in range(count):
        yield random_chain(rng.randrange(2, 1500), seed=seed, construction=construction)


def test_proof_level_counts_blocks_at_and_above_each_level():
    chain = scripted_chain([0, 2, 2, 1, 1, 3, 0])  # Levels >= 2: genesis, 2, 2, 3; levels >= 1: six blocks.
    assert proof_level(chain, K=2) == 2
    assert proof_level(chain, K=3) == 1
    assert proof_level(chain[:2], K=2) == 0


@pytest.mark.parametrize('construction', ['ccs2025', 'ours'])
def test_proof_is_a_subsequence_keeping_genesis_x_and_omega(construction):
    for chain in chains(150, construction):
        proof = compress(chain, SMALL)
        heights = [b.height for b in proof]
        assert heights == sorted(set(heights)) and all(chain[h] is b for h, b in zip(heights, proof))
        assert proof[0] is chain[0]
        tail = SMALL.k + SMALL.chi
        assert proof[-tail:] == chain[-tail:]


def test_rows_hold_2K_blocks_and_overlap_K():
    for chain in chains(150):
        D, top, x, omega = dissolve(chain, SMALL)
        prefix = chain[:len(chain) - len(x) - len(omega)]
        if len(prefix) < 2 * SMALL.K:
            assert D == {0: prefix} and top == 0
            continue
        assert D[top] == upward(prefix, top)
        assert any(b.level == GENESIS_LEVEL for b in D[top])
        for mu in range(top):
            row = D[mu]
            assert len(row) >= 2 * SMALL.K
            assert row == upward(prefix, mu)[-len(row):]  # A suffix of the mu-blocks.
            anchor = D[mu + 1][-SMALL.K]
            assert row[0].height <= anchor.height  # Every mu-block after the K-th last (mu+1)-block.
            assert len(row) == 2 * SMALL.K or row[0] is anchor


def test_level_is_the_highest_with_2K_blocks():
    for chain in chains(100):
        D, top, x, omega = dissolve(chain, SMALL)
        prefix = chain[:len(chain) - len(x) - len(omega)]
        if len(prefix) >= 2 * SMALL.K:
            assert len(upward(prefix, top)) >= 2 * SMALL.K
            assert len(upward(prefix, top + 1)) < 2 * SMALL.K or top + 1 > GENESIS_LEVEL


@pytest.mark.parametrize('construction', ['ccs2025', 'ours'])
def test_compress_is_idempotent(construction):
    for chain in chains(100, construction):
        proof = compress(chain, SMALL)
        assert compress(proof, SMALL) == proof


@pytest.mark.parametrize('construction', ['ccs2025', 'ours'])
def test_updating_a_proof_block_by_block_equals_compressing_the_chain(construction):
    """Onlineness: a prover that never held the chain ends with the proof of the chain."""
    for chain in list(chains(30, construction)):
        proof = []
        for block in chain:
            proof = compress(proof + [block], SMALL)
            assert proof == compress(chain[:block.height + 1], SMALL)


def test_bitcoin_sized_parameters_on_a_long_chain():
    chain = random_chain(60_000, seed=11)
    p = Params(K=104, k=6)
    proof = compress(chain, p)
    D, top, x, omega = dissolve(chain, p)
    assert len(x) == 4032 and len(omega) == 6
    assert 2 * 104 * 2 ** top <= 2 * (len(chain) - 4038)  # A level-top row needs about 2K * 2^top blocks.
    assert len(proof) < 4038 + 2 * 104 * (top + 1) * 2
