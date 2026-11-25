"""Header bytes against the size formula, field by field (vmls.encoding)."""

import random

import pytest

from vmls.chain import GENESIS_TARGET, bits_to_target, random_chain
from vmls.encoding import CORE, HASH, Links, decode, encode, header_size, n_levels, target_to_bits

H = lambda block: block.hash.to_bytes(HASH, 'big')  # noqa: E731


def test_n_levels_is_ceil_log2_of_height_plus_two():
    import math
    for height in range(0, 5000):
        assert n_levels(height) == max(1, math.ceil(math.log2(height + 2)))


def test_formula():
    assert header_size('ccs2025', 977_192, 6) == 80 + 32 * 20
    assert header_size('ours', 977_192, 6) == 108 + 32 * 5 + 128 * 20
    assert header_size('ours', 977_192, 323) - header_size('ours', 977_192, 6) == 32 * 317
    with pytest.raises(ValueError):
        header_size('blind', 1, 6)


def test_target_to_bits_is_the_inverse_of_bits_to_target():
    assert target_to_bits(GENESIS_TARGET) == 0x1D00FFFF
    rng = random.Random(1)
    for _ in range(2000):
        bits = (rng.randrange(4, 0x20) << 24) | rng.randrange(0x8000, 0x800000)
        assert bits_to_target(target_to_bits(bits_to_target(bits))) == bits_to_target(bits)


@pytest.mark.parametrize('construction', ['ccs2025', 'ours'])
@pytest.mark.parametrize('k', [1, 6, 323])
def test_length_is_the_formula_at_every_height(construction, k):
    chain = random_chain(1200, seed=2, construction=construction)
    links = Links(chain, construction, k)
    for block in chain:
        assert len(encode(chain, links, block.height)) == header_size(construction, block.height, k)


def test_ccs_fields_round_trip_and_point_to_the_last_mu_blocks():
    chain = random_chain(1500, seed=3)
    links = Links(chain, 'ccs2025', 6)
    for height in (1, 2, 17, 700, 1499):
        block = chain[height]
        header = decode(encode(chain, links, height), 'ccs2025', 6)
        assert header.previous == H(chain[height - 1])
        assert header.time == block.time and bits_to_target(header.bits) == block.target
        assert header.commitment is None and len(header.pointers) == n_levels(height)
        for mu, pointer in enumerate(header.pointers, start=1):
            last = max(b.height for b in chain[:height] if b.level >= mu)  # The genesis block always qualifies.
            assert pointer == H(chain[last])


def test_ours_fields_point_to_predecessors_and_reveal_only_k_deep_blocks():
    k = 6
    chain = random_chain(1500, seed=4, construction='ours')
    links = Links(chain, 'ours', k)
    for height in (1, 3, 7, 8, 300, 1499):
        block = chain[height]
        data = encode(chain, links, height)
        header = decode(data, 'ours', k)
        assert data[:CORE - 4] == encode(chain, links, height)[:CORE - 4]
        assert header.previous == H(chain[height - 1])
        assert header.commitment == __import__('hashlib').sha256(block.ctr).digest()
        predecessors = [H(chain[h]) if h >= 0 else bytes(HASH) for h in range(height - k, height - 1)]
        assert list(header.pointers[:k - 1]) == predecessors
        revealed = [b for b in chain[:max(height - k, 0)]]
        for mu, start in zip(range(1, n_levels(height) + 1), range(0, 4 * n_levels(height), 2)):
            expected = [b for b in revealed if b.level >= mu][-2:]
            expected = [None] * (2 - len(expected)) + expected
            got = header.nonces[start:start + 2]
            for b, (h, ctr) in zip(expected, got):
                assert (h, ctr) == ((H(b), b.ctr or bytes(HASH)) if b else (bytes(HASH), bytes(HASH)))
        for h, ctr in header.nonces:  # Nothing less than k + 1 deep is revealed.
            if h != bytes(HASH):
                assert next(b for b in chain if H(b) == h).height < height - k
