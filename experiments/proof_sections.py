"""Size of each part of a NIPoPoW against the height: the abridged subchain D, the uncompressed subchain X and the
unstable subchain Omega, in blocks and in bytes, for CCS 2025 and for blind mining, headers as the papers write them.

The proof at a height is the proof of the chain up to that height. Omega counts its headers only; its full blocks
are measured on the node (results/omega-sizes-<height>.json).

    python -m experiments.proof_sections --headers HEADERS --out results/proof-sections.json
"""

import argparse
import json

from vmls.chain import blocks_from_headers, load_headers
from vmls.nipopow import Params, compress
from vmls.sizes import proof_size

K_VALUES = (104, 208, 416)
SCHEME = {False: 'ccs', True: 'draft'}  # Header layout of each construction, without the Merkle variants.


def main() -> None:
    """Measures the parts of the proof at every height and writes them."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--headers', required=True, help='Exported headers.')
    parser.add_argument('--step', type=int, default=25_000, help='Blocks between two heights.')
    parser.add_argument('-k', type=int, default=323, help='Common prefix parameter.')
    parser.add_argument('-chi', type=int, default=4032, help='Length of the uncompressed subchain.')
    parser.add_argument('--out', required=True, help='JSON file.')
    args = parser.parse_args()

    headers = load_headers(args.headers)
    heights = list(range(args.step, len(headers), args.step)) + [len(headers) - 1]
    rows = []
    for blind, scheme in SCHEME.items():
        chain = blocks_from_headers(headers, blind=blind)
        for height in heights:
            for K in K_VALUES:
                p = Params(K, args.k, args.chi)
                proof = [block.height for block in compress(chain[:height + 1], p)]
                parts = {'D': proof[:-p.k - p.chi], 'X': proof[-p.k - p.chi:-p.k], 'Omega': proof[-p.k:]}
                rows.append({'scheme': scheme, 'height': height, 'K': K,
                             'blocks': {name: len(part) for name, part in parts.items()},
                             'bytes': {name: proof_size(scheme, part if name == 'D' else [],
                                                        part if name == 'X' else [],
                                                        part if name == 'Omega' else [], p.k)
                                       for name, part in parts.items()}})
        print(f'{scheme} done', flush=True)
    with open(args.out, 'w') as f:
        json.dump({'headers': str(args.headers), 'n_headers': len(headers), 'k': args.k, 'chi': args.chi,
                   'rows': rows}, f, indent=1)
    print(f'{args.out} written')


if __name__ == '__main__':
    main()
