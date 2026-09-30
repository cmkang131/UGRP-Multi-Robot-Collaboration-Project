"""Mutate new modules in child memory, never the worktree or frozen sources."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
TEST = 'tests/test_zone_own_executor_target.py::'
MUTANTS = [
    ('public_ambiguity_removed', 'harness.zone_target_identity',
     "return 'PUBLIC_CUE_AMBIGUOUS'", 'pass',
     TEST+'test_ambiguity_never_submits_even_when_the_detection_is_named_like_the_item[public_duplicate-PUBLIC_CUE_AMBIGUOUS]'),
    ('active_ambiguity_cancel_removed', 'harness.zone_target_identity',
     "self._stop('OWN_CUE_AMBIGUOUS')", 'pass',
     TEST+'test_ambiguity_during_delivery_cancels_before_refresh_without_backend_fault'),
    ('explicit_target_removed', 'harness.zone_target_executor',
     'self.delivery_factory(self.inner, self.inner.job, target, view, point)',
     'self.delivery_factory(self.inner, self.inner.job, None, view, point)',
     TEST+'test_backend_passes_exact_target_to_delivery_and_cancel_drops_scheduled_commands'),
    ('host_queue_cancel_removed', 'harness.zone_target_executor',
     'self.cancel_scheduled(self.now, reason)', 'pass',
     TEST+'test_cancel_uses_actual_host_queue_drop_and_does_not_touch_peer'),
    ('rgb_recognizer_removed', 'harness.zone_target_rgb',
     "if information['sufficient']:", 'if False:',
     TEST+'test_real_saved_rgb_recognizer_produces_specific_grounding_without_labels'),
    ('target_mask_removed', 'harness.zone_target_rgb',
     'selected[mask == 0] = 0', 'pass',
     TEST+'test_attention_excludes_other_objects_and_preserves_selected_pixel_geometry'),
    ('target_freshness_relaxed', 'harness.zone_target_executor',
     "<= .25:", '<= 25.:',
     TEST+'test_freshness_timeout_stops_before_lower_step'),
    ('bundle_drift_gate_removed', 'scripts.zone_target_bundle',
     'if expected != actual:', 'if False:',
     'tests/test_zone_target_workflow.py::test_bundle_freezes_all_new_control_files_config_assets_and_verifies_drift'),
]
CHILD = '''import importlib, pathlib, sys, pytest
module = importlib.import_module(sys.argv[1])
source = pathlib.Path(module.__file__).read_text()
assert source.count(sys.argv[2]) == 1, 'mutation anchor must be unique'
exec(compile(source.replace(sys.argv[2], sys.argv[3]), module.__file__, 'exec'), module.__dict__)
raise SystemExit(pytest.main(['-q', sys.argv[4], '--tb=short']))
'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    rows = []
    for name, module, before, after, test in MUTANTS:
        path = ROOT/(module.replace('.', '/')+'.py')
        original = hashlib.sha256(path.read_bytes()).hexdigest()
        result = subprocess.run([sys.executable, '-c', CHILD, module, before, after, test],
                                cwd=ROOT, capture_output=True, text=True, timeout=120)
        (args.output/(name+'.log')).write_text(result.stdout+result.stderr)
        unchanged = hashlib.sha256(path.read_bytes()).hexdigest() == original
        rows.append({'name': name, 'module': module, 'before': before, 'after': after, 'test': test,
                     'source_sha256': original, 'pytest_exit_code': result.returncode,
                     'caught': result.returncode == 1 and 'FAILED ' in result.stdout,
                     'worktree_unchanged': unchanged})
    summary = {'schema': 'ugrp.t13_offline_mutations.v1', 'physics_run': False,
               'temporary_extraction_directories': [], 'mutants': rows,
               'all_caught': all(r['caught'] and r['worktree_unchanged'] for r in rows)}
    (args.output/'results.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary['all_caught'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
