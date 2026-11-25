"""The bytes of a header under each construction, and the formula that predicts their length.

A Bitcoin header is 80 bytes: version, previous hash, Merkle root, time, bits and nonce. The constructions add:

- ccs2025: an interlink, one pointer per level mu = 1..L to the last mu-block before the block (Remark 1);
- ours: the 4-byte nonce becomes the commitment H(ctr) (32 bytes); k - 1 pointers to the k predecessors besides the
  previous hash, which is the k-th; and per level mu = 1..L a tuple (H(b1), ctr1, H(b2), ctr2), b1 and b2 the last two
  revealed mu-blocks, whose H(b2) is the interlink of that level. A block is revealed once k blocks follow it.

L = ceil(log2(height + 2)), the "up to log #C" of the papers. Exported headers hold the hash, bits and time of each
block but not its version, Merkle root and Bitcoin nonce: those fields are zero here. Every pointer holds the real hash
of the block it designates, so a verifier can check that a proof is linked.

    links = Links(chain, 'ours', k=6)
    data = encode(chain, links, height=977_000)
"""

import bisect
from dataclasses import dataclass

import numpy as np

from vmls.chain import Block, sha256

CORE = 80  # Bytes of a Bitcoin header.
HASH = 32  # Bytes of a hash, a pointer or a nonce.
ZERO = bytes(HASH)


def n_levels(height: int) -> int:
    """Number of levels L a header at this height carries pointers for: ceil(log2(height + 2))."""
    return (height + 1).bit_length()


def header_size(construction: str, height: int, k: int) -> int:
    """The length of a header, by formula.

    Args:
        construction: 'ccs2025' or 'ours'.
        height: Height of the block.
        k: The common prefix parameter.

    Returns:
        The size in bytes.

    Raises:
        ValueError: If the construction is unknown.
    """
    if construction == 'ccs2025':
        return CORE + HASH * n_levels(height)
    if construction == 'ours':
        return CORE - 4 + HASH + HASH * (k - 1) + 4 * HASH * n_levels(height)
    raise ValueError(f'unknown construction {construction!r}')


def target_to_bits(target: int) -> int:
    """Encodes a target in the compact form of a header (the inverse of chain.bits_to_target)."""
    size = (target.bit_length() + 7) // 8
    mantissa = target >> (8 * (size - 3)) if size > 3 else target << (8 * (3 - size))
    if mantissa & 0x800000:  # The mantissa is signed: keep its top bit clear.
        mantissa >>= 8
        size += 1
    return (size << 24) | mantissa


def _hash(block: Block) -> bytes:
    """The 32 bytes of a block hash."""
    return block.hash.to_bytes(HASH, 'big')


class Links:
    """What the headers of a chain point to: for each level, the heights of its mu-blocks.

    Args:
        chain: The chain, indexed by height.
        construction: 'ccs2025' or 'ours'.
        k: The common prefix parameter.
    """

    def __init__(self, chain: list[Block], construction: str, k: int):
        self.chain, self.construction, self.k = chain, construction, k
        levels = np.fromiter((block.level for block in chain), dtype=np.int64, count=len(chain))
        self.rows = [np.zeros(0, dtype=np.int64)] + [np.flatnonzero(levels >= mu) for mu in
                                                     range(1, n_levels(len(chain)) + 1)]

    def last(self, mu: int, before: int, count: int) -> list[Block | None]:
        """The last mu-blocks at heights strictly below a bound, oldest first, padded with None.

        Args:
            mu: The level, at least 1.
            before: The bound on heights.
            count: How many to return.

        Returns:
            The blocks, None where the chain has fewer.
        """
        row = self.rows[mu]
        end = bisect.bisect_left(row, before)
        found = [self.chain[int(h)] for h in row[max(end - count, 0):end]]
        return [None] * (count - len(found)) + found


def encode(chain: list[Block], links: Links, height: int) -> bytes:
    """The header of a block, as a proof carries it.

    Args:
        chain: The chain, indexed by height.
        links: The links of that chain.
        height: Height of the block.

    Returns:
        The bytes of the header.
    """
    block, k = chain[height], links.k
    previous = _hash(chain[height - 1]) if height else ZERO
    core = (bytes(4) + previous + bytes(32) + block.time.to_bytes(4, 'little')
            + target_to_bits(block.target).to_bytes(4, 'little'))
    levels = range(1, n_levels(height) + 1)
    if links.construction == 'ccs2025':
        interlink = [links.last(mu, height, 1)[0] for mu in levels]
        return core + bytes(4) + b''.join(_hash(b) if b else ZERO for b in interlink)
    commitment = sha256(block.ctr) if block.ctr is not None else ZERO
    pointers = [_hash(chain[h]) if h >= 0 else ZERO for h in range(height - k, height - 1)]
    tuples = []
    for mu in levels:  # Revealed blocks only: those followed by k blocks before this one.
        for b in links.last(mu, height - k, 2):
            tuples += [_hash(b), b.ctr or ZERO] if b else [ZERO, ZERO]
    return core + commitment + b''.join(pointers) + b''.join(tuples)


@dataclass(frozen=True)
class Header:
    """A header read back from its bytes.

    Attributes:
        previous: Hash of the previous block.
        time: Unix time.
        bits: Compact target.
        commitment: H(ctr) under ours, None under ccs2025.
        pointers: Hashes this header points to besides the previous one: the interlink under ccs2025, the k - 1
            pointers and the H(b1), H(b2) of every tuple under ours.
        nonces: Under ours, the hash and nonce of every block a tuple reveals.
    """

    previous: bytes
    time: int
    bits: int
    commitment: bytes | None
    pointers: tuple[bytes, ...]
    nonces: tuple[tuple[bytes, bytes], ...]


def decode(data: bytes, construction: str, k: int) -> Header:
    """Reads a header back.

    Args:
        data: The bytes of the header.
        construction: 'ccs2025' or 'ours'.
        k: The common prefix parameter.

    Returns:
        The header.
    """
    previous, time, bits = data[4:36], int.from_bytes(data[68:72], 'little'), int.from_bytes(data[72:76], 'little')
    if construction == 'ccs2025':
        rest = data[CORE:]
        return Header(previous, time, bits, None, tuple(rest[i:i + HASH] for i in range(0, len(rest), HASH)), ())
    commitment, rest = data[76:108], data[108:]
    pointers = [rest[i:i + HASH] for i in range(0, HASH * (k - 1), HASH)]
    nonces = []
    for i in range(HASH * (k - 1), len(rest), 2 * HASH):
        pointers.append(rest[i:i + HASH])
        nonces.append((rest[i:i + HASH], rest[i + HASH:i + 2 * HASH]))
    return Header(previous, time, bits, commitment, tuple(pointers), tuple(nonces))

