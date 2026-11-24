# Changelog

All notable changes to this project are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

Version 2: the code rewritten as a Python package, with one command per measurement. It reproduces the proofs of
version 1 block for block (K = 104 and 208, regression tests against the dumps of the CCS 2025 code).

### Breaking changes

- The scripts of `src/` and the notebooks of `analysis/` are replaced by the package `vmls/`, the commands of
  `experiments/` and the scripts of `figures/`. Commands become `python -m experiments.<name>`; results go to
  `results/` and figures to `out/`, neither tracked. Version 1 stays available under the tags `v1.0.0` and `ccs-2025`.
- RPC credentials are no longer read from the code: the client uses the node's cookie, then
  `~/.config/vmls/rpc.env`, then the variables `VMLS_RPC_USER` and `VMLS_RPC_PASSWORD`.
- Python 3.12 or later.

### Added

- Blind mining: blind levels from a committed nonce, revealed k blocks deep; `compare_blind` with the capped Score.
- `experiments.proof_over_chain`: the proof grown block by block over the whole chain, with the update time, the size
  in blocks and in bytes, and the verifier's time on forks near the tip and deep in the chain.
- `experiments.build_time`: the time to build a proof from scratch at many heights, step by step.
- `experiments.proof_sections`: the size of each part of a proof (D, X, Ω) against the height; with
  `experiments.block_sizes`, which reads the size of every block from a stopped node's block files, the full blocks
  of Ω.
- `experiments.export_headers`, which checks that an export is contiguous down to the genesis block and extends the
  previous one.
- `experiments.gamma`: the hashrate fluctuation γ as the original notebook estimates it, and γ(s, w) with exact
  confidence intervals; `experiments.attack_probability`; `experiments.show_proof`.
- The byte model of headers and proofs (`vmls.sizes`), with and without a Merkle root over the pointers.
- The published figures of the CCS 2025 paper in `paper-figures/ccs-2025/`, and `figures.ccs2025` to redraw them.
- `figures.blind`: proof size, construction from scratch and update per block, blind mining against CCS 2025.
- Tests on synthetic chains, regressions on the real chain (`--runslow`), a check that no tracked file holds the path
  of a machine, and CI on Linux, Windows and macOS with Python 3.12 and 3.14.
- `rpc.env.example`, the RPC credentials file, and lower bounds for the dependencies (the versions the regressions
  were checked with).

### Fixed

- The verifier follows the published Compare rule (`compare_published`): the code of version 1 counted the blocks
  of X and Ω whatever their level.

### Security

- The history was rewritten on 2026-11-23 to remove an RPC user and password committed in `src/snapshot_size.py`
  (since rotated) and to use the maintainer's noreply address. Clones made before that date hold the old history;
  re-clone rather than merge.

## [1.0.0] - 2025-04-25

The code and data of the CCS 2025 paper *Mining in Logarithmic Space with Variable Difficulty*: the prover and the
verifier replayed over the 865,043 Bitcoin headers up to October 11, 2024, and the notebooks that draw the paper's
figures. Same commit as the tag `ccs-2025`.

[Unreleased]: https://github.com/loicmiller/variable-mls/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/loicmiller/variable-mls/releases/tag/v1.0.0
