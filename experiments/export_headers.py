"""Exports the headers of a synced Bitcoin Core node, checked against an earlier export.

    python -m experiments.export_headers --datadir ~/.bitcoin --reference headers/headers.json --out-dir headers

Writes headers/headers-up-to-<height>.json, never over an existing file; the last blocks are left out, since they can
still be reorganized. See vmls.node for credentials.
"""

import argparse
import sys

from vmls.chain import load_headers
from vmls.node import Node, export_headers, extends, save_headers


def main() -> None:
    """Exports, checks and writes the headers."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--datadir', default=None, help='Data directory of the node, for its cookie.')
    parser.add_argument('--url', default='http://127.0.0.1:8332', help='URL of the node.')
    parser.add_argument('--reference', default=None, help='Earlier export the new one must extend.')
    parser.add_argument('--margin', type=int, default=6, help='Blocks to leave out below the tip.')
    parser.add_argument('--out-dir', default='headers', help='Directory of the output file.')
    args = parser.parse_args()

    headers = export_headers(Node(args.url, args.datadir), args.margin)
    if args.reference and not extends(headers, load_headers(args.reference)):
        sys.exit(f'The export does not extend {args.reference}.')
    print(f'{len(headers)} headers in {save_headers(headers, args.out_dir)}')


if __name__ == '__main__':
    main()
