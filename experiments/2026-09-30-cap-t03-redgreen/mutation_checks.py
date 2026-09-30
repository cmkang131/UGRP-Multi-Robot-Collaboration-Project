"""T03 behavioral mutants in isolated memory; no source edits, physics or host lock."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
GUARD = Path(__file__).parent
MUTATIONS = (('red_green_dispatch_removed',
  'harness.zone_color_box_executor',
  "supported = BOX_KINDS if self.box_profile == 'm1_color_boxes_v1' else ('cyan',)",
  "supported = ('cyan',)",
  'tests/test_zone_own_executor_color_boxes.py::test_executor_passes_kind_into_controller_and_skill'),
 ('search_kind_filter_removed',
  'harness.m1_color_delivery',
  "if d['kind'] == self.box_kind:",
  'if True:',
  'tests/test_zone_own_executor_color_boxes.py::test_m1_search_and_coarse_order_keep_kind'),
 ('red_segmentation_changed_to_cyan',
  'harness.m1_color_perception',
  "'red': ((0, 6), (172, 179))",
  "'red': ((85, 98),)",
  'tests/test_zone_own_executor_color_boxes.py::test_same_policy_and_box_geometry_for_three_kinds[red]'),
 ('attachment_kind_reverted_to_cyan',
  'harness.wrist_color_boxes',
  'kind=self.box_kind, **kwargs',
  "kind='cyan', **kwargs",
  'tests/test_zone_own_executor_color_boxes.py::test_full_fake_attachment_probe_then_other_color_loss'),
 ('placement_kind_barrier_removed',
  'harness.zone_color_box_executor',
  "and placement.get('kind') != job.args['box_kind']",
  'and False',
  'tests/test_zone_own_executor_color_boxes.py::test_wrong_kind_placement_cannot_increment_delivered_count'),
 ('clip_kind_reverted_to_cyan',
  'harness.zone_color_box_delivery',
  'cyan = color_mask(frame, kind) > 0',
  "cyan = color_mask(frame, 'cyan') > 0",
  'tests/test_zone_own_executor_color_boxes.py::test_bottom_clip_uses_ordered_kind'),
 ('slot_filter_removed',
  'harness.zone_color_box_delivery',
  "self.cyan[n:] = [d for d in self.cyan[n:] if self._in_slot(d['map_xy'])]",
  'self.cyan[n:] = self.cyan[n:]',
  'tests/test_zone_own_executor_color_seals.py::test_actual_slot_filter_and_clip_use_selected_kind'),
 ('controller_search_reverted_to_cyan',
  'harness.zone_color_box_delivery',
  'ColorBoxDeliveryMixin._search_detect(self, obs, report)',
  'LegacyDeliverController._search_detect(self, obs, report)',
  'tests/test_zone_own_executor_color_seals.py::test_actual_slot_filter_and_clip_use_selected_kind'),
 ('finished_job_kind_lost',
  'harness.zone_color_box_executor',
  'return self._holding_kind',
  "return 'cyan'",
  'tests/test_zone_own_executor_color_boxes.py::test_kind_survives_job_end_and_wrong_kind_held_flag_is_not_yes'),
 ('holding_kind_barrier_removed',
  'harness.zone_color_box_executor',
  "getattr(box, 'box_kind', None) == self._held_kind()",
  'True',
  'tests/test_zone_own_executor_color_boxes.py::test_kind_survives_job_end_and_wrong_kind_held_flag_is_not_yes'))

MUTATIONS += (
 ('invalid_target_keeps_old_votes', 'harness.m1_color_perception',
  'except (TypeError, ValueError, OverflowError):\n            self.reset_window()',
  'except (TypeError, ValueError, OverflowError):\n            pass',
  'tests/test_review_325b.py::test_real_kind_loss_requires_fresh_face_votes'),
 ('nonfinite_target_keeps_old_votes', 'harness.m1_color_perception',
  'if not (math.isfinite(tx) and math.isfinite(ty)) or math.hypot(tx, ty) <= 1e-9:\n            self.reset_window()',
  'if not (math.isfinite(tx) and math.isfinite(ty)) or math.hypot(tx, ty) <= 1e-9:\n            pass',
  'tests/test_review_325b.py::test_invalid_target_ends_all_alignment_evidence[nan]'),
 ('lost_frame_keeps_old_votes', 'harness.m1_color_perception',
  'if not ok:', 'if False:',
  'tests/test_review_325b.py::test_current_evidence_loss_ends_ready_window'),
 ('reset_keeps_old_ready_metadata', 'harness.m1_color_perception',
  'self._previous_normal = None\n        self.last_ready = None', 'pass',
  'tests/test_review_325b.py::test_base_motion_reset_ends_alignment_evidence'),
 ('expired_vote_keeps_last_ready', 'harness.m1_color_perception',
  '            self.last_ready = None\n            return {**base,',
  '            return {**base,',
  'tests/test_review_325b.py::test_ready_result_expires_when_votes_no_longer_agree'),
 ('invalid_own_frame_keeps_old_votes', 'harness.wrist_color_boxes',
  'except ValueError:\n            self._face_aligner.reset_window()',
  'except ValueError:\n            pass',
  'tests/test_review_325b.py::test_rejected_own_frame_invalidates_prior_votes'),
 ('default_mode_reverted_to_diagnostic', 'harness.wrist_color_boxes',
  "def __init__(self, order, *, mode='m1', **kwargs):",
  "def __init__(self, order, *, mode='diagnostic', **kwargs):",
  'tests/test_review_325b.py::test_default_skill_and_placement_require_m1_pose'),
 ('factory_mode_barrier_removed', 'harness.zone_color_box_executor',
  "if getattr(skill, 'mode', None) != self.mode:", 'if False:',
  'tests/test_review_325b.py::test_m1_executor_rejects_factory_mode_mismatch'),
)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    output = Path(sys.argv[1]).resolve()
    output.mkdir(parents=True, exist_ok=False)
    records = []
    for name, module, old, new, target in MUTATIONS:
        path = ROOT / (module.replace('.', '/') + '.py')
        source = path.read_text()
        assert source.count(old) == 1, name
        original = sha(path)
        with tempfile.TemporaryDirectory(prefix='t03-mutant-') as temporary:
            plugin = Path(temporary) / 't03_mutant.py'
            plugin.write_text('import importlib\nimport offline_guard\n'
                + 'def pytest_configure(config):\n'
                + f'    module = importlib.import_module({module!r})\n'
                + f'    exec(compile({source.replace(old, new)!r}, {str(path)!r}, "exec"), module.__dict__)\n')
            xml = output / f'{name}.xml'
            command = [sys.executable, '-m', 'pytest', '-q', '-p', 't03_mutant', target, '--junitxml', str(xml)]
            env = {**os.environ, 'PYTHONPATH': os.pathsep.join((temporary, str(GUARD), str(ROOT))),
                   'PYTHONDONTWRITEBYTECODE': '1', 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1'}
            result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
            log = output / f'{name}.log'
            log.write_text(result.stdout + result.stderr)
            tree = ET.parse(xml)
            failures = tree.findall('.//failure')
            errors = tree.findall('.//error')
            assertions_only = all('AssertionError' in (f.text or '') or f.get('message', '').startswith('assert ')
                                  for f in failures)
            record = {'name': name, 'module': module, 'old': old, 'new': new, 'target': target,
                      'command': command, 'returncode': result.returncode, 'failures': len(failures),
                      'errors': len(errors), 'assertions_only': assertions_only,
                      'killed': result.returncode == 1 and bool(failures) and not errors and assertions_only,
                      'source_sha256': original, 'source_unchanged': original == sha(path),
                      'log_sha256': sha(log), 'junit_sha256': sha(xml)}
            records.append(record)
            print(name, record['killed'], len(failures), len(errors), flush=True)
    (output / 'summary.json').write_text(json.dumps(records, indent=2) + '\n')
    return 0 if all(r['killed'] and r['source_unchanged'] for r in records) else 1


if __name__ == '__main__':
    raise SystemExit(main())
