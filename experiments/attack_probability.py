"""Success probability of the zero-difficulty attack over the life of Bitcoin, from the proof level transitions.

The attack against a proof of level mu succeeds with probability at most p(mu) = (1 - 2^-mu)^(2m + k): Theorem 1 of
the draft at Delta = 0, the hyperactivity factor 1 - e^-Omega(K) taken as 1, as in Table 1. The proof reaches level l
once 2K blocks of level l exist; transitions are read from the headers, then extrapolated at 10 minutes per block.

    python -m experiments.attack_probability --headers headers/headers.json -K 104 --out results/attack.json
"""

import argparse
import json

import numpy as np

from vmls.chain import blocks_from_headers, load_headers
from vmls.nipopow import level_changes

BLOCK_SECONDS = 600
TABLE_1 = {8: 0.000000039576, 9: 0.000200604207, 10: 0.014192981938, 11: 0.119196227986, 12: 0.345292901557}


def p_attack(mu: float | np.ndarray, n: int) -> np.ndarray:
    """Largest success probability of the attack against a proof of level mu, (1 - 2^-mu)^n.

    Args:
        mu: The proof level, scalar or array.
        n: The exponent 2m + k, that is chi + k.

    Returns:
        The probability; 0 at level 0, and 0.0 where it underflows (mu <= 5).
    """
    mu = np.asarray(mu, dtype=float)
    with np.errstate(divide='ignore'):
        return np.exp(n * np.log1p(-np.power(2.0, -mu)))


def main() -> None:
    """Writes the transitions, their expected heights and dates, and p at each level."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--headers', required=True, help='Exported headers.')
    parser.add_argument('-K', type=int, default=104, help='Security parameter.')
    parser.add_argument('-k', type=int, default=323, help='Common prefix parameter.')
    parser.add_argument('-chi', type=int, default=4032, help='Length of the uncompressed subchain.')
    parser.add_argument('--out', required=True, help='JSON file.')
    args = parser.parse_args()

    n = args.chi + args.k
    for mu, reference in TABLE_1.items():
        assert abs(float(p_attack(mu, 4355)) - reference) < 1e-9, mu
    chain = blocks_from_headers(load_headers(args.headers))
    times = [block.timestamp for block in chain]
    changes = level_changes(np.array([block.level for block in chain]), args.K)
    last = len(changes)
    result = {
        'K': args.K, 'n': n, 'last_height': len(chain) - 1, 'last_time': times[-1], 'genesis_time': times[0],
        'transitions': [{'level': mu, 'height': h, 'time': times[h]} for mu, h in enumerate(changes, start=1)],
        'expected': [{'level': mu, 'height': 2 * args.K * 2 ** mu, 'time': times[0] + BLOCK_SECONDS * 2 * args.K * 2 ** mu}
                     for mu in range(1, last + 2)],
        'p': {mu: float(p_attack(mu, n)) for mu in range(0, last + 3)},
    }
    with open(args.out, 'w') as f:
        json.dump(result, f, indent=1)
    print(f'{args.out} written: level {last} since height {changes[-1]}, p = {result["p"][last]:.3f}')


if __name__ == '__main__':
    main()
