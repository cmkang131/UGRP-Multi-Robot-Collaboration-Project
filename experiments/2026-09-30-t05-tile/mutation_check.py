"""Offline mutation evidence. Mutate temporary module copies, never the worktree.

Usage: <existing python> experiments/2026-09-30-t05-tile/mutation_check.py
       --output /absolute/new/output/directory
Exit 0 requires every targeted regression to FAIL with pytest exit 1 (not an
import/collection error). Output files are exclusive; no existing run is erased.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
TEST = 'tests/test_zone_own_executor_tile.py'
MUTATIONS = (
    ('role_guard_removed', 'tile_own_skill.py',
     "if role != 'west' or FORMATIONS['tile'] != ('west',):", 'if False:', 'wrong_role_rejected'),
    ('box_height_substituted', 'tile_own_skill.py',
     'height_m=vision.GRASP_HEIGHT_M', 'height_m=.024', 'normal_low_grasp_hold_and_release'),
    ('hold_confirmation_removed', 'tile_own_skill.py',
     "self.state == 'verify_hold' and self.hold_streak >= CONFIRM_FRAMES", "self.state == 'verify_hold'",
     'hold_and_release_need_two_post_transition_frames'),
    ('release_evidence_removed', 'tile_own_skill.py',
     "released = (self.view.holding == 'no' and xy is not None and math.dist(xy, self.target_xy) <= .025)",
     'released = True', 'open_command_alone_and_absence_without_visible_floor_tile'),
    ('own_camera_guard_removed', 'tile_own_skill.py',
     " or obs.get('camera') != 'robot_cam'", '', 'bad_camera_input_fails_closed'),
    ('background_boundary_removed', 'tile_own_vision.py',
     'fill >= .60 and containment >= .75 and boundary', 'fill >= .60 and containment >= .75',
     'real_holding_requires_tile_boundary'),
    ('native_duration_reverted', 'tile_own_skill.py',
     "('forward', 'left', 'turn', 'duration_s')", "('forward', 'left', 'turn', 'duration')",
     'overlapping_native_motion_keeps_latest_end'),
    ('motion_end_gate_removed', 'tile_own_skill.py',
     ' and self.frame_time >= self.motion_until', '', 'overlapping_native_motion_keeps_latest_end'),
    ('post_command_capture_gate_removed', 'tile_own_skill.py',
     'and self.frame_time > self.motion_time', 'and True',
     'native_motion_waits_for_post_motion_capture'),
    ('duplicate_capture_accepted', 'tile_own_skill.py',
     'or t <= self.frame_time', 'or t < self.frame_time',
     'same_capture_time_with_new_id'),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args().output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sources = {p.name: p.read_text() for p in (ROOT / 'harness').glob('tile_own_*.py')}
    rows = []
    for name, module, before, after, select in MUTATIONS:
        assert sources[module].count(before) == 1, name
        with tempfile.TemporaryDirectory(prefix='t05-mutant-') as scratch:
            overlay = Path(scratch)
            for filename, source in sources.items():
                (overlay / filename).write_text(source.replace(before, after, 1) if filename == module else source)
            code = ('import harness, pytest\n'
                    f'harness.__path__ = [{str(overlay)!r}, *list(harness.__path__)]\n'
                    f'raise SystemExit(pytest.main(["-q", {TEST!r}, "-k", {select!r}]))\n')
            run = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True,
                                 env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}, timeout=120)
            log = run.stdout + run.stderr
            (output / f'{name}.log').write_text(log)
            killed = run.returncode == 1 and f'FAILED {TEST}::' in log and 'ERROR collecting' not in log
            rows.append({'name': name, 'module': module, 'before': before, 'after': after,
                         'test_selector': select, 'pytest_exit': run.returncode, 'killed': killed,
                         'log_sha256': hashlib.sha256(log.encode()).hexdigest()})
            print(f'{name}: {"killed" if killed else "NOT KILLED"}', flush=True)
    record = {'schema': 't05.offline_mutation.v1', 'physical_steps': 0, 'render_calls': 0,
              'model_calls': 0, 'worktree_mutated': False,
              'source_sha256': {n: hashlib.sha256(s.encode()).hexdigest() for n, s in sources.items()},
              'mutations': rows, 'all_killed': all(row['killed'] for row in rows)}
    (output / 'mutation.json').write_text(json.dumps(record, indent=2) + '\n')
    return 0 if record['all_killed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
