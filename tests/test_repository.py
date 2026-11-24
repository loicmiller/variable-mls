"""What the repository must never hold: paths of a machine, in code, docs or saved notebook outputs."""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
# Built in pieces so that this file does not match itself.
MACHINE_PATH = re.compile('/' + 'home/[a-z]|/' + 'Users/[A-Za-z]|[A-Z]:' + r'\\Users')


def test_no_machine_paths():
    try:
        files = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip('not a git checkout')
    found = []
    for name in files.splitlines():
        try:
            text = (ROOT / name).read_text(encoding='utf-8')
        except (UnicodeDecodeError, FileNotFoundError):
            continue  # Binary files (headers.zip, PDFs).
        found += [f'{name}:{i}' for i, line in enumerate(text.splitlines(), 1) if MACHINE_PATH.search(line)]
    assert not found, f'paths of a machine: {found}'
