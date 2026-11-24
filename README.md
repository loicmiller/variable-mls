# Mining in Logarithmic Space with Variable Difficulty

Code and data of NIPoPoWs (Non-Interactive Proofs of Proof-of-Work) whose blocks are mined at variable difficulty,
measured on the real Bitcoin header chain.

A NIPoPoW keeps a logarithmic number of blocks of a proof-of-work chain, sampled by level, so that a light client can
compare two chains without downloading them. This repository implements the prover and the verifiers, replays them
over the whole history of Bitcoin, and measures what they cost: proof size, prover and verifier time, and the
hashrate fluctuation the security proofs assume.

Two constructions are implemented: the one of the CCS 2025 paper, and **blind mining**, where the level of a block
stays hidden until the block is k blocks deep (against targeted block suppression), with a capped Score against
difficulty manipulation.

## Papers

- **CCS 2025.** Loïc Miller, Dorian Pacaud, Nathanaël Derousseaux-Lebert, Emmanuelle Anceaume and Romaric Ludinard.
  *Mining in Logarithmic Space with Variable Difficulty.* ACM CCS 2025, DOI
  [10.1145/3719027.3744874](https://doi.org/10.1145/3719027.3744874).
  The code and data of the paper are tagged [`ccs-2025`](../../tree/ccs-2025); the published figures are in
  [`paper-figures/ccs-2025/`](paper-figures/ccs-2025). The current code reproduces them (see below).

## Install

Python 3.12 or later.

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

`results/`, `out/` and `data/` are not tracked. `rpc.env.example` shows the RPC credentials file (see Bitcoin data).

## How it fits together

```
headers (JSON or zip) ── vmls.chain.blocks_from_headers ──> list[Block], each with its level
                                                              │
     prover:  vmls.nipopow.compress, called once per new block (Dissolve, then keep D, X and Omega)
                                                              │
   verifier:  vmls.cost.validate_proof, then vmls.nipopow.compare_published (CCS 2025)
              or compare_blind (blind: level 0, else the Score capped by v, else the online test, not waited for)
                                                              │
   measures:  vmls.sizes (bytes of headers and proofs), vmls.cost (timings), vmls.gamma* (hashrate fluctuation)
                                                              │
experiments/<name>.py ──> results/*.json, *.npz ──> figures/<name>.py ──> out/*.pdf
```

- **Levels.** Under CCS 2025, a block's level is the number of times its hash beats its own target (`level`).
  Under blind mining, it comes from a nonce `ctr` committed in the header and revealed k blocks later
  (`blind_level`). Bitcoin headers have no such nonce: `simulated_nonce` derives one from the block hash, so blind
  levels follow the distribution of a blind-mined chain and runs are reproducible. This is the main assumption of the
  measurements.
- **Parameters** (`vmls.nipopow.Params`): `K` (K* in the papers), a level enters the proof once it holds 2K blocks;
  `k = 323`, the length of the unstable suffix Omega, kept as full blocks; `chi = 4032`, the length of X, kept
  uncompressed for the difficulty checks. D holds the sampled blocks below them.
- **Schemes** (`vmls.sizes.SCHEMES`), the byte models the measurements compare:

  | Scheme | Construction | Header |
  |---|---|---|
  | `ccs` | CCS 2025 | the 80-byte Bitcoin header plus one pointer per level |
  | `draft` | blind mining | the header plus the commitment H(ctr), k pointers and a tuple per level |
  | `ccs-merkle`, `draft-merkle` | the same | pointers and tuples replaced by a Merkle root (a possible optimisation) |

  `experiments.proof_over_chain --mode ccs` measures `ccs` and `ccs-merkle`; `--mode blind`, `draft` and
  `draft-merkle`.
- **Tests.** `tests/` runs every piece on synthetic chains (`vmls.synthetic`); the slow regressions replay the real
  chain and compare proofs, block by block, with those of version 1.

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
python -m experiments.build_time --headers HEADERS --out results/build-time.json   # building a proof from scratch
python -m experiments.block_sizes --datadir ~/.bitcoin --headers HEADERS --out results/block-sizes.npy
python -m experiments.proof_sections --headers HEADERS --block-sizes results/block-sizes.npy --out results/sections.json
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

The size of every block (`experiments.block_sizes`) is read from a stopped node's block files, a few minutes. The
size of the UTXO set at every height, which a NIPoPoW must carry, comes from a full replay of the blocks
(`experiments/utxo_snapshot.py`, days and some 80 GB); at the tip alone, the node gives it directly
(`bitcoin-cli gettxoutsetinfo`).

RPC credentials never go in the repository: the client reads the node's cookie, then `~/.config/vmls/rpc.env`
(`VMLS_RPC_USER=…` and `VMLS_RPC_PASSWORD=…`, readable by you only), then the environment variables of the same names.

## History

- **Version 2** (in progress): the package `vmls`, one command per measurement, tests and CI. See
  [CHANGELOG.md](CHANGELOG.md).
- **Version 1.0.0** (2025-04-25, tags `v1.0.0` and `ccs-2025`): the code and data of the CCS 2025 paper.

## Citing

The code is by Loïc Miller; the construction it implements is the work of all the authors of the CCS 2025 paper.
Cite that paper, and the version of this code you used; [CITATION.cff](CITATION.cff) holds both.

## Security

See [SECURITY.md](SECURITY.md); to contribute, [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT. See [LICENSE](LICENSE).
