###############################################################################
# Imports

import subprocess
import json
import requests

from block import Block # Importing Block class from block module
import config # Configuration file with user credentials and constants



###############################################################################
# Constants

server_url = f'http://{config.user}:{config.passphrase}@localhost:8332' # Server URL for Bitcoin RPC calls
LOAD_FROM_HEADERS_FILE = False # Flag indicating whether to load headers from a file



###############################################################################
# Main functions

def load_headers(break_at):
    """
    Loads headers from the Bitcoin blockchain or a file.

    Args:
        break_at (int): The block height to break loading at.

    Returns:
        int: The number of headers loaded.
    """
    print('Loading headers...')
    global headers
    if not LOAD_FROM_HEADERS_FILE:
        headers_number = break_at if break_at else cli_json(['-rpcuser=' + config.user, '-rpcpassword=' + config.passphrase, 'getblockchaininfo'])['headers']
        header_hashes = pull('getblockhash', list(range(headers_number)), 2)
        headers = pull('getblockheader', header_hashes, 4)
    else:
        with open(config.HEADERS_FILE_PATH) as f:
            headers = json.load(f)
        headers_number = break_at if break_at else len(headers)
    print('Headers were loaded!')
    return headers_number

def get_block_by_height(height):
    """
    Retrieves a block by its height.

    Args:
        height (int): The height of the block to retrieve.

    Returns:
        Block: The block object.
    """
    block_header = headers[height]
    block_hash = int(block_header['hash'], 16)
    target = bits_to_target(int(block_header['bits'], 16))
    timestamp = int(block_header['time'])
    block = Block(height, target, block_hash, timestamp)
    return block



###############################################################################
# Helper functions

def pull(command, params, slices):
    """
    Makes RPC calls in chunks and aggregates results.

    Args:
        command (str): The RPC command to execute.
        params (list): The parameters to pass to the command.
        slices (int): The number of slices to split the parameters into.

    Returns:
        list: A list containing the aggregated results.
    """
    params_chunks = split_list(params, slices)
    pull_results = []
    for params in params_chunks:
        payload = [{'method': command, 'params': [param]} for param in params]
        responses = requests.post(server_url, json=payload)
        data = responses.json()
        results = [response['result'] for response in data]
        pull_results += results
    return pull_results

def bits_to_target(bits):
    """
    Converts bits to target.

    Args:
        bits (int): The bits value to convert.

    Returns:
        int: The target value.
    """
    bits_n = (bits >> 24) & 0xff
    bits_base = bits & 0xffffff
    target = bits_base << (8 * (bits_n - 3))
    return target

def cli(arguments):
    """
    Executes bitcoin-cli commands and returns the output.

    Args:
        arguments (list): The list of command-line arguments.

    Returns:
        str: The output of the command.
    """
    return subprocess.check_output(['bitcoin-cli'] + arguments).decode('utf-8')[:-1]

def cli_json(arguments):
    """
    Executes bitcoin-cli commands and returns the output as a JSON object.

    Args:
        arguments (list): The list of command-line arguments.

    Returns:
        dict: The output of the command parsed as a JSON object.
    """
    return json.loads(cli(arguments))

def split_list(alist, wanted_parts):
    """
    Splits a list into equal-sized chunks.

    Args:
        alist (list): The list to split.
        wanted_parts (int): The number of desired parts.

    Returns:
        list: A list of sublists.
    """
    length = len(alist)
    return [alist[i*length // wanted_parts: (i+1)*length // wanted_parts] for i in range(wanted_parts)]