"""Blocks, their work and their level, read from exported headers or made up for tests.

A block is a mu-block when its proof of work beats what validity asks by a factor 2^mu. The two constructions read
that factor differently:

- ccs2025: from the block hash and its target, hash * 2^mu <= target (Relation 4 of the papers);
- ours: from a nonce ctr committed in the header as H(ctr) and revealed k blocks later,
  H(ctr, H(H(ctr), h)) < 2^(256 - mu). A block whose nonce is never revealed has level 0.

Bitcoin headers carry no committed nonce: simulated_nonce derives one from the block hash, so that levels follow the
distribution of a chain mined that way and runs are reproducible.

    chain = chain_from_headers(load_headers('headers/headers-up-to-977192.json'), 'ours')
"""

import hashlib
import json
import lzma
import random
import zipfile
from dataclasses import dataclass
from pathlib import Path

CONSTRUCTIONS = ('ccs2025', 'ours')
GENESIS_TARGET = 0xffff << 208  # Target of the genesis block, difficulty 1.
GENESIS_LEVEL = 256  # The genesis block has an infinite level by convention.


@dataclass(slots=True)
class Block:
    """A block, reduced to what a NIPoPoW needs.

    Attributes:
        height: Height in its chain.
        hash: Block hash, as an integer.
        target: Mining target.
        time: Unix time set by the miner.
        level: Level under the construction the chain was built for.
        ctr: Nonce of the block under ours, None if never revealed (and always None under ccs2025).
    """

    height: int
    hash: int
    target: int
    time: int
    level: int
    ctr: bytes | None = None

    @property
    def work(self) -> int:
        """Expected number of hashes to find this block, as Bitcoin counts chain work."""
        return (1 << 256) // (self.target + 1)


def sha256(data: bytes) -> bytes:
    """Single SHA-256."""
    return hashlib.sha256(data).digest()


def sha256d(data: bytes) -> bytes:
    """Double SHA-256, as Bitcoin hashes its headers."""
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def bits_to_target(bits: int | str) -> int:
    """Decodes the compact target of a header.

    Args:
        bits: The compact target, as an integer or a hexadecimal string.

    Returns:
        The target.
    """
    bits = int(bits, 16) if isinstance(bits, str) else bits
    return (bits & 0xFFFFFF) << (8 * ((bits >> 24) - 3))


def ccs_level(block_hash: int, target: int) -> int:
    """Level under ccs2025: the largest mu with block_hash * 2^mu <= target, in exact integers.

    Args:
        block_hash: The block hash, at most the target.
        target: The target of the block.

    Returns:
        The level.
    """
    mu = max(target.bit_length() - block_hash.bit_length(), 0)
    while mu > 0 and block_hash << mu > target:
        mu -= 1
    while block_hash << (mu + 1) <= target:
        mu += 1
    return mu


def committed_level(ctr: bytes | None, block_hash: int) -> int:
    """Level under ours: the largest mu with H(ctr, y) < 2^(256 - mu), y the proof-of-work hash of the block.

    Args:
        ctr: The revealed nonce, None if never revealed.
        block_hash: The proof-of-work hash H(H(ctr), h), as an integer.

    Returns:
        The number of leading zero bits of H(ctr, y), or 0 for an unrevealed nonce.
    """
    if ctr is None:
        return 0
    return 256 - int.from_bytes(sha256(ctr + block_hash.to_bytes(32, 'big')), 'big').bit_length()


def simulated_nonce(block_hash: int) -> bytes:
    """The nonce ctr a historical block would carry under ours, derived from its hash.

    Args:
        block_hash: The block hash.

    Returns:
        A 32-byte nonce.
    """
    return sha256(block_hash.to_bytes(32, 'big') + b'ctr')


def load_headers(path: str | Path) -> list[dict]:
    """Reads exported headers: a JSON list of {'hash', 'bits', 'time'}, plain, xz-compressed or in a zip.

    Args:
        path: The .json, .json.xz or .zip file.

    Returns:
        One header per height, from the genesis block.
    """
    path = Path(path)
    if path.suffix == '.zip':
        with zipfile.ZipFile(path) as archive:
            return json.loads(archive.read(next(n for n in archive.namelist() if n.endswith('.json'))))
    opener = lzma.open if path.suffix == '.xz' else open
    with opener(path, 'rt', encoding='utf-8') as f:
        return json.load(f)


def make_block(height: int, block_hash: int, target: int, time: int, construction: str,
               ctr: bytes | None = None) -> Block:
    """A block with its level under a construction.

    Args:
        height: Height in the chain.
        block_hash: Block hash.
        target: Mining target.
        time: Unix time.
        construction: 'ccs2025' or 'ours'.
        ctr: Under ours, the nonce; simulated from the hash if None.

    Returns:
        The block.

    Raises:
        ValueError: If the construction is unknown.
    """
    if construction == 'ccs2025':
        return Block(height, block_hash, target, time, ccs_level(block_hash, target))
    if construction == 'ours':
        ctr = ctr if ctr is not None else simulated_nonce(block_hash)
        return Block(height, block_hash, target, time, committed_level(ctr, block_hash), ctr)
    raise ValueError(f'unknown construction {construction!r}')


def chain_from_headers(headers: list[dict], construction: str, stop: int | None = None) -> list[Block]:
    """The chain of exported headers, with the level of each block under a construction.

    Args:
        headers: The headers, one per height, from the genesis block.
        construction: 'ccs2025' or 'ours'.
        stop: Height to stop before, the whole chain if None.

    Returns:
        The blocks, the genesis block at level GENESIS_LEVEL.
    """
    chain = [make_block(height, int(h['hash'], 16), bits_to_target(h['bits']), int(h['time']), construction)
             for height, h in enumerate(headers[:stop])]
    chain[0].level, chain[0].ctr = GENESIS_LEVEL, None
    return chain


def scripted_chain(levels: list[int]) -> list[Block]:
    """A ccs2025 chain at the genesis target whose blocks have the given levels, for tests and figures.

    Args:
        levels: The level of each block, the first one being the genesis block.

    Returns:
        The blocks, ten minutes apart.
    """
    chain = [Block(height, (GENESIS_TARGET >> mu) - height, GENESIS_TARGET, 600 * height, mu)  # Level exactly mu.
             for height, mu in enumerate(levels)]
    chain[0].level = GENESIS_LEVEL
    return chain


def random_levels(n: int, rng: random.Random) -> list[int]:
    """Geometric levels: a block has level at least mu with probability 2^-mu.

    Args:
        n: Number of levels.
        rng: The random generator.

    Returns:
        The levels.
    """
    levels = []
    for _ in range(n):
        mu = 0
        while rng.random() < 0.5:
            mu += 1
        levels.append(mu)
    return levels


def random_chain(n: int, seed: int, construction: str = 'ccs2025') -> list[Block]:
    """A chain of n blocks with geometric levels, at the genesis target.

    Args:
        n: Number of blocks, the genesis block included.
        seed: Seed of the levels.
        construction: 'ccs2025' or 'ours'.

    Returns:
        The blocks. Under ours, each block gets a random nonce and the level it gives.
    """
    rng = random.Random(seed)
    if construction == 'ccs2025':
        return scripted_chain(random_levels(n, rng))
    chain = [make_block(height, GENESIS_TARGET - height, GENESIS_TARGET, 600 * height, 'ours', ctr=rng.randbytes(32))
             for height in range(n)]
    chain[0].level, chain[0].ctr = GENESIS_LEVEL, None
    return chain


def make_fork(chain: list[Block], fork_height: int, n_blocks: int, target_factor: float, seed: int,
              construction: str, reveal: bool = True) -> list[Block]:
    """Blocks an adversary mines after a block of the chain, at a constant target of its choice.

    Args:
        chain: The chain.
        fork_height: Height of the last common block.
        n_blocks: Number of blocks to mine.
        target_factor: Target of the fork, relative to the target of the last common block.
        seed: Seed of the block hashes.
        construction: 'ccs2025' or 'ours'.
        reveal: Under ours, whether the adversary reveals its nonces (if not, its blocks have level 0).

    Returns:
        The blocks of the fork.
    """
    rng = random.Random(seed)
    target = min(int(chain[fork_height].target * target_factor), (1 << 256) - 1)
    fork = []
    for i in range(n_blocks):
        block = make_block(fork_height + 1 + i, rng.randrange(1, target + 1), target, chain[fork_height].time + 1 + i,
                           construction, ctr=rng.randbytes(32) if construction == 'ours' else None)
        if not reveal:
            block.ctr, block.level = None, 0
        fork.append(block)
    return fork
