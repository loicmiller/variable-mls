"""Headers, blocks, difficulties and levels.

A block is a level-mu block when its hash is at least 2^mu times below what it needs to be valid. Two definitions
coexist: the one of the CCS 2025 paper, from the block hash and its target, and the blind one, from a nonce revealed
k blocks after the block.
"""

import hashlib
import json
import math
import zipfile
from dataclasses import dataclass
from pathlib import Path

GENESIS_TARGET = 0xffff << 208
GENESIS_LEVEL = 256  # The genesis block has an infinite level by convention.


@dataclass(slots=True)
class Block:
    """A block, reduced to what the NIPoPoW needs.

    Attributes:
        height: Height in the chain.
        target: Mining target.
        block_hash: Block hash, as an integer.
        timestamp: Unix time set by the miner.
        diff: Difficulty, relative to the genesis target.
        level: Level, real or blind.
        ctr: Revealed nonce, for blind levels only.
        commitment: H(ctr), carried by the header, for blind levels only.
    """

    height: int
    target: int
    block_hash: int
    timestamp: int
    diff: int
    level: int
    ctr: bytes | None = None
    commitment: bytes | None = None


def sha256(data: bytes) -> bytes:
    """Single SHA-256.

    Args:
        data: The data to hash.

    Returns:
        The digest.
    """
    return hashlib.sha256(data).digest()


def bits_to_target(bits: int | str) -> int:
    """Decodes the compact target of a header.

    Args:
        bits: The compact target, as an integer or a hexadecimal string.

    Returns:
        The target.
    """
    bits = int(bits, 16) if isinstance(bits, str) else bits
    return (bits & 0xffffff) << (8 * ((bits >> 24) - 3))


def difficulty(target: int) -> int:
    """Difficulty of a target, relative to the genesis target.

    Args:
        target: The target.

    Returns:
        The difficulty, rounded to 4 decimals then truncated, as the CCS 2025 code does.
    """
    return int(round(GENESIS_TARGET / target, 4))


def level(block_hash: int, target: int) -> int:
    """Level of a block in the CCS 2025 paper: the largest mu with block_hash <= target / 2^mu.

    Computed in floating point, as the CCS 2025 code does, so a hash within one part in 2^53 above target / 2^mu can
    still get level mu; kept as is so that results stay identical.

    Args:
        block_hash: The block hash.
        target: The target of the block.

    Returns:
        The level.
    """
    return math.floor(-math.log2(block_hash / target))


def blind_level(ctr: bytes, y: bytes) -> int:
    """Level of a block under blind mining: the largest mu with H(ctr, y) < 2^(256 - mu).

    Args:
        ctr: The revealed nonce.
        y: The proof-of-work hash H(H(ctr), h) of the block.

    Returns:
        The number of leading zero bits of H(ctr, y).
    """
    return 256 - int.from_bytes(sha256(ctr + y), 'big').bit_length()


def simulated_nonce(block_hash: int) -> tuple[bytes, bytes]:
    """The nonce and commitment blind mining would have given a historical block.

    Bitcoin headers have no such nonce. It is derived from the block hash, so that runs are reproducible, and the block
    hash stands in for the proof-of-work hash y. A blind chain would carry the commitment in the header and reveal the
    nonce k blocks later: a prover reads both, so this derivation is not part of its work.

    Args:
        block_hash: The block hash.

    Returns:
        The nonce ctr and its commitment H(ctr).
    """
    ctr = sha256(block_hash.to_bytes(32, 'big') + b'ctr')
    return ctr, sha256(ctr)


def make_blind(block: Block, nonce: tuple[bytes, bytes] | None = None) -> None:
    """Gives a block its nonce and commitment, checks that the nonce opens the commitment, then sets its blind level.

    Args:
        block: The block, changed in place.
        nonce: The nonce and commitment, as read from the chain; simulated from the block hash if None.

    Raises:
        ValueError: If the nonce does not open the commitment.
    """
    block.ctr, block.commitment = nonce if nonce is not None else simulated_nonce(block.block_hash)
    if sha256(block.ctr) != block.commitment:
        raise ValueError(f'block {block.height} does not open its commitment')
    block.level = blind_level(block.ctr, block.block_hash.to_bytes(32, 'big'))


def load_headers(path: str | Path) -> list[dict]:
    """Reads exported headers: a JSON list of {'hash', 'bits', 'time'}, or a zip holding one.

    Args:
        path: The JSON or zip file.

    Returns:
        One header per height, from the genesis block.
    """
    path = Path(path)
    if path.suffix == '.zip':
        with zipfile.ZipFile(path) as archive:
            name = next(n for n in archive.namelist() if n.endswith('.json'))
            return json.loads(archive.read(name))
    with open(path) as f:
        return json.load(f)


def blocks_from_headers(headers: list[dict], blind: bool = False, stop: int | None = None,
                        nonces: list[tuple[bytes, bytes]] | None = None) -> list[Block]:
    """Builds the chain from exported headers: the level of each block, CCS 2025 or blind, not both.

    Args:
        headers: The headers, one per height.
        blind: Whether levels are the blind ones.
        stop: Height to stop before, the whole chain if None.
        nonces: Under blind mining, the nonce and commitment of each block as a blind chain would carry them
            (simulated_nonce); derived on the fly if None.

    Returns:
        The blocks, the genesis block with level GENESIS_LEVEL.
    """
    chain = []
    for height, header in enumerate(headers[:stop]):
        target = bits_to_target(header['bits'])
        block_hash = int(header['hash'], 16)
        block = Block(height, target, block_hash, int(header['time']), difficulty(target), 0)
        if blind:
            make_blind(block, nonces[height] if nonces is not None else None)
        else:
            block.level = level(block_hash, target)
        chain.append(block)
    chain[0].level = GENESIS_LEVEL
    return chain
