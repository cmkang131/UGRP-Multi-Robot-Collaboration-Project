"""Run explicit offline regression files without accessing the shared outputs."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
SHARED = '/Users/changmin/projects/ugrp/outputs'
def guard(event, args):
    if event in ('open', 'os.listdir', 'os.scandir', 'os.mkdir', 'os.remove',
                 'os.rmdir', 'os.rename', 'os.chmod', 'os.truncate'):
        for arg in args[:2]:
            if isinstance(arg, (str, bytes)):
                path = os.path.abspath(os.fsdecode(arg))
                if path == SHARED or path.startswith(SHARED + '/'):
                    raise RuntimeError('PR352 must not access shared outputs: ' + event)
sys.addaudithook(guard)
import pytest
raise SystemExit(pytest.main(sys.argv[1:]))
