"""Terminal release review on gcp3 CPU: native own RGB and evaluator-only top.

No stepping, contacts, controller observation, or inferred missing state. The
frozen runner may omit its final state sample; show a labelled blank top there.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import socket
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--world', type=int, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--asset-root', type=Path, required=True)
    a = p.parse_args()
    assert socket.gethostname().split('.')[0] == 'ugrp-act-l4-gcp3'
    receipt = json.loads(a.run.with_suffix('.receipt.json').read_text())
    assert isinstance(receipt['exit_code'], int)
    summary = json.loads((a.run / 'summary.json').read_text())
    assert summary['flow'] == 'release'
    os.environ.update(MUJOCO_GL='osmesa', LP_NUM_THREADS='1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
    os.chdir(a.asset_root)
    import numpy as np
    import mujoco
    from PIL import Image, ImageDraw

    world = a.run / f'world-{a.world:03d}'
    state_path = a.run / f'world-{a.world:03d}-states.npz'
    states = np.load(state_path)
    index = {int(t): i for i, t in enumerate(states['ticks'])}
    assert index
    origin = summary['native_initialization_only_sim_s'][a.world]
    model = mujoco.MjModel.from_xml_string((world / 'raw/scene.xml').read_text())
    data = mujoco.MjData(model)
    roots = [model.body_rootid[model.body(name).id] for name in ('r1__robot', 'r2__robot', 'cargo_beam_1')]
    gids = np.flatnonzero(np.isin(model.body_rootid[model.geom_bodyid], roots) & np.isin(model.geom_group, [0, 1, 2, 3]))
    low, high = np.full(3, np.inf), np.full(3, -np.inf)
    for qpos in states['qpos']:
        data.qpos[:] = qpos
        mujoco.mj_kinematics(model, data)
        xyz, radius = data.geom_xpos[gids], model.geom_rbound[gids, None]
        low, high = np.minimum(low, (xyz-radius).min(axis=0)), np.maximum(high, (xyz+radius).max(axis=0))
    cid = model.camera('cctv_top').id
    half, centre = (high-low)/2, (high+low)/2
    tan_v = math.tan(math.radians(float(model.cam_fovy[cid]))/2)
    # Same evaluation-only overview fit as the existing warp4 playback helper;
    # no physical or acceptance constant is changed.
    model.cam_pos[cid] = [centre[0], centre[1], high[2]+max(half[0]/(tan_v*4/3)*320/318, half[1]/tan_v*240/238)]
    model.cam_quat[cid] = [1., 0., 0., 0.]
    renderer = mujoco.Renderer(model, height=240, width=320)
    a.out.mkdir(parents=True, exist_ok=False)
    missing, source_files = set(), {str(state_path): digest(state_path)}

    def compose(t, images, target):
        canvas = Image.new('RGB', (960, 270), (20, 20, 20))
        draw = ImageDraw.Draw(canvas)
        tick = round(t*10)
        if tick in index:
            i = index[tick]
            data.qpos[:], data.qvel[:] = states['qpos'][i], states['qvel'][i]
            mujoco.mj_kinematics(model, data)
            mujoco.mj_camlight(model, data)
            data.cam_xpos[cid], data.cam_xmat[cid] = model.cam_pos[cid], np.eye(3).reshape(-1)
            renderer.update_scene(data, camera='cctv_top')
            canvas.paste(Image.fromarray(renderer.render()), (0, 30))
        else:
            missing.add(round(t, 8))
            draw.text((8, 100), 'top state not saved', fill='white')
        for k, rid in enumerate(('r1', 'r2'), 1):
            path = images[rid]
            source_files[str(path)] = digest(path)
            canvas.paste(Image.open(path).convert('RGB').resize((320, 240)), (k*320, 30))
            draw.text((k*320+4, 5), rid+' original own RGB', fill='white')
        draw.text((4, 5), f'+{t-origin:.1f} SIM / world{t:.1f}', fill='white')
        canvas.save(target, quality=86)

    def sheets(paths, name):
        for start in range(0, len(paths), 18):
            image = Image.new('RGB', (2880, 1620), (30, 30, 30))
            for j, path in enumerate(paths[start:start+18]):
                image.paste(Image.open(path), ((j%3)*960, (j//3)*270))
            image.resize((1920, 1080)).save(a.out / f'{name}-{start//18:02d}.jpg', quality=88)

    full, tail = a.out / 'full', a.out / 'tail'
    full.mkdir()
    tail.mkdir()
    full_paths, full_times = [], []
    for f in sorted((world / 'review-2hz/r1').glob('*.jpg')):
        t = origin + int(f.stem)/10
        target = full / f'{len(full_paths):05d}.jpg'
        compose(t, {rid: world / 'review-2hz' / rid / f.name for rid in ('r1', 'r2')}, target)
        full_paths.append(target)
        full_times.append(t)
    rows = json.loads((world / 'tail-10hz.json').read_text())
    assert full_paths and rows
    tail_paths = []
    for row in rows:
        target = tail / f'{len(tail_paths):05d}.jpg'
        compose(row['world_t'], {k: Path(v) for k, v in row['files'].items()}, target)
        tail_paths.append(target)
    renderer.close()
    sheets(full_paths, 'full-2hz')
    sheets(tail_paths, 'last10s-10hz')
    native = a.out / 'native-six'
    native.mkdir()
    picks = np.linspace(0, len(rows)-1, min(6, len(rows)), dtype=int)
    for j, i in enumerate(picks):
        for rid, path in rows[i]['files'].items():
            (native / f'{j:02d}-{rid}.jpg').write_bytes(Path(path).read_bytes())
    concat = a.out / 'full-tail.ffconcat'
    lines = ['ffconcat version 1.0']
    for path, t in zip(full_paths, full_times):
        if t < rows[0]['world_t']-1e-8:
            lines += ["file '"+str(path)+"'", 'duration '+str(.5/3)]
    for path in tail_paths:
        lines += ["file '"+str(path)+"'", 'duration '+str(.1/3)]
    concat.write_text('\n'.join(lines)+'\n')
    video = a.out / 'playback-full-tail-3x.mp4'
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', str(concat),
        '-r', '30', '-fps_mode', 'cfr', '-c:v', 'libx264', '-threads', '1', '-crf', '30',
        '-pix_fmt', 'yuv420p', str(video)], check=True)
    assert video.stat().st_size <= 8_000_000
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'quiet', '-show_format', '-show_streams', '-of', 'json', str(video)]))
    metadata = dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(), run=str(a.run), world=a.world,
        simulation_host='gcp3', analysis_host='gcp3_CPU', receipt=receipt, source_sha=summary['source_sha'],
        origin=origin, full_2hz_N=len(full_paths), full_SIM_range=[full_times[0]-origin, full_times[-1]-origin],
        tail_10hz_N=len(rows), tail_SIM_range=[rows[0]['world_t']-origin, rows[-1]['world_t']-origin],
        exact_top_missing_world_times=sorted(missing), native_six_world_times=[rows[i]['world_t'] for i in picks],
        source_file_sha256=source_files, video=dict(path=str(video), bytes=video.stat().st_size,
        sha256=digest(video), ffprobe=probe), script_sha256=digest(Path(__file__)),
        scope='native own RGB; top from saved qpos only; missing top is explicitly blank; no interpolation or physics step; verdict requires separate raw recount')
    (a.out / 'playback-meta.json').write_text(json.dumps(metadata, indent=2)+'\n')
    print(json.dumps({k:v for k,v in metadata.items() if k not in ('source_file_sha256','video')}))


if __name__ == '__main__':
    main()
