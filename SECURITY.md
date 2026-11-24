# Security

## Reporting a vulnerability

Please do **not** describe a security problem in a public issue. Open an issue titled "Security contact" without
any detail, and a maintainer will get in touch to receive the report privately. Say which version or commit you use.

Never include an RPC password, a `rpc.env` file or a node's cookie in a report.

## What the code touches, and how

- **Bitcoin Core RPC**: only `vmls export` and `vmls utxo` talk to a node, at `http://127.0.0.1:8332` by default. Credentials never live in the
  repository: the client reads the cookie bitcoind writes in its data directory, then `~/.config/vmls/rpc.env`
  (keep it readable by you only, `chmod 600`), then the variables `VMLS_RPC_USER` and `VMLS_RPC_PASSWORD`. They are
  sent as HTTP basic authentication and never printed, logged or written to a result. Keep the node's RPC bound to
  127.0.0.1, which is Bitcoin Core's default when `rpcbind` is not set.
- **Block files**: `vmls block-sizes` opens the node's `blocks/blk*.dat` files for reading only, 88 bytes per
  block, and decodes them with the node's own XOR key. Run it on a stopped node.
- **Data**: headers, results and figures hold public Bitcoin data only. `results/`, `out/`, `data/` and the header
  exports are not tracked.
- **Network**: apart from the local RPC, nothing connects anywhere.

## Review of version 2 (2026-11-24)

- No server, no network access but RPC calls to the local node (`requests`, with a timeout); no `subprocess`,
  `eval`, `pickle` or unverified TLS in the package.
- Results are written with exclusive creation: a run never overwrites an earlier one.
- Dependencies: nothing outdated in the package's own dependencies (`pip list --outdated`: pip and packaging only).
- History: no credential added since the rewrite of 2026-11-23 (`git log -p`); the paths of a machine that version 1's
  notebook outputs printed are in the public history and are no secret; `tests/test_repository.py` keeps any new one
  out.

## History

Until 2026-11-23 the repository held an RPC user and password for a local node in `src/snapshot_size.py`. The
password was rotated and the history rewritten without it; a clone made before that date still holds it.
