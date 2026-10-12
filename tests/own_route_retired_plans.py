"""Shared check for the egomap64/65 checkpoint-resume plans (PR #405 main merge).

The plans pin `frozen_modules` so that egomap63 checkpoints pickled at
`checkpoint_source_sha` only resume under the same code. Merging main changed
13 of those modules, so on a merged tree the plans are retired (resume only at
the original SHA) instead of re-hashed: re-hashing would let old pickles resume
under different code. `scripts/own_route_budget_schedule.admit_checkpoint`
already refuses with FROZEN_MODULE_CHANGED; this helper checks that the
retirement is recorded and the original plan bytes are preserved.
"""
import hashlib
import json
from pathlib import Path

RECORD = 'experiments/2026-10-12-pr405-main-merge/retired-plans.json'


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def assert_frozen_or_retired(root, plan_path):
    root = Path(root)
    plan_path = str(plan_path)
    plan = json.loads((root / plan_path).read_text())
    changed = sorted(name for name, digest in plan['frozen_modules'].items()
                     if not (root / name).is_file() or _sha(root / name) != digest)
    if not changed:
        return 'frozen'
    record = json.loads((root / RECORD).read_text())
    entry = next((e for e in record['retired'] if e['plan'] == plan_path), None)
    assert entry is not None, ('frozen modules changed but plan not retired', plan_path, changed)
    assert _sha(root / plan_path) == entry['sha256'], 'retired plan bytes changed'
    preserved = root / entry['preserved_copy']
    assert preserved.is_file() and _sha(preserved) == entry['sha256'], 'preserved copy missing or changed'
    assert entry['replay_only_at_source_sha'] == plan['checkpoint_source_sha']
    assert entry['replacement'] is None
    # Non-empty `changed` is exactly the condition under which admit_checkpoint refuses.
    return 'retired'
