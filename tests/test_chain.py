"""Targets, work and levels under both constructions, header files, and synthetic chains (vmls.chain)."""

import json
import lzma
import random

import pytest

from vmls.chain import (GENESIS_LEVEL, GENESIS_TARGET, bits_to_target, ccs_level, chain_from_headers, committed_level,
                        load_headers, make_block, make_fork, random_chain, scripted_chain, simulated_nonce)

GENESIS = {'hash': '000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f', 'bits': '1d00ffff',
           'time': 1231006505}
BLOCK_1 = {'hash': '00000000839a8e6886ab5951d76f411475428afc90947ee320161bbf18eb6048', 'bits': '1d00ffff',
           'time': 1231469665}


def test_bits_to_target():
    assert bits_to_target('1d00ffff') == GENESIS_TARGET
    assert bits_to_target(0x17021673) == 0x021673 << (8 * (0x17 - 3))


def test_work_is_bitcoins_chain_work():
    assert make_block(0, 1, GENESIS_TARGET, 0, 'ccs2025').work == 0x100010001  # Bitcoin's work of the genesis block.


def test_ccs_level_is_exact_at_the_boundary():
    target = GENESIS_TARGET  # 0xffff << 208: target >> mu << mu == target for every mu below 208.
    for mu in range(200):
        assert ccs_level(target >> mu, target) == mu  # hash * 2^mu == target exactly.
        if mu:
            assert ccs_level((target >> mu) + 1, target) == mu - 1  # One above: misses level mu.
    odd = (1 << 230) + 1
    assert ccs_level(odd >> 3, odd) == 3 and ccs_level((odd >> 3) + 1, odd) == 2  # A float would round both alike.


def test_ccs_level_matches_its_definition():
    rng = random.Random(1)
    for _ in range(2000):
        target = rng.randrange(1 << 200, 1 << 230)
        block_hash = rng.randrange(1, target + 1)
        mu = ccs_level(block_hash, target)
        assert block_hash << mu <= target < block_hash << (mu + 1)


def test_committed_levels_are_geometric_and_independent_of_the_hash():
    rng = random.Random(2)
    n = 40_000
    counts = [0] * 8
    agree = 0
    for _ in range(n):
        target = GENESIS_TARGET
        block_hash = rng.randrange(1, target)
        mu = committed_level(rng.randbytes(32), block_hash)
        counts[min(mu, 7)] += 1
        agree += mu == ccs_level(block_hash, target)
    expected = [n * 2.0 ** -(mu + 1) for mu in range(7)] + [n * 2.0 ** -7]
    assert sum((c - e) ** 2 / e for c, e in zip(counts, expected)) < 24.3  # 7 degrees of freedom, p = 0.001.
    assert abs(agree / n - 1 / 3) < 0.02  # Two independent geometric levels agree with probability 1/3.


def test_unrevealed_nonce_has_level_zero():
    assert committed_level(None, 123) == 0


def test_simulated_nonce_is_reproducible():
    assert simulated_nonce(42) == simulated_nonce(42) != simulated_nonce(43)


@pytest.mark.parametrize('suffix', ['.json', '.json.xz'])
def test_load_headers(tmp_path, suffix):
    path = tmp_path / f'headers{suffix}'
    opener = lzma.open if suffix == '.json.xz' else open
    with opener(path, 'wt', encoding='utf-8') as f:
        json.dump([GENESIS, BLOCK_1], f)
    assert load_headers(path) == [GENESIS, BLOCK_1]


@pytest.mark.parametrize('construction', ['ccs2025', 'ours'])
def test_chain_from_headers(construction):
    chain = chain_from_headers([GENESIS, BLOCK_1], construction)
    assert chain[0].level == GENESIS_LEVEL and chain[0].ctr is None
    assert chain[1].hash == int(BLOCK_1['hash'], 16) and chain[1].time == BLOCK_1['time']
    if construction == 'ours':
        assert chain[1].ctr == simulated_nonce(chain[1].hash)
        assert chain[1].level == committed_level(chain[1].ctr, chain[1].hash)
    else:
        assert chain[1].level == ccs_level(chain[1].hash, chain[1].target) == 0


def test_unknown_construction():
    with pytest.raises(ValueError):
        make_block(0, 1, GENESIS_TARGET, 0, 'blind')


def test_scripted_chain_has_the_given_levels():
    levels = [0, 3, 0, 1, 7, 2]
    chain = scripted_chain(levels)
    assert [b.level for b in chain[1:]] == levels[1:]
    assert all(ccs_level(b.hash, b.target) == b.level for b in chain[1:])
    assert len({b.hash for b in chain}) == len(chain)


def test_random_chain_ours_takes_levels_from_nonces():
    chain = random_chain(500, seed=3, construction='ours')
    assert all(b.level == committed_level(b.ctr, b.hash) for b in chain[1:])


@pytest.mark.parametrize('construction', ['ccs2025', 'ours'])
def test_fork(construction):
    chain = random_chain(100, seed=4, construction=construction)
    fork = make_fork(chain, 50, 30, 4.0, seed=5, construction=construction)
    assert [b.height for b in fork] == list(range(51, 81))
    assert all(b.target == 4 * chain[50].target or b.target == (1 << 256) - 1 for b in fork)
    assert all(b.hash <= b.target for b in fork)
    hidden = make_fork(chain, 50, 30, 4.0, seed=5, construction=construction, reveal=False)
    assert all(b.level == 0 and b.ctr is None for b in hidden)
