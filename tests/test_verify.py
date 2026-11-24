"""The verifier: header checks and every tampering they must catch, Score, and both comparison rules (vmls.verify)."""

import dataclasses

import pytest

from vmls.chain import GENESIS_TARGET, make_fork, random_chain, scripted_chain
from vmls.encoding import HASH, Links, encode
from vmls.proof import Params, compress, dissolve, split
from vmls.verify import (after, check, check_model, compare_ccs, compare_ours, lowest_common_ancestor,
                         reveal_coverage, score, work)

P = Params(K=8, k=6, chi=40)


def encoded(chain, proof, construction, p=P):
    """The headers of a proof of a chain."""
    links = Links(chain, construction, p.k)
    return [encode(chain, links, b.height) for b in proof]


@pytest.fixture(scope='module', params=['ccs2025', 'ours'])
def honest(request):
    """A chain, its proof and the proof's headers, under each construction."""
    chain = random_chain(6000, seed=1, construction=request.param)
    proof = compress(chain, P)
    return request.param, chain, proof, encoded(chain, proof, request.param)


def test_an_honest_proof_passes(honest):
    construction, chain, proof, headers = honest
    check(proof, headers, construction, P)
    check_model(proof, construction, P)


def test_a_block_missing_its_target_is_caught(honest):
    construction, chain, proof, headers = honest
    i = len(proof) // 2
    bad = proof[:i] + [dataclasses.replace(proof[i], hash=proof[i].target + 1)] + proof[i + 1:]
    with pytest.raises(ValueError, match='target'):
        check(bad, headers, construction, P)


def test_blocks_cut_out_of_a_proof_are_caught(honest):
    """Cutting more than k blocks after a level-0 block leaves the next one pointing to nothing the proof holds.

    Removing a single low block may leave the proof linked through a higher interlink, as for any NIPoPoW.
    """
    construction, chain, proof, headers = honest
    start = len(proof) - P.k - P.chi
    i = next(i for i in range(start + 1, len(proof) - 2 * P.k) if proof[i - 1].level == 0)
    cut = P.k + 1
    with pytest.raises(ValueError, match='not linked'):
        check(proof[:i] + proof[i + cut:], headers[:i] + headers[i + cut:], construction, P)


def test_a_wrong_pointer_is_caught(honest):
    construction, chain, proof, headers = honest
    i = 5
    data = bytearray(headers[i])
    data[4:36] = bytes(32)  # The previous hash.
    if construction == 'ours':
        data[108:] = bytes(len(data) - 108)  # The k - 1 pointers and every tuple.
    else:
        data[80:] = bytes(len(data) - 80)  # The interlink.
    with pytest.raises(ValueError, match='not linked'):
        check(proof, headers[:i] + [bytes(data)] + headers[i + 1:], construction, P)


def test_a_nonce_that_does_not_open_its_commitment_is_caught():
    chain = random_chain(3000, seed=2, construction='ours')
    proof = compress(chain, P)
    headers = encoded(chain, proof, 'ours')
    i = 10
    bad = proof[:i] + [dataclasses.replace(proof[i], ctr=bytes(32))] + proof[i + 1:]
    with pytest.raises(ValueError, match='commitment'):
        check(bad, headers, 'ours', P)


def test_a_level_claimed_without_its_nonce_is_caught():
    chain = random_chain(3000, seed=3, construction='ours')
    proof = compress(chain, P)
    headers = encoded(chain, proof, 'ours')
    i = next(i for i, b in enumerate(proof) if b.height and b.level > 0)
    bad = proof[:i] + [dataclasses.replace(proof[i], ctr=None)] + proof[i + 1:]
    with pytest.raises(ValueError, match='without a revealed nonce'):
        check(bad, headers, 'ours', P)


def test_headers_of_another_chain_are_not_linked():
    a, b = random_chain(3000, seed=4), random_chain(3000, seed=5)
    proof = compress(a, P)
    links = Links(b, 'ccs2025', P.k)
    with pytest.raises(ValueError, match='not linked'):
        check(proof, [encode(b, links, block.height) for block in proof], 'ccs2025', P)


def test_reveal_coverage_is_a_share():
    chain = random_chain(6000, seed=6, construction='ours')
    proof = compress(chain, P)
    share = reveal_coverage(proof, encoded(chain, proof, 'ours'), P)
    assert 0.5 < share <= 1.0


def test_score_caps_an_outlier_and_counts_an_honest_sequence_in_full():
    chain = scripted_chain([0] + [1] * 9)
    honest = chain[1:]
    assert score(honest, v=2.0) == work(honest)
    outlier = honest[:-1] + [dataclasses.replace(honest[-1], target=GENESIS_TARGET // 1000)]
    assert score(outlier, v=2.0) == work(honest[:-1]) + 2 * honest[0].work
    assert score(outlier, v=2000.0) == work(outlier)


def test_lowest_common_ancestor_is_matched_by_hash():
    chain = random_chain(3000, seed=7)
    proof = compress(chain, P)
    fork = make_fork(chain, 2000, 900, 1, seed=8, construction='ccs2025')
    other = compress(chain[:2001] + fork, P)
    D_1, _, _ = split(proof, P)
    D_2, _, _ = split(other, P)
    mu, b = lowest_common_ancestor(D_1, D_2)
    assert b.height <= 2000 and all(x.hash != b.hash for x in fork)
    assert after(D_1[mu], b)[0] is b
    assert lowest_common_ancestor(D_1, {}) == (None, None)


@pytest.mark.parametrize('depth', [2000, 6000, 12000])
def test_the_honest_proof_beats_weaker_forks(depth):
    """A fork with half the honest blocks loses, at every depth, under both rules (K large enough for the odds)."""
    p = Params(K=32, k=6, chi=40)
    for construction, compare in (('ccs2025', lambda a, b: compare_ccs(a, b, p)),
                                  ('ours', lambda a, b: compare_ours(a, b, p, v=33.0))):
        for seed in range(3):
            chain = random_chain(20_000, seed=depth + seed, construction=construction)
            proof = compress(chain, p)
            fork = make_fork(chain, len(chain) - 1 - depth, depth // 2, 1, seed=seed, construction=construction)
            other = compress(chain[:len(chain) - depth] + fork, p)
            winner, branch = compare(proof, other)
            assert winner == 1 or branch == 'online', (construction, depth, seed, winner, branch)
            assert compare(other, proof)[0] in (2, None)


def test_branches_of_our_verifier():
    chain = random_chain(8000, seed=10, construction='ours')
    proof = compress(chain, P)
    near = compress(chain[:-3] + make_fork(chain, len(chain) - 4, 2, 1, seed=1, construction='ours'), P)
    assert compare_ours(proof, near, P, v=33.0) == (1, 'level-0')
    deep = compress(chain[:4000] + make_fork(chain, 3999, 3200, 1, seed=2, construction='ours'), P)
    assert compare_ours(proof, deep, P, v=33.0)[1] in ('score', 'online')


def zero_difficulty_attack(construction: str, reveal: bool = True):
    """The attack of the papers on a synthetic chain.

    b* is the last block at the proof level followed by k + chi lower blocks: the honest proof then holds no block of
    that level after b*, while the adversary forks after b* and mines, at a far easier target, enough blocks for K
    of them to reach that level.

    Returns:
        The parameters, the honest proof and the adversarial proof.
    """
    p = Params(K=8, k=6, chi=40)
    chain = random_chain(40_000, seed=12, construction=construction)
    for star in range(len(chain) - p.k - p.chi - 2, 0, -1):
        top = dissolve(chain[:star + p.k + p.chi + 2], p)[1]
        if chain[star].level >= top and all(b.level < top for b in chain[star + 1:star + p.k + p.chi + 2]):
            break
    honest = compress(chain[:star + p.k + p.chi + 2], p)
    fork = make_fork(chain, star, 8 * 2 ** top * p.K, 4 ** 6, seed=13, construction=construction)
    kth = [i for i, b in enumerate(fork) if b.level >= top][p.K - 1]  # Stop once K top-level blocks follow b*.
    fork = fork[:kth + 1 + p.chi + p.k]
    if not reveal:
        for b in fork:
            b.ctr, b.level = None, 0
    return p, honest, compress(chain[:star + 1] + fork, p)


def test_the_zero_difficulty_attack_beats_ccs_and_not_ours():
    p, honest, adversarial = zero_difficulty_attack('ccs2025')
    assert compare_ccs(honest, adversarial, p)[0] == 2  # CCS 2025 accepts the forged proof.
    p, honest, adversarial = zero_difficulty_attack('ours')
    assert compare_ours(honest, adversarial, p, v=33.0)[0] in (1, None)  # Ours rejects it or waits.


def test_hiding_nonces_does_not_help_the_adversary():
    p, honest, revealed = zero_difficulty_attack('ours', reveal=True)
    p, honest, hidden = zero_difficulty_attack('ours', reveal=False)
    assert compare_ours(honest, hidden, p, v=33.0)[0] in (1, None)
    assert compare_ours(honest, revealed, p, v=33.0)[0] in (1, None)
