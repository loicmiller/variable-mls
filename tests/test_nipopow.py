"""The prover and the verifiers on synthetic chains (vmls.nipopow)."""

import numpy as np
import pytest

from vmls.chain import Block
from vmls.nipopow import (Params, compare_blind, compare_published, compress, dissolve, level_changes,
                          lowest_common_ancestor, proof_level, proof_levels, score, split, upward)
from vmls.synthetic import make_fork, random_chain, scripted_chain

P = Params(K=4, k=6, chi=10)


@pytest.fixture(scope='module')
def chain():
    """A random chain of 3,000 blocks, shared by the module."""
    return random_chain(3_000, seed=1)


def test_proof_level_counts_blocks_at_and_above_each_level():
    blocks = scripted_chain([0] + [3] * 4 + [1] * 4)
    assert proof_level(blocks[1:], K=2) == 3
    assert proof_level(blocks[1:], K=3) == 1
    assert proof_level(blocks[1:], K=5) == 0


def test_compress_keeps_the_suffix_and_the_genesis_block(chain):
    proof = compress(chain, P)
    assert proof[0].height == 0
    assert proof[-P.k - P.chi:] == chain[-P.k - P.chi:]
    assert [b.height for b in proof] == sorted({b.height for b in proof})
    assert len(proof) < len(chain) / 10


def test_compress_is_idempotent(chain):
    proof = compress(chain, P)
    assert compress(proof, P) == proof


def test_onlineness(chain):
    # Mining on the proof gives the proof of the extended chain.
    proof = compress(chain[:2_000], P)
    for block in chain[2_000:2_300]:
        proof = compress(proof + [block], P)
    assert proof == compress(chain[:2_300], P)


def test_rows_keep_2K_blocks_and_overlap(chain):
    D, top, _ = dissolve(chain, P)
    assert len(upward(D[top], top)) == len(D[top])
    for mu in range(top):
        assert len(D[mu]) >= 2 * P.K
        above = D[mu + 1][-P.K:]
        assert set(b.height for b in above) <= set(b.height for b in D[mu])


def test_level_changes_match_proof_level(chain):
    block_levels = np.array([b.level for b in chain])
    levels = proof_levels(block_levels, P.K)
    for height in (10, 100, 1_000, 2_999):
        assert levels[height] == proof_level(chain[:height + 1], P.K)
    assert level_changes(block_levels, P.K) == sorted(level_changes(block_levels, P.K))


def test_lowest_common_ancestor_matches_blocks_by_hash(chain):
    D_1, _, _ = dissolve(chain, P)
    fork = make_fork(chain, 2_000, 900, 1, seed=3, blind=False)
    D_2, _, _ = dissolve(chain[:2_001] + fork, P)
    mu, b = lowest_common_ancestor(D_1, D_2)
    assert b.height <= 2_000
    assert mu == min(m for m in D_1 if any(x.height <= 2_000 for x in D_1[m]) and m in D_2)


def test_score_caps_outliers():
    blocks = [Block(i, 1, 1, 0, 10, 1) for i in range(9)] + [Block(9, 1, 1, 0, 10_000, 1)]
    assert score(blocks, 2) == 9 * 10 + 20
    assert score(blocks[:9], 2) == 90


def test_honest_proof_beats_a_weaker_fork(chain):
    honest = compress(chain, P)
    fork = make_fork(chain, 2_400, 300, 1, seed=5, blind=False)
    other = compress(chain[:2_401] + fork, P)
    assert compare_published(honest, other, P)[0] == 1
    assert compare_published(other, honest, P)[0] == 2
    winner, path = compare_blind(honest, other, P, v=33)
    assert winner in (1, None) and path in ('level-0', 'score', 'online')


def test_split_separates_X_and_Omega(chain):
    proof = compress(chain, P)
    D, X, Omega = split(proof, P)
    assert len(X) == P.chi and len(Omega) == P.k
    assert X + Omega == proof[-P.k - P.chi:]
