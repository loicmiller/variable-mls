"""Time to build a NIPoPoW from scratch, from the headers of the chain up to a given height.

A new prover starts from the headers: it turns them into blocks (decoding targets, computing levels: one division
for CCS 2025; under blind mining, checking that each revealed nonce opens its commitment and hashing it with the block,
two SHA-256), compresses the chain, and with the Merkle variant builds the tree of each block it keeps. Each step is
timed separately, as the median of several runs on one core. Reading the headers file is timed once; it does not
depend on the construction. Bitcoin has no blind nonces: they are simulated before the timers, as a blind chain would
carry them.

    taskset -c 2 python -m experiments.build_time --headers HEADERS --out results/build-time.json
"""

import argparse
import json
import statistics
import time

import numpy as np

from vmls.chain import Block, blocks_from_headers, load_headers, simulated_nonce
from vmls.nipopow import Params, compress
from vmls.sizes import merkle_root, n_levels

K_VALUES = (104, 208, 416)


def timed(function, repetitions: int):
    """Median time of a call, and its result.

    Args:
        function: The call, without arguments.
        repetitions: Number of runs.

    Returns:
        The median time in seconds, and the result of the last run.
    """
    times = []
    for _ in range(repetitions):
        start = time.perf_counter()
        result = function()
        times.append(time.perf_counter() - start)
    return statistics.median(times), result


def merkle_roots(chain: list[Block], proof: list[Block], k: int) -> None:
    """Builds the tree of each block the proof keeps: its k pointers, and for each level the last two blocks of that
    level with their nonces.

    Args:
        chain: The chain, blind levels.
        proof: The blocks kept.
        k: The common prefix parameter.
    """
    levels = np.array([block.level for block in chain])
    hashes = [block.block_hash.to_bytes(32, 'big') for block in chain]
    by_level = {mu: np.flatnonzero(levels >= mu) for mu in range(n_levels(len(chain)))}
    for block in proof:
        j = block.height
        leaves = hashes[max(0, j - k):j]
        for mu in range(n_levels(j)):
            for i in by_level[mu][max(0, np.searchsorted(by_level[mu], j) - 2):np.searchsorted(by_level[mu], j)]:
                leaves += [hashes[i], chain[i].ctr]
        merkle_root(leaves or [b''])


def main() -> None:
    """Times every step at every height and writes the results."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--headers', required=True, help='Exported headers.')
    parser.add_argument('--step', type=int, default=50_000, help='Blocks between two heights.')
    parser.add_argument('--repetitions', type=int, default=5, help='Runs per measure.')
    parser.add_argument('-k', type=int, default=323, help='Common prefix parameter.')
    parser.add_argument('-chi', type=int, default=4032, help='Length of the uncompressed subchain.')
    parser.add_argument('--out', required=True, help='JSON file.')
    args = parser.parse_args()

    read_seconds, headers = timed(lambda: load_headers(args.headers), 1)
    nonces = [simulated_nonce(int(header['hash'], 16)) for header in headers]  # Read from the chain, not timed.
    heights = list(range(args.step, len(headers), args.step)) + [len(headers) - 1]
    rows = []
    for blind in (False, True):
        scheme = 'draft' if blind else 'ccs'
        for height in heights:
            blocks_seconds, chain = timed(lambda: blocks_from_headers(headers, blind=blind, stop=height + 1,
                                                                      nonces=nonces if blind else None),
                                          args.repetitions)
            for K in K_VALUES:
                p = Params(K, args.k, args.chi)
                compress_seconds, proof = timed(lambda: compress(chain, p), args.repetitions)
                row = {'scheme': scheme, 'height': height, 'K': K, 'blocks_s': blocks_seconds,
                       'compress_s': compress_seconds, 'proof_blocks': len(proof)}
                if blind:
                    row['merkle_s'] = timed(lambda: merkle_roots(chain, proof, args.k), max(1, args.repetitions // 2))[0]
                rows.append(row)
                print(json.dumps(row), flush=True)
    with open(args.out, 'w') as f:
        json.dump({'headers': str(args.headers), 'n_headers': len(headers), 'read_s': read_seconds,
                   'repetitions': args.repetitions, 'rows': rows}, f, indent=1)
    print(f'{args.out} written')


if __name__ == '__main__':
    main()
