"""Validate round3 partitions, reviewer exclusions and graph artifacts (read-only)."""
import base64
import csv
import hashlib
import json
from pathlib import Path
import sys
import zlib

REPO = Path(__file__).resolve().parents[3]
DEST = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts import outputs_prune_stream as batches
from scripts import outputs_retention_graph as graph
from scripts.outputs_prune import sha256


def file_set(manifest, manifest_path, action):
    return {('/'.join(filter(None, (row['folder'], name))))
            for row, names in batches.rows(manifest, manifest_path, action) for name in names}


def graph_rows(label):
    for sidecar in json.loads((DEST / f'round3-graph-{label}.json').read_text()):
        p = DEST / sidecar['path']
        assert sha256(p) == sidecar['sha256']
        count = 0
        for line in p.open():
            batch = json.loads(line)
            raw = zlib.decompress(base64.b64decode(batch['entries_zlib_base64'], validate=True))
            assert hashlib.sha256(raw).hexdigest() == batch['uncompressed_sha256']
            rows = json.loads(raw)
            assert len(rows) == batch['rows']
            count += 1
            for row in rows:
                yield dict(zip(batch['fields'], row))
        assert count == sidecar['batches']


def main():
    old_path, new_path = DEST / 'round2-manifest.json', DEST / 'manifest.json'
    old, new = (json.loads(p.read_text()) for p in (old_path, new_path))
    old_delete, old_keep = (file_set(old, old_path, a) for a in ['delete', 'keep'])
    delete, keep = (file_set(new, new_path, a) for a in ['delete', 'keep'])
    assert not delete & keep
    assert delete <= old_delete
    assert old_keep <= keep
    assert delete | keep == old_delete | old_keep
    exclusions = json.loads((DEST / 'reviewer-exclusions.json').read_text())
    excluded = {p for p in old_delete if graph.exclusion_ids(p, exclusions)}
    assert not excluded & delete
    assert excluded <= keep
    assert hashlib.sha256(''.join(p + '\n' for p in sorted(excluded)).encode()).hexdigest() == exclusions['union_delete_totals']['sorted_paths_lf_sha256']
    protected = {row['path'] for row in graph_rows('protected')}
    assert not protected & delete
    assert old_delete - delete <= protected
    source_count = sum(1 for _ in graph_rows('sources'))
    reference_count = sum(1 for _ in graph_rows('refs'))
    folder_count = sum(1 for _ in graph_rows('folders'))
    restored = list(csv.DictReader((DEST / 'round3-json-reconstruction.csv').open()))
    d5 = {p for row, names in batches.rows(new, new_path, 'delete') if row['rule_id'] == 'D5'
          for p in ['/'.join(filter(None, (row['folder'], name))) for name in names]}
    assert {r['deleted_path'] for r in restored} == d5
    for row in restored:
        assert row['retained_source'] in keep
    dry = json.loads((DEST / 'dry-run.json').read_text())
    assert dry['execute'] is False
    assert dry['manifest_sha256'] == sha256(new_path)
    assert dry['files'] == len(delete)
    assert dry['kept_files_verified'] == len(keep)
    report = {'manifest_sha256': sha256(new_path), 'original_delete_files': len(old_delete),
              'new_delete_files': len(delete), 'new_keep_files': len(keep),
              'restored_to_keep': len(old_delete - delete),
              'reviewer_excluded_files': len(excluded), 'protected_inventory_entries': len(protected),
              'candidate_protection_overlap': 0, 'candidate_reviewer_overlap': 0,
              'graph_sources': source_count, 'matched_reference_edges': reference_count,
              'folder_edges': folder_count, 'd5_reconstruction_links': len(restored),
              'original_partition_preserved': True, 'new_candidates_added': 0,
              'dry_run_files_verified': True, 'actual_deleted_files': 0,
              'execution_blocker': dry.get('execution_blocker')}
    (DEST / 'round3-consistency.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
