"""Headers, targets, difficulties and levels, real and blind (vmls.chain)."""

import random

from vmls.chain import GENESIS_LEVEL, GENESIS_TARGET, Block, bits_to_target, blind_level, blocks_from_headers, difficulty, level, make_blind

GENESIS = {'hash': '000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f', 'bits': '1d00ffff', 'time': 1231006505}


def test_bits_to_target():
    assert bits_to_target('1d00ffff') == GENESIS_TARGET
    assert bits_to_target(0x1d00ffff) == GENESIS_TARGET
    assert bits_to_target('17030ecd') == 0x030ecd << (8 * (0x17 - 3))


def test_difficulty_of_genesis_target_is_one():
    assert difficulty(GENESIS_TARGET) == 1
    assert difficulty(GENESIS_TARGET // 4) == 4


def test_level_counts_halvings_below_the_target():
    target = GENESIS_TARGET
    assert level(target, target) == 0
    assert level(target // 2, target) == 1
    assert level(target * 6 // 10, target) == 0
    assert level(target // 3, target) == 1
    assert level(target >> 10, target) == 10


def test_genesis_block_has_infinite_level():
    chain = blocks_from_headers([GENESIS])
    assert chain[0].level == GENESIS_LEVEL
    assert chain[0].diff == 1


def test_blind_levels_are_geometric():
    rng = random.Random(0)
    counts = [0] * 6
    n = 40_000
    for height in range(n):
        block = Block(height, GENESIS_TARGET, rng.randrange(1, GENESIS_TARGET), 0, 1, 0)
        make_blind(block)
        assert block.level == blind_level(block.ctr, block.block_hash.to_bytes(32, 'big'))
        counts[min(block.level, 5)] += 1
    for mu in range(5):
        expected = n * 2.0 ** -(mu + 1)
        assert abs(counts[mu] - expected) < 5 * expected ** 0.5, (mu, counts[mu], expected)


def test_blind_level_does_not_depend_on_the_real_level():
    # A block far below its target is not more likely to be high under blind mining.
    low = Block(1, GENESIS_TARGET, 1, 0, 1, level(1, GENESIS_TARGET))
    make_blind(low)
    assert low.level < 20
