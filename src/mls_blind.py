###############################################################################
# Imports

import argparse
import collections
import hashlib
import json
import math
import random
import statistics
import sys
import time
from datetime import datetime

import numpy as np

import bitcoin
import config
import mls
import proof_bytes
from block import Block, genesisTarget, level as ccs_level



###############################################################################
# Constants

MAX_POINTER_LEVEL = 64 # Interlink levels tracked by a prover (the genesis block has level 256).
HASH_BUFFER = random.Random(0).randbytes(20_000) # Stand-in for serialized headers, only its length matters to SHA-256.
VERIFIER_REPETITIONS = 5 # Verifier timings are the median of this many runs.



###############################################################################
# Block levels under blind mining

def sha256(data):
    """
    Single SHA-256.

    Args:
    - data (bytes): The data to hash.

    Returns:
    - bytes: The digest.
    """
    return hashlib.sha256(data).digest()


def sha256d(data):
    """
    Double SHA-256, as Bitcoin hashes its headers.

    Args:
    - data (bytes): The data to hash.

    Returns:
    - bytes: The digest.
    """
    return sha256(sha256(data))


def blind_level(ctr, y):
    """
    Level of a block from its revealed nonce.

    Args:
    - ctr (bytes): The revealed nonce.
    - y (bytes): The PoW hash H(H(ctr), h) of the block.

    Returns:
    - int: The largest mu such that H(ctr, y) < 2^(256-mu), i.e. the number of leading zero bits.

    Notes:
    - This is the corrected definition. As written in the draft, H(ctr, y) < T_b/2^mu holds with probability T_b/2^(256+mu).
    """
    return 256 - int.from_bytes(sha256(ctr + y), 'big').bit_length()


def set_blind_fields(block):
    """
    Gives a historical block the fields blind mining would have given it, then its blind level.

    Args:
    - block (Block): The block, modified in place.

    Returns:
    - None

    Notes:
    - Bitcoin headers have no ctr. It is derived from the block hash, so that a run is reproducible, and the real block
      hash stands in for the PoW hash y. Targets and timestamps stay the real ones.
    """
    block.y = block.block_hash.to_bytes(32, 'big')
    block.ctr = sha256(block.y + b'ctr')
    block.commitment = sha256(block.ctr)
    block.level = blind_level(block.ctr, block.y)


class SyntheticBlock:
    """
    A block of a fork: same attributes as Block, without the cost of building one from a real header.
    """
    __slots__ = ('height', 'target', 'block_hash', 'timestamp', 'diff', 'level', 'y', 'ctr', 'commitment')

    def __init__(self, height, target, rng, blind):
        """
        Constructor for SyntheticBlock class.

        Args:
            height (int): The height of the block.
            target (int): The target of the block.
            rng (random.Random): The source of the block hash.
            blind (bool): Whether the level is the blind one or the one from the block hash.
        """
        self.height = height
        self.target = target
        self.block_hash = rng.randrange(1, target)
        self.timestamp = 0
        self.diff = int(genesisTarget / target)
        if blind:
            set_blind_fields(self)
        else:
            self.level = ccs_level(self.block_hash, target)


def make_fork(chain, fork_height, n_blocks, target_factor, seed, blind):
    """
    Blocks mined after a block of the chain, at a constant target.

    Args:
    - chain (list): The chain, as a list of blocks.
    - fork_height (int): The height of the last common block.
    - n_blocks (int): The number of blocks to mine.
    - target_factor (float): The target of the fork relative to the target of the last common block.
    - seed (int): The seed of the fork.
    - blind (bool): Whether levels are the blind ones.

    Returns:
    - list: The blocks of the fork.
    """
    rng = random.Random(seed)
    target = int(chain[fork_height].target * target_factor)
    return [SyntheticBlock(fork_height + 1 + i, target, rng, blind) for i in range(n_blocks)]



###############################################################################
# Verifier

def split_proof(proof):
    """
    Dissolves a proof and separates its unstable subchain.

    Args:
    - proof (list): The proof, as a list of blocks.

    Returns:
    - D, X, Omega (tuple): The dissolved chain, the uncompressed subchain and the unstable subchain.
    """
    D, _, remainder = mls.Dissolve(proof)
    return D, remainder[:-mls.k_args], remainder[-mls.k_args:]


def lowest_common_ancestor(D_1, D_2):
    """
    Finds the level to compare two proofs at and their last common block at this level.

    Args:
    - D_1 (dict): The dissolved chain of the first proof.
    - D_2 (dict): The dissolved chain of the second proof.

    Returns:
    - mu, b (tuple): The level and the block, or (None, None) if the proofs share no block.

    Notes:
    - Blocks are matched by hash. mls.intersection matches them by height, which only holds for two proofs of one chain.
    """
    common = {}
    for mu in D_1.keys() & D_2.keys():
        hashes = {block.block_hash for block in D_2[mu]}
        blocks = [block for block in D_1[mu] if block.block_hash in hashes]
        if blocks:
            common[mu] = blocks
    if not common:
        return None, None
    mu = min(common)
    return mu, common[mu][-1]


def from_block(row, b):
    """
    The blocks of a row of D from a block onwards, the D{b:} of the paper.

    Args:
    - row (list): A row of the dissolved chain.
    - b (Block): The block, included in the result.

    Returns:
    - list: The blocks from b onwards.
    """
    return row[next(i for i, block in enumerate(row) if block.block_hash == b.block_hash):]


def score(blocks, v):
    """
    The Score algorithm of the draft.

    Args:
    - blocks (list): Blocks of a single level.
    - v (float): The factor v_mu.

    Returns:
    - float: The difficulty of the blocks, each capped at v times their median difficulty.
    """
    cap = v * statistics.median(block.diff for block in blocks)
    return sum(min(block.diff, cap) for block in blocks)


def compare_vmls(proof_1, proof_2):
    """
    The verifier of Miller et al. as the paper describes it: it compares mu-blocks only, X and Omega included.

    Args:
    - proof_1 (list): The first proof.
    - proof_2 (list): The second proof.

    Returns:
    - winner, path (tuple): 1 or 2 (None if the online test decides), and the branch taken.

    Notes:
    - mls.Compare counts X and Omega whatever their level, where the paper only counts their mu-blocks. Under the
      Zero-Difficulty attack the honest proof then wins by its X and Omega, so the paper's version is the one attacked.
    """
    D_1, X_1, Omega_1 = split_proof(proof_1)
    D_2, X_2, Omega_2 = split_proof(proof_2)
    mu, b = lowest_common_ancestor(D_1, D_2)
    if mu is None:
        return None, 'online'
    score_1 = mls.chain_score(from_block(D_1[mu], b) + mls.filter_chain_by_level(X_1 + Omega_1, mu))
    score_2 = mls.chain_score(from_block(D_2[mu], b) + mls.filter_chain_by_level(X_2 + Omega_2, mu))
    return (2 if score_2 > score_1 else 1), f'level-{"0" if mu == 0 else "mu"}'


def compare_blind(proof_1, proof_2, K, v):
    """
    The Compare algorithm of the draft, without the wait of the online test.

    Args:
    - proof_1 (list): The first proof.
    - proof_2 (list): The second proof.
    - K (int): The security parameter.
    - v (float): The factor v_mu.

    Returns:
    - winner, path (tuple): 1 or 2 (None if the online test decides), and the branch taken: 'level-0', 'score' or 'online'.

    Notes:
    - The blocks of Omega are left out of the score, since an honest prover has not revealed them yet.
    """
    D_1, X_1, Omega_1 = split_proof(proof_1)
    D_2, X_2, Omega_2 = split_proof(proof_2)
    mu, b = lowest_common_ancestor(D_1, D_2)
    if mu is None:
        return None, 'online'
    row_1, row_2 = from_block(D_1[mu], b), from_block(D_2[mu], b)
    if mu == 0:
        difficulty_1 = mls.chain_score(row_1 + X_1 + Omega_1)
        difficulty_2 = mls.chain_score(row_2 + X_2 + Omega_2)
        return (1 if difficulty_1 >= difficulty_2 else 2), 'level-0'
    if len(row_1) >= K and len(row_2) >= K:
        score_1 = score(row_1 + mls.filter_chain_by_level(X_1, mu), v)
        score_2 = score(row_2 + mls.filter_chain_by_level(X_2, mu), v)
        return (1 if score_1 > score_2 else 2), 'score'
    return None, 'online'


def validate_proof(proof, scheme, k):
    """
    What a verifier must hash to accept a proof: mls.proof_not_valid is a stub, so this cost was never measured.

    Args:
    - proof (list): The proof, as a list of blocks.
    - scheme (str): One of 'ccs', 'ccs-merkle', 'draft', 'draft-merkle'.
    - k (int): The common prefix parameter.

    Returns:
    - None

    Raises:
    - ValueError: If a block does not satisfy its target or its commitment.

    Notes:
    - Headers and Merkle paths are not in the historical data: the hash calls are real and of the right length, but their
      input is a stand-in. Only the checks on block hashes, targets and commitments compare real values.
    """
    n_compressed = len(proof) - mls.k_args - mls.chi_args
    n_revealed = len(proof) - k
    blind = scheme.startswith('draft')
    for i, block in enumerate(proof):
        sha256d(HASH_BUFFER[:proof_bytes.header_size(scheme, block.height, k)])
        if block.block_hash > block.target:
            raise ValueError(f'block {block.height} does not satisfy its target')
        if blind and i < n_revealed:
            if sha256(block.ctr) != block.commitment:
                raise ValueError(f'block {block.height} does not open its commitment')
            blind_level(block.ctr, block.y)
        if scheme == 'ccs-merkle' and i < n_compressed:
            depth = proof_bytes.merkle_path(proof_bytes.n_levels(block.height)) // proof_bytes.HASH
            for _ in range(depth):
                sha256(HASH_BUFFER[:64])
        if scheme == 'draft-merkle' and i < n_revealed:
            depth = proof_bytes.merkle_path(proof_bytes.draft_leaves(block.height, k)) // proof_bytes.HASH
            for _ in range(2 * depth if i < n_compressed else depth):
                sha256(HASH_BUFFER[:64])


def time_verifier(proof_1, proof_2, scheme, K, k, v):
    """
    CPU time of a verifier on two proofs: it validates both, dissolves both and compares them.

    Args:
    - proof_1 (list): The first proof.
    - proof_2 (list): The second proof.
    - scheme (str): One of 'ccs', 'ccs-merkle', 'draft', 'draft-merkle'.
    - K (int): The security parameter.
    - k (int): The common prefix parameter.
    - v (float): The factor v_mu.

    Returns:
    - milliseconds, winner, path (tuple): The median time, and the outcome of the comparison.
    """
    timings = []
    for _ in range(VERIFIER_REPETITIONS):
        start = time.perf_counter_ns()
        validate_proof(proof_1, scheme, k)
        validate_proof(proof_2, scheme, k)
        if scheme.startswith('draft'):
            winner, path = compare_blind(proof_1, proof_2, K, v)
        else:
            winner, path = compare_vmls(proof_1, proof_2)
        timings.append(time.perf_counter_ns() - start)
    return statistics.median(timings) / 1e6, winner, path


def tip_fork(chain, proof, blind):
    """
    A competing proof that forks in the unstable subchain, with fewer blocks of the same difficulty.

    Args:
    - chain (list): The chain, as a list of blocks.
    - proof (list): The honest proof.
    - blind (bool): Whether levels are the blind ones.

    Returns:
    - list: The competing proof.
    """
    depth = mls.k_args // 2
    return proof[:-depth] + make_fork(chain, proof[-depth - 1].height, depth - 10, 1, seed=proof[-1].height, blind=blind)


def deep_fork(chain, height, blind):
    """
    A competing proof that forks a quarter of the chain ago, with 80% of the honest blocks and the difficulty of the fork
    point, so that it shares an ancestor at a level above 0.

    Args:
    - chain (list): The chain, as a list of blocks.
    - height (int): The height of the tip.
    - blind (bool): Whether levels are the blind ones.

    Returns:
    - list: The competing proof.
    """
    depth = max(height // 4, 2 * (mls.k_args + mls.chi_args))
    fork = make_fork(chain, height - depth, int(0.8 * depth), 1, seed=height, blind=blind)
    return mls.Compress(chain[:height - depth + 1] + fork)



###############################################################################
# Measurements

def proof_byte_sizes(proof, k, schemes):
    """
    Sizes of the current proof under each scheme.

    Args:
    - proof (list): The proof, as a list of blocks.
    - k (int): The common prefix parameter.
    - schemes (tuple): The schemes to size the proof for.

    Returns:
    - dict: The size of the proof in bytes, per scheme.
    """
    heights = [block.height for block in proof]
    D, X, Omega = heights[:-mls.k_args - mls.chi_args], heights[-mls.k_args - mls.chi_args:-mls.k_args], heights[-mls.k_args:]
    return {scheme: proof_bytes.proof_size(scheme, D, X, Omega, k) for scheme in schemes}


def merkle_root(leaves):
    """
    Root of a Merkle tree, rebuilt from its leaves.

    Args:
    - leaves (list): The leaves, as a list of bytes.

    Returns:
    - bytes: The root.
    """
    nodes = leaves
    while len(nodes) > 1:
        nodes = [sha256(b''.join(nodes[i:i + 2])) for i in range(0, len(nodes), 2)]
    return nodes[0]


def run(args):
    """
    Grows the proof over the whole chain, block after block, and measures both the prover and the verifier.

    Args:
    - args (argparse.Namespace): The command-line arguments.

    Returns:
    - None

    Notes:
    - The ccs mode measures the schemes 'ccs' and 'ccs-merkle', the blind mode 'draft' and 'draft-merkle'.
    - A blind prover learns a level only k blocks later. Its update reveals the block at depth k, whereas D, built on the
      prefix deeper than k+chi blocks, never holds an unrevealed block. Levels are then set ahead of time, outside the timers.
    - The Merkle root is rebuilt from scratch at each block, which is an upper bound on its cost.
    """
    blind = args.mode == 'blind'
    schemes = ('draft', 'draft-merkle') if blind else ('ccs', 'ccs-merkle')
    K, k, chi = args.K, args.k, args.chi
    mls.K_args, mls.k_args, mls.chi_args = K, k, chi
    config.HEADERS_FILE_PATH = args.headers
    bitcoin.LOAD_FROM_HEADERS_FILE = True
    n = bitcoin.load_headers(args.break_at)

    latency_base = np.zeros(n, dtype=np.uint32)
    latency_compress = np.zeros(n, dtype=np.uint32)
    latency_merkle = np.zeros(n, dtype=np.uint32)
    proof_sizes = np.zeros(n, dtype=np.uint32)
    proof_levels = np.zeros(n, dtype=np.uint16) if args.regress else None
    block_levels = np.zeros(n, dtype=np.uint16)
    byte_samples = []
    verifier_samples = []

    chain = []
    proof = []
    window = collections.deque(maxlen=k) # The k pointers of the next header.
    last_blocks = [[] for _ in range(MAX_POINTER_LEVEL)] # The interlink: last block(s) of each level.
    kept_per_level = 2 if blind else 1 # A blind header keeps the last two blocks of each level, with their nonces.

    print('Starting compression loop...')
    for height in range(n):
        b = bitcoin.get_block_by_height(height)
        if blind:
            set_blind_fields(b)
        if height == 0:
            b.level = 256 # Set level of genesis block to infinity.
        block_levels[height] = b.level
        chain.append(b)

        # The prover receives a block: it checks the block, updates its interlink, then its proof.
        start = time.perf_counter_ns()
        sha256d(HASH_BUFFER[:proof_bytes.header_size(schemes[0], height, k)])
        revealed = b
        if blind:
            revealed = chain[height - k] if height >= k else None
            if revealed is not None:
                if sha256(revealed.ctr) != revealed.commitment:
                    raise ValueError(f'block {revealed.height} does not open its commitment')
                blind_level(revealed.ctr, revealed.y)
            window.append(b)
        if revealed is not None:
            for mu in range(min(revealed.level, MAX_POINTER_LEVEL - 1) + 1):
                last_blocks[mu] = last_blocks[mu][-(kept_per_level - 1):] + [revealed] if kept_per_level > 1 else [revealed]
        compress_start = time.perf_counter_ns()
        proof.append(b)
        proof = mls.Compress(proof)
        end = time.perf_counter_ns()
        latency_compress[height] = (end - compress_start) // 1_000
        latency_base[height] = (end - start) // 1_000

        # The Merkle variant replaces the hash of the long header by the hash of a short one and the root of the pointers.
        start = time.perf_counter_ns()
        sha256d(HASH_BUFFER[:proof_bytes.header_size(schemes[1], height, k)])
        leaves = [(block.block_hash).to_bytes(32, 'big') for block in window]
        for blocks in last_blocks[:proof_bytes.n_levels(height)]:
            leaves += [(block.block_hash).to_bytes(32, 'big') for block in blocks]
            if blind:
                leaves += [block.ctr for block in blocks]
        merkle_root(leaves or [b''])
        latency_merkle[height] = (time.perf_counter_ns() - start) // 1_000

        proof_sizes[height] = len(proof)
        if args.regress:
            proof_levels[height] = mls.get_proof_level(proof)

        if height % args.byte_stride == 0 and height > k + chi:
            byte_samples.append({'height': height, 'blocks': len(proof), **proof_byte_sizes(proof, k, schemes)})

        if not args.no_verifier and height % args.verifier_stride == 0 and height >= args.verifier_from:
            v = args.v
            for fork_name, other in (('tip', tip_fork(chain, proof, blind)), ('deep', deep_fork(chain, height, blind))):
                for scheme in schemes:
                    milliseconds, winner, path = time_verifier(proof, other, scheme, K, k, v)
                    verifier_samples.append({'height': height, 'fork': fork_name, 'scheme': scheme, 'ms': milliseconds, 'winner': winner, 'path': path, 'blocks': [len(proof), len(other)]})

        if height % args.print_step == 0:
            print(f'{datetime.now():%H:%M:%S} height={height} size={len(proof)} compress={latency_compress[height]} us', flush=True)

    stamp = datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
    name = f'data/{stamp}-blind-eval-{args.mode}-up-to-{n}-K-{K}-chi-{chi}-k-{k}'
    np.savez_compressed(f'{name}.npz', latency_base=latency_base, latency_compress=latency_compress, latency_merkle=latency_merkle, proof_size=proof_sizes, block_level=block_levels)
    with open(f'{name}.json', 'w') as f:
        json.dump({'args': vars(args), 'bytes': byte_samples, 'verifier': verifier_samples}, f)
    print(f'Results in {name}.npz and {name}.json')

    if args.regress:
        with open(args.regress) as f:
            reference = json.load(f)
        for field, values in (('proof_size', proof_sizes), ('proof_level', proof_levels), ('block_level', block_levels)):
            mismatches = int((np.array(reference[field][:n]) != values).sum())
            print(f'regression {field}: {mismatches} mismatches over {n} blocks')
            if mismatches:
                sys.exit(1)



###############################################################################
# Main

def get_parser():
    """
    Creates the command-line parser.

    Args:
    - None

    Returns:
    - argparse.ArgumentParser: The parser.
    """
    parser = argparse.ArgumentParser(description='Costs of blind-mining NIPoPoWs on the Bitcoin header chain.')
    parser.add_argument('--mode', choices=['ccs', 'blind'], required=True, help='Scheme to measure.')
    parser.add_argument('-K', type=int, default=208, help='Security parameter.')
    parser.add_argument('-k', type=int, default=323, help='Common prefix parameter.')
    parser.add_argument('-chi', type=int, default=4032, help='Length of the uncompressed part.')
    parser.add_argument('-v', type=float, default=33.0, help='Factor v_mu of the Score algorithm.')
    parser.add_argument('--headers', default=config.HEADERS_FILE_PATH, help='Path to the headers file.')
    parser.add_argument('-b', '--break-at', type=int, default=None, help='Stop at this height.')
    parser.add_argument('--byte-stride', type=int, default=2016, help='Blocks between two proof size samples.')
    parser.add_argument('--verifier-stride', type=int, default=16128, help='Blocks between two verifier samples.')
    parser.add_argument('--verifier-from', type=int, default=32256, help='Height of the first verifier sample.')
    parser.add_argument('--no-verifier', action='store_true', help='Do not measure the verifier.')
    parser.add_argument('--regress', default=None, help='Check proof sizes and levels against this mls.py data dump.')
    parser.add_argument('--print-step', type=int, default=20_000, help='Blocks between two status lines.')
    return parser


if __name__ == '__main__':
    run(get_parser().parse_args())
