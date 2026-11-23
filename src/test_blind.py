###############################################################################
# Imports

import math
import sys

import bitcoin
import config
import mls
import mls_blind
import proof_bytes



###############################################################################
# Checks

K, k, chi = 208, 323, 4032
OCTOBER_2024_BLOCKS = 865043 # The headers of the CCS paper.
OCTOBER_2024_D = 2720 # |D| at that height, computed separately from the raw headers with real levels.


def load(blind):
    """
    Loads the whole chain.

    Args:
    - blind (bool): Whether levels are the blind ones.

    Returns:
    - list: The chain, as a list of blocks.
    """
    n = bitcoin.load_headers(None)
    chain = []
    for height in range(n):
        block = bitcoin.get_block_by_height(height)
        if blind:
            mls_blind.set_blind_fields(block)
        if height == 0:
            block.level = 256
        chain.append(block)
    return chain


def check_levels_are_geometric(chain):
    """
    Blind levels are at least mu with probability 2^-mu: chi-squared over the exact levels 0..11 and the tail.
    """
    n = len(chain) - 1
    counts = [0] * 13
    for block in chain[1:]:
        counts[min(block.level, 12)] += 1
    expected = [n * 2.0 ** -(mu + 1) for mu in range(12)] + [n * 2.0 ** -12]
    statistic = sum((c - e) ** 2 / e for c, e in zip(counts, expected))
    assert statistic < 32.9, statistic # Critical value for 12 degrees of freedom at p = 0.001.
    print(f'levels: chi2 = {statistic:.1f} (12 d.o.f., threshold 32.9), counts {counts}')


def check_honest_score_is_full_difficulty(chain):
    """
    At low levels, the Score of honest blocks is their accumulated difficulty when v is 13 (gamma = 1.51, eta = 1/4).
    """
    v = 1.51 * 1.995 / (0.25 * (1 - 1.995 * 0.03))
    for mu in range(4):
        row = mls.filter_chain_by_level(chain[-200_000:], mu)[-2 * K:]
        assert mls_blind.score(row, v) == sum(block.diff for block in row), mu
    print(f'score: honest score = accumulated difficulty for mu <= 3 at the tip (v = {v:.1f})')


def check_honest_proof_wins(chain, blind):
    """
    The honest proof beats a fork at the tip (level 0) and a deep fork (a level above 0). The new verifier may instead leave
    the deep fork to the online test, when fewer than K blocks follow the common ancestor, but it never picks the fork.
    """
    height = len(chain) - 1
    proof = mls.Compress(chain)
    assert len(proof) == len(mls.Compress(mls.Compress(chain)))
    for name, other in (('tip', mls_blind.tip_fork(chain, proof, blind)), ('deep', mls_blind.deep_fork(chain, height, blind))):
        if blind:
            winner, path = mls_blind.compare_blind(proof, other, K, 33.0)
        else:
            winner, path = mls_blind.compare_vmls(proof, other)
        assert winner == 1 or (blind and name == 'deep' and path == 'online'), (name, winner, path)
        print(f'compare ({"blind" if blind else "vmls"}): {name} fork, honest wins through {path}' if winner == 1 else f'compare (blind): {name} fork, left to the online test')
    return proof


def check_score_branch(chain):
    """
    On the headers of the CCS paper, the new verifier decides the deep fork through the Score, for the honest proof.
    """
    prefix = chain[:OCTOBER_2024_BLOCKS]
    outcome = mls_blind.compare_blind(mls.Compress(prefix), mls_blind.deep_fork(prefix, len(prefix) - 1, True), K, 33.0)
    assert outcome == (1, 'score'), outcome
    print('compare (blind): deep fork at October 2024, honest wins through score')


def check_zero_difficulty_attack(chain, blind):
    """
    An adversarial proof built by the Zero-Difficulty attack wins against the paper's verifier and goes to the online test
    with the new one.
    """
    # The latest block of the level of the honest proof, followed by k+chi blocks of lower level: there the attack conditions hold.
    star, level_star = None, None
    for height in range(len(chain) - k - chi - 2, 0, -1):
        if chain[height].level >= 9:
            level = mls.get_proof_level(chain[:height + 2])
            if chain[height].level >= level and all(block.level < level for block in chain[height + 1:height + k + chi + 2]):
                star, level_star = height, level
                break
    honest = mls.Compress(chain[:star + k + chi + 2])
    print(f'attack: b* at height {star}, honest proof of level {level_star}')

    fork = mls_blind.make_fork(chain, star, int(1.4 * 2 ** level_star * K) + 2 * 2016 + k, 4 ** 6, seed=star, blind=blind)
    adversarial = mls.Compress(chain[:star + 1] + fork)
    if blind:
        winner, path = mls_blind.compare_blind(honest, adversarial, K, 33.0)
        assert path == 'online', (winner, path)
        print(f'attack: the new verifier falls back on the online test')
    else:
        winner, path = mls_blind.compare_vmls(honest, adversarial)
        assert winner == 2, (winner, path)
        print(f'attack: the verifier of the paper accepts the adversarial proof through {path}')


def check_bytes(proof):
    """
    The byte model gives the sizes announced for the real chain.
    """
    D_size = len(proof) - k - chi
    sizes = mls_blind.proof_byte_sizes(proof, k, ('ccs', 'ccs-merkle', 'draft', 'draft-merkle'))
    print(f'bytes: {len(proof)} blocks, |D| = {D_size}; ' + ', '.join(f'{name} = {size / 1e6:.2f} MB' for name, size in sizes.items()) + f'; SPV = {proof_bytes.spv_size(proof[-1].height) / 1e6:.2f} MB')
    assert proof_bytes.header_size('ccs', 865042, k) == 80 + 32 * 20
    assert proof_bytes.header_size('draft', 865042, k) == 80 + 28 + 32 * 323 + 128 * 20
    assert proof_bytes.header_size('draft-merkle', 865042, k) == 140
    return D_size



###############################################################################
# Main

if __name__ == '__main__':
    mls.K_args, mls.k_args, mls.chi_args = K, k, chi
    config.HEADERS_FILE_PATH = sys.argv[1] if len(sys.argv) > 1 else config.HEADERS_FILE_PATH
    bitcoin.LOAD_FROM_HEADERS_FILE = True

    chain = load(blind=False)
    proof = check_honest_proof_wins(chain, blind=False)
    check_bytes(proof)
    assert len(mls.Compress(chain[:OCTOBER_2024_BLOCKS])) - k - chi == OCTOBER_2024_D
    check_zero_difficulty_attack(chain, blind=False)

    chain = load(blind=True)
    check_levels_are_geometric(chain)
    check_honest_score_is_full_difficulty(chain)
    proof = check_honest_proof_wins(chain, blind=True)
    check_score_branch(chain)
    check_bytes(proof)
    check_zero_difficulty_attack(chain, blind=True)
    print('All checks passed.')
