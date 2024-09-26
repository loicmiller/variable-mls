import math

# Constants
genesisTarget = 26959535291011309493156476344723991336010898738574164086137773096960
IS_EPSILON_TARGET_DEFINITION = True

class Block:
    """
    A class to represent a block in the Bitcoin blockchain.

    Attributes:
    - height (int): The height of the block.
    - target (int): The target of the block.
    - block_hash (int): The hash of the block.
    - timestamp (int): The timestamp of the block.
    - diff (int/float): The difficulty of the block.
    - level (int): The level of the block.
    """
    def __init__(self, height: int, target: int, block_hash: int, timestamp: int) -> None:
        """
        Constructor for Block class.

        Args:
            height (int): The height of the block.
            target (int): The target of the block.
            block_hash (int): The hash of the block.
            timestamp (int): The timestamp of the block.
        """
        self.height = height
        self.target = target
        self.block_hash = block_hash
        self.timestamp = timestamp
        self.diff = int(round(genesisTarget / target, 4)) if IS_EPSILON_TARGET_DEFINITION else genesisTarget / target # As penultimate and most minimal difference targets differ only up to the third decimal.
        self.level = level(block_hash, target)        

    def __hash__(self):
        return hash((self.height, self.target, self.block_hash, self.timestamp, self.diff, self.level))

    def __eq__(self, other):
        return isinstance(other, self.__class__) and self.__dict__ == other.__dict__

    def __lt__(self, other):
        return self.height < other.height

    def __repr__(self):
        return f"Block({self.height}, {self.target}, {self.block_hash}, {self.timestamp}, {self.diff}, {self.level})"

    def __str__(self):
        return f"height={self.height}, target={self.target}, block_hash={self.block_hash}, timestamp={self.timestamp}, diff={self.diff}, level={self.level}"


def level(block_hash: int, target: int) -> int:
    """
    Calculate the level of the block.

    Args:
        block_hash (int): The hash of the block.
        target (int): The target of the block.

    Returns:
        int: The level of the block.
    """
    ratio = block_hash / target
    return math.floor(-math.log2(ratio))
