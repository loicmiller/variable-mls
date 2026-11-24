# Contributing

## Setup

Python 3.12 or later, in a virtual environment outside the repository:

```bash
python3 -m venv ~/.venvs/vmls
~/.venvs/vmls/bin/pip install -e '.[dev]'
```

## Tests

```bash
python -m pytest              # fast tests, on synthetic chains (about a minute)
python -m pytest --runslow    # also the regressions on the real chain (a few minutes)
python -m pytest --cov=vmls --cov-branch --cov-report=term-missing   # branch coverage
```

The fast tests cover about 85 % of the branches. What they leave is either covered by the slow tests (gamma(s, w) on
the real chain) or needs a live node (the RPC session in `vmls.node`, the `export` and `utxo` commands).

The slow tests need the Bitcoin headers and the reference data, kept outside the repository; they are skipped when
missing. `VMLS_HEADERS` points to a headers export (default `headers/headers-up-to-974505.json`) and
`VMLS_REFERENCE` to the reference directory (default `data/reference`). CI runs the fast tests on Linux, Windows and
macOS, with Python 3.12 and 3.14, at every push.

## Rules

- Small, readable changes; Google-style docstrings (Args, Returns, Raises) and type hints; no dead code.
- One subcommand of `vmls` per measurement (`vmls/cli.py` parses, `vmls/measure.py` measures), writing JSON or NPZ to
  `results/`; `vmls figures` reads them and writes PDFs to `out/`. Every number a paper quotes comes from a result
  file. The figures of the README come from `docs/make_figures.py`: run it after a change to what they show.
- Figures are drawn at the width they are printed, with the style of `vmls/figures.py`.
- Nothing personal or secret in the repository: no credentials, no paths of a machine, no data files. Version 1's
  notebooks were committed with their outputs, which printed the paths of the machine they ran on: clear outputs
  before committing a notebook, and print paths relative to the repository. `tests/test_repository.py` fails on a
  machine path in any tracked file.
- A change users can see gets its line under *Unreleased* in `CHANGELOG.md`, in the same commit.
- Commits use the GitHub noreply address.

## Releases

Versions follow [Semantic Versioning](https://semver.org/): PATCH for fixes only, MINOR for something new that leaves
existing commands, options and result files working, MAJOR when one of them stops working as it was (the changelog
then says what to do). A paper's code also gets a tag named after the paper, such as `ccs-2025`.

On release day: choose the number from *Unreleased*; set it in `pyproject.toml`, `vmls/__init__.py` and
`CITATION.cff` (with `date-released`); turn *Unreleased* into a dated heading in `CHANGELOG.md`, add a new empty
*Unreleased* and the comparison links; commit « Release X.Y.Z » with the tests passing; tag `vX.Y.Z` (annotated);
push the branch, then the tag; publish the release on GitHub from that tag.
