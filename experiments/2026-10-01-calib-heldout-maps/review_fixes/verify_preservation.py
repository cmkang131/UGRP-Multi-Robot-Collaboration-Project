"""Verify complete v88 bytes and truthful current source hashes without execution."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
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

EVIDENCE = Path(__file__).resolve().parent
main = subprocess.check_output(['git', 'rev-parse', 'origin/main'], cwd=ROOT, text=True).strip()
tree = subprocess.check_output(['git', 'ls-tree', '-rz', main], cwd=ROOT)
blobs = {row.split(b'\t', 1)[1].decode(): row.split(b'\t', 1)[0].split()[2].decode()
         for row in tree.split(b'\0') if row}
def blob_id(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
def writer(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()
def source_audit(bundle, *, old):
    for path, sha in bundle['source_sha256'].items():
        raw = (ROOT/path).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == sha, path
        if old:
            assert blob_id(raw) == blobs[path], path
    return len(bundle['source_sha256'])
rows = {}
for check, expected in BASE_BYTES.items():
    bundle = c.bundle(MAP_ID, check)
    count = source_audit(bundle, old=True)
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        assert run.main(['--check', check, '--map-id', MAP_ID, '--seed', '911',
                         '--expected-source-sha', 'a'*40, '--output', '/private/tmp/unused-pr352-plan']) == 0
    actual = {'bundle': hashlib.sha256(writer(bundle)).hexdigest(),
              'plan': hashlib.sha256(captured.getvalue().encode()).hexdigest()}
    assert actual == expected
    rows[check] = {**actual, 'source_files_identical_to_main': count}
new = {}
for map_id in heldout.MAPS:
    value = heldout.bundle(map_id, heldout.CHECK)
    new[map_id] = {'source_hashes_verified': source_audit(value, old=False),
                   'bundle': hashlib.sha256(writer(value)).hexdigest()}
durations = json.loads((ROOT/'configs/ci_test_durations.json').read_text())
files = collect_test_files(ROOT, TEST_PATTERNS)
known = set(files) & durations.keys()
shards = shard_test_files(files, 8, durations)
assert len(known)/len(files) >= .9
assert sum(shard.count('tests/test_review_352.py') for shard in shards) == 1
assert sum(shard.count('tests/test_zone_final_pair_heldout.py') for shard in shards) == 1
assert not subprocess.check_output(['git', 'diff', main, '--', '.github/workflows'], cwd=ROOT)
record = {'main': main, 'v88': rows, 'v90': new,
          'ci_duration_coverage': {'measured': len(known), 'total': len(files),
                                   'ratio': len(known)/len(files)},
          'new_tests_in_exactly_one_shard': True, 'github_workflows_unchanged': True,
          'extraction_directories_created': []}
(EVIDENCE/'preservation.json').write_text(json.dumps(record, indent=2)+'\n')
print(json.dumps(record, indent=2))
