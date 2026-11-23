"""Shared settings: slow tests need the Bitcoin headers and reference data, and are skipped without them.

    pytest                     # fast tests, synthetic data only
    pytest --runslow           # also the regressions on the real chain

Data locations, overridable by environment variables:
    VMLS_HEADERS     headers file (default headers/headers-up-to-974505.json)
    VMLS_REFERENCE   reference directory (default data/reference)
"""

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HEADERS = Path(os.environ.get('VMLS_HEADERS', ROOT / 'headers' / 'headers-up-to-974505.json'))
REFERENCE = Path(os.environ.get('VMLS_REFERENCE', ROOT / 'data' / 'reference'))


def pytest_addoption(parser):
    parser.addoption('--runslow', action='store_true', help='Run the regressions on the real chain.')


def pytest_configure(config):
    config.addinivalue_line('markers', 'slow: needs the Bitcoin headers and minutes of computation')


def pytest_collection_modifyitems(config, items):
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
