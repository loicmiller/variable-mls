"""Regressions on the real chain, against data kept outside the repository (see conftest.py), run with --runslow.

The CCS 2025 construction of this version must give, block for block, what the code of the CCS 2025 paper gave: the
dumps of that code (data/reference/*dump*.json, K = 104 and 208, k = 323, headers up to October 11, 2024) and the
proofs of version 1 at 20 heights (old-compress-2026-11-23.json).
"""

import hashlib
import json

import pytest

from tests.conftest import HEADERS, REFERENCE, require
from vmls.chain import chain_from_headers, load_headers
from vmls.encoding import Links, encode, header_size
from vmls.measure import deep_fork, k_star, tip_fork, v_by_level
from vmls.proof import Params, compress, dissolve, proof_level
from vmls.verify import check, compare_ccs, compare_ours

pytestmark = pytest.mark.slow
CCS_HEADERS = HEADERS.parent / 'headers.zip'  # The 865,043 headers of the CCS 2025 paper.


@pytest.fixture(scope='module')
def headers():
    """The Bitcoin headers (VMLS_HEADERS)."""
    return load_headers(require(HEADERS))


@pytest.fixture(scope='module')
def chains(headers):
    """The chain under each construction."""
    return {c: chain_from_headers(headers, c) for c in ('ccs2025', 'ours')}


@pytest.fixture(scope='module')
def ccs_chain():
    """The chain of the CCS 2025 paper, under its construction."""
    return chain_from_headers(load_headers(require(CCS_HEADERS)), 'ccs2025')


def test_levels_match_the_ccs_2025_code(ccs_chain):
    dump = json.loads(require(REFERENCE / '2025-07-dump-K-104.json').read_text())
    assert [b.level for b in ccs_chain[1:]] == dump['block_level'][1:]  # Exact integers, as the floats of 2025.


@pytest.mark.parametrize('K, name', [(104, '2025-07-dump-K-104.json'), (208, 'ccs-2025-dump-K-208.json')])
def test_proof_sizes_match_the_ccs_2025_code(ccs_chain, K, name):
    dump = json.loads(require(REFERENCE / name).read_text())
    p = Params(K, k=323)
    for height in list(range(10_000, len(ccs_chain), 10_000)) + [len(ccs_chain) - 1]:
        proof = compress(ccs_chain[:height + 1], p)
        assert len(proof) == dump['proof_size'][height], height
        # The CCS 2025 data count the level over the whole chain, X and Omega included, not over C' as Dissolve does.
        assert proof_level(ccs_chain[:height + 1], K) == dump['proof_level'][height], height


def test_proofs_match_version_1(chains):
    reference = json.loads(require(REFERENCE / 'old-compress-2026-11-23.json').read_text())
    for r in reference['proofs']:
        p = Params(K=r['K'], k=323)
        chain = chains['ours' if r['blind'] else 'ccs2025'][:r['height'] + 1]
        proof = compress(chain, p)
        D, top, _, _ = dissolve(chain, p)
        digest = hashlib.sha256(','.join(str(b.height) for b in proof).encode()).hexdigest()
        assert (len(proof), top, {str(mu): len(D[mu]) for mu in D}, digest) == \
            (r['size'], r['level'], r['rows'], r['sha256']), r


@pytest.mark.parametrize('construction', ['ccs2025', 'ours'])
@pytest.mark.parametrize('k', [6, 323])
def test_real_headers_link_every_proof_and_match_the_formula(chains, construction, k):
    chain = chains[construction]
    p = Params(208, k)
    proof = compress(chain, p)
    links = Links(chain, construction, k)
    headers = [encode(chain, links, b.height) for b in proof]
    assert [len(h) for h in headers] == [header_size(construction, b.height, k) for b in proof]
    check(proof, headers, construction, p, chain[0].hash)


def test_committed_levels_are_geometric(chains):
    chain = chains['ours']
    n = len(chain) - 1
    counts = [0] * 13
    for block in chain[1:]:
        counts[min(block.level, 12)] += 1
    expected = [n * 2.0 ** -(mu + 1) for mu in range(12)] + [n * 2.0 ** -12]
    assert sum((c - e) ** 2 / e for c, e in zip(counts, expected)) < 32.9  # 12 degrees of freedom, p = 0.001.


@pytest.mark.parametrize('construction', ['ccs2025', 'ours'])
def test_the_honest_proof_beats_both_forks_on_bitcoin(headers, chains, construction):
    chain = chains[construction]
    p = Params(208, 6)
    proof = compress(chain, p)
    v = v_by_level(headers, p.K)
    compare = (lambda a, b: compare_ccs(a, b, p)) if construction == 'ccs2025' else (lambda a, b: compare_ours(a, b, p, v))
    assert compare(proof, tip_fork(chain, proof, p, construction)[1])[0] == 1
    winner, branch = compare(proof, deep_fork(chain, len(chain) - 1, p, construction)[1])
    assert winner == 1 or (construction == 'ours' and branch == 'online')


def test_k_star_of_the_review(headers):
    """K* on Bitcoin with the bound of Lemma lem:adversarial_score, headers up to 977,192."""
    if len(headers) != 977_193:
        pytest.skip('the review measured the headers up to 977,192')
    result = k_star(headers)
    level_0 = result['levels'][0]
    assert level_0['spread_recent'] == pytest.approx(1.39, abs=0.01)
    assert level_0['k_star'] == pytest.approx(3381, abs=1)
    assert result['k_star_floor'] == pytest.approx(798, abs=1)
