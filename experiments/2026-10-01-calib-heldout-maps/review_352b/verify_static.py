"""Read-only Git/archive audit. Does not inspect any shared outputs."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

archive, repo = map(Path, sys.argv[1:3])
sys.path.insert(0, str(archive))
HEAD = 'fa2119ca6926a66a317a455701cbc389d7d3fb58'
def git(*args):
    return subprocess.check_output(['git', *args], cwd=repo)
def sha(raw):
    return hashlib.sha256(raw).hexdigest()
def blob(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
def inventory(ref):
    return {row.split(b'\t', 1)[1].decode(): row.split(b'\t')[0].split()[2].decode()
            for row in git('ls-tree', '-rz', ref).split(b'\0') if row}

main = git('rev-parse', 'origin/main').decode().strip()
assert git('rev-parse', 'origin/codex/calib-heldout-maps').decode().strip() == HEAD
trees = {ref: inventory(ref) for ref in (HEAD, main, '2523269857596ffdd1a8cda9814a6e92f399f1da')}
mismatches = [p for p, oid in trees[HEAD].items() if blob((archive / p).read_bytes()) != oid]
assert not mismatches, mismatches

from harness import zone_final_pair_contract as c
from harness import zone_final_pair_heldout as h
from harness.zone_final_pair_excitation import MAP_ID
from scripts.run_ci_tests import TEST_PATTERNS, collect_test_files, shard_test_files

v88 = {}
for check in ('calibration-unloaded', 'calibration-fine', 'calibration-loaded'):
    value = c.bundle(MAP_ID, check)
    for path, expected in value['source_sha256'].items():
        raw = (archive / path).read_bytes()
        assert sha(raw) == expected, path
        assert len({tree[path] for tree in trees.values()} | {blob(raw)}) == 1, path
    v88[check] = len(value['source_sha256'])
v90 = {}
for map_id in h.MAPS:
    value = h.bundle(map_id, h.CHECK)
    for path, expected in value['source_sha256'].items():
        assert sha((archive / path).read_bytes()) == expected, path
    v90[map_id] = len(value['source_sha256'])

manifest = json.loads((archive / 'experiments/2026-10-01-calib-heldout-maps/preserved_files.json').read_text())
preserved = {}
for path, expected in manifest['byte_identical_sha256'].items():
    raw = (archive / path).read_bytes()
    assert sha(raw) == expected, path
    assert len({tree[path] for tree in trees.values()} | {blob(raw)}) == 1, path
    preserved[path] = expected
criterion_paths = [p for p in trees[main] if p.startswith('experiments/2026-10-01-final-env-v87-calibration-fit/')]
assert all(trees[main][p] == trees[HEAD][p] for p in criterion_paths)
assert all(trees[main][p] == trees[HEAD][p] for p in trees[main] if p.startswith('.github/workflows/'))

prs = json.loads(subprocess.check_output(['gh', 'pr', 'list', '--state', 'open', '--limit', '100',
    '--json', 'number,headRefName,headRefOid'], cwd=repo))
reservations = []
for pr in [{'number': None, 'headRefName': 'main', 'headRefOid': main}, *prs]:
    ref = 'origin/' + pr['headRefName']
    assert git('rev-parse', ref).decode().strip() == pr['headRefOid'], ref
    scan = subprocess.run(['git', 'grep', '-n', '-E',
        'zone-final-pair-v90|zone-final-pair-heldout-v90|3\\.2\\.0|zone-[a-z0-9-]+-v[0-9]+',
        ref, '--', 'harness', 'configs'], cwd=repo, capture_output=True, text=True)
    assert scan.returncode in (0, 1)
    collisions = [line for line in scan.stdout.splitlines() if re.search(
        r'zone-final-pair-v90\b|zone-final-pair-heldout-v90\b|["\']3\.2\.0["\']', line)]
    if pr['number'] != 352:
        assert not collisions, (ref, collisions)
    ids = [int(x) for x in re.findall(r'zone-[a-z0-9-]+-v(\d+)\b', scan.stdout)]
    runnable = git('grep', '-n', 'RUNNABLE_ID', ref, '--', 'harness/rgb_execution_bundle.py').decode()
    reservations.append({**pr, 'max_bundle_number': max(ids), 'v90_or_3_2_0_hits': collisions,
                         'runnable_id': runnable.strip()})
files = collect_test_files(archive, TEST_PATTERNS)
durations = json.loads((archive / 'configs/ci_test_durations.json').read_text())
known = set(files) & durations.keys()
assert len(known) / len(files) >= .9
shards = shard_test_files(files, 8, durations)
assert sorted(p for shard in shards for p in shard) == sorted(files)
record = {'head': HEAD, 'main': main, 'archive_files_verified': len(trees[HEAD]),
    'v88_sources_identical_to_original_base_main_and_head': v88,
    'v90_truthful_source_hashes': v90, 'preserved_files': preserved,
    'unchanged_frozen_experiment_files': len(criterion_paths),
    'github_workflows_unchanged': True, 'reservations': reservations,
    'ci_duration_coverage': {'measured': len(known), 'total': len(files), 'ratio': len(known)/len(files)},
    'shard_coverage_exactly_once': True}
print(json.dumps(record, indent=2))
