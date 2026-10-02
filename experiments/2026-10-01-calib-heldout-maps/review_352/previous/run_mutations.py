"""Review-only source reversions in the disposable archive; restore every byte."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'review-evidence'
PYTHON = '/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python'
H = 'harness/zone_final_pair_heldout.py'
R = 'scripts/run_final_pair_v3.py'
C = 'harness/zone_final_pair_clearance.py'
S = 'sim/final_pair_v3.py'
J = 'configs/zone_final_pair_v90.json'
TEST = 'tests/test_zone_final_pair_heldout.py'
MUTATIONS = [
    ('seed_guard_removed', [(H,
        "    if bundle['execution_bundle_id'] == BUNDLE_ID and seed != SEED:\n        raise ValueError('v90 held-out collection requires seed 911')",
        '    return None')], [TEST + '::test_seed_is_fixed_at_cli_case_and_direct_backend']),
    ('heldout_workflow_guard_removed', [(R,
        "    if heldout_only and not heldout.selected(args.check, args.map_id):\n        raise ValueError('v90 requires unloaded collection on a registered held-out map')\n",
        '')], [TEST + '::test_new_workflow_cannot_select_training_or_student']),
    ('runtime_interlock_bypassed', [(S,
        "        if not self.bundle['check'].startswith('calibration-'):\n            return\n        import mujoco",
        '        return\n        import mujoco')], [TEST + '::test_same_abort_interlock_preserves_partial_invalid_heldout']),
    ('start_pose_gate_removed', [(C,
        "return {'admitted': start['admitted'], 'envelope_policy': 'ADVISORY',",
        "return {'admitted': True, 'envelope_policy': 'ADVISORY',")],
        ['tests/test_zone_final_pair_review_fixes.py::test_unsafe_start_rejects_all_entry_points_before_output_or_physics']),
    ('training_label_in_code_and_registry', [(H, 'HELD_OUT_VALIDATION', 'TRAINING'),
                                            (J, 'HELD_OUT_VALIDATION', 'TRAINING')], [TEST]),
]
rows = []
for name, changes, tests in MUTATIONS:
    folder = EVIDENCE / 'mutations' / name
    folder.mkdir(parents=True, exist_ok=True)
    original = {p: (ROOT / p).read_bytes() for p, _, _ in changes}
    try:
        edits = []
        for path, before, after in changes:
            text = (ROOT / path).read_text()
            assert text.count(before) == 1, (name, path, text.count(before))
            (ROOT / path).write_text(text.replace(before, after))
            edits.append({'path': path, 'before': before, 'after': after})
        command = [PYTHON, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', *tests,
                   '--basetemp', str(folder / 'tmp'), '--junitxml', str(folder / 'pytest.xml')]
        with (folder / 'pytest.log').open('w') as log:
            result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                    env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        row = {'name': name, 'reversions': edits, 'tests': tests, 'exit_code': result.returncode,
               'outcome': 'SURVIVED' if result.returncode == 0 else 'DETECTED',
               'summary': (folder / 'pytest.log').read_text().splitlines()[-1],
               'log_sha256': hashlib.sha256((folder / 'pytest.log').read_bytes()).hexdigest()}
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    finally:
        for path, raw in original.items():
            (ROOT / path).write_bytes(raw)
        assert all((ROOT / path).read_bytes() == raw for path, raw in original.items())
    (EVIDENCE / 'mutations.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n')
