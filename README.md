# Mining in Logarithmic Space with Variable Difficulty

Code and data of NIPoPoWs (Non-Interactive Proofs of Proof-of-Work) whose blocks are mined at variable difficulty,
measured on the real Bitcoin header chain.

A NIPoPoW keeps a logarithmic number of blocks of a proof-of-work chain, sampled by level, so that a light client can
compare two chains without downloading them. This repository implements the prover and the verifiers, replays them
over the whole history of Bitcoin, and measures what they cost: proof size, prover and verifier time, and the
hashrate fluctuation the security proofs assume.

## Papers

- **CCS 2025.** Loïc Miller, Dorian Pacaud, Nathanaël Derousseaux-Lebert, Emmanuelle Anceaume and Romaric Ludinard.
  *Mining in Logarithmic Space with Variable Difficulty.* ACM CCS 2025, DOI
  [10.1145/3719027.3744874](https://doi.org/10.1145/3719027.3744874).
  The code and data of the paper are tagged [`ccs-2025`](../../tree/ccs-2025); the published figures are in
  [`paper-figures/ccs-2025/`](paper-figures/ccs-2025). The current code reproduces them (see below).
- **Blind mining.** A variant where the level of a block stays hidden until the block is k blocks deep, against
  targeted block suppression, with a capped Score against difficulty manipulation. Work in progress.

## Install

Python 3.11 or later.

```bash
python3 -m venv ~/.venvs/vmls
~/.venvs/vmls/bin/pip install -e '.[dev]'
~/.venvs/vmls/bin/python -m pytest        # fast tests, on synthetic chains
```

## Layout

| Path | Content |
|---|---|
| `vmls/` | The library: `chain` (headers, levels), `nipopow` (prover, verifiers), `synthetic`, `sizes` (byte model), `cost` (hashing work), `gamma` and `gamma_bound` (hashrate fluctuation), `node` (Bitcoin Core RPC), `style` (figures) |
| `experiments/` | One command per measurement; each writes JSON or NPZ files to `results/` |
| `figures/` | One script per set of figures, reading those results and writing PDFs to `out/` |
| `tests/` | Fast tests on synthetic chains; regressions on the real chain with `--runslow` |
| `headers/headers.zip` | The 865,043 Bitcoin headers of the CCS 2025 paper (up to October 11, 2024) |
| `paper-figures/` | The figures as published |

`results/`, `out/` and `data/` are not tracked.

## Reproduce the CCS 2025 figures

```bash
python -m experiments.proof_over_chain --mode ccs --headers headers/headers.zip -K 208 --stop 865043 --no-verifier
python -m figures.ccs2025 --headers headers/headers.zip --run results/<stamp>-proof-over-chain-ccs-up-to-865042-K-208-chi-4032-k-323
```

The replay takes about 15 minutes on one core. The proof ends with 7,075 blocks at level 11, as in the paper.
Latencies depend on the machine.

## Other measurements

```bash
python -m experiments.proof_over_chain --mode blind --headers HEADERS -K 208   # blind mining, with verifier timings
python -m experiments.gamma estimate HEADERS --out results/gamma               # gamma as the original notebook estimates it
python -m experiments.gamma bound HEADERS --out results/gamma-bound            # gamma(s, w) with exact intervals
python -m experiments.gamma simulate --out results/gamma-simulation.json      # estimators against known hashrate paths
python -m experiments.attack_probability --headers HEADERS --out results/attack.json
python -m experiments.show_proof --random 60 --seed 1 -K 2 -k 2 -chi 9 --out out/proof.pdf
```

## Bitcoin data

`headers/headers.zip` holds the headers used by the CCS 2025 paper. To extend them, run a synced Bitcoin Core node
and export its headers; the export checks that the chain is contiguous down to the genesis block and that it extends
the previous export:

```bash
python -m experiments.export_headers --datadir ~/.bitcoin --reference headers/headers.zip --out-dir headers
```

The size of the UTXO set at every height, which a NIPoPoW must carry, comes from a full replay of the blocks
(`experiments/utxo_snapshot.py`, days and some 80 GB).

RPC credentials never go in the repository: the client reads the node's cookie, then `~/.config/vmls/rpc.env`
(`VMLS_RPC_USER=…` and `VMLS_RPC_PASSWORD=…`, readable by you only), then the environment variables of the same names.

## License

MIT. See [LICENSE](LICENSE).
