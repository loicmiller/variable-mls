"""Size of every block of the chain, read from the block files of a stopped Bitcoin Core node.

Each record of a blk*.dat file is the network magic, the block size and the block. Only the first 88 bytes of each
record are read (size and header), so the scan is fast even on a network share; the header hash maps each size to
its height through the exported headers. Files are read only, with the XOR key of Bitcoin Core 28+ (blocks/xor.dat);
blocks off the main chain are ignored.

    python -m experiments.block_sizes --datadir ~/.bitcoin --headers HEADERS --out results/block-sizes.npy
"""

import argparse
import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from vmls.chain import load_headers

MAGIC = bytes.fromhex('f9beb4d9')  # Mainnet.


def scan(path: Path, key: bytes) -> list[tuple[str, int]]:
    """Reads the hash and size of each block stored in one file.

    Args:
        path: A blk*.dat file.
        key: The XOR key of the block files (8 bytes; all zeros when not obfuscated).

    Returns:
        (block hash in RPC byte order, size in bytes) for each record.
    """
    blocks = []
    with open(path, 'rb', buffering=0) as f:
        end = path.stat().st_size
        position = 0
        while position + 88 <= end:
            f.seek(position)
            raw = bytes(b ^ key[(position + i) % len(key)] for i, b in enumerate(f.read(88)))
            if raw[:4] != MAGIC:  # Preallocated zeros at the end of the file.
                break
            size = int.from_bytes(raw[4:8], 'little')
            block_hash = hashlib.sha256(hashlib.sha256(raw[8:88]).digest()).digest()[::-1].hex()
            blocks.append((block_hash, size))
            position += 8 + size
    return blocks


def main() -> None:
    """Scans every block file and writes the size of each block of the exported chain, by height."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--datadir', required=True, help='Data directory of the node (stopped).')
    parser.add_argument('--headers', required=True, help='Exported headers, which fix the chain and its heights.')
    parser.add_argument('--threads', type=int, default=16, help='Files read at once (latency of a network share).')
    parser.add_argument('--out', required=True, help='.npy file: the size of each block, -1 if not found.')
    args = parser.parse_args()

    blocks_dir = Path(args.datadir).expanduser() / 'blocks'
    key_path = blocks_dir / 'xor.dat'
    key = key_path.read_bytes() if key_path.exists() else bytes(8)
    files = sorted(blocks_dir.glob('blk*.dat'))
    height_of = {header['hash']: height for height, header in enumerate(load_headers(args.headers))}
    sizes = np.full(len(height_of), -1, dtype=np.int64)
    with ThreadPoolExecutor(args.threads) as pool:
        for i, blocks in enumerate(pool.map(lambda path: scan(path, key), files)):
            for block_hash, size in blocks:
                if block_hash in height_of:
                    sizes[height_of[block_hash]] = size
            if i % 500 == 0:
                print(f'{i}/{len(files)} files', flush=True)
    np.save(args.out, sizes)
    missing = int((sizes < 0).sum())
    print(f'{args.out}: {len(sizes)} blocks, {sizes[sizes > 0].sum() / 1e9:.1f} GB, {missing} not found')


if __name__ == '__main__':
    main()
