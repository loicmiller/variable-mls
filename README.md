# Mining in Logarithmic Space with Variable Difficulty

This project implements a blockchain compression scheme that works in a variable difficulty setting.
It interacts with the Bitcoin blockchain to generate a Non-Interactive Proof of Proof-of-Work by identifying and retaining only the relevant parts of the chain.
The project uses the `bitcoin-cli` command to retrieve blockchain headers and processes them for compression.

In addition to real Bitcoin data, the project supports **synthetic and scripted chains**, which are useful for experimentation, visualization, and theoretical analysis.

## Features

- **Blockchain Dissolve Algorithm**: The project uses a custom scheme to compress the blockchain while maintaining security guarantees.
- **Multiple Chain Generation Modes**:
  - Bitcoin blockchain (default). Retrieves block headers directly from the Bitcoin network via RPC calls.
  - Random chains generated from a geometric distribution.
  - Scripted chains with explicitly specified block levels.
- **Proof Comparison**: Provides functions to compare blockchain proofs and select the best one.
- **Argument Parsing**: Customizable runtime options for verbosity, data dumping, and step-wise execution.
- **Visualization Tools**: Visual representations of the full chain, compressed proof, and dissolved structure.
- **JSON Data Export**: Compressed blockchain data and execution results are exported as JSON for further analysis.

## Requirements

- Python 3.x
- Modules:
  - `argparse`
  - `json`
  - `requests`
  - `subprocess`
  - `math`
  - `random`
- (optional) Bitcoin Core with RPC enabled (`bitcoind`, `bitcoin-cli`)

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
usage: mls.py [-h] [--version] [-v] [-k COMMON_PREFIX_PARAMETER] [-chi UNCOMPRESSED_PART_LENGTH]
              [-K SECURITY_PARAMETER] [-q] [-d] [--dump-proof DUMP_PROOF]
              [--chain {bitcoin,random,scripted}] [--p P] [--seed SEED] [--levels LEVELS]
              [--load-from-headers] [--headers HEADERS_FILE_PATH] [--step] [-s STEP_SIZE] [-b HEIGHT]

Variable MLS on Bitcoin implementation

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  -v, --verbose         Increase output verbosity. (default: 0)
  -k COMMON_PREFIX_PARAMETER, --unstable-part-length COMMON_PREFIX_PARAMETER
                        Length of the unstable part (common prefix parameter, 'k'). (default: 323)
  -chi UNCOMPRESSED_PART_LENGTH, --uncompressed-part-length UNCOMPRESSED_PART_LENGTH
                        Length of the uncompressed part ('χ'). (default: 4032)
  -K SECURITY_PARAMETER, --security-parameter SECURITY_PARAMETER
                        Value for the security parameter ('K'). (default: 208)
  -q, --quiet           Suppress non-essential output. (default: False)
  -d, --dump-data       Dump execution data to the data/ folder. (default: False)
  --dump-proof DUMP_PROOF
                        Dump final proof structure to a JSON file. (default: None)
  --chain {bitcoin,random,scripted}
                        Chain source: bitcoin (default), random, or scripted. (default: bitcoin)
  --p P                 Geometric distribution parameter for random chain. (default: 0.5)
  --seed SEED           Seed for random chain generation. (default: None)
  --levels LEVELS       Comma-separated list of block levels (e.g. 0,0,3,0,1,0,5). (default: None)
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

### Chain Generation Modes

#### 1. Bitcoin chain (default)

```bash
python3 src/mls.py --load-from-headers -s 100 -d -k 323 -chi 4032 -K 208
```

If `--load-from-headers` is not set, the script attempts to query a running `bitcoind` instance via RPC.

#### 2. Random (geometric) chain

Generates a synthetic chain where block levels follow a geometric distribution:
$$\Pr[\mu = k] = (1 - p) \cdot p^k$$

Options:
  - `--p` : geometric parameter
  - `--seed` : RNG seed (optional, for reproducibility)

Example:
```
python3 src/mls.py --chain random --p 0.5 --break-at 30 -k=1 -K=2 -chi=0
```

This mode is useful for:
  - expected-case analysis,
  - statistical experiments,
  - rarity and deviation studies.

#### 3. Scripted chain (explicit levels)

Generates a chain with explicitly specified block levels.

Options:
  - `--levels` : comma-separated list of non-negative integers

Example:
```
python3 src/mls.py --chain scripted --levels "9,9,9,9,9,9,9,9,9,9,9,9,9" -k=1 -K=2 -chi=0
```

This mode is particularly useful for:
- constructing adversarial or rare chains,
- debugging,
- generating clean illustrative figures for papers or talks.

### Data Export

The script can export compressed blockchain data to JSON files in the `data/` directory with a filename based on the execution time and parameters used.

### Analysis

We analyze the obtained data from the export with IPython notebooks in the `analysis/` directory.
Specifically, the `analysis/plots.ipynb` file contains code to generate some of the figures of our paper.
For your convenience, a prepared data file in the `data/` directory has already been generated with the example command above.

## License

This project is licensed under the MIT License. See the LICENSE file for more details.