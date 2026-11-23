# Contributing

## Setup

Python 3.11 or later, in a virtual environment outside the repository:

```bash
python3 -m venv ~/.venvs/vmls
~/.venvs/vmls/bin/pip install -e '.[dev]'
```

## Tests

```bash
python -m pytest              # fast tests, on synthetic chains (under a second)
python -m pytest --runslow    # also the regressions on the real chain (a few minutes)
```

The slow tests need the Bitcoin headers and the reference data, kept outside the repository; they are skipped when
missing. `VMLS_HEADERS` points to a headers export (default `headers/headers-up-to-974505.json`) and
`VMLS_REFERENCE` to the reference directory (default `data/reference`). CI runs the fast tests on Python 3.11 and
3.14 at every push.

## Rules

- Small, readable changes; Google-style docstrings (Args, Returns, Raises) and type hints; no dead code.
- One command per measurement in `experiments/`, writing JSON or NPZ to `results/`; one script per set of figures in
  `figures/`, reading those results and writing PDFs to `out/`. Every number a paper quotes comes from a result file.
- Figures are drawn at the width they are printed, with the style of `vmls/style.py`.
- Nothing personal or secret in the repository: no credentials, no paths of a machine, no data files.
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
