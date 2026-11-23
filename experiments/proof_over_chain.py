"""Grows a NIPoPoW over the Bitcoin header chain, block after block, and measures the prover and the verifier.

For each block: the time to update the proof (checking the header, revealing the block k deep under blind mining,
compressing), the extra time of a Merkle root over the pointers, the size of the proof and the level of the block.
Every few epochs: the size of the proof in bytes under each scheme, and the CPU time of a verifier facing a fork near
the tip and a fork a quarter of the chain ago.

    python -m experiments.proof_over_chain --mode ccs --headers headers/headers.json -K 208

The ccs mode measures the schemes 'ccs' and 'ccs-merkle', the blind mode 'draft' and 'draft-merkle'. A blind prover
learns a level k blocks late; D, built on the prefix deeper than k + chi blocks, never holds an unrevealed block, so
levels are set ahead of time, outside the timers. The Merkle root is rebuilt from scratch at each block, an upper bound.
"""

import argparse
import collections
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from vmls.chain import blind_level, blocks_from_headers, load_headers, sha256
from vmls.cost import HASH_BUFFER, sha256d, time_verifier
from vmls.nipopow import Params, compress, difficulty_sum, dissolve, proof_levels
from vmls.sizes import n_levels, header_size, merkle_root, proof_size
from vmls.synthetic import deep_fork, tip_fork

MAX_POINTER_LEVEL = 64  # Interlink levels a prover tracks (the genesis block has level 256).


def byte_sizes(proof: list, p: Params, schemes: tuple[str, ...]) -> dict[str, int]:
    """Size of a proof under each scheme.

    Args:
        proof: The proof.
        p: The parameters.
        schemes: The schemes.

    Returns:
        The size in bytes, by scheme.
    """
    heights = [block.height for block in proof]
    D, X, Omega = heights[:-p.k - p.chi], heights[-p.k - p.chi:-p.k], heights[-p.k:]
    return {scheme: proof_size(scheme, D, X, Omega, p.k) for scheme in schemes}


def run(args: argparse.Namespace) -> Path:
    """Grows the proof over the chain and writes the measurements.

    Args:
        args: The command line.

    Returns:
        The prefix of the files written (.npz and .json).
    """
    blind = args.mode == 'blind'
    schemes = ('draft', 'draft-merkle') if blind else ('ccs', 'ccs-merkle')
    p = Params(args.K, args.k, args.chi)
    chain = blocks_from_headers(load_headers(args.headers), blind=blind, stop=args.stop)
    n = len(chain)

    latency_base = np.zeros(n, dtype=np.uint32)
    latency_compress = np.zeros(n, dtype=np.uint32)
    latency_merkle = np.zeros(n, dtype=np.uint32)
    sizes = np.zeros(n, dtype=np.uint32)
    block_levels = np.array([block.level for block in chain], dtype=np.uint16)
    byte_samples, verifier_samples = [], []

    proof = []
    window = collections.deque(maxlen=p.k)  # The k pointers of the next header.
    last_blocks = [[] for _ in range(MAX_POINTER_LEVEL)]  # The interlink: last block, or last two under blind mining.
    kept_per_level = 2 if blind else 1

    for height, b in enumerate(chain):
        # The prover receives a block: it checks it, updates its interlink, then its proof.
        start = time.perf_counter_ns()
        sha256d(HASH_BUFFER[:header_size(schemes[0], height, p.k)])
        revealed = b
        if blind:
            revealed = chain[height - p.k] if height >= p.k else None
            if revealed is not None:
                if sha256(revealed.ctr) != revealed.commitment:
                    raise ValueError(f'block {revealed.height} does not open its commitment')
                blind_level(revealed.ctr, revealed.block_hash.to_bytes(32, 'big'))
            window.append(b)
        if revealed is not None:
            for mu in range(min(revealed.level, MAX_POINTER_LEVEL - 1) + 1):
                last_blocks[mu] = last_blocks[mu][-(kept_per_level - 1):] + [revealed] if kept_per_level > 1 else [revealed]
        compress_start = time.perf_counter_ns()
        proof.append(b)
        proof = compress(proof, p)
        end = time.perf_counter_ns()
        latency_compress[height] = (end - compress_start) // 1_000
        latency_base[height] = (end - start) // 1_000

        # The Merkle variant hashes a short header and rebuilds the root of the pointers.
        start = time.perf_counter_ns()
        sha256d(HASH_BUFFER[:header_size(schemes[1], height, p.k)])
        leaves = [block.block_hash.to_bytes(32, 'big') for block in window]
        for blocks in last_blocks[:n_levels(height)]:
            leaves += [block.block_hash.to_bytes(32, 'big') for block in blocks]
            if blind:
                leaves += [block.ctr for block in blocks]
        merkle_root(leaves or [b''])
        latency_merkle[height] = (time.perf_counter_ns() - start) // 1_000
        sizes[height] = len(proof)

        if height % args.byte_stride == 0 and height > p.k + p.chi:
            byte_samples.append({'height': height, 'blocks': len(proof), **byte_sizes(proof, p, schemes)})
        if not args.no_verifier and height % args.verifier_stride == 0 and height >= args.verifier_from:
            for fork_name, other in (('tip', tip_fork(chain, proof, p, blind)), ('deep', deep_fork(chain, height, p, blind))):
                for scheme in schemes:
                    milliseconds, winner, path = time_verifier(proof, other, scheme, p, args.v)
                    verifier_samples.append({'height': height, 'fork': fork_name, 'scheme': scheme, 'ms': milliseconds,
                                             'winner': winner, 'path': path, 'blocks': [len(proof), len(other)]})
        if height % args.print_step == 0:
            print(f'{datetime.now():%H:%M:%S} height={height} size={len(proof)} compress={latency_compress[height]} us', flush=True)

    D, _, _ = dissolve(proof, p)
    last_K_difficulty = {mu: difficulty_sum(row[-p.K:]) for mu, row in D.items()}  # The last row of the CCS 2025 data.
    Path(args.out_dir).mkdir(parents=True, exist_ok=True)
    prefix = Path(args.out_dir) / f'{datetime.now():%Y-%m-%d-%H-%M-%S}-proof-over-chain-{args.mode}-up-to-{n - 1}-K-{p.K}-chi-{p.chi}-k-{p.k}'
    np.savez_compressed(prefix.with_suffix('.npz'), latency_base=latency_base, latency_compress=latency_compress,
                        latency_merkle=latency_merkle, proof_size=sizes, block_level=block_levels)
    with open(prefix.with_suffix('.json'), 'w') as f:
        json.dump({'args': vars(args), 'bytes': byte_samples, 'verifier': verifier_samples,
                   'last_K_difficulty': last_K_difficulty}, f)
    print(f'Results in {prefix}.npz and .json')

    if args.regress:
        with open(args.regress) as f:
            reference = json.load(f)
        checks = {'proof_size': sizes, 'block_level': block_levels, 'proof_level': proof_levels(block_levels, p.K)}
        for field, values in checks.items():
            if field in reference:
                mismatches = int((np.array(reference[field][:n]) != values).sum())
                print(f'regression {field}: {mismatches} mismatches over {n} blocks')
                if mismatches:
                    sys.exit(1)
    return prefix


def parser() -> argparse.ArgumentParser:
    """The command line.

    Returns:
        The parser.
    """
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--mode', choices=['ccs', 'blind'], required=True, help='Construction to measure.')
    parser.add_argument('--headers', required=True, help='Exported headers (JSON, or the zip of the repository).')
    parser.add_argument('-K', type=int, default=208, help='Security parameter.')
    parser.add_argument('-k', type=int, default=323, help='Common prefix parameter.')
    parser.add_argument('-chi', type=int, default=4032, help='Length of the uncompressed subchain.')
    parser.add_argument('-v', type=float, default=33.0, help='Factor v_mu of the Score.')
    parser.add_argument('--stop', type=int, default=None, help='Height to stop before.')
    parser.add_argument('--byte-stride', type=int, default=2016, help='Blocks between two size samples.')
    parser.add_argument('--verifier-stride', type=int, default=16128, help='Blocks between two verifier samples.')
    parser.add_argument('--verifier-from', type=int, default=32256, help='Height of the first verifier sample.')
    parser.add_argument('--no-verifier', action='store_true', help='Do not measure the verifier.')
    parser.add_argument('--regress', default=None, help='Check sizes and levels against a data dump of the CCS 2025 code.')
    parser.add_argument('--print-step', type=int, default=20_000, help='Blocks between two status lines.')
    parser.add_argument('--out-dir', default='results', help='Directory of the results.')
    return parser


if __name__ == '__main__':
    run(parser().parse_args())
