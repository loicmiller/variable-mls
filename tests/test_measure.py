"""The parameters measured on a chain and the dates of the attack (vmls.measure)."""

import random

import pytest

from vmls.chain import GENESIS_TARGET, chain_from_headers
from vmls.encoding import n_levels, target_to_bits
from vmls.measure import EPOCH, attack, epochs_since, v_by_level
from vmls.proof import Params, dissolve


def synthetic_headers(epochs: list[tuple[int, int]]) -> list[dict]:
    """Headers of full epochs, each given as (difficulty, seconds per block), with hashes below the target."""
    rng = random.Random(1)
    headers, time = [], 0
    for difficulty, seconds in epochs:
        target = GENESIS_TARGET // difficulty
        for _ in range(EPOCH):
            headers.append({'hash': f'{rng.randrange(1, target):064x}', 'bits': f'{target_to_bits(target):08x}',
                            'time': time})
            time += seconds
    return headers


def test_v_by_level_is_the_formula_of_algorithm_4():
    headers = synthetic_headers([(1, 600), (2, 300), (2, 600), (4, 1200), (4, 600)])
    epochs, rates, first = epochs_since(headers, since=0)
    assert rates == [1.0, 2.0, 1.0, 0.5] and first == 0  # The last epoch has no end: four rates.
    assert [epochs[i] / epochs[0] for i in range(5)] == pytest.approx([1, 2, 2, 4, 4], rel=1e-4)
    slack = 2.0 / (0.5 * (1 - 2.0 * 0.03))  # theta / (eta (1 - theta f))
    v = v_by_level(headers, K=8, since=0)
    assert len(v) == n_levels(len(headers)) + 1
    assert v[0] == pytest.approx(2 * slack, rel=1e-4)  # 8 blocks touch two epochs: difficulties at most doubled.
    assert v[8] == pytest.approx(2 * slack, rel=1e-4)  # 2,048 blocks touch three.
    assert v[9] == pytest.approx(4 * slack, rel=1e-4)  # 4,096 blocks touch four: from 1 to 4.
    assert v[-1] == pytest.approx(4 * slack, rel=1e-4)
    recent = v_by_level(headers, K=8, since=headers[2 * EPOCH]['time'])  # Difficulties 2, 4, 4; rates 1 and 0.5.
    assert recent[-1] == pytest.approx(2 * 1.0 / (0.5 * (1 - 0.03)), rel=1e-4)
    with pytest.raises(ValueError, match='no full epoch'):
        v_by_level(headers, K=8, since=headers[-1]['time'])


def test_the_attack_dates_each_rise_where_the_level_of_the_proof_rises():
    headers = synthetic_headers([(1, 600)] * 4)
    p = Params(K=8, k=6, chi=40)
    result = attack(headers, p.K, p.k, p.chi)
    chain = chain_from_headers(headers, 'ccs2025')
    assert len(result['rises']) >= 5
    for rise in result['rises']:
        assert dissolve(chain[:rise['height'] + 1], p)[1] >= rise['level']
        assert dissolve(chain[:rise['height']], p)[1] < rise['level']
    assert result['proof_level_now'] == dissolve(chain, p)[1]
