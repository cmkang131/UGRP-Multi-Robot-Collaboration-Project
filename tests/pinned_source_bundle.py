"""Build historical static bundles from their Git source, never today's closure."""
from functools import lru_cache
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=16)
def json_at(revision, code, extra_paths):
    # Code and configuration are small; media are selected explicitly by path.
    tree = set(subprocess.check_output(
        ['git', 'ls-tree', '-r', '--name-only', revision], cwd=ROOT, text=True).splitlines())
    paths = ['harness', 'sim', 'scripts', 'configs', 'maps']
    paths += sorted(p for p in extra_paths if p in tree and not p.startswith(tuple(x + '/' for x in paths)))
    archive = subprocess.check_output(['git', 'archive', revision, '--', *paths], cwd=ROOT)
    with tempfile.TemporaryDirectory(prefix='ugrp-pinned-bundle-') as directory:
        with tarfile.open(fileobj=io.BytesIO(archive)) as source:
            source.extractall(directory, filter='data')
        return json.loads(subprocess.check_output([sys.executable, '-c', code], cwd=directory, text=True))


def bundle_at(revision, module, map_id, check, extra_paths):
    code = ('import importlib,json; '
            'm=importlib.import_module(' + repr(module) + '); '
            'print(json.dumps(m.bundle(' + repr(map_id) + ',check=' + repr(check) + ')))')
    return json_at(revision, code, extra_paths)
