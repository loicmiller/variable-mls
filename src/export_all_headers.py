#!/usr/bin/python3

import subprocess
import json
import requests
import config

# https://github.com/bitcoin/bitcoin/blob/dfe2dc1d84436d4eae351612dbf0b92f032389be/share/rpcauth/rpcauth.py
serverURL = f'http://{config.user}:{config.passphrase}@localhost:8332'

def split_list(alist, wanted_parts):
    length = len(alist)
    return [alist[i*length // wanted_parts: (i+1)*length // wanted_parts] for i in range(wanted_parts)]

def pull(command, params, slices):
    paramsChunks = split_list(params, slices)
    pullResults = []
    for params in paramsChunks:
        payload = [{'method': command, 'params': [param]} for param in params]
        responses = requests.post(serverURL, json=payload)
        data = responses.json()
        results = [response['result'] for response in data]
        pullResults += results
    return pullResults

def loadAllHeaders():
    global headers
    print('loading all headers')
    headersNumber = cli_json(['getblockchaininfo'])['headers']
    headerHashes = pull('getblockhash', list(range(headersNumber)), 2)
    headers = pull('getblockheader', headerHashes, 4)
    headers = [{key: header[key] for key in ['hash', 'bits', 'time']} for header in headers]
    print('all headers were loaded')

def cli(arguments):
    return subprocess.check_output(['bitcoin-cli'] + arguments).decode('utf-8')[:-1]

def cli_json(arguments):
    return json.loads(cli(arguments))

loadAllHeaders()

with open('headers.json', 'w') as f:
    json.dump(headers, f, separators=(',', ':'))
