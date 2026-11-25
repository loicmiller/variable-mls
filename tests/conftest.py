"""Shared settings: slow tests run on the Bitcoin headers; those that need reference data are skipped without it.

    pytest                     # fast tests, synthetic data only
    pytest --runslow           # also the regressions on the real chain

Data locations, overridable by environment variables:
    VMLS_HEADERS     headers file (default headers/headers-up-to-977192.json.xz, in the repository)
    VMLS_REFERENCE   reference directory (default data/reference, kept outside the repository)

The gamma(s, w) regression was measured on the headers up to 974,505: it runs with VMLS_HEADERS set to that export.
"""

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HEADERS = Path(os.environ.get('VMLS_HEADERS', ROOT / 'headers' / 'headers-up-to-977192.json.xz'))
REFERENCE = Path(os.environ.get('VMLS_REFERENCE', ROOT / 'data' / 'reference'))


def pytest_addoption(parser: pytest.Parser) -> None:
    """Adds --runslow."""
    parser.addoption('--runslow', action='store_true', help='Run the regressions on the real chain.')


def pytest_configure(config: pytest.Config) -> None:
    """Declares the slow marker."""
    config.addinivalue_line('markers', 'slow: needs the Bitcoin headers and minutes of computation')


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skips the slow tests unless --runslow is given."""
    if config.getoption('--runslow'):
        return
    skip = pytest.mark.skip(reason='needs --runslow')
    for item in items:
        if 'slow' in item.keywords:
            item.add_marker(skip)


def require(path: Path) -> Path:
    """Skips the test if a data file is missing.

    Args:
        path: The file.

    Returns:
        The file.
    """
    if not path.exists():
        pytest.skip(f'{path} is missing')
    return path
