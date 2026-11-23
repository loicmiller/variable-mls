"""Size of each part of a NIPoPoW against the height: the abridged subchain D, the uncompressed subchain X and the
unstable subchain Omega, in blocks and in bytes, for CCS 2025 and for blind mining, headers as the papers write them.

The proof at a height is the proof of the chain up to that height. 'bytes' counts headers only. With --block-sizes
(experiments.block_sizes), 'bytes_paper' counts what each paper puts in the proof: the headers of D, the full blocks of
X and Omega for CCS 2025 ("the headers of the blocks of D, and the full blocks of X, Omega"), the headers
of D and X and the full blocks of Omega for blind mining. A full block is its Bitcoin size plus what the scheme adds to
its header; the UTXO snapshot both papers attach is left out.

    python -m experiments.proof_sections --headers HEADERS --block-sizes SIZES --out results/proof-sections.json
"""

import argparse
import json

import numpy as np

from vmls.chain import blocks_from_headers, load_headers
from vmls.nipopow import Params, compress
from vmls.sizes import BITCOIN_HEADER, proof_size

K_VALUES = (104, 208, 416)
SCHEME = {False: 'ccs', True: 'draft'}  # Header layout of each construction, without the Merkle variants.
FULL_PARTS = {'ccs': ('X', 'Omega'), 'draft': ('Omega',)}  # Parts each paper ships as full blocks.


def main() -> None:
    """Measures the parts of the proof at every height and writes them."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--headers', required=True, help='Exported headers.')
    parser.add_argument('--step', type=int, default=25_000, help='Blocks between two heights.')
    parser.add_argument('-k', type=int, default=323, help='Common prefix parameter.')
    parser.add_argument('-chi', type=int, default=4032, help='Length of the uncompressed subchain.')
    parser.add_argument('--block-sizes', default=None, help='Output of experiments.block_sizes (optional).')
    parser.add_argument('--out', required=True, help='JSON file.')
    args = parser.parse_args()

    headers = load_headers(args.headers)
    sizes = np.load(args.block_sizes) if args.block_sizes else None
    heights = list(range(args.step, len(headers), args.step)) + [len(headers) - 1]
    rows = []
    for blind, scheme in SCHEME.items():
        chain = blocks_from_headers(headers, blind=blind)
        for height in heights:
            for K in K_VALUES:
                p = Params(K, args.k, args.chi)
                proof = [block.height for block in compress(chain[:height + 1], p)]
                parts = {'D': proof[:-p.k - p.chi], 'X': proof[-p.k - p.chi:-p.k], 'Omega': proof[-p.k:]}
                row = {'scheme': scheme, 'height': height, 'K': K,
                       'blocks': {name: len(part) for name, part in parts.items()},
                       'bytes': {name: proof_size(scheme, part if name == 'D' else [], part if name == 'X' else [],
                                                  part if name == 'Omega' else [], p.k)
                                 for name, part in parts.items()}}
                if sizes is not None:
                    row['bytes_paper'] = {name: row['bytes'][name] + (
                        int(sizes[part].sum()) - BITCOIN_HEADER * len(part) if name in FULL_PARTS[scheme] else 0)
                        for name, part in parts.items()}
                rows.append(row)
        print(f'{scheme} done', flush=True)
    with open(args.out, 'w') as f:
        json.dump({'headers': str(args.headers), 'n_headers': len(headers), 'k': args.k, 'chi': args.chi,
                   'rows': rows}, f, indent=1)
    print(f'{args.out} written')


if __name__ == '__main__':
    main()
