###############################################################################
# Imports

import argparse
import json
import os
import sys

import requests



###############################################################################
# Constants

BATCH = 5_000 # RPC calls per request.
KEEP = ('hash', 'bits', 'time')



###############################################################################
# RPC

def rpc_session(datadir):
    """
    Opens a session on the node through its cookie, which only exists while the node runs.

    Args:
    - datadir (str): The data directory of the node.

    Returns:
    - requests.Session: The authenticated session.
    """
    with open(os.path.join(datadir, '.cookie')) as f:
        user, password = f.read().strip().split(':', 1)
    session = requests.Session()
    session.auth = (user, password)
    return session


def call(session, url, method, params_list):
    """
    Makes RPC calls by batches and aggregates their results.

    Args:
    - session (requests.Session): The authenticated session.
    - url (str): The URL of the node.
    - method (str): The RPC command to execute.
    - params_list (list): The parameters of each call.

    Returns:
    - list: The result of each call, in order.

    Raises:
    - RuntimeError: If a call fails.
    """
    results = []
    for start in range(0, len(params_list), BATCH):
        chunk = params_list[start:start + BATCH]
        payload = [{'jsonrpc': '1.0', 'id': i, 'method': method, 'params': params} for i, params in enumerate(chunk)]
        responses = sorted(session.post(url, json=payload, timeout=600).json(), key=lambda response: response['id'])
        for response in responses:
            if response['error'] is not None:
                raise RuntimeError(response['error'])
            results.append(response['result'])
    return results



###############################################################################
# Main

def main():
    """
    Exports the active chain of a synced node, and checks it against an earlier export.

    Args:
    - None

    Returns:
    - None

    Notes:
    - The last blocks are left out, since they can still be reorganized.
    - The output never overwrites an existing file.
    """
    parser = argparse.ArgumentParser(description='Export block headers up to the tip of a synced node.')
    parser.add_argument('--datadir', required=True, help='Data directory of the node.')
    parser.add_argument('--out-dir', default='headers', help='Directory of the output file.')
    parser.add_argument('--reference', default='headers/headers.json', help='Earlier export the new one must extend.')
    parser.add_argument('--margin', type=int, default=6, help='Blocks to leave out below the tip.')
    parser.add_argument('--url', default='http://127.0.0.1:8332', help='URL of the node.')
    args = parser.parse_args()

    session = rpc_session(args.datadir)
    info = call(session, args.url, 'getblockchaininfo', [[]])[0]
    print(f"blocks={info['blocks']} headers={info['headers']} ibd={info['initialblockdownload']}")
    if info['initialblockdownload'] or info['blocks'] != info['headers']:
        sys.exit('The node is not synced.')

    n = info['blocks'] - args.margin + 1
    hashes = call(session, args.url, 'getblockhash', [[height] for height in range(n)])
    headers = call(session, args.url, 'getblockheader', [[block_hash] for block_hash in hashes])

    # The chain is contiguous, down to the genesis block.
    assert headers[0]['hash'] == '000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f'
    for height in range(1, n):
        assert headers[height]['height'] == height and headers[height]['previousblockhash'] == headers[height - 1]['hash'], height
    headers = [{key: header[key] for key in KEEP} for header in headers]

    # The new export extends the earlier one, field by field.
    with open(args.reference) as f:
        reference = json.load(f)
    mismatches = sum(a != b for a, b in zip(reference, headers))
    print(f'{mismatches} mismatches with the {len(reference)} blocks of {args.reference}')
    if mismatches or len(headers) < len(reference):
        sys.exit('The new export does not extend the earlier one.')

    path = os.path.join(args.out_dir, f'headers-up-to-{n - 1}.json')
    with open(path, 'x') as f:
        json.dump(headers, f, separators=(',', ':'))
    print(f'{n} headers in {path}')


if __name__ == '__main__':
    main()
