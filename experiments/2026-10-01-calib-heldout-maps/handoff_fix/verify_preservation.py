"""Read-only source/bundle preservation check for the R3 documentation fix."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from harness import zone_final_pair_contract as c
from harness import zone_final_pair_heldout as heldout
from harness.zone_final_pair_excitation import MAP_ID
from scripts import run_final_pair_v3 as run
from scripts.run_ci_tests import TEST_PATTERNS, collect_test_files, shard_test_files
from tests.test_review_352 import BASE_BYTES

BASE = 'fa2119ca6926a66a317a455701cbc389d7d3fb58'
EVIDENCE = Path(__file__).resolve().parent
baseline = json.loads((EVIDENCE.parent / 'review_fixes/preservation.json').read_text())
tree = subprocess.check_output(['git', 'ls-tree', '-rz', BASE], cwd=ROOT)
blobs = {row.split(b'\t', 1)[1].decode(): row.split(b'\t', 1)[0].split()[2].decode()
         for row in tree.split(b'\0') if row}


def writer(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()


def check_sources(bundle):
    for name, expected in bundle['source_sha256'].items():
        data = (ROOT / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == expected, name
        blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        assert blob == blobs[name], name
    return len(bundle['source_sha256'])


v88 = {}
for check, expected in BASE_BYTES.items():
    bundle = c.bundle(MAP_ID, check)
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        assert run.main(['--check', check, '--map-id', MAP_ID, '--seed', '911',
                         '--expected-source-sha', 'a' * 40,
                         '--output', '/private/tmp/unused-pr352-plan']) == 0
    actual = {'bundle': hashlib.sha256(writer(bundle)).hexdigest(),
              'plan': hashlib.sha256(captured.getvalue().encode()).hexdigest()}
    assert actual == expected
    v88[check] = {**actual, 'unchanged_source_files': check_sources(bundle)}

v90 = {}
for map_id in heldout.MAPS:
    bundle = heldout.bundle(map_id, heldout.CHECK)
    digest = hashlib.sha256(writer(bundle)).hexdigest()
    assert digest == baseline['v90'][map_id]['bundle']
    assert bundle['execution_bundle_id'] == 'zone-final-pair-v90'
    assert bundle['workflow_version'] == '3.2.0'
    v90[map_id] = {'bundle': digest, 'unchanged_source_files': check_sources(bundle)}

old = subprocess.check_output(['git', 'show', BASE + ':PHYSICS_HANDOFF.md'], cwd=ROOT)
new = (ROOT / 'PHYSICS_HANDOFF.md').read_bytes()
assert old.split(b'\n---\n', 1)[1] == new.split(b'\n---\n', 1)[1]
assert re.search(rb'```bash\n(.*?)\n```', old, re.S)[0] == re.search(rb'```bash\n(.*?)\n```', new, re.S)[0]
assert not subprocess.check_output(['git', 'diff', BASE, '--', '.github/workflows'], cwd=ROOT)
files = collect_test_files(ROOT, TEST_PATTERNS)
durations = json.loads((ROOT / 'configs/ci_test_durations.json').read_text())
shards = shard_test_files(files, 8, durations)
assert sum(s.count('tests/test_review_352.py') for s in shards) == 1
assert len(set(files) & durations.keys()) / len(files) >= .9
record = {'source_base': BASE, 'v88': v88, 'v90': v90,
          'old_handoff_sections_unchanged': True, 'collection_shell_block_unchanged': True,
          'github_workflows_unchanged': True, 'review_test_in_exactly_one_ci_shard': True,
          'ci_duration_coverage': {'measured': len(set(files) & durations.keys()), 'total': len(files)},
          'extraction_directories_created': []}
(EVIDENCE / 'preservation.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
