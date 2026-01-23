###############################################################################
# Imports

import random
from typing import List
from block import Block, genesisTarget


class ChainGenerator:
    """
    Base class for chain generators.

    A chain generator is responsible for producing blocks
    at a given height.
    """

    def get_block_by_height(self, height: int) -> Block:
        """
        Return the block at a given height.

        Args:
            height (int): Block height.

        Returns:
            Block: The generated block.
        """
        raise NotImplementedError



###############################################################################
# Scripted level chain generator

class ScriptedLevelChainGenerator(ChainGenerator):
    """
    Chain generator with explicitly prescribed block levels.
    """

    def __init__(self, levels: List[int]) -> None:
        """
        Constructor for ScriptedLevelChainGenerator.

        Args:
            levels (List[int]): Block levels indexed by height.
        """
        self.levels = levels

    def get_block_by_height(self, height: int) -> Block:
        """
        Generate a synthetic block with a prescribed level.

        Args:
            height (int): Block height.

        Returns:
            b (Block): Synthetic block.
        """
        level = self.levels[height]

        # Construct a hash ensuring the desired level
        target = genesisTarget
        block_hash = target >> level
        timestamp = height

        b = Block(
            height=height,
            target=target,
            block_hash=block_hash,
            timestamp=timestamp
        )

        # Genesis block convention
        if height == 0:
            b.level = 256

        return b



###############################################################################
# Random level chain generator

class RandomLevelChainGenerator(ChainGenerator):
    """
    Chain generator with randomly generated block levels.
    """

    def __init__(self, p: float = 0.5, seed: int = None) -> None:
        """
        Constructor for RandomLevelChainGenerator.

        Args:
            p (float): Probability parameter for geometric distribution.
            seed (int, optional): Random seed.
        """
        self.p = p
        if seed is not None:
            random.seed(seed)

    def sample_level(self) -> int:
        """
        Sample a block level using a geometric distribution.

        Returns:
            int: Sampled block level.
        """
        level = 0
        while random.random() < self.p:
            level += 1
        return level

    def get_block_by_height(self, height: int) -> Block:
        """
        Generate a random synthetic block.

        Args:
            height (int): Block height.

        Returns:
            b (Block): Synthetic block.
        """
        level = self.sample_level()

        target = genesisTarget
        block_hash = target >> level
        timestamp = height

        b = Block(
            height=height,
            target=target,
            block_hash=block_hash,
            timestamp=timestamp
        )

        # Genesis block convention
        if height == 0:
            b.level = 256

        return b