"""gcp3 CPU: compare frozen perception on native RGB and same-state C RGB.

No physics stepping or control execution. C RGB is evaluation-only. Both
image paths retain the original fisheye remap and JPEG quality; the C path
also applies the frozen no_mip_v1 context settings.
"""
import argparse
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys


def read(path):
    return json.loads(path.read_text() if path.exists() else
                      subprocess.check_output(['zstd', '-qdc', str(path) + '.zst'], text=True))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--world', type=int, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    assert socket.gethostname().split('.')[0] == 'ugrp-act-l4-gcp3'
    assert not a.out.exists()
    os.environ.update(MUJOCO_GL='osmesa', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', LP_NUM_THREADS='1')
    sys.path.insert(0, str(a.source))
    os.chdir(a.source)
    import cv2
    import mujoco
    import numpy as np
    from PIL import Image
    from scripts import run_grasp_act_release as frozen
    from sim.lookaround_localization import LookaroundLocalizer
    from sim.camera_render_quality import configure_model, configure_context, sampling_stages

    world = a.run / f'world-{a.world:03d}'
    raw = world / 'raw'
    result = read(raw / 'result.json')
    plan = read(raw / 'plan.json')
    static = frozen.make_scene(plan).config['static_map']
    states = np.load(a.run / f'world-{a.world:03d}-states.npz')
    indices = {int(t): i for i, t in enumerate(states['ticks'])}
    model = mujoco.MjModel.from_xml_string((raw / 'scene.xml').read_text())
    width, height = configure_model(model, 'no_mip_v1')
    data = mujoco.MjData(model)
    renderer = mujoco.Renderer(model, height=height, width=width)
    quality = configure_context(renderer, model, 'no_mip_v1')
    a.out.mkdir(parents=True)
    reports = {}
    source_files = {}
    for rid, recorded in result['lookaround_result'].items():
        localizers = {kind: LookaroundLocalizer(static, [0., 0., 0.], mode='setdown_global_v1',
            map_pose_known=False, odometry_profile=result['effective_motion_profile'],
            localization_support=result['localization_support']) for kind in ('native', 'C_same_state')}
        rows = []
        for n, view in enumerate(recorded['localizer']['views']):
            tick = round(view['t'] * 10)
            assert tick in indices, 'never interpolate missing saved state'
            native_path = raw / view['input_jpeg']
            native_bytes = native_path.read_bytes()
            source_files[str(native_path)] = hashlib.sha256(native_bytes).hexdigest()
            native = np.asarray(Image.open(io.BytesIO(native_bytes)).convert('RGB'))
            k = indices[tick]
            data.qpos[:], data.qvel[:] = states['qpos'][k], states['qvel'][k]
            mujoco.mj_kinematics(model, data)
            mujoco.mj_camlight(model, data)
            renderer.update_scene(data, camera=rid + '__robot_cam')
            image = sampling_stages(renderer.render().copy(), 'no_mip_v1')['final']
            buffer = io.BytesIO()
            Image.fromarray(image).save(buffer, format='JPEG', quality=82)
            c_jpeg = buffer.getvalue()
            c_path = a.out / f'{rid}-{n:02d}-C.jpg'
            c_path.write_bytes(c_jpeg)
            c_rgb = np.asarray(Image.open(io.BytesIO(c_jpeg)).convert('RGB'))
            servo = {int(key): value for key, value in view['servo'].items()}
            measures = {}
            for kind, rgb in (('native', native), ('C_same_state', c_rgb)):
                loc = localizers[kind]
                loc.command_own.x = np.asarray(view['command_pose'])
                rec = loc.observe(view['t'], rgb, servo)
                measures[kind] = {key: rec.get(key) for key in ('status', 'wall_points', 'floor_lines', 'doors')}
            rows.append(dict(t=view['t'], recorded={key: view.get(key) for key in ('status', 'wall_points', 'floor_lines', 'doors')},
                             observations=measures, C_jpeg_sha256=hashlib.sha256(c_jpeg).hexdigest()))
        reports[rid] = dict(rows=rows, recorded_decision=recorded['localizer']['decision'],
            decisions={kind: loc.finalize(view_start=0) for kind, loc in localizers.items()})
    renderer.close()
    output = dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(), host='gcp3_CPU', run=str(a.run), world=a.world,
        source=str(a.source), mujoco=mujoco.__version__, cv2=cv2.__version__, quality=quality,
        source_file_sha256=source_files, reports=reports, physics_steps=0,
        controller_execution=0, scope='offline image/perception comparison only; no physical success verdict')
    (a.out / 'summary.json').write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps({rid: {kind: {key: decision.get(key) for key in ('accepted','reason','groups','score_gap')}
                           for kind, decision in row['decisions'].items()} for rid, row in reports.items()}))


if __name__ == '__main__':
    main()
