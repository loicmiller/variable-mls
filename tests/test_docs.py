"""The figures of the README are drawn by docs/make_figures.py from the code: it must keep running."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_readme_figures_are_drawn(tmp_path):
    subprocess.run([sys.executable, str(ROOT / 'docs' / 'make_figures.py'), str(tmp_path)], check=True, cwd=ROOT,
                   capture_output=True)
    names = {p.name for p in tmp_path.iterdir()}
    for name in ('architecture', 'usage', 'proof-anatomy', 'header-layout'):
        assert {f'{name}.svg', f'{name}.pdf'} <= names
