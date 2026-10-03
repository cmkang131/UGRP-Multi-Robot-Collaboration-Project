"""Offline B-double-prime support audit of a FULL headless v92 pre-check.

This reads only the supplied new run, never held-out collections. It cannot
produce calibration/training data or claim identifiability of fitted parameters.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from harness import zone_final_pair_loaded as loaded
from harness import zone_final_pair_loaded_schedule as schedule
from scripts.final_pair_calibration_v92_io import Inputs, loaded_arrays
from scripts.final_pair_calibration_io import loaded_mask, selected_segments
from scripts import validate_consumer_criterion_b as b
from scripts.run_final_environment_checks import write


def support_cells(mask, plan, criterion, levels=schedule.FROZEN_LEVELS):
    """All endpoints included; no window bridges a single invalid sample.

    Apply B-double-prime's 100-window group floor conservatively to each
    robot/axis/sign/level/horizon cell. Overlapping windows are not independent.
    Relative-yaw and common-orbit companion commands never replace axis steps.
    """
    expected = round(plan['sim_cap_s']/plan['control_period_s'])+1
    if np.asarray(mask).dtype != np.dtype(bool) or len(mask) != expected:
        raise ValueError('full boolean loaded mask required')
    commands, motion, _ = loaded_arrays(plan)
    selected = selected_segments(motion, mask)
    minimum = criterion['split']['minimum_windows_per_group']
    rows = []
    for rid in ('r1', 'r2'):
        for axis, name in enumerate(b.AXES):
            command_axis = b.COMMAND_AXES[axis]
            for sign in (-1, 1):
                for magnitude in levels:
                    # Only primary steps of this axis; no PRBS/relative-yaw.
                    spans = [(round(s['start_s']/.05), round((s['start_s']+s['duration_s'])/.05))
                             for s in plan['segments'] if s['axis'] == command_axis
                             and s['mode'] != 'relative_yaw' and s['phase'] == 'step'
                             and schedule.action_vector(s, rid)[command_axis] == sign*magnitude]
                    if not spans:
                        continue  # low translation-only diagnostic levels
                    for horizon in criterion['parent_text']['horizons_s']:
                        starts, k = b.c.windows(spans, horizon, .05)
                        kept_spans = selected[name]['steps']
                        valid_starts = (b.c.windows(kept_spans, horizon, .05)[0]
                                        if any(z-a >= k for a, z in kept_spans) else np.array([], int))
                        surviving = np.intersect1d(starts, valid_starts)
                        # Audit the actual recorded schedule's primary command
                        # over the entire horizon, including all mixed orbit input.
                        outside = np.r_[0, np.cumsum(commands[rid][:, axis] != sign*magnitude)]
                        if np.any(outside[starts+k] != outside[starts]):
                            raise ValueError('cell contains another command level')
                        rows.append({'robot': rid, 'axis': command_axis, 'sign': sign,
                            'level': magnitude, 'horizon_s': horizon,
                            'pre_filter_windows': len(starts), 'complete_windows': len(surviving),
                            'excluded_windows': len(starts)-len(surviving), 'minimum_windows': minimum,
                            'pass': len(surviving) >= minimum})
    return rows


def audit(root):
    inputs = Inputs()
    root = inputs.protect(root)
    result = inputs.json(root/'summary.json')
    if (result['status'] != 'HEADLESS_CHECK_COMPLETE' or result.get('collection') is not False
            or result.get('check_sim_s', -1) < schedule.CAP_S-1e-7
            or result.get('source_unchanged') is not True or result.get('render_calls') != 0):
        raise ValueError('complete render-free pre-check required')
    manifest = inputs.json(root/'artifacts.sha256.json')
    for name, digest in manifest.items():
        path = inputs.protect(root/name)
        if not path.is_relative_to(root) or path.is_symlink():
            raise ValueError('invalid artifact path')
        inputs.add(path)
        if inputs.files[str(path)]['sha256'] != digest:
            raise ValueError('artifact changed: '+name)
    bundle = inputs.json(root/'bundle.json')
    plan = bundle['measurement']
    if (plan != schedule.design() or inputs.json(root/'commands.json') != schedule.schedule()
            or bundle['source_sha'] != result['source_sha']):
        raise ValueError('source/schedule identity mismatch')
    criterion = inputs.json(loaded.previous.ROOT/loaded.CRITERION)
    if inputs.files[str((loaded.previous.ROOT/loaded.CRITERION).resolve())]['sha256'] != loaded.criterion_registration()['sha256']:
        raise ValueError('criterion changed')
    robots = {}
    for rid in ('r1', 'r2'):
        poses = inputs.rows(root/f'eval_only/{rid}/pose.jsonl')
        t = np.array([row['t'] for row in poses])
        if (len(t) != round(schedule.CAP_S/.05)+1
                or not np.allclose(t-t[0], np.arange(len(t))*.05, atol=1e-7, rtol=0)):
            raise ValueError('incomplete pose clocks')
        issued = inputs.rows(root/f'robots/{rid}/commands.jsonl')
        actual = [{**row, 't': round(row['t']-t[0], 7)} for row in issued
                  if row['kind'] != 'initial_servo_command']
        expected = [{'t': e['t'], **e['action']} for e in schedule.schedule() if e['robot_id'] == rid]
        if actual != expected:
            raise ValueError('issued commands differ from schedule')
        robots[rid] = {'t': t}
    if not np.allclose(robots['r1']['t'], robots['r2']['t'], atol=1e-8, rtol=0):
        raise ValueError('robot clocks differ')
    data = {'folder': root, 'robots': robots}
    mask, reasons = loaded_mask(data, inputs, criterion['loaded_selection'])
    cells = support_cells(mask, plan, criterion)
    if len(cells) != 288:
        raise ValueError('required 288-cell command support missing')
    low = support_cells(mask, plan, criterion, schedule.LOW_LEVELS)
    failed = [row for row in cells if not row['pass']]
    inputs.verify()
    return {'scope': 'full headless pre-check; not collection, fit, RGB or student acceptance',
        'source_sha': result['source_sha'], 'raw_root': str(root),
        'schedule_sha256': loaded.schedule_registration()['sha256'],
        'criterion_sha256': loaded.criterion_registration()['sha256'],
        'raw_manifest_sha256': inputs.files[str(root/'artifacts.sha256.json')]['sha256'],
        'mask_samples': len(mask), 'valid_samples': int(mask.sum()), 'sample_reasons': reasons,
        'required_cells': len(cells), 'passed_cells': len(cells)-len(failed),
        'minimum_complete_windows': min(row['complete_windows'] for row in cells),
        'support_pass': not failed, 'cells': cells, 'low_level_diagnostics': low,
        'identifiability_13_parameters': 'NOT_TESTED; support is necessary, not sufficient',
        'inputs': inputs.files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('raw', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.output.resolve().is_relative_to(args.raw.resolve()):
        raise ValueError('new output outside immutable raw required')
    report = audit(args.raw)
    write(args.output, report)
    print(f"{report['passed_cells']}/288 cells pass; min complete windows={report['minimum_complete_windows']}")
    return 0 if report['support_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
