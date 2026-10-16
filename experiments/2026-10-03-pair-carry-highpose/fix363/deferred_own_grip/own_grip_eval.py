"""DEFERRED (not wired): own-grip HIGH view check scored on recorded own RGB.

v96 runs the grip monitor log-only (user scope decision 2026-10-03). This
exploratory score is kept for the deferred own-grip-loss + partner-signal work.


Validation order (survey, coordinator): zero check -> nominal split (template
and thresholds fixed on seed 911 before 912/913 were scored) -> drop detection
rate/latency. Ground truth (eval_label) is used ONLY to score, never by the
check. Thresholds are the module constants (MIN_ZNCC, MAX_SHIFT_PX), fixed
before the held-out seeds were looked at.

Template: seed 911 nominal own frame at t=30.0 s (HIGH pose), one per robot.
This is a STAND-IN for the production template (own-camera loaded HIGH frames
of the D5 v92 loaded collection), which is not measured yet.

Usage: python own_grip_eval.py <out.json>
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[3]))
sys.path.insert(0, str(HERE))
import hold_reference as grip  # noqa: E402
from harness import zone_pair_highpose as pose  # noqa: E402

OUT = Path('/Users/changmin/projects/ugrp/outputs')
ROOTS = {911: OUT/'pr363-render-frames-20261003', 912: OUT/'pr363-render-frames-seed912-20261003',
         913: OUT/'pr363-render-frames-seed913-20261003'}
HIGH = {'3': 896, '4': 2035, '5': 1894, '6': 1500}
TEMPLATE_T = 30.0
DROP_T = 12.0
RAISE_START_S = 10.0                # reviewer schedule; r2 +2 s in partner_delay_2s


def raise_until(condition, rid):
    # Queue end from the controller's own path constants (ArmSequence.queue:
    # duration + settle per step), not from the recorded data.
    until = RAISE_START_S + sum(d+s for _, d, s in pose.raise_path())
    return until + (2. if condition == 'partner_delay_2s' and rid == 'r2' else 0.)


def in_monitor_window(row):
    until = raise_until(row['condition'], row['rid'])
    return until-grip.STABLE_S-1e-8 <= row['t'] <= until+grip.STABLE_WAIT_MAX_S+1e-8


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def at_high(row):
    return all(row['issued_servo'].get(k) == v for k, v in HIGH.items())


def main(dest):
    templates = {}
    for rid in ('r1', 'r2'):
        path = ROOTS[911]/'nominal'/'frames'/f'{rid}_{TEMPLATE_T:05.1f}.jpg'
        templates[rid] = (grip.HoldReference.from_image(path.read_bytes(), 'stand-in:seed911:'+path.name),
                          {'file': str(path), 'sha256': sha(path)})
    rows, inputs = [], {}
    for seed, root in ROOTS.items():
        index = json.loads((root/'index.json').read_text())
        inputs[str(seed)] = {'index': str(root/'index.json'), 'sha256': sha(root/'index.json'),
                             'source_sha': index['source_sha']}
        for f in index['frames']:
            if f['rid'] not in templates or not at_high(f):
                continue
            check = templates[f['rid']][0].check((root/f['file']).read_bytes())
            rows.append({'seed': seed, 'condition': f['condition'], 'rid': f['rid'], 't': f['t'],
                         'window': f['eval_label']['window'], 'own_gripper_cmd': f['eval_label']['own_gripper_cmd'],
                         'partner_gripper_cmd': f['eval_label']['partner_gripper_cmd'],
                         'in_monitor_window': None, 'ok': check['ok'], 'zncc': round(check['zncc'], 4),
                         'ecc_shift_px': round(check['ecc_shift_px'], 3) if math.isfinite(check['ecc_shift_px']) else None,
                         'ecc_failed': not math.isfinite(check['ecc_shift_px']), 'frame_sha256': f['sha256']})

    for r in rows:
        r['in_monitor_window'] = in_monitor_window(r)

    def group(seed=None, condition=None, rid=None):
        return [r for r in rows if (seed is None or r['seed'] == seed) and (condition is None or r['condition'] == condition)
                and (rid is None or r['rid'] == rid)]

    def summary(sel):
        z = [r['zncc'] for r in sel]
        return {'frames': len(sel), 'flagged': sum(not r['ok'] for r in sel),
                'zncc_min': min(z) if z else None, 'zncc_max': max(z) if z else None,
                'ecc_failed': sum(r['ecc_failed'] for r in sel),
                'shift_max_px': max((r['ecc_shift_px'] for r in sel if not r['ecc_failed']), default=None)}

    groups, window_groups = {}, {}
    for seed in ROOTS:
        for cond in ('nominal', 'partner_delay_2s', 'raise_grip_loss'):
            for rid in ('r1', 'r2'):
                sel = group(seed, cond, rid)
                if sel:
                    groups[f'{seed}/{cond}/{rid}'] = summary(sel)
                    window_groups[f'{seed}/{cond}/{rid}'] = summary([r for r in sel if r['in_monitor_window']])
    held = [r for r in rows if r['seed'] in (912, 913) and r['condition'] == 'nominal' and r['in_monitor_window']]
    own_drop = [r for r in group(911, 'raise_grip_loss', 'r2') if r['in_monitor_window']]
    first = min((r['t'] for r in own_drop if not r['ok']), default=None)
    result = {
        'schema': 'pr363_own_grip_eval_v1',
        'driver_sha256': sha(__file__),
        'check': {'method': 'masked ZNCC + ECC translation vs own HIGH template',
                  'min_zncc': grip.MIN_ZNCC, 'max_shift_px': grip.MAX_SHIFT_PX,
                  'thresholds_fixed_before_heldout': True},
        'templates': {rid: meta for rid, (_, meta) in templates.items()},
        'template_note': 'stand-in from seed 911 nominal; production template = D5 v92 loaded HIGH own frames (unmeasured)',
        'inputs': inputs,
        'scope': 'frames whose issued servo equals the HIGH pose; decisions use the monitor window only; no carry/base motion frames exist',
        'seed_note': 'seeds 912/913 render almost identically to 911 (same commands, deterministic physics); weak held-out evidence',
        'monitor_window': {'definition': '[until-STABLE_S, until+STABLE_WAIT_MAX_S], until = 10 s + sum(raise_path duration+settle)',
                           'until_s': raise_until('nominal', 'r1'), 'stable_s': grip.STABLE_S,
                           'wait_max_s': grip.STABLE_WAIT_MAX_S, 'r2_delay_shift_s': 2.},
        'groups_all_high_command_frames': groups,
        'groups_monitor_window': window_groups,
        'heldout_nominal_false_alarm': {'frames': len(held), 'flagged': sum(not r['ok'] for r in held),
                                        'seeds': [912, 913], 'robots': ['r1', 'r2']},
        'own_grip_loss_r2': {'frames': len(own_drop), 'flagged': sum(not r['ok'] for r in own_drop),
                             'first_flag_t_s': first, 'drop_command_t_s': DROP_T,
                             'latency_s': None if first is None else round(first-DROP_T, 3),
                             'latency_note': 'checked only in the monitor window at the end of the raise queue (beam not judged below HIGH)'},
        'partner_drop_r1': summary([r for r in group(911, 'raise_grip_loss', 'r1') if r['in_monitor_window']]),
        'partner_drop_r1_note': 'r1 own view also changes when r2 drops its end (load tilt); flag is conservative, not partner detection',
        'n_seeds_note': 'n = 3 nominal seeds (1 template + 2 held-out), 1 delay, 1 grip-loss episode; not a rate estimate',
        'rows': rows,
    }
    Path(dest).write_text(json.dumps(result, indent=1, allow_nan=False)+'\n')
    print(json.dumps({k: result[k] for k in ('groups_monitor_window', 'heldout_nominal_false_alarm', 'own_grip_loss_r2', 'partner_drop_r1')}, indent=1))


if __name__ == '__main__':
    main(sys.argv[1])
