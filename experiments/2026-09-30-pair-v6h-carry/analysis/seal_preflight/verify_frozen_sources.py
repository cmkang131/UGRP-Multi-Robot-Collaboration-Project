"""Read-only seal preflight: git blobs and source files only, never cohort raw.

Run from any directory with the existing simulation Python environment.
Exit 0: frozen pins match and main has no pin changes; 3: stop condition.
The stdout JSON is an audit record, not a seal or execution authorization.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
SOURCE = '4c6b439f3f7c9a147c901f8b260a1e214d4eb396'
EXPECTED_COUNT = 274


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def audit():
    # Refuse to obtain the pin set from a modified registration definition.
    definition = 'scripts/zone_pair_v6_contract.py'
    if (ROOT / definition).read_bytes() != git('show', f'{SOURCE}:{definition}'):
        raise ValueError('frozen pin-set definition changed; use the original source')
    sys.path.insert(0, str(ROOT))
    from scripts.zone_pair_v6_contract import candidate_contract, V6H_EXTRA_SOURCE_PATHS

    pins = candidate_contract('v6h')['source_sha256']
    if len(pins) != EXPECTED_COUNT or not set(V6H_EXTRA_SOURCE_PATHS) <= set(pins):
        raise ValueError('frozen 274-file pin set or explicit extra sources changed')
    rows = {}
    for path, preview_sha in sorted(pins.items()):
        expected = sha256(git('show', f'{SOURCE}:{path}'))
        actual = sha256((ROOT / path).read_bytes())
        rows[path] = {'git_sha256': expected, 'worktree_sha256': actual,
                      'preview_sha256': preview_sha,
                      'matches': expected == actual == preview_sha}

    main = git('rev-parse', 'origin/main').decode().strip()
    base = git('merge-base', SOURCE, main).decode().strip()
    main_changes = set(git('diff', '--name-only', base, main).decode().splitlines())
    changed_pins = {}
    for path in sorted(main_changes & pins.keys()):
        changed_pins[path] = {
            'frozen_sha256': rows[path]['git_sha256'],
            'main_sha256': sha256(git('show', f'{main}:{path}')),
            'commits': git('log', '--format=%H %s', f'{base}..{main}', '--', path).decode().splitlines(),
        }
    classifier = git('rev-parse', 'origin/claude/b-v6h-gain').decode().strip()
    classifier_base = git('merge-base', SOURCE, classifier).decode().strip()
    incoming = set(git('diff', '--name-only', classifier_base, classifier).decode().splitlines())
    classifier_different_pins = [
        path for path in sorted(incoming & pins.keys())
        if git('show', f'{SOURCE}:{path}') != git('show', f'{classifier}:{path}')
    ]
    mismatches = [path for path, row in rows.items() if not row['matches']]
    return {
        'status': 'STOP_MAIN_PIN_DRIFT' if changed_pins else ('STOP_PIN_MISMATCH' if mismatches else 'PASS'),
        'source': SOURCE, 'worktree_head': git('rev-parse', 'HEAD').decode().strip(),
        'main': main, 'main_merge_base': base, 'classifier': classifier,
        'pin_count': len(rows), 'extra_source_paths': list(V6H_EXTRA_SOURCE_PATHS),
        'mismatches': mismatches, 'main_changed_pinned_files': changed_pins,
        'classifier_incoming_different_pins': classifier_different_pins,
        'pins': rows,
        'scope': 'source hash and branch-diff audit only; no raw, physics, render, or outcomes',
    }


if __name__ == '__main__':
    result = audit()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['status'] == 'PASS' else 3)
