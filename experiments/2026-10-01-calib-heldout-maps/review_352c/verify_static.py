"""Independent preservation audit; argv: candidate archive, review Git checkout.

Reads Git objects and the archive only; prints evidence JSON, writes nothing.
"""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT, REPO = map(lambda p: Path(p).resolve(), sys.argv[1:3])
BASE = 'fa2119ca6926a66a317a455701cbc389d7d3fb58'
FIX = '6b1ba45bb4ded61161cab3891925526ff5c42b12'
HEAD = 'f476e61ff0bbfc264533aa01248314601a705118'
SHARED = '/Users/changmin/projects/ugrp/outputs'


def guard(event, args):
    if event in ('open', 'os.listdir', 'os.scandir', 'os.mkdir', 'os.remove',
                 'os.rmdir', 'os.rename', 'os.chmod', 'os.truncate'):
        for value in args[:2]:
            if isinstance(value, (str, bytes)):
                path = os.path.abspath(os.fsdecode(value))
                if path == SHARED or path.startswith(SHARED + '/'):
                    raise RuntimeError('shared outputs forbidden')


sys.addaudithook(guard)
sys.path.insert(0, str(ROOT))
for name in ('mujoco', 'torch', 'torchvision', 'sim.multi_masterpi_production'):
    sys.modules[name] = None
from harness import zone_final_pair_contract as c
from harness import zone_final_pair_heldout as heldout
from harness.zone_final_pair_excitation import MAP_ID
from scripts import run_final_pair_v3 as legacy


def git(*args):
    return subprocess.check_output(['git', '-C', str(REPO), *args])


def tree(ref):
    rows = git('ls-tree', '-rz', ref).split(b'\0')
    return {row.split(b'\t', 1)[1].decode(): row.split(b'\t')[0].split()[2].decode()
            for row in rows if row}


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def writer(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()


trees = {ref: tree(ref) for ref in (BASE, FIX, HEAD)}
for name, expected in trees[HEAD].items():
    path = ROOT / name
    data = os.readlink(path).encode() if path.is_symlink() else path.read_bytes()
    assert blob(data) == expected, name

changed = git('diff', '--name-only', BASE, FIX).decode().splitlines()
assert all(name in ('PHYSICS_HANDOFF.md', 'tests/test_review_352.py') or
           name.startswith('experiments/2026-10-01-calib-heldout-maps/handoff_fix/')
           for name in changed)
merge_changed = git('diff', '--name-only', FIX, HEAD).decode().splitlines()
assert merge_changed == ['.github/workflows/tests.yml', 'CONTRIBUTING.md']
for directory in ('configs', 'harness', 'sim', 'scripts', 'maps', 'calibration'):
    assert not git('diff', BASE, HEAD, '--', directory), directory
assert not git('diff', BASE, FIX, '--', '.github/workflows')

prior = json.loads((REPO / 'experiments/2026-10-01-calib-heldout-maps/review_352b/static.json').read_text())
for name, expected in prior['preserved_files'].items():
    assert sha((ROOT / name).read_bytes()) == expected, name
    assert len({trees[ref][name] for ref in trees}) == 1, name
frozen = [name for name in trees[BASE]
          if name.startswith('experiments/2026-10-01-final-env-v87-calibration-fit/')]
assert set(frozen) == {name for name in trees[HEAD]
                      if name.startswith('experiments/2026-10-01-final-env-v87-calibration-fit/')}
assert all(len({trees[ref][name] for ref in trees}) == 1 for name in frozen)


def check_sources(bundle):
    for name, expected in bundle['source_sha256'].items():
        data = (ROOT / name).read_bytes()
        assert sha(data) == expected, name
        assert all(blob(data) == trees[ref][name] for ref in trees), name
    return len(bundle['source_sha256'])


# Expectations from the independent first review, not the implementer's record.
from importlib.util import module_from_spec, spec_from_file_location
spec = spec_from_file_location('original_review', REPO / 'tests/test_review_352.py')
original = module_from_spec(spec)
spec.loader.exec_module(original)
v88 = {}
for check, expected in original.BASE_BYTES.items():
    bundle = c.bundle(MAP_ID, check)
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        assert legacy.main(['--check', check, '--map-id', MAP_ID, '--seed', '911',
                            '--expected-source-sha', 'a' * 40,
                            '--output', str(ROOT / 'unused-preview')]) == 0
    actual = {'bundle': sha(writer(bundle)), 'plan': sha(captured.getvalue().encode())}
    assert actual == expected, check
    v88[check] = {**actual, 'identical_source_files': check_sources(bundle)}
assert not (ROOT / 'unused-preview').exists()
v90 = {}
for map_id in heldout.MAPS:
    bundle = heldout.bundle(map_id, 'calibration-unloaded')
    assert bundle['execution_bundle_id'] == 'zone-final-pair-v90'
    assert bundle['workflow_id'] == 'zone-final-pair-heldout-v90'
    assert bundle['workflow_version'] == '3.2.0'
    v90[map_id] = {'bundle': sha(writer(bundle)), 'identical_source_files': check_sources(bundle)}

old = git('show', BASE + ':PHYSICS_HANDOFF.md')
new = (ROOT / 'PHYSICS_HANDOFF.md').read_bytes()
assert re.search(rb'```bash\n(.*?)\n```', old, re.S)[0] == re.search(rb'```bash\n(.*?)\n```', new, re.S)[0]
assert old.split(b'\n---\n', 1)[1] == new.split(b'\n---\n', 1)[1]
print(json.dumps({'base': BASE, 'fix': FIX, 'head': HEAD,
    'archive_files_verified': len(trees[HEAD]), 'changed_files': changed,
    'merge_changed_files': merge_changed, 'frozen_files_verified': len(frozen),
    'preserved_files': prior['preserved_files'], 'v88': v88, 'v90': v90,
    'bundle_numbers_unchanged': True, 'collection_shell_bytes_unchanged': True,
    'old_handoff_sections_unchanged': True}, indent=2))
