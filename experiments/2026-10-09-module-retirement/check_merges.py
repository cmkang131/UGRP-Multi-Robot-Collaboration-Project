"""Virtual merge every frozen PR head, without changing any checkout or ref."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys
from audit import BASE, Blobs, Graph, ROOT, git, snapshot

HERE = Path(__file__).resolve().parent


def merge(left, right):
    result = subprocess.run(['git', 'merge-tree', '--write-tree', '--name-only', left, right],
                            cwd=ROOT, capture_output=True, text=True)
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr)
    header = result.stdout.split('\n\n', 1)[0].splitlines()
    return {'tree': header[0], 'exit_code': result.returncode,
            'conflicts': header[1:] if result.returncode else []}


def main():
    candidate = git('rev-parse', sys.argv[1] if len(sys.argv) > 1 else 'HEAD').strip()
    inventory = json.loads((HERE / 'inventory.json').read_text())
    retired = set(inventory['dead_core'] + inventory['dead_tests'])
    baseline = snapshot(BASE)
    current = snapshot(candidate)
    blobs = Blobs()
    cache = {(p, baseline[p]): set(edges) for p, edges in
             json.loads((HERE / 'edges.json').read_text()).items() if p in baseline}
    report = {'candidate': candidate, 'base': BASE, 'branches': []}
    for row in inventory['branches']:
        branch = snapshot(row['sha'])
        before = merge(BASE, row['sha'])
        after = merge(candidate, row['sha'])
        merged = snapshot(after['tree'])
        # Include removed names in resolution so a dangling import is detected,
        # not silently misclassified as a missing external dependency.
        known = baseline | current | branch | merged
        graph = Graph(known, lambda p: blobs.read(known[p]))
        bad, errors = [], []
        variants = [(p, oid) for p, oid in merged.items()
                    if p.endswith('.py') and p not in after['conflicts']]
        for p in after['conflicts']:
            if p.endswith('.py'):
                variants.extend((p, side[p]) for side in (current, branch) if p in side)
        for p, oid in variants:
            if (p, oid) not in cache:
                graph.read = lambda _, object_id=oid: blobs.read(object_id)
                graph.edges.pop(p, None)
                cache[p, oid] = graph.parse(p)
            for target in sorted(cache[p, oid] & retired):
                bad.append({'caller': p, 'caller_blob': oid, 'retired_target': target})
        errors.extend(graph.errors)
        record = {'branch': row['branch'], 'sha': row['sha'],
                  'baseline_merge': before, 'cleanup_merge': after,
                  'new_conflict_paths': sorted(set(after['conflicts']) - set(before['conflicts'])),
                  'removed_path_conflicts': sorted(set(after['conflicts']) & retired),
                  'resurrected_paths': sorted(set(merged) & retired),
                  'python_variants_checked': len(variants), 'dangling_retired_imports': bad,
                  'parse_errors': errors}
        report['branches'].append(record)
        print(row['branch'], 'imports', len(bad), 'new conflicts', record['new_conflict_paths'],
              'resurrections', record['resurrected_paths'], flush=True)
    blobs.close()
    (HERE / 'merge_checks.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    if any(r['dangling_retired_imports'] or r['removed_path_conflicts'] or r['resurrected_paths'] or
           r['parse_errors'] for r in report['branches']):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
