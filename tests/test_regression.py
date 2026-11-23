"""Regressions on the real chain, against reference data kept outside the repository (see conftest.py).

References: proofs of the previous code at 20 heights, 3 values of K, real and blind levels; the gamma notebook's
printed values; the gamma(s, w) brackets of November 2026; the checks of the blind-mining measurements.
"""

import hashlib
import json
from argparse import Namespace

import numpy as np
import pytest

from tests.conftest import HEADERS, REFERENCE, require
from vmls.chain import blocks_from_headers, load_headers
from vmls.nipopow import Params, compare_blind, compare_published, compress, dissolve, proof_level, score
from vmls.synthetic import deep_fork, make_fork, tip_fork

pytestmark = pytest.mark.slow
K, k, chi = 208, 323, 4032
P = Params(K, k, chi)
OCTOBER_2024_BLOCKS = 865_043  # The headers of the CCS 2025 paper.


@pytest.fixture(scope='module')
def headers():
    return load_headers(require(HEADERS))


@pytest.fixture(scope='module')
def chains(headers):
    return {blind: blocks_from_headers(headers, blind=blind) for blind in (False, True)}


def test_proofs_match_the_previous_code(chains):
    reference = json.loads(require(REFERENCE / 'old-compress-2026-11-23.json').read_text())
    for r in reference['proofs']:
        p = Params(K=r['K'])
        chain = chains[r['blind']][:r['height'] + 1]
        proof = compress(chain, p)
        D, top, _ = dissolve(chain, p)
        digest = hashlib.sha256(','.join(str(b.height) for b in proof).encode()).hexdigest()
        assert (len(proof), top, {str(mu): len(D[mu]) for mu in D}, digest) == (r['size'], r['level'], r['rows'], r['sha256']), r


def test_blind_levels_are_geometric(chains):
    chain = chains[True]
    n = len(chain) - 1
    counts = [0] * 13
    for block in chain[1:]:
        counts[min(block.level, 12)] += 1
    expected = [n * 2.0 ** -(mu + 1) for mu in range(12)] + [n * 2.0 ** -12]
    assert sum((c - e) ** 2 / e for c, e in zip(counts, expected)) < 32.9  # 12 degrees of freedom, p = 0.001.


def test_honest_score_is_the_accumulated_difficulty(chains):
    v = 1.51 * 1.995 / (0.25 * (1 - 1.995 * 0.03))  # gamma = 1.51, eta = 1/4.
    for mu in range(4):
        row = [b for b in chains[True][-200_000:] if b.level >= mu][-2 * K:]
        assert score(row, v) == sum(b.diff for b in row)


@pytest.mark.parametrize('blind', [False, True])
def test_honest_proof_never_loses(chains, blind):
    chain = chains[blind]
    proof = compress(chain, P)
    for name, other in (('tip', tip_fork(chain, proof, P, blind)), ('deep', deep_fork(chain, len(chain) - 1, P, blind))):
        winner, path = compare_blind(proof, other, P, 33.0) if blind else compare_published(proof, other, P)
        # The new verifier may leave a deep fork to the online test, when fewer than K blocks follow the ancestor.
        assert winner == 1 or (blind and name == 'deep' and path == 'online'), (name, winner, path)


def test_score_branch_on_the_ccs_headers(chains):
    prefix = chains[True][:OCTOBER_2024_BLOCKS]
    assert compare_blind(compress(prefix, P), deep_fork(prefix, len(prefix) - 1, P, True), P, 33.0) == (1, 'score')


@pytest.mark.parametrize('blind', [False, True])
def test_zero_difficulty_attack(chains, blind):
    # The latest high block of the proof's level followed by k + chi lower blocks: the attack conditions hold there.
    chain = chains[blind]
    for star in range(len(chain) - k - chi - 2, 0, -1):
        if chain[star].level >= 9:
            top = proof_level(chain[:star + 2], K)
            if chain[star].level >= top and all(b.level < top for b in chain[star + 1:star + k + chi + 2]):
                break
    honest = compress(chain[:star + k + chi + 2], P)
    fork = make_fork(chain, star, int(1.4 * 2 ** top * K) + 2 * 2016 + k, 4 ** 6, seed=star, blind=blind)
    adversarial = compress(chain[:star + 1] + fork, P)
    if blind:
        assert compare_blind(honest, adversarial, P, 33.0)[1] == 'online'
    else:
        assert compare_published(honest, adversarial, P)[0] == 2


def test_gamma_notebook_values():
    from experiments.gamma import estimate
    reference = json.loads(require(REFERENCE / 'gamma-865042.json').read_text())
    headers = require(HEADERS.parent / 'headers.json')
    result = estimate(Namespace(headers=headers, check_notebook=True))
    assert result['rows'][0]['q95'] == pytest.approx(reference['rows'][0]['q95'], rel=1e-12)


def test_gamma_bound_brackets(headers):
    from experiments.gamma import bound
    reference = json.loads(require(REFERENCE / 'gamma-bound-974505.json').read_text())
    if reference['n_headers'] != len(headers):
        pytest.skip('reference measured on another headers file')
    result = bound(Namespace(headers=HEADERS, workers=16))
    assert json.loads(json.dumps(result)) == reference
