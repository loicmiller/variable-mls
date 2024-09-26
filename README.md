# Mining in Logarihtmic Space with Variable Difficulty

This project implements a blockchain compression scheme that works in a variable difficulty setting.
It interacts with the Bitcoin blockchain to generate a Non-Interactive Proof of Proof-of-Work by identifying and retaining only the relevant parts of the chain.
The project uses the `bitcoin-cli` command to retrieve blockchain headers and processes them for compression.

## Features

- **Blockchain Dissolve Algorithm**: The project uses a custom scheme to compress the blockchain while maintaining security guarantees.
- **Bitcoin Blockchain Interaction**: Retrieves block headers directly from the Bitcoin network via RPC calls.
- **Proof Comparison**: Provides functions to compare blockchain proofs and select the most valid one.
- **Argument Parsing**: Customizable runtime options for verbosity, data dumping, and step-wise execution.
- **JSON Data Export**: Compressed blockchain data and execution results are exported as JSON for further analysis.

## Requirements

- Python 3.x
- Modules:
  - `argparse` (for command-line argument parsing)
  - `json`, `requests`, `subprocess`, and other standard Python modules
- (optional) Bitcoin Core with RPC enabled (`bitcoin-cli`)

## Setup

1. Clone this repository and install any necessary Python dependencies.
2. Install Bitcoin Core and configure it with RPC access by modifying your `bitcoin.conf` file (use the provided `rpcauth.py`).
3. Configure your RPC credentials in the `config.py` file:
   ```python
   user = 'your_rpc_username'
   passphrase = 'your_rpc_password'
   ```

By default, `mls.py` will fetch block header data from a running `bitcoind` client, but headers have already been extracted in `headers/headers.zip` for your convenience, so steps 2 and 3 are optional.

## How to Use

### Command-Line Arguments

You can run the project with various options.

```bash
usage: mls.py [-h] [--version] [-v] [-k K_PARAMETER] [-m M_PARAMETER] [-q] [-d] [--load-from-headers]
              [--headers HEADERS_FILE_PATH] [--step] [-s STEP_SIZE] [-b HEIGHT]

Variable MLS on Bitcoin implementation

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  -v, --verbose         Increase output verbosity. (default: 0)
  -k K_PARAMETER, --unstable-part-length K_PARAMETER
                        Length of the unstable part (common prefix parameter, 'k'). (default: 1)
  -m M_PARAMETER, --security-parameter M_PARAMETER
                        Value for the security parameter ('m'). (default: 2)
  -q, --quiet           Suppress non-essential output. (default: False)
  -d, --dump-data       Dump execution data to the data/ folder. (default: False)
  --load-from-headers   Load data from headers. (default: False)
  --headers HEADERS_FILE_PATH
                        Path to the headers file. If --load-from-headers is set and this is not
                        provided, default path from config will be used. (default: headers/headers.json)
  --step                Stop at each step, awaiting user input. (default: False)
  -s STEP_SIZE, --print-step STEP_SIZE
                        Size of steps for printing output to command line. (default: 1)
  -b HEIGHT, --break-at HEIGHT
                        Stop execution at specified block height. (default: None)
```

By default, `mls.py` will fetch block header data from a running `bitcoind` client, but headers have already been extracted in `headers/headers.zip` for your convenience.
Simply extract the zip file in the same folder, and use the `--load-from-headers` option.
You can generate a headers file yourself from a running `bitcoind` client, and using the `export_all_headers.py` file.

### Example Usage

```bash
python3 src/mls.py --load-from-headers -s 100 -b 860000 -d -k 2016 -m 208
```

### Data Export

The script can export compressed blockchain data to JSON files in the `data/` directory with a filename based on the execution time and parameters used.

### Analysis

We analyze the obtained data from the export with IPython notebooks in the `analysis/` directory.
Specifically, the `analysis/plots.ipynb` file contains code to generate some of the figures of our paper.
For your convenience, a prepared data file in the `data/` directory has already been generated with the example command above.

## License

This project is licensed under the MIT License. See the LICENSE file for more details.

