"""Restore the reviewed, incorrect scope wording in memory; never edit files."""
from pathlib import Path
import subprocess
import sys
import pytest

root = Path(__file__).resolve().parents[4]
old = '2c863fda3fd2de2f0fc714c2367c3e81b440b530'
paths = [root/'experiments/2026-09-30-pair-v6h-carry'/name for name in ('README.md', 'REGISTRATION_PLAN.md')]
text = {p: subprocess.check_output(['git', 'show', f'{old}:{p.relative_to(root)}'], cwd=root, text=True) for p in paths}
read = Path.read_text
Path.read_text = lambda self, *args, **kwargs: text[self] if self in text else read(self, *args, **kwargs)
raise SystemExit(pytest.main(sys.argv[1:]))
