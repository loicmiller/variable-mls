"""Reading headers and blocks from a Bitcoin Core node over JSON-RPC.

Credentials never live in this repository. In order, the client uses the cookie bitcoind writes in its data
directory, then a file ~/.config/vmls/rpc.env, then the environment variables VMLS_RPC_USER and VMLS_RPC_PASSWORD:

    VMLS_RPC_USER=...
    VMLS_RPC_PASSWORD=...

Keep that file readable by you only (chmod 600), and the RPC port bound to 127.0.0.1.
"""

import json
import os
from pathlib import Path

import requests

GENESIS_HASH = '000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f'
CONFIG_FILE = Path.home() / '.config' / 'vmls' / 'rpc.env'
BATCH = 5_000  # Calls per request.


def credentials(datadir: str | Path | None = None, config_file: Path = CONFIG_FILE,
                environ: dict | None = None) -> tuple[str, str]:
    """Finds the RPC credentials: the node's cookie, then the config file, then the environment.

    Args:
        datadir: Data directory of the node, where bitcoind writes its cookie while it runs.
        config_file: File of VMLS_RPC_USER and VMLS_RPC_PASSWORD lines.
        environ: The environment, os.environ if None.

    Returns:
        The user and the password.

    Raises:
        RuntimeError: If no credentials are found.
    """
    if datadir is not None:
        cookie = Path(datadir) / '.cookie'
        if cookie.exists():
            user, password = cookie.read_text().strip().split(':', 1)
            return user, password
    values = {}
    if config_file.exists():
        for line in config_file.read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key, value = line.split('=', 1)
                values[key.strip()] = value.strip()
    environ = os.environ if environ is None else environ
    user = values.get('VMLS_RPC_USER') or environ.get('VMLS_RPC_USER')
    password = values.get('VMLS_RPC_PASSWORD') or environ.get('VMLS_RPC_PASSWORD')
    if not user or not password:
        raise RuntimeError(f'No RPC credentials: start the node with its data directory, or fill {config_file}.')
    return user, password


class Node:
    """A JSON-RPC client of a Bitcoin Core node.

    Args:
        url: URL of the node.
        datadir: Data directory of the node, for its cookie.
        timeout: Seconds before a request fails.
    """

    def __init__(self, url: str = 'http://127.0.0.1:8332', datadir: str | Path | None = None, timeout: float = 600):
        """Opens a session authenticated with credentials()."""
        self.url = url
        self.timeout = timeout
        self.session = requests.Session()
        self.session.auth = credentials(datadir)

    def call(self, method: str, *params) -> object:
        """One call.

        Args:
            method: The RPC method.
            *params: Its parameters.

        Returns:
            The result.

        Raises:
            RuntimeError: If the node returns an error.
        """
        return self.batch(method, [list(params)])[0]

    def batch(self, method: str, params_list: list[list], parse_float=float) -> list:
        """Many calls of one method, by batches.

        Args:
            method: The RPC method.
            params_list: The parameters of each call.
            parse_float: Type of the decimal numbers of the answers; decimal.Decimal keeps amounts exact.

        Returns:
            The result of each call, in order.

        Raises:
            RuntimeError: If a call fails.
        """
        results = []
        for start in range(0, len(params_list), BATCH):
            chunk = params_list[start:start + BATCH]
            payload = [{'jsonrpc': '1.0', 'id': i, 'method': method, 'params': params} for i, params in enumerate(chunk)]
            response = self.session.post(self.url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            for answer in sorted(response.json(parse_float=parse_float), key=lambda a: a['id']):
                if answer['error'] is not None:
                    raise RuntimeError(answer['error'])
                results.append(answer['result'])
        return results


def export_headers(node: Node, margin: int = 6) -> list[dict]:
    """Headers of the active chain of a synced node, checked down to the genesis block.

    Args:
        node: The node.
        margin: Blocks left out below the tip, since they can still be reorganized.

    Returns:
        One {'hash', 'bits', 'time'} per height.

    Raises:
        RuntimeError: If the node is still syncing.
        ValueError: If the chain is not contiguous down to the genesis block.
    """
    info = node.call('getblockchaininfo')
    if info['initialblockdownload'] or info['blocks'] != info['headers']:
        raise RuntimeError('The node is not synced.')
    n = info['blocks'] - margin + 1
    hashes = node.batch('getblockhash', [[height] for height in range(n)])
    headers = node.batch('getblockheader', [[block_hash] for block_hash in hashes])
    if headers[0]['hash'] != GENESIS_HASH:
        raise ValueError('The first header is not the genesis block.')
    for height in range(1, n):
        if headers[height]['height'] != height or headers[height]['previousblockhash'] != headers[height - 1]['hash']:
            raise ValueError(f'The chain breaks at height {height}.')
    return [{'hash': h['hash'], 'bits': h['bits'], 'time': h['time']} for h in headers]


def extends(headers: list[dict], reference: list[dict]) -> bool:
    """Whether headers extend an earlier export, field by field.

    Args:
        headers: The new export.
        reference: The earlier one.

    Returns:
        True if the new export is at least as long and starts with the earlier one.
    """
    return len(headers) >= len(reference) and all(a == b for a, b in zip(reference, headers))


def save_headers(headers: list[dict], directory: str | Path) -> Path:
    """Writes headers to headers-up-to-<height>.json, never over an existing file.

    Args:
        headers: The headers.
        directory: Where to write.

    Returns:
        The path written.
    """
    path = Path(directory) / f'headers-up-to-{len(headers) - 1}.json'
    with open(path, 'x') as f:
        json.dump(headers, f, separators=(',', ':'))
    return path
