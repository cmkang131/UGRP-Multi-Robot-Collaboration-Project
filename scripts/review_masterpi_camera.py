"""Finite offline image audit / locked static MuJoCo render; no control or model calls.

This reads an existing standard Scene artifact, not a new mission launch path.
Evaluation poses are used only for diagnostic reconstruction, never control.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PRIMARY = Path('/Users/changmin/projects/ugrp')
LOCK = PRIMARY / 'scripts/agent_lock.py'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, data):
    with Path(path).open('x') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def rows(path):
    return [json.loads(s) for s in Path(path).read_text().splitlines()]


def cyan_metrics(bgr):
    import cv2
    import numpy as np
    from harness.zone_color_boxes import _mask, OWN_ZONE_CYAN_HSV
    from sim.masterpi_camera_profile import raw_fisheye_remap
    h, w = bgr.shape[:2]
    mask = _mask(cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV), OWN_ZONE_CYAN_HSV).astype(bool)
    mx, my = raw_fisheye_remap(w, h)
    valid = (mx >= 0) & (mx <= w-1) & (my >= 0) & (my <= h-1)
    return {'cyan_pixels': int(mask.sum()), 'full_pixels': h*w,
            'valid_pixels': int(valid.sum()), 'full_fraction': float(mask.mean()),
            'valid_fraction': float(np.sum(mask & valid)/valid.sum())}


def carry_frames(source):
    from harness.zone_pair_highpose import HIGH
    record = json.loads((source/'student_record.json').read_text())
    events = [e for e in record['events'] if e['event'] == 'state']
    times = [e['t'] for e in events]
    selected = []
    for frame in rows(source/'robots/r3/frames.jsonl'):
        index = bisect.bisect_right(times, frame['sim_time']) - 1
        if index < 0 or events[index]['state'] != 'carry':
            continue
        if all(frame['commanded_servo'].get(str(k)) == v for k, v in HIGH.items()):
            selected.append(frame)
    return selected


def analyze(source, out):
    import cv2
    import numpy as np
    selected = carry_frames(source)
    if not selected:
        raise ValueError('no HIGH carry frames')
    metrics = []
    for f in selected:
        p = source/f['path']
        if sha(p) != f['sha256']:
            raise ValueError('source image hash mismatch: '+str(p))
        metrics.append({'path': f['path'], 'sha256': f['sha256'], 't': f['sim_time'],
                        **cyan_metrics(cv2.imread(str(p)))})
    with (out/'frames.jsonl').open('x') as stream:
        for row in metrics:
            stream.write(json.dumps(row)+'\n')
    summary = {'source': str(source), 'source_sha': json.loads((source/'result.json').read_text())['source_sha'],
               'selection': 'all recorded r3 frames in controller carry state with issued HIGH PWM',
               'mask': 'unchanged OWN_ZONE_CYAN_HSV; image colour occupancy, not semantic wall visibility',
               'frames': len(metrics), 'frames_sha256': sha(out/'frames.jsonl'),
               'model_calls': 0, 'commands': 0}
    for key in ('full_fraction', 'valid_fraction'):
        v = np.asarray([m[key] for m in metrics])
        summary[key] = dict(zip(('min', 'median', 'max'), map(float, (v.min(), np.median(v), v.max()))))
    summary['input_hashes'] = {s: sha(source/s) for s in
        ('student_record.json', 'robots/r3/frames.jsonl', 'result.json')}
    write(out/'summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False))


def lock_command(*args):
    p = subprocess.run([sys.executable, str(LOCK), *args], check=True, capture_output=True, text=True)
    return json.loads(p.stdout)


def render(source, out):
    # Status checked immediately before atomic acquisition; another Codex is NOT us.
    if lock_command('status') is not None:
        raise RuntimeError('shared physics lock occupied; no render attempted')
    identity = lock_command('acquire', '--owner', 'codex', '--branch', 'codex/robot-camera-review',
        '--purpose', 'six static camera review frames; no mj_step', '--pid', str(os.getpid()),
        '--expected-minutes', '1')
    write(out/'lock-acquire.json', identity)
    try:
        _render_locked(source, out)
    finally:
        held = lock_command('status')
        if held and held.get('pid') == os.getpid() and held.get('branch') == identity['branch']:
            write(out/'lock-release.json', lock_command('release', '--owner', 'codex'))
        else:
            raise RuntimeError('lock ownership changed; refusing release')


def _render_locked(source, out):
    import math
    import time
    import cv2
    import mujoco
    import numpy as np
    from sim.masterpi_camera_review_v1 import PROFILE_ID, transform_xml, record
    from sim.masterpi_camera_profile import raw_fisheye_remap, mujoco_pixel_intrinsic
    from sim.masterpi_dynamics_v2 import MasterPiDynamicsV2
    from harness.zone_pair_highpose import HIGH
    start = time.monotonic()
    xml = (source/'scene.xml').read_text()
    setup = json.loads((source/'eval_only/setup.json').read_text())
    trajectory = rows(source/'eval_only/trajectory.jsonl')
    frames = carry_frames(source)
    results = []
    for profile in ('baseline', PROFILE_ID):
        applied = xml if profile == 'baseline' else transform_xml(xml, profile_id=profile)
        (out/(profile+'.xml')).write_text(applied)
        model = mujoco.MjModel.from_xml_string(applied)
        cid = model.camera('r3__robot_cam').id
        # Same post-compile intrinsic configuration as the production renderer.
        model.cam_resolution[cid] = [640, 480]
        model.cam_sensorsize[cid] = [640, 480]
        model.cam_intrinsic[cid] = mujoco_pixel_intrinsic(640, 480)
        option = mujoco.MjvOption()
        option.geomgroup[:] = 1
        option.geomgroup[4:6] = 0
        renderer = mujoco.Renderer(model, height=480, width=640)
        try:
            for t in (105., 180., 270.):
                sample = min(trajectory, key=lambda r: abs(r['t']-t))
                frame = min(frames, key=lambda r: abs(r['sim_time']-t))
                if abs(sample['t']-t) > .11 or abs(frame['sim_time']-t) > .051:
                    raise ValueError('missing preselected carry sample')
                data = mujoco.MjData(model)
                for rid, spawn in setup['spawns'].items():
                    adr = model.jnt_qposadr[model.joint(rid+'__base_free').id]
                    data.qpos[adr:adr+3] = spawn[:3]
                    data.qpos[adr+3:adr+7] = [math.cos(spawn[3]/2), 0, 0, math.sin(spawn[3]/2)]
                adr = model.jnt_qposadr[model.joint('r3__base_free').id]
                data.qpos[adr:adr+3] = sample['robot_xyz_m']
                yaw = sample['robot_yaw_rad']
                data.qpos[adr+3:adr+7] = [math.cos(yaw/2), 0, 0, math.sin(yaw/2)]
                target = MasterPiDynamicsV2.pulse_to_joint_targets(
                    SimpleNamespace(physical_params={'servo6_center_pwm': 1500}), {**HIGH, 1: 1500})
                names = {'yaw': 'arm_yaw', 'shoulder': 'shoulder_pitch',
                         'elbow': 'elbow_pitch', 'wrist': 'wrist_pitch'}
                for key, name in names.items():
                    data.qpos[model.jnt_qposadr[model.joint('r3__'+name).id]] = target[key]
                # Closed PWM targets, not measured finger positions. Both variants identical.
                for side in ('left', 'right'):
                    data.qpos[model.jnt_qposadr[model.joint('r3__'+side+'_gripper_close').id]] = target['gripper']
                obj = next(iter(setup['objects'].values()))
                adr = model.jnt_qposadr[model.joint(obj['joint_name']).id]
                data.qpos[adr:adr+3] = sample['cyan_xyz_m']
                q = np.empty(4)
                mujoco.mju_mat2Quat(q, np.array(sample['cyan_rotation']))
                data.qpos[adr+3:adr+7] = q
                mujoco.mj_forward(model, data)
                renderer.update_scene(data, camera=cid, scene_option=option)
                ideal = renderer.render().copy()
                rgb = cv2.remap(ideal, *raw_fisheye_remap(640, 480), cv2.INTER_LINEAR,
                                borderMode=cv2.BORDER_CONSTANT)
                name = f'{profile}-t{int(t)}.png'
                cv2.imwrite(str(out/name), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
                origin = data.cam_xpos[cid].copy()
                axes = data.cam_xmat[cid].reshape(3, 3)
                forward = -axes[:, 2]
                body = data.body('r3__gripper')
                cargo_tool = body.xmat.reshape(3, 3).T @ (np.array(sample['cyan_xyz_m'])-body.xpos)
                results.append({'profile': profile, 't': t, 'image': name, 'sha256': sha(out/name),
                    **cyan_metrics(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)),
                    'camera_parent': model.body(model.cam_bodyid[cid]).name,
                    'camera_pos_world_m': origin.tolist(), 'camera_forward_world': forward.tolist(),
                    'optical_pitch_world_deg': math.degrees(math.asin(forward[2])),
                    'cargo_centre_gripper_m': cargo_tool.tolist(),
                    'qpos_sha256': hashlib.sha256(data.qpos.tobytes()).hexdigest(),
                    'recorded_frame': frame['path'], 'recorded_frame_sha256': frame['sha256'],
                    'recorded_frame_metrics': cyan_metrics(cv2.imread(str(source/frame['path'])))})
        finally:
            renderer.close()
    write(out/'render-summary.json', {'schema': 'ugrp.camera-review.static.v1', 'profile': record(),
        'scope': 'static HIGH command pose plus recorded evaluation cargo/base; no dynamic replay, no hardware validation',
        'missing_state': 'actual arm joints/base roll-pitch/finger contact positions not recorded; commanded pose is not actual pose',
        'source_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'source_scene_sha256': sha(source/'scene.xml'), 'mujoco': mujoco.__version__,
        'results': results, 'mj_step_calls': 0, 'model_calls': 0, 'commands': 0,
        'wall_s': time.monotonic()-start, 'loadavg': os.getloadavg()})
    print(json.dumps(results))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['analyze', 'render'])
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    out = args.output.resolve()
    if not args.output.is_absolute() or not out.is_relative_to(PRIMARY/'outputs'):
        p.error('output must be an absolute path under primary outputs')
    out.mkdir(parents=True, exist_ok=False)
    (analyze if args.mode == 'analyze' else render)(args.source.resolve(), out)


if __name__ == '__main__':
    main()
