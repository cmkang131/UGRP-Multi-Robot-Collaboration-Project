"""Read-only own-input replay; no physics, model calls, or truth-fed controller.

Reconstruct the released-clock PF and compare every pose to the saved record.
Rejected scan gate diagnostics are saved outside the original run.
"""
import argparse
import base64
import copy
import hashlib
import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness import zone_solo_cyan_contract_v106 as contract
from harness import zone_solo_cyan_v106 as solo
from harness import zone_pair_highpose_frame_gate as frame_gate
from harness.zone_pair_highpose_exact_speedups import install


def main():
    p = argparse.ArgumentParser()
    p.add_argument('run', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--candidate', action='store_true', help='new predictor on old fixed commands; not a physical run')
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    raw = json.loads((args.run/'student_record.json').read_text())
    frames = [json.loads(line) for line in (args.run/'robots/r3/frames.jsonl').read_text().splitlines()]
    _, undo = install('v98-exact-v6')
    from harness.zone_study_pose_delay_p03 import DelayedPoseSource
    inner = solo.partial.build_source_class()(contract.hp.resolve(contract.MAP_ID)[0],
        contract.ROOT/contract.CALIBRATION, contract.CALIBRATION_SHA, 911)
    inner.carry_yaw_fallback = None
    if args.candidate:
        solo.solo_motion.install(inner.loc._pf)
    provider = DelayedPoseSource(inner)
    src, pf = provider.provider, provider.provider.loc._pf
    if 'unloaded' in raw['motion_proxy'].lower():
        pf.params['motion_loaded'] = copy.deepcopy(pf.params['motion'])
    prior = raw['provider']['provider']['prior']
    provider.init_prior(prior['mean'], prior['std'], source=prior['source'])
    gates, maximum, mismatch, checked = [], 0., 0, 0
    update = pf.update_obs

    def observed(t, obs, pose):
        result = update(t, obs, pose)
        q = pf.partial_fix_last
        if q is not None:
            gates.append({'t': t, 'servo': dict(pose), 'columns': int(obs.informative.sum()),
                          'measured': bool(result.get('measured')), **copy.deepcopy(q)})
        return result

    pf.update_obs = observed
    commands = {}
    for row in raw['commands']:
        commands.setdefault(round(row['t'], 6), []).append(row)
    relooks = {round(e['t'], 6) for e in raw['events'] if e['event'] == 'state' and e['state'] == 'scan' and e['t'] > 2}
    # First initial-servo command is issued before the first capture.
    first = commands[round(frames[0]['sim_time'], 6)].pop(0)
    provider.on_command(first)
    servo = {int(k): v for k, v in first['pulses'].items()}
    try:
        for i, (frame, saved) in enumerate(zip(frames, raw['poses'])):
            now = frame['sim_time']
            data = (args.run/frame['path']).read_bytes()
            assert hashlib.sha256(data).hexdigest() == frame['sha256']
            rgb = np.asarray(Image.open(io.BytesIO(data)).convert('RGB'))
            verdict, _ = frame_gate.gate().assess({**frame, 'image': base64.b64encode(data).decode()}, 'r3', now, ob=False)
            assert verdict != frame_gate.INVALID, (now, verdict)
            rep = provider.on_frame(now, rgb if verdict == frame_gate.VALID else None)
            err = max(abs(rep.x_m-saved['x']), abs(rep.y_m-saved['y']), abs(rep.yaw_rad-saved['yaw']))
            maximum = max(maximum, err)
            mismatch += err > 1e-12
            checked += 1
            if round(now, 6) in relooks:
                provider.begin_relocalization(now, servo)
            for row in commands.get(round(now, 6), []):
                provider.on_command(row)
                if row['kind'] == 'arm':
                    servo[row['servo_id']] = row['pulse']
                elif row['kind'] == 'look':
                    servo[6] = row['pan_pulse']
            if i % 1000 == 0:
                print(json.dumps({'frame': i, 't': now, 'max_pose_delta': maximum}), flush=True)
        (args.output/'gates.json').write_text(json.dumps(gates, indent=1)+'\n')
        summary = {'source': str(args.run), 'candidate': args.candidate,
                   'student_record_sha256': hashlib.sha256((args.run/'student_record.json').read_bytes()).hexdigest(),
                   'poses_compared': checked, 'poses_different_above_1e12': mismatch, 'max_pose_delta': maximum,
                   'scans': len(gates), 'physics_runs': 0, 'model_calls': 0}
        (args.output/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
        print(json.dumps(summary), flush=True)
    finally:
        provider.close()
        undo()


if __name__ == '__main__':
    main()
