"""Synthetic chains and competing proofs.

Forks stand for an adversary: blocks mined after a block of the real chain, at a target of its choice. Synthetic
chains with chosen or random levels serve to illustrate and test the prover.
"""

import random

from vmls.chain import GENESIS_LEVEL, GENESIS_TARGET, Block, level, make_blind
from vmls.nipopow import Params, compress


def make_fork(chain: list[Block], fork_height: int, n_blocks: int, target_factor: float, seed: int,
              blind: bool) -> list[Block]:
    """Blocks mined after a block of the chain, at a constant target.

    Args:
        chain: The chain.
        fork_height: Height of the last common block.
        n_blocks: Number of blocks to mine.
        target_factor: Target of the fork, relative to the target of the last common block.
        seed: Seed of the block hashes.
        blind: Whether levels are the blind ones.

    Returns:
        The blocks of the fork.
    """
    rng = random.Random(seed)
    target = int(chain[fork_height].target * target_factor)
    fork = []
    for i in range(n_blocks):
        block_hash = rng.randrange(1, target)
        block = Block(fork_height + 1 + i, target, block_hash, 0, int(GENESIS_TARGET / target), level(block_hash, target))
        if blind:
            make_blind(block)
        fork.append(block)
    return fork


def tip_fork(chain: list[Block], proof: list[Block], p: Params, blind: bool) -> list[Block]:
    """A competing proof forking in the unstable subchain, with fewer blocks of the same difficulty.

    Args:
        chain: The chain.
        proof: The honest proof.
        p: The parameters.
        blind: Whether levels are the blind ones.

    Returns:
        The competing proof.
    """
    depth = p.k // 2
    return proof[:-depth] + make_fork(chain, proof[-depth - 1].height, depth - 10, 1, seed=proof[-1].height, blind=blind)


def deep_fork(chain: list[Block], height: int, p: Params, blind: bool) -> list[Block]:
    """A competing proof forking a quarter of the chain ago, with 80% of the honest blocks at the difficulty of the fork.

    Args:
        chain: The chain.
        height: Height of the tip.
        p: The parameters.
        blind: Whether levels are the blind ones.

    Returns:
        The competing proof.
    """
    depth = max(height // 4, 2 * (p.k + p.chi))
    fork = make_fork(chain, height - depth, int(0.8 * depth), 1, seed=height, blind=blind)
    return compress(chain[:height - depth + 1] + fork, p)


def scripted_chain(levels: list[int]) -> list[Block]:
    """A chain whose blocks have the given levels.

    Args:
        levels: The level of each block, the first one being the genesis block.

    Returns:
        The blocks, at the genesis target, each with its own hash.
    """
    chain = [Block(height, GENESIS_TARGET, (GENESIS_TARGET >> mu) - height, height, 1, mu) for height, mu in enumerate(levels)]
    chain[0].level = GENESIS_LEVEL
    return chain


def random_chain(n: int, seed: int, p: float = 0.5) -> list[Block]:
    """A chain whose levels are geometric: a block has level at least mu with probability p^mu.

    Args:
        n: Number of blocks.
        seed: Seed of the levels.
        p: Parameter of the geometric distribution, 1/2 for proof-of-work.

    Returns:
        The blocks, at the genesis target.
    """
    rng = random.Random(seed)
    levels = []
    for _ in range(n):
        mu = 0
        while rng.random() < p:
            mu += 1
        levels.append(mu)
    return scripted_chain(levels)
