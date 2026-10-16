"""GCP-only evaluation playback from saved 10 Hz qpos, without a controller.

No physics steps, planning, interpolation or new observations enter a teacher.
The overview uses evaluator state only. Own camera calibration is restored from
camera-runtime.json; the original 1 Hz JPEGs remain available for comparison.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

from scripts.audit_beampair1 import read, read_bytes


def review(raw, out):
    if sys.platform != 'linux':
        raise RuntimeError('GCP only; no Mac rendering')
    os.environ.setdefault('MUJOCO_GL', 'osmesa')
    import mujoco
    import numpy as np
    from PIL import Image, ImageDraw

    out.mkdir(parents=True, exist_ok=False)
    data, _, _ = read_bytes(raw / 'eval-only.jsonl')
    rows = [json.loads(x) for x in data.splitlines() if x.strip()]
    plan = read(raw / 'plan.json')
    ring_root = raw.parent / 'adapter/failure-tail'
    ring = read(ring_root / 'manifest.json') if (ring_root / 'manifest.json').exists() or Path(str(ring_root / 'manifest.json')+'.zst').exists() else {'frames': []}
    originals = {(round(f['t'], 5), f['robot']): ring_root / f['path'] for f in ring['frames']}
    for f in ring['frames']:
        if hashlib.sha256((ring_root/f['path']).read_bytes()).hexdigest() != f['sha256']:
            raise ValueError('original tail frame hash mismatch')
    original_used = 0
    labels = {rid: [json.loads(x) for x in read_bytes(raw / f'teacher-{rid}.jsonl')[0].splitlines()]
              for rid in plan['roles']}
    model = mujoco.MjModel.from_xml_string((raw/'scene.xml').read_text())
    state = mujoco.MjData(model)
    camera_ids = {}
    for rid, calibration in read(raw / 'camera-runtime.json')['cameras'].items():
        candidates = [i for i in range(model.ncam)
                      if model.camera(i).name.startswith(rid + '__')]
        if len(candidates) != 1:
            raise ValueError(f'ambiguous own camera {rid}: {candidates}')
        cid = candidates[0]
        camera_ids[rid] = cid
        for attr in ('pos', 'quat', 'intrinsic', 'resolution'):
            getattr(model, 'cam_' + attr)[cid] = calibration[attr]
    # Evaluation-only fixed framing derived from the saved trajectory bounds.
    xy = np.array([row['robots'][r]['pose'][:2] for row in rows for r in plan['roles']]
                  + [v[:2] for row in rows for v in row['beam']['ends'].values()])
    center = (xy.min(axis=0) + xy.max(axis=0)) / 2
    overview = mujoco.MjvCamera()
    overview.lookat[:] = [*center, 0]
    overview.distance = max(float(np.ptp(xy, axis=0).max()) * 1.3, 1.)
    overview.azimuth = 90
    overview.elevation = -90
    renderer = mujoco.Renderer(model, height=240, width=320)
    from sim.camera_render_quality import configure_context
    configure_context(renderer,model,'no_mip_v1')
    import cv2
    from sim.masterpi_camera_profile import raw_fisheye_remap
    mx,my=raw_fisheye_remap(320,240)
    own_option=mujoco.MjvOption();own_option.geomgroup[:]=1;own_option.geomgroup[4]=0;own_option.geomgroup[5]=0
    for rid in ('r1','r2','r3'):
        for name in ('camera_bracket','camera_body','camera_lens_visual'):
            gid=mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_GEOM,rid+'__'+name)
            if gid>=0:model.geom_group[gid]=5
    origin = rows[0]['t']
    duration = rows[-1]['t'] - origin
    full, tail, timeline, frame_hashes = [], [], [], []
    max_body_error = 0.
    video = out / 'playback-3x.mp4'
    command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-threads', '1',
               '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '960x272', '-r', '30',
               '-i', 'pipe:0', '-an', '-c:v', 'libx264', '-threads', '1',
               '-preset', 'fast', '-crf', '28', '-pix_fmt', 'yuv420p',
               '-movflags', '+faststart', str(video)]
    proc = subprocess.Popen(command, stdin=subprocess.PIPE)
    try:
        for i, row in enumerate(rows):
            state.qpos[:] = row['joints']
            state.time = row['t']
            mujoco.mj_forward(model, state)
            for rid, v in row['robots'].items():
                max_body_error = max(max_body_error,
                    float(np.max(np.abs(state.body(rid + '__robot').xpos - v['xyz']))))
            canvas = Image.new('RGB', (960, 272))
            for k, camera in enumerate([overview, camera_ids['r1'], camera_ids['r2']]):
                original = originals.get((round(row['t'], 5), 'r'+str(k))) if k else None
                if original is not None:
                    canvas.paste(Image.open(original).convert('RGB').resize((320,240)), (320*k,0))
                    original_used += 1
                else:
                    renderer.update_scene(state, camera=camera,scene_option=own_option if k else None)
                    pixels=renderer.render().copy()
                    if k:pixels=cv2.remap(pixels,mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
                    canvas.paste(Image.fromarray(pixels), (320 * k, 0))
            elapsed = row['t'] - origin
            draw = ImageDraw.Draw(canvas)
            phases = {r: labels[r][i]['teacher_phase'] if i < len(labels[r]) else 'no_command_exception_tick'
                      for r in plan['roles']}
            draw.text((4, 242), f'SIM {elapsed:.1f} / world {row["t"]:.1f} | EVAL overview; own RGB tail / qpos elsewhere | 3x', fill='white')
            draw.text((4, 257), 'overview EVAL ONLY | ' + ' | '.join(
                f'{r}={end} {phases[r]}' for r, end in plan['roles'].items()), fill='yellow')
            proc.stdin.write(canvas.tobytes())
            if i % 5 == 0 or i == len(rows) - 1:
                full.append((elapsed, canvas.copy()))
                timeline.append(dict(elapsed_sim_s=elapsed, world_t=row['t'], roles=plan['roles'],
                    phases=phases, evidence={r: [m for m in row.get('visible_measurements', {}).get(r, [])
                        if m['id'] == 'band_' + plan['roles'][r]] for r in plan['roles']},
                    evaluator_nearest_ends={r: min(row['beam']['ends'], key=lambda end:
                        math.dist(row['robots'][r]['pose'][:2], row['beam']['ends'][end][:2]))
                        for r in plan['roles']}, evaluator_only=True))
            if elapsed >= duration - 10 - 1e-6:
                tail.append((elapsed, canvas.copy()))
            if i % 10 == 0:
                # Separate rendering from original JPEG decoding. Never claim
                # byte equality between these two image formation paths.
                frame_hashes.append(dict(t=row['t'], qpos_sha256=hashlib.sha256(
                    np.asarray(row['joints'], dtype='<f8').tobytes()).hexdigest()))
    finally:
        proc.stdin.close()
        code = proc.wait()
        renderer.close()
    if code:
        raise RuntimeError('ffmpeg failed')
    if video.stat().st_size > 8_000_000:
        raise RuntimeError('video exceeds user 8 MB limit')
    sheets = []
    for name, items, hz in [('full', full, 2), ('tail', tail, 10)]:
        for page, start in enumerate(range(0, len(items), 24)):
            selected = items[start:start + 24]
            sheet = Image.new('RGB', (1920, 44 + 136 * 6))
            draw = ImageDraw.Draw(sheet)
            draw.text((5, 5), f'{raw.parent.name} {name} {hz}Hz | saved qpos / calibrated own cameras | evaluation only', fill='white')
            for j, (t, canvas) in enumerate(selected):
                sheet.paste(canvas.resize((480, 136)), ((j % 4) * 480, 44 + (j // 4) * 136))
            path = out / f'{name}-{page + 1:02d}.jpg'
            sheet.save(path, quality=92)
            sheets.append(dict(file=path.name, times=[t for t, _ in selected], hz=hz))
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-count_frames',
        '-show_entries', 'stream=width,height,nb_read_frames,duration', '-of', 'json', str(video)]))
    sources = [raw / 'scene.xml', raw / 'camera-runtime.json', raw / 'plan.json']
    for name in ('eval-only.jsonl', 'teacher-r1.jsonl', 'teacher-r2.jsonl'):
        p = raw / name
        sources.append(p if p.exists() else Path(str(p) + '.zst'))
    if originals:
        p = ring_root/'manifest.json'
        sources.append(p if p.exists() else Path(str(p)+'.zst'))
    result = dict(raw=str(raw), seed=plan['seed'], roles=plan['roles'],
        original_own_rgb_frames_used=original_used,
        original_failure_tail_root=str(ring_root) if originals else None,
        assignment_source=plan['assignment_source'], origin_world_t=origin,
        duration_sim_s=duration, saved_eval_rows=len(rows), max_body_xyz_error_m=max_body_error,
        video=str(video), video_bytes=video.stat().st_size, ffprobe=probe,
        video_sha256=hashlib.sha256(video.read_bytes()).hexdigest(),
        sources={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        timeline=timeline, sheets=sheets, qpos_hashes=frame_hashes,
        scope=('Evaluation overview qpos rendering; original 10Hz own RGB for saved failure tail, calibrated qpos own rendering elsewhere. '
               if originals else 'Evaluation saved-state rendering; original own JPEGs are 1Hz; qpos is 10Hz. ')
              +'No physics/controller rerun or inferred motion frames. Qpos own views use original raw_fisheye_remap and actor geomgroup masks; native tail originals kept.',
        direct_visual_review_completed=False)
    (out / 'review.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('seed', 'duration_sim_s', 'saved_eval_rows', 'max_body_xyz_error_m', 'video_bytes')}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    review(a.raw, a.out)
