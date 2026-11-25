# Changelog

All notable changes to this project are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

Version 2, written anew: one package of nine modules and one command, `vmls`. Its CCS 2025 construction gives, block
for block, what the code of the CCS 2025 paper gave (levels of the 865,043 blocks, proof sizes and levels of its data
at K = 104 and 208, k = 323), and our construction the proofs of the earlier rewrite.

### Breaking changes

- The scripts of `src/` and the notebooks of `analysis/` are gone, as are the `experiments/` and `figures/` scripts
  of the earlier rewrite: every measurement and figure is a subcommand of `vmls` (`vmls --help`). Results go to
  `results/` and figures to `out/`, neither tracked. Version 1 stays available under the tags `v1.0.0` and `ccs-2025`.
- The constructions are named `ccs2025` and `ours` (formerly `ccs` and `draft` or `blind`); figures say
  « Our construction ».
- The common prefix parameter k defaults to 6, Bitcoin's (323 was a numerical application of the backbone analysis).
- Levels under CCS 2025 are computed in exact integers, and work is Bitcoin's chain work (formerly floats, and a
  difficulty rounded to four decimals). On Bitcoin, no level changes.
- RPC credentials are no longer read from the code: the client uses the node's cookie, then
  `~/.config/vmls/rpc.env`, then the variables `VMLS_RPC_USER` and `VMLS_RPC_PASSWORD`.
- Python 3.12 or later.

### Added

- Our construction: levels from a nonce committed in the header and revealed k blocks deep (a block never revealed
  has level 0), and the verifier with the capped Score (`compare_ours`).
- Real headers (`vmls.encoding`): the bytes of each header, field by field, with the real hashes its pointers
  designate; the verifier reads them and checks that each proof is linked. The size formula is checked against them;
  the earlier byte model counted one pointer too many per header of our construction (32 bytes).
- `vmls replay`: a proof grown block by block over the whole chain, with the update time and the size of each part.
- `vmls verifier`: the verifier's time at several heights, with real headers and by formula, on forks near the tip
  and deep in the chain. The verifier checks that a proof starts at the genesis block, that X and Omega are
  contiguous and that each level is the one the construction gives. Score takes v_mu, level by level, from the
  formula of Algorithm 4, with its parameters measured on the chain since 2020 (`v_by_level`).
- `vmls build-time`, `vmls sections` (with `vmls block-sizes`, the full blocks of Omega), `vmls kstar` (the K* the
  security bound asks for on Bitcoin), `vmls attack`, `vmls gamma classic|bound` (with `--since` for a recent
  period), `vmls export`, `vmls utxo`, `vmls figures`.
- A prover that builds a proof from the headers in one pass (`compress_in_one_pass`): it fills D while it reads the
  chain and holds O(K) blocks per level; `vmls build-time` times it beside levels-then-Compress and checks that both
  give the same proof. Both hash every header, as an update does.
- `vmls figures --timings`: the update and build times of runs made alone replace those of the main results.
- The headers up to height 977,192 (`headers/headers-up-to-977192.json.xz`) and the size of each of these blocks
  (`data/block-sizes-977192.npy`), on which the measurements of version 2 run.
- The figures of the README, drawn from the code by `docs/make_figures.py`.
- The published figures of the CCS 2025 paper in `paper-figures/ccs-2025/`.
- Tests: properties of the prover on hundreds of synthetic chains, every tampering the verifier must catch, the
  zero-difficulty attack (it beats CCS 2025, not ours), regressions on the real chain (`--runslow`), no machine path
  and no venue under review in the repository, CI on Linux, Windows and macOS with Python 3.12 and 3.14.
- `rpc.env.example`, and lower bounds for the dependencies (the versions the regressions were checked with).

### Removed

- The Merkle-root variants of the headers, the drawing of a proof (now a figure of the README), the full replay of
  the UTXO set (`vmls utxo` asks the node for the tip), the redrawing of the CCS 2025 figures (see the tag).

### Fixed

- The verifier follows the published Compare rule (`compare_ccs`): the code of version 1 counted the blocks of X
  and Omega whatever their level.

### Security

- The history was rewritten on 2026-11-23 to remove an RPC user and password committed in `src/snapshot_size.py`
  (since rotated) and to use the maintainer's noreply address. Clones made before that date hold the old history;
  re-clone rather than merge.

## [1.0.0] - 2025-04-25

The code and data of the CCS 2025 paper *Mining in Logarithmic Space with Variable Difficulty*: the prover and the
verifier replayed over the 865,043 Bitcoin headers up to October 11, 2024, and the notebooks that draw the paper's
figures. Same commit as the tag `ccs-2025`.

[Unreleased]: https://github.com/loicmiller/vmls/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/loicmiller/vmls/releases/tag/v1.0.0
