"""Initial s1052 own-RGB replay only; no world/physics/evaluation access."""
import argparse
import base64
import copy
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from harness import zone_solo_cyan_contract_v106 as c
from harness.zone_solo_cyan_global_start import Runtime, OPTION
from harness.zone_pair_highpose_exact_speedups import install
from harness import zone_pair_highpose_frame_gate as frame_gate

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def replay(option, out):
    if out.exists():
        raise ValueError('new output required')
    criteria = json.loads((HERE/'dock-global-criteria.json').read_text())
    raw = Path(criteria['raw'])
    read = lambda name: json.loads((raw/name).read_text())
    record = read('student_record.json'); bundle = read('bundle.json')
    commands = {}
    for row in record['commands']:
        commands.setdefault(round(row['t'], 6), []).append(row)
    frames = [json.loads(l) for l in (raw/'robots/r3/frames.jsonl').read_text().splitlines()]
    frames = [f for f in frames if f['sim_time'] < criteria['window_sim_s'][1]]
    exclude = ('drive_profile', 'stagnation_watch', 'idle_robot_contacts', 'dev_grasp_policy', 'eval_camera_trace')
    kwargs = {k: v for k, v in bundle['options'].items() if k not in exclude}
    kwargs.update(start_localization=option, motion_model=bundle['motion_model'],
        pulse_calibration=bundle['pulse_calibration'], extrinsic_calibration=bundle['extrinsic_calibration'],
        floor_appearance=bundle['floor_appearance'])
    _, undo = install('v98-exact-v6')
    runtime = Runtime(c.hp.resolve(c.MAP_ID)[0], ROOT/c.CALIBRATION, c.CALIBRATION_SHA, seed=1052, **kwargs)
    provider = runtime.pose
    provider.on_command(commands[round(frames[0]['sim_time'], 6)].pop(0))
    poses = []; particles = []; max_delta = 0.
    try:
        for f, old in zip(frames, record['poses']):
            now = f['sim_time']; data = (raw/f['path']).read_bytes()
            assert hashlib.sha256(data).hexdigest() == f['sha256']
            rgb = cv2.cvtColor(cv2.imdecode(np.frombuffer(data, np.uint8), 1), cv2.COLOR_BGR2RGB)
            verdict, _ = frame_gate.gate().assess({**f, 'image': base64.b64encode(data).decode()}, 'r3', now, ob=False)
            report = provider.on_frame(now, rgb if verdict == frame_gate.VALID else None)
            pf = provider.provider.loc._pf
            row = dict(t=now, t_est=report.t_est, x=report.x_m, y=report.y_m, yaw=report.yaw_rad,
                std_xy_m=report.std_xy_m, last_fix_t=report.last_fix_t,
                modes=copy.deepcopy(pf.estimate().get('global_modes')))
            poses.append(row)
            max_delta = max(max_delta, *(abs(row[k]-old[k]) for k in ('x','y','yaw','std_xy_m')))
            for cmd in commands.get(round(now, 6), []):
                assert not (cmd['kind'] in ('drive','mecanum') and any(cmd.get(k,0) for k in ('forward','left','turn')))
                provider.on_command(cmd)
        particles = pf.px.tolist()
        audit = copy.deepcopy(runtime.amcl_audit)
    finally:
        runtime.close(); undo()
    result = dict(option=option, poses=poses, particles_final=particles, amcl=audit,
        gt_inputs=False, physics_runs=0, model_calls=0, commands_fixed=True,
        active_spin_images_available=False, baseline_max_delta=max_delta,
        frame_count=len(frames), raw=str(raw),
        source_sha256=hashlib.sha256((ROOT/'harness/zone_solo_cyan_global_start.py').read_bytes()).hexdigest())
    out.write_text(json.dumps(result)+'\n')
    if option == 'off':
        assert max_delta == 0., 'default-off differs from saved execution'
    print(json.dumps(dict(option=option, frames=len(frames), updates=audit['updates'], max_delta=max_delta)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--start-localization', choices=['off', OPTION], default='off')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    replay(args.start_localization, args.output)
