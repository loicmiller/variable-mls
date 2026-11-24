"""The measurements: each function replays the Bitcoin headers and returns what it measured, ready for JSON.

- replay: grows a proof block after block over the whole chain, timing each update, sampling its size and timing
  the verifier against a fork near the tip and a fork a quarter of the chain back;
- build_time: builds a proof from scratch at several heights, step by step;
- sections: the size of D, X and Omega at several heights and values of K;
- k_star: the K* the bound of Lemma lem:adversarial_score asks for on Bitcoin, from the spread of difficulties;
- attack: when the proof level of Bitcoin rose, and the success probability of the zero-difficulty attack at each.

Every timing runs on one thread; a median of several runs where a measure is short.
"""

import collections
import math
import statistics
import time
from collections.abc import Callable

import numpy as np

from vmls.chain import (GENESIS_LEVEL, Block, bits_to_target, ccs_level, chain_from_headers, committed_level,
                        make_fork, sha256, sha256d, simulated_nonce)
from vmls.encoding import Links, encode, header_size
from vmls.proof import Params, compress, dissolve, proof_level
from vmls.verify import check, check_model, compare_ccs, compare_ours, reveal_coverage

EPOCH = 2016  # Blocks between two target recalculations (m).
BLOCK_SECONDS = 600


def timed(function: Callable[[], object], repetitions: int = 1) -> tuple[float, object]:
    """The median time of a call, in seconds, and its last result."""
    times, result = [], None
    for _ in range(repetitions):
        start = time.perf_counter()
        result = function()
        times.append(time.perf_counter() - start)
    return statistics.median(times), result


def parts(proof: list[Block], p: Params) -> dict[str, list[Block]]:
    """D, X and Omega of a proof, by position (the last k blocks, the chi before them, the rest)."""
    n = len(proof)
    return {'D': proof[:max(n - p.k - p.chi, 0)], 'X': proof[max(n - p.k - p.chi, 0):n - p.k], 'Omega': proof[n - p.k:]}


def size_by_part(proof: list[Block], construction: str, p: Params, block_sizes: np.ndarray | None = None) -> dict:
    """Blocks and bytes of each part of a proof: headers of D and X, full blocks of Omega when sizes are known.

    Args:
        proof: The proof.
        construction: 'ccs2025' or 'ours'.
        p: The parameters.
        block_sizes: The size of every block by height, from node.block_sizes.

    Returns:
        {'blocks': {...}, 'bytes': {...}} by part; Omega's bytes add the block bodies to its headers.
    """
    out = {'blocks': {}, 'bytes': {}}
    for name, blocks in parts(proof, p).items():
        out['blocks'][name] = len(blocks)
        out['bytes'][name] = sum(header_size(construction, b.height, p.k) for b in blocks)
        if name == 'Omega' and block_sizes is not None:
            out['bytes'][name] += sum(int(block_sizes[b.height]) - 80 for b in blocks)
    return out


def tip_fork(chain: list[Block], proof: list[Block], p: Params, construction: str) -> tuple[list[Block], list[Block]]:
    """A competing chain that forks inside Omega, with one block fewer at the same target.

    Returns:
        The competing chain and its proof.
    """
    depth = max(p.k // 2, 1)
    fork_height = proof[-depth - 1].height
    fork = make_fork(chain, fork_height, depth - 1, 1, seed=proof[-1].height, construction=construction)
    return chain[:fork_height + 1] + fork, proof[:-depth] + fork


def deep_fork(chain: list[Block], height: int, p: Params, construction: str) -> tuple[list[Block], list[Block]]:
    """A competing chain that forks a quarter of the chain back, with 80 % of the honest blocks at the same target.

    Returns:
        The competing chain and its proof.
    """
    depth = max(height // 4, 2 * (p.k + p.chi))
    fork = make_fork(chain, height - depth, int(0.8 * depth), 1, seed=height, construction=construction)
    other = chain[:height - depth + 1] + fork
    return other, compress(other, p)


def time_verifier(chain: list[Block], proof: list[Block], other_chain: list[Block], other: list[Block],
                  construction: str, p: Params, v: float, repetitions: int = 5) -> dict:
    """Times a verifier that checks two proofs, then compares them, with real headers and by formula.

    Args:
        chain: The honest chain.
        proof: Its proof.
        other_chain: The competing chain.
        other: Its proof.
        construction: 'ccs2025' or 'ours'.
        p: The parameters.
        v: The factor v_mu of Score.
        repetitions: Runs per timing; the median is kept.

    Returns:
        Milliseconds with real headers and by formula, the winner and the branch taken.
    """
    headers = [encode(chain, Links(chain, construction, p.k), b.height) for b in proof]
    other_links = Links(other_chain, construction, p.k)
    other_headers = [encode(other_chain, other_links, b.height) for b in other]
    compare = (lambda: compare_ccs(proof, other, p)) if construction == 'ccs2025' else \
        (lambda: compare_ours(proof, other, p, v))

    def real() -> tuple:
        check(proof, headers, construction, p)
        check(other, other_headers, construction, p)
        return compare()

    def model() -> tuple:
        check_model(proof, construction, p)
        check_model(other, construction, p)
        return compare()

    real_s, (winner, branch) = timed(real, repetitions)
    model_s, _ = timed(model, repetitions)
    row = {'ms_headers': 1e3 * real_s, 'ms_model': 1e3 * model_s, 'winner': winner, 'branch': branch,
           'blocks': [len(proof), len(other)]}
    if construction == 'ours':
        row['reveal_coverage'] = reveal_coverage(proof, headers, p)
    return row


def replay(headers: list[dict], construction: str, p: Params, v: float = 33.0, stop: int | None = None,
           size_every: int = EPOCH, verifier_every: int = 8 * EPOCH, verifier_from: int = 16 * EPOCH,
           verifier: bool = True, log: Callable[[str], None] = print) -> tuple[dict, dict[str, np.ndarray]]:
    """Grows a proof over the chain block after block, as a prover that never held the chain.

    Each update is timed as a prover does it: hash the new header; under ours, open the commitment of the block k
    deep, now revealed, and compute its level; then Compress. Headers are built from the chain outside the timer.

    Args:
        headers: The exported headers.
        construction: 'ccs2025' or 'ours'.
        p: The parameters.
        v: The factor v_mu of Score.
        stop: Height to stop before, the whole chain if None.
        size_every: Blocks between two size samples.
        verifier_every: Blocks between two verifier samples.
        verifier_from: Height of the first verifier sample; the tip is always sampled.
        verifier: Whether to time the verifier.
        log: Where to print progress.

    Returns:
        The samples (JSON) and, per block, the update time in microseconds, the proof length and the block level.
    """
    chain = chain_from_headers(headers, construction, stop)
    links = Links(chain, construction, p.k)
    n = len(chain)
    update_us = np.zeros(n, dtype=np.uint32)
    proof_blocks = np.zeros(n, dtype=np.uint32)
    sizes, verifier_rows, proof = [], [], []
    commitments = collections.deque(maxlen=p.k + 1)  # Those of the last k + 1 headers, as the prover holds them.
    for height, block in enumerate(chain):
        data = encode(chain, links, height)
        commitments.append(data[76:108])
        revealed = chain[height - p.k] if construction == 'ours' and height > p.k else None
        start = time.perf_counter_ns()
        sha256d(data)
        if revealed is not None:  # The block k deep is revealed now: open its commitment, compute its level.
            if sha256(revealed.ctr) != commitments[0]:
                raise ValueError(f'block {revealed.height} does not open its commitment')
            committed_level(revealed.ctr, revealed.hash)
        proof = compress(proof + [block], p)
        update_us[height] = (time.perf_counter_ns() - start) // 1000
        proof_blocks[height] = len(proof)
        if height % size_every == 0 and height > p.k + p.chi:
            sizes.append({'height': height, **size_by_part(proof, construction, p)})
        if verifier and ((height >= verifier_from and height % verifier_every == 0) or height == n - 1):
            honest = chain[:height + 1]
            for name, (other_chain, other) in (('tip', tip_fork(honest, proof, p, construction)),
                                               ('deep', deep_fork(honest, height, p, construction))):
                verifier_rows.append({'height': height, 'fork': name,
                                      **time_verifier(honest, proof, other_chain, other, construction, p, v)})
        if height % 100_000 == 0:
            log(f'{construction} K={p.K} k={p.k}: height {height}, {len(proof)} blocks, {update_us[height]} us')
    levels = np.array([min(b.level, GENESIS_LEVEL) for b in chain], dtype=np.uint16)
    samples = {'construction': construction, 'params': vars(p) | {'v': v}, 'height': n - 1,
               'sizes': sizes, 'verifier': verifier_rows}
    return samples, {'update_us': update_us, 'proof_blocks': proof_blocks, 'level': levels}


def build_time(headers: list[dict], construction: str, p: Params, heights: list[int], repetitions: int = 5) -> list:
    """Times a prover that builds a proof from the headers alone, at several heights.

    The levels step reads each header (hash and target) and computes its level; under ours it also opens each
    revealed commitment, two hashes per block. The nonces, which Bitcoin does not carry, are derived outside the timer.

    Args:
        headers: The exported headers.
        construction: 'ccs2025' or 'ours'.
        p: The parameters.
        heights: Heights at which to build.
        repetitions: Runs per timing.

    Returns:
        One row per height: seconds for levels, for Compress and in total, and the proof length.
    """
    nonces = [simulated_nonce(int(h['hash'], 16)) for h in headers] if construction == 'ours' else None
    commitments = [sha256(c) for c in nonces] if nonces else None

    def levels(height: int) -> list[Block]:
        chain = []
        for i, h in enumerate(headers[:height + 1]):
            block_hash, target = int(h['hash'], 16), bits_to_target(h['bits'])
            if construction == 'ccs2025':
                chain.append(Block(i, block_hash, target, h['time'], ccs_level(block_hash, target)))
            else:
                ctr = nonces[i]
                if sha256(ctr) != commitments[i]:
                    raise ValueError(f'block {i} does not open its commitment')
                chain.append(Block(i, block_hash, target, h['time'], committed_level(ctr, block_hash), ctr))
        chain[0].level, chain[0].ctr = GENESIS_LEVEL, None
        return chain

    rows = []
    for height in heights:
        levels_s, chain = timed(lambda: levels(height), repetitions)
        compress_s, proof = timed(lambda: compress(chain, p), repetitions)
        rows.append({'construction': construction, 'height': height, 'K': p.K, 'k': p.k, 'levels_s': levels_s,
                     'compress_s': compress_s, 'total_s': levels_s + compress_s, 'proof_blocks': len(proof)})
    return rows


def sections(headers: list[dict], construction: str, Ks: list[int], k: int, heights: list[int],
             block_sizes: np.ndarray | None = None) -> list:
    """Blocks and bytes of D, X and Omega at several heights, for several K.

    Args:
        headers: The exported headers.
        construction: 'ccs2025' or 'ours'.
        Ks: The values of K.
        k: The common prefix parameter.
        heights: The heights.
        block_sizes: The size of every block, for Omega's full blocks.

    Returns:
        One row per height and K.
    """
    chain = chain_from_headers(headers, construction)
    rows = []
    for height in heights:
        for K in Ks:
            p = Params(K, k)
            proof = compress(chain[:height + 1], p)
            rows.append({'construction': construction, 'height': height, 'K': K, 'k': k,
                         **size_by_part(proof, construction, p, block_sizes)})
    return rows


def adversary_share(epsilon: float, theta_f: float) -> float:
    """The adversarial share of the hashing power that Relation relationdelta tolerates.

    Args:
        epsilon: The concentration parameter.
        theta_f: The product theta * f.

    Returns:
        t / n for the smallest delta with (1 - theta f)((1 - eps)/(1 + eps))^2 > 1 - delta.
    """
    ratio = (1 - theta_f) * ((1 - epsilon) / (1 + epsilon)) ** 2
    return ratio / (1 + ratio)


def k_star_bound(v: float, epsilon: float, security_bits: int = 80, ln_queries_per_k: float = 59.7) -> tuple[float, float]:
    """The smallest K* for which the bound of Lemma lem:adversarial_score is below 2^-lambda, and the best rho.

    The bound is (floor(log_rho(#J/K*)) + 1)(exp(-(2-rho)^2 K*/(12 rho)) + exp(-eps^2 K*/(8 v (rho + eps/3)))); each
    term is brought below 2^-lambda / (2N), N the number of slices.

    Args:
        v: The cap factor v_mu.
        epsilon: The concentration parameter.
        security_bits: lambda.
        ln_queries_per_k: ln(#J / K*): #J grows with K*; 59.7 for 1e21 hashes per second, half of them adversarial,
            over 2^8 * 208 blocks.

    Returns:
        K* and rho.
    """
    best = (math.inf, 0.0)
    for i in range(1, 1000):
        rho = 1 + i / 1000
        slices = math.floor(ln_queries_per_k / math.log(rho)) + 1
        exponent = security_bits * math.log(2) + math.log(2 * slices)
        best = min(best, (max(12 * rho / (2 - rho) ** 2, 8 * v * (rho + epsilon / 3) / epsilon ** 2) * exponent, rho))
    return best


def k_star(headers: list[dict], K: int = 208, levels: tuple[int, ...] = (0, 2, 4, 6, 8, 10, 11), since: int = 1577836800,
           f: float = 0.03, theta_f_paper: float = 1.995 * 0.03) -> dict:
    """What Bitcoin asks of v_mu and K*: the worst spread of difficulties over the window of K* mu-blocks.

    Args:
        headers: The exported headers.
        K: The K* whose window 2^mu K* is measured.
        levels: The levels mu.
        since: Unix time from which the recent period starts (2020-01-01 by default).
        f: Honest success probability per round.
        theta_f_paper: theta f of the papers, for the adversarial share.

    Returns:
        eta and theta measured, and per level the spread, v_mu by formula, and the K* the bound asks for.
    """
    starts = range(0, len(headers), EPOCH)
    epochs = [(1 << 256) // (bits_to_target(headers[i]['bits']) + 1) for i in starts]
    times = [headers[i]['time'] for i in starts]
    rates = [EPOCH * BLOCK_SECONDS / (b - a) for a, b in zip(times, times[1:])]
    first = next(i for i, t in enumerate(times) if t >= since)

    def spread(work: list[int], window: int) -> float:
        touched = min(len(work), (window - 2) // EPOCH + 2 if window > 1 else 1)
        return max(max(work[i:i + touched]) / min(work[i:i + touched]) for i in range(len(work) - touched + 1))

    eta, theta = min(rates[first:]), max(rates[first:])
    slack = theta / (eta * (1 - theta * f))
    out = {'K': K, 'since': since, 'eta': eta, 'theta': theta, 'eta_all': min(rates[1:]), 'theta_all': max(rates[1:]),
           'levels': [], 'epsilon': []}
    for mu in levels:
        recent = spread(epochs[first:], 2 ** mu * K)
        out['levels'].append({'mu': mu, 'window_blocks': 2 ** mu * K, 'spread_all': spread(epochs, 2 ** mu * K),
                              'spread_recent': recent, 'v_formula': recent * slack,
                              'k_star': k_star_bound(recent, 0.5)[0], 'k_star_formula': k_star_bound(recent * slack, 0.5)[0]})
    v0 = out['levels'][0]['spread_recent']
    for epsilon in (0.5, 0.2, 0.1, 0.05, 0.01):
        out['epsilon'].append({'epsilon': epsilon, 'adversary_share': adversary_share(epsilon, theta_f_paper),
                               'k_star': k_star_bound(v0, epsilon)[0]})
    out['k_star_floor'] = k_star_bound(0, 1)[0]
    out['adversary_share_limit'] = adversary_share(0, theta_f_paper)
    return out


def attack(headers: list[dict], K: int, k: int, chi: int = 2 * EPOCH) -> dict:
    """When the proof level of Bitcoin rose, and the zero-difficulty attack's success probability at each level.

    The attack against a proof of level mu succeeds with probability at most (1 - 2^-mu)^(chi + k): no honest block of
    level mu among the chi + k blocks after b* (Lemma PropprobabilityOfSuccessOfTailStep, p_A taken as 1).

    Args:
        headers: The exported headers.
        K: The security parameter.
        k: The common prefix parameter.
        chi: The length of X.

    Returns:
        The height and time of each rise of the proof level, the height expected at 2K * 2^mu blocks, and p per level.
    """
    chain = chain_from_headers(headers, 'ccs2025')
    levels = np.array([min(b.level, 64) for b in chain])
    rises = []
    for mu in range(1, int(levels[1:].max()) + 1):
        height = int(np.searchsorted(np.cumsum(levels >= mu), 2 * K))
        if height < len(levels):
            rises.append({'level': mu, 'height': height, 'time': chain[height].time})
    n = chi + k
    top = len(rises)
    return {'K': K, 'k': k, 'n': n, 'last_height': len(chain) - 1, 'last_time': chain[-1].time,
            'genesis_time': chain[0].time, 'rises': rises,
            'expected': [{'level': mu, 'height': 2 * K * 2 ** mu} for mu in range(1, top + 2)],
            'p': {mu: (1 - 2.0 ** -mu) ** n if mu else 0.0 for mu in range(top + 3)},
            'proof_level_now': proof_level(chain, K)}
