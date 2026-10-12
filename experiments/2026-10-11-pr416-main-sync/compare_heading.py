"""Compare pre-merge selectors and S3 stage commands without physics or models."""
import hashlib
import json
import math
from pathlib import Path
import subprocess
import types
import uuid

import pytest

from harness import own_map_heading, zone_s3_pair_alignment, zone_s3_pair_heading
from harness import zone_s3_recovery_contract as contract
from harness import zone_solo_cyan_path_heading as heading
from harness.zone_solo_cyan_pulse_cal import action_of
from harness.zone_s3_recovery_runtime import Runtime
from scripts import run_s2_unknown_start
from tests import s3_stage_probe as probe

BEFORE = 'b3d52826997712e964812eecefe32aeb67d20b7f'
OUT = Path('outputs/pr416-main-sync/contract-on-v1')


def historical(path):
    source = subprocess.check_output(['git', 'show', f'{BEFORE}:{path}'], text=True)
    module = types.ModuleType('harness._before_' + Path(path).stem)
    exec(compile(source, f'{BEFORE}:{path}', 'exec'), module.__dict__)
    return module


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=True).encode()


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    previous = historical('harness/zone_solo_cyan_path_heading.py')
    previous_map = historical('harness/own_map_heading.py')
    previous_map.select_waypoint = previous.select_waypoint
    previous_pair = historical('harness/zone_s3_pair_heading.py')
    previous_pair.select_waypoint = previous.select_waypoint
    previous_align = historical('harness/zone_s3_pair_alignment.py')
    previous_align.select = previous.select
    profiles = json.loads(Path('configs/s2_motion_v7_pulse_cal_v1.json').read_text())['profiles']
    mismatches, counts = [], {}

    def compare(kind, inputs, before, after):
        counts[kind] = counts.get(kind, 0) + 1
        if canonical(before) != canonical(after):
            mismatches.append(dict(kind=kind, inputs=inputs, before=before, after=after))

    for loaded in (False, True):
        for x, y in ((0., .01), (0., .02), (0., .04), (.04, 0.), (-.04, 0.),
                     (.08, .04), (.101, 0.), (.5, .5), (1., 0.), (0., -1.)):
            for yaw in (-math.pi + 1e-4, -math.pi / 2, -.06, 0., .06, math.pi / 2, math.pi - 1e-4):
                distance = math.hypot(x, y)
                for tolerance in (.003, .03):
                    args = (profiles, loaded, [x, y], yaw, distance)
                    kwargs = dict(position_tolerance_m=tolerance)
                    compare('select', [loaded, x, y, yaw, tolerance],
                        previous.select(*args, **kwargs),
                        heading.select(*args, **kwargs, min_command_contract=True))
                args = (profiles, loaded, (0., 0., yaw), (x, y), (x, y))
                compare('select_waypoint', [loaded, x, y, yaw], previous.select_waypoint(*args),
                    heading.select_waypoint(*args, min_command_contract=True))
                plan = dict(coordinate_frame='r3/own_odom', status='goal_approach',
                            path_m=[[x, y]], heading_rad=0.)
                kwargs = dict(robot_id='r3', loaded=loaded)
                compare('own_map_heading.command', [loaded, x, y, yaw],
                    previous_map.command(plan, (0., 0., yaw), profiles, **kwargs),
                    own_map_heading.command(plan, (0., 0., yaw), profiles, **kwargs,
                                            min_command_contract=True))
                if not loaded:
                    compare('S3 approach', [x, y, yaw],
                        previous_pair.approach_proposal(profiles, (0., 0., yaw), (x, y), (x, y), 0.),
                        zone_s3_pair_heading.approach_proposal(profiles, (0., 0., yaw), (x, y), (x, y), 0.))
                    compare('S3 RGB alignment', [x, y, yaw],
                        previous_align.project(profiles, (x, y, -yaw)),
                        zone_s3_pair_alignment.project(profiles, (x, y, -yaw)))

    def before_runtime(parent):
        original = previous.runtime_class(parent)
        class BeforeRuntime(original):
            def __init__(self, *args, **kwargs):
                kwargs.pop('min_command_contract', None)
                super().__init__(*args, **kwargs)
        return BeforeRuntime

    reports = {}
    for name in ('before', 'after'):
        out = OUT / name
        out.mkdir()
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(uuid, 'uuid4', lambda: uuid.UUID(int=0))
            patch.setattr(probe, 'contract', contract)
            patch.setattr(probe, 'Runtime', Runtime)
            if name == 'before':
                patch.setattr(run_s2_unknown_start, 'heading_runtime', before_runtime)
                patch.setattr(zone_s3_pair_heading, 'select_waypoint',
                    lambda *a, min_command_contract=True, **kw: previous.select_waypoint(*a, **kw))
                patch.setattr(zone_s3_pair_alignment, 'select',
                    lambda *a, min_command_contract=True, **kw: previous.select(*a, **kw))
            report = probe.sweep(out, patch, invalid_pose_cases=True)
            reports[name] = dict(errors=report['error_count'], cases=len(report['rows']),
                                 commands=report['commands'])
    before = json.loads((OUT / 'before/commands.json').read_text())
    after = json.loads((OUT / 'after/commands.json').read_text())
    changes = sum(canonical(a) != canonical(b) for a, b in zip(before, after)) + abs(len(before) - len(after))
    result = dict(reference_sha=BEFORE, min_command_contract='on_v1', default='off',
        selector_cases=counts, selector_mismatches=len(mismatches), stage_probe=reports,
        command_mismatches=changes, before_command_sha256=hashlib.sha256(canonical(before)).hexdigest(),
        after_command_sha256=hashlib.sha256(canonical(after)).hexdigest(),
        physics_runs=0, model_calls=0, verification_scope='offline selectors and synthetic stage commands')
    (OUT / 'comparison.json').write_text(json.dumps(result, indent=2) + '\n')
    if mismatches:
        (OUT / 'mismatches.json').write_text(json.dumps(mismatches, indent=2) + '\n')
    for name in ('before', 'after'):
        path = OUT / name / 'commands.json'
        compressed = path.with_suffix('.json.zst')
        subprocess.run(['zstd', '-q', '-o', str(compressed), str(path)], check=True)
        restored = subprocess.check_output(['zstd', '-q', '-d', '-c', str(compressed)])
        assert restored == path.read_bytes()
        result.setdefault('artifacts', {})[str(compressed)] = dict(
            sha256=hashlib.sha256(compressed.read_bytes()).hexdigest(), bytes=compressed.stat().st_size,
            uncompressed_sha256=hashlib.sha256(restored).hexdigest(), uncompressed_bytes=len(restored))
        path.unlink()
    (OUT / 'comparison.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    if mismatches or changes or any(r['errors'] for r in reports.values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
