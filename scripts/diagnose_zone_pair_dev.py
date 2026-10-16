"""Read-only dev03/dev04 admission/guard reconstruction. No physics or model calls.

Run as a module with --raw-root and --output (a new file outside raw).
The source reports are rounded receipts, not a rerun of the particle filter.
"""
from __future__ import annotations

import argparse
import base64
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from harness.owncam_drive import WIDE_LOOK_PANS
from harness.owncam_pose_source import PoseReport
from harness.zone_own_guards import OwnPose, SweepGuard, UncertaintyGate
from harness.zone_pair_admission import readiness_snapshot
from harness.zone_pair_vision import valid_frame


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reconstruct_gate(frames, cutoff):
    gate = UncertaintyGate()
    for frame in frames:
        if frame['t'] > cutoff:
            break
        r = frame['report']
        gate.update(frame['t'], r['initialized'], r['std_xy_m'], r['std_yaw_rad'])
    return gate


def guard_receipt(guard, evidence):
    e = evidence['own_estimate']
    pose = OwnPose(e['x_m'], e['y_m'], e['yaw_rad'], e['std_xy_m'], e['std_yaw_rad'])
    cur = {int(k): v for k, v in evidence['current_pwm'].items()}
    target = {int(k): v for k, v in evidence['target_pwm'].items()}
    loaded = evidence['loaded']
    exact = guard.transition_diagnostic(cur, target, pose, loaded=loaded)
    nominal = OwnPose(pose.x, pose.y, pose.yaw, 0., 0.)
    return {'recorded': evidence, 'recomputed': exact,
            'transition_clear': guard.transition_clear(cur, target, pose, loaded=loaded),
            'zero_sigma_transition_clear': guard.transition_clear(cur, target, nominal, loaded=loaded),
            'current_arm_clearance_mm': guard.arm_clearance(cur, pose, loaded=loaded)[0] * 1000,
            'chassis_clearance_mm': guard.chassis_clearance(pose)[0] * 1000,
            'safe_alternative_pans': [pan for pan in WIDE_LOOK_PANS if
                guard.transition_clear(cur, {6: pan}, pose, loaded=loaded)],
            'east_8cm_translation_clear': guard.translation_clear(cur, pose, .08, 0., loaded=loaded)}


def diagnose(raw_root):
    raw_root = Path(raw_root).resolve()
    output = {'schema': 'ugrp.zone_pair_dev_diagnosis.v1', 'raw_root': str(raw_root),
              'scope': 'post-hoc rounded-report gate replay and exact saved guard inputs; not physics/PF replay',
              'runs': {}}
    for run_id in ('dev03', 'dev04'):
        root = raw_root / run_id
        files = json.loads((root / 'artifacts.sha256.json').read_text())
        # Verify the complete existing receipt without modifying any source.
        mismatches = [name for name, record in files.items() if sha(root / name) != record['sha256']]
        if mismatches:
            raise ValueError(f'{run_id}: raw hash mismatch: {mismatches}')
        static = json.loads((root / 'inputs/static.json').read_text())
        robots = json.loads((root / 'robots.json').read_text())
        api = json.loads((root / 'api_calls.json').read_text())
        guard = SweepGuard(static['map'])
        result = {'verified_artifact_count': len(files), 'hash_mismatches': mismatches,
                  'source_sha256': {name: sha(root / name) for name in
                    ('artifacts.sha256.json', 'robots.json', 'commands.jsonl', 'events.jsonl',
                     'api_calls.json', 'inputs/static.json', 'eval_only/trace.jsonl')}, 'robots': {}}
        for rid in ('r1', 'r2'):
            frames = robots[rid]['frames']
            ack = next(a for a in api if a['robot_id'] == rid and a['api'] == 'pair_carry')
            now = ack['sim_s']
            frame = next(f for f in reversed(frames) if f['t'] <= now)
            r = frame['report']
            obs = json.loads((root / 'inputs' / rid / f"{frame['frame']:05d}.json").read_text())
            obs['image'] = base64.b64encode((root / obs['image_file']).read_bytes()).decode()
            gate = reconstruct_gate(frames, now)
            report = PoseReport(**{k: v for k, v in r.items() if k != 'xyyaw'},
                                **dict(zip(('x_m', 'y_m', 'yaw_rad'), r['xyyaw'])))
            ex = SimpleNamespace(last_report=report, last_obs=obs, gate=gate, mode='m1', robot_id=rid,
                stopped=None, job=None, servo={int(k): v for k, v in frame['commanded_servo'].items()},
                holding=lambda: {'answer': 'no'})
            receipt = readiness_snapshot(ex, now)
            events = [json.loads(line) for line in (root / 'events.jsonl').read_text().splitlines()]
            blocked = [guard_receipt(guard, e['detail']['guard']) for e in events
                       if e['robot_id'] == rid and e['detail'].get('reason') == 'SWEEP_TRANSITION_BLOCKED']
            result['robots'][rid] = {
                'actual_ack': ack, 'reconstructed_readiness': receipt,
                'assumptions_checked_in_raw': 'no active job at submit; commanded gripper open; mode m1',
                'frame_gate_independent_check': valid_frame(obs, rid, now),
                'gate_transitions_through_submit': gate.transitions,
                'gate_transitions_through_end': reconstruct_gate(frames, float('inf')).transitions,
                'minimum_sigma_before_submit_m': min(f['report']['std_xy_m'] for f in frames if f['t'] <= now),
                'submission_frame': frame, 'blocked_sweeps': blocked}
        # This separate block is static geometry/evaluation only, never a control input.
        initial = json.loads((root / 'eval_only/trace.jsonl').open().readline())
        result['eval_only_initial_robot_poses'] = initial['robots']
        cur = {int(k): v for k, v in robots['r1']['frames'][0]['commanded_servo'].items()}
        result['static_dock_options_not_selected'] = [
            {'pose': asdict(p), 'chassis_clearance_mm': 1000 * guard.chassis_clearance(p)[0],
             'east_8cm_translation_clear': guard.translation_clear(cur, p, .08, 0., loaded=False)}
            for p in (OwnPose(-.85, -.85, 0., 0., 0.), OwnPose(-.85, -.85, 0., .05, .06),
                      OwnPose(-.70, -.85, 0., .05, .06), OwnPose(-.65, -.85, 0., .05, .06))]
        output['runs'][run_id] = result
    return output


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.resolve().is_relative_to(args.raw_root.resolve()):
        p.error('output must be outside the read-only raw root')
    result = diagnose(args.raw_root)
    with args.output.open('x') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


if __name__ == '__main__':
    main()
