"""Oracle-only evaluation replay of S4 r3 issued commands, with no model client."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

CONDITIONS = ('no_comm', 'peer_ko', 'leader_ko', 'structured')
ROBOTS = ('r1', 'r2', 'r3')
BASE_SHA = '1ed6df46d342e55983ca8ad3af586995bed7d7d0'
ORIGINAL_SHA = '4ea229487b623bd3b5e5f4156a9b926aff2b852c'


def read(path):
    return json.loads(Path(path).read_text())


def rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n')


def audit_tape(raw):
    """Check global issue order against all three independent actuator logs."""
    tape = read(raw/'decision-command-links.json')
    frames = rows(raw/'robots/r1/frames.jsonl')
    start = frames[0]['sim_time']
    end = round(start+read(raw/'result.json')['check_sim_s'], 9)
    grouped = {}
    previous = start
    for row in tape:
        t = row['t']
        if t < previous-1e-8 or t > end+1e-8 or row['robot_id'] not in ROBOTS:
            raise ValueError('nonchronological or out-of-range original command')
        previous = t
        tick = round((t-start)/.05)
        if abs(start+tick*.05-t) > 1e-8:
            raise ValueError('command outside original 0.05s clock')
        grouped.setdefault(tick, []).append(row)
    for rid in ROBOTS:
        actual = rows(raw/f'robots/{rid}/commands.jsonl')
        prefix = [row for row in actual if row['t'] < start-1e-8]
        reconstructed = prefix+[
            {'t':row['t'], **row['action']} for row in tape if row['robot_id']==rid
        ]+[{'t':end, 'kind':'hold'}]
        if reconstructed != actual:
            raise ValueError('global command tape does not reproduce '+rid+' log')
    return start, end, grouped


def message_timeline(raw):
    """Use recorded acceptance times (relative to stage), never request times."""
    events = []
    for row in read(raw/'llm/actions.json'):
        if row['kind'] != 'claim_order':
            continue
        args = row['arguments']
        text = f"{row['actor']} claim {args.get('order_id')} {args.get('role')}"
        if not row['accepted']:
            text += ' [rejected]'
        events.append((row['submitted_at_sim_s'], text))
    for row in read(raw/'pair-handshake.json')['decisions']:
        action = row['action']; choice = action.get('choice')
        if choice not in ('go', 'ack_go'):
            continue
        text = f"{row['robot_id']} {'GO' if choice=='go' else 'ACK'} epoch={action.get('epoch')}"
        if choice == 'ack_go':
            text += ' -> '+str(action.get('peer_go_ref'))
        if not row['accepted']:
            text += ' [rejected]'
        events.append((row['at'], text))
    return sorted(events, key=lambda event:event[0])


def latest_message(events, relative):
    eligible = [event for event in events if event[0] <= relative+1e-8]
    if not eligible:
        return 'LLM: waiting for claim'
    t, message = eligible[-1]
    return f'LLM @{t:.2f}s: {message}'


class Video:
    """Observer model and data are independent of the physical replay world."""
    def __init__(self, host, condition, start, events):
        import mujoco
        from PIL import ImageFont
        self.mj, self.condition, self.start, self.events = mujoco, condition, start, events
        self.model = mujoco.MjModel.from_xml_path(str(host.out/'scene.xml'))
        self.model.vis.global_.offwidth = max(960, self.model.vis.global_.offwidth)
        self.model.vis.global_.offheight = max(444, self.model.vis.global_.offheight)
        self.model.vis.global_.fovy = 32
        self.data = mujoco.MjData(self.model)
        self.renderer = mujoco.Renderer(self.model, height=444, width=960)
        self.camera = mujoco.MjvCamera()
        self.camera.type = mujoco.mjtCamera.mjCAMERA_FREE
        self.camera.lookat[:] = (2.175, -.85, .12)
        self.camera.distance, self.camera.azimuth, self.camera.elevation = 8., 90., -60.
        font = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
        self.font = ImageFont.truetype(font, 17)
        self.next_t, self.frames = start, 0
        self.output = host.out.parent/'overview.mp4'
        self.process = subprocess.Popen([shutil.which('ffmpeg'), '-nostdin', '-n', '-v', 'error',
            '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '1280x480', '-r', '20', '-i', '-',
            '-an', '-c:v', 'libx264', '-threads', '1', '-preset', 'veryfast', '-crf', '20',
            '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(self.output)], stdin=subprocess.PIPE)

    def frame(self, host, own):
        import numpy as np
        from PIL import Image, ImageDraw
        if host.now+1e-8 < self.next_t:
            return
        self.mj.mj_copyData(self.data, host.world.model, host.world.data)
        self.renderer.update_scene(self.data, camera=self.camera)
        canvas = Image.new('RGB', (1280, 480), '#101820')
        canvas.paste(Image.fromarray(self.renderer.render()), (0,36))
        draw = ImageDraw.Draw(canvas)
        relative = round(host.now-self.start, 8)
        draw.text((8,8), f'{self.condition} | SIM+{relative:.2f}s (t={host.now:.2f}s)',
                  font=self.font, fill='#f4f8ff')
        text = latest_message(self.events, relative)
        while draw.textlength(text, font=self.font) > 850:
            text = text[:-4]+'...'
        draw.text((420,8), text, font=self.font, fill='#f9d36b')
        for i, rid in enumerate(('r1','r2')):
            y = 36+i*222
            draw.text((970,y+3), rid+' own RGB', font=self.font, fill='#f4f8ff')
            image = Image.fromarray(own[rid][1])
            image.thumbnail((320,200), Image.Resampling.LANCZOS)
            canvas.paste(image, (960+(320-image.width)//2, y+22+(200-image.height)//2))
        self.process.stdin.write(np.asarray(canvas).tobytes())
        self.frames += 1
        self.next_t += .2  # 5 SIM frames/s, 20 playback frames/s: fourfold.

    def close(self):
        try:
            self.process.stdin.close()
            if self.process.wait(timeout=30) or not self.frames:
                raise RuntimeError('overview encoder failed')
        finally:
            if self.process.poll() is None:
                self.process.kill()
                self.process.wait()
            self.renderer.close()


def run(original, output, execution_sha, *, path_check=False):
    import numpy as np
    import mujoco
    from sim.s4_pair_live import PhysicsBackend
    from scripts.run_s3_alignment_probe import restore_scene
    from harness.zone_pair_highpose_exact_speedups import install
    original = Path(original); raw = original/'raw'
    start, end, grouped = audit_tape(raw)
    b = read(raw/'bundle.json'); condition = b['condition']
    if b['source_sha'] != ORIGINAL_SHA or condition not in CONDITIONS:
        raise ValueError('wrong S4 r3 original source/condition')
    root = Path(__file__).resolve().parents[1]
    checked = {}
    for path, expected in b['source_sha256'].items():
        if path.startswith(('sim/','harness/','scripts/','configs/')):
            checked[path] = sha(root/path)
            if checked[path] != expected:
                raise ValueError('original replay dependency changed: '+path)
    output.mkdir(parents=True, exist_ok=False)
    summary = dict(condition=condition, status='RUNNING', execution_sha=execution_sha,
        base_sha=BASE_SHA, original_source_sha=ORIGINAL_SHA, original_path=str(original),
        original_outcome=read(raw/'result.json')['status'], source_sha256=checked,
        model_calls=0, evaluation_only=True, controller_run=False, physics_correction=False,
        loadavg_start=os.getloadavg(), start_sim_s=start, end_sim_s=end,
        subtitle_time_basis='recorded stage-relative acceptance time; SIM+ label, absolute t also shown',
        playback_speed=4, width=1280, height=480)
    backend = video = None; issued = []; began = time.monotonic(); _, undo = install('v98-exact-v6')
    try:
        backend = PhysicsBackend(b, output, seed=b['seed'])
        backend.reset(b['reset_cap_s'])
        restore_scene(backend, read(raw/'eval_only/stage-setup.json'))
        if abs(backend.now-start) > 1e-8:
            raise ValueError('original stage start differs')
        spec = mujoco.mjtState.mjSTATE_INTEGRATION
        state = np.empty(mujoco.mj_stateSize(backend.world.model, spec))
        mujoco.mj_getState(backend.world.model, backend.world.data, state, spec)
        old = np.load(raw/'eval_only/stage-integration-state.npz')['state']
        summary['initial_state_exact'] = bool(np.array_equal(old, state))
        if not summary['initial_state_exact']:
            raise ValueError('initial integration state differs; no state correction applied')
        backend.set_deadline(end)
        video = Video(backend, condition, start, message_timeline(raw))
        frame_times = {round(row['sim_time'],9) for row in rows(raw/'robots/r1/frames.jsonl')}
        steps = round((end-start)/.05)
        if path_check:
            steps = min(steps, 1)
        for i in range(steps+1):
            backend.eval_sample()
            if round(backend.now,9) in frame_times:
                own = backend.capture()  # same original 20Hz RGB/presentation calls
                video.frame(backend, own)
            for row in grouped.get(i, []):
                backend.issue(row['robot_id'], row['action'])
                issued.append(dict(t=backend.now, robot_id=row['robot_id'], action=row['action']))
            if i%20 == 0:
                write(output.parent/'health.json', dict(status='RUNNING', absolute_sim_s=backend.now,
                    relative_sim_s=round(backend.now-start,8), wall_s=time.monotonic()-began,
                    video_frames=video.frames, pid=os.getpid(), loadavg=os.getloadavg()))
            if i < steps:
                backend.advance_to(start+(i+1)*.05)
        for rid in ROBOTS:
            backend.issue(rid, {'kind':'hold'})  # original finally block, same order
        summary['status'] = 'PATH_CHECK' if path_check else 'COMPLETED'
    except Exception:
        import traceback
        summary.update(status='HOST_ERROR', error=traceback.format_exc())
    finally:
        for name, closer in [('video', video.close if video else None),
                             ('backend', backend.close if backend else None), ('speedups', undo)]:
            if closer is not None:
                try:
                    closer()
                except Exception:
                    import traceback
                    summary.update(status='HOST_ERROR')
                    summary.setdefault('cleanup_errors', {})[name] = traceback.format_exc()
        if video is not None:
            summary['video_frames'] = video.frames
        summary.update(wall_s=time.monotonic()-began, loadavg_end=os.getloadavg())
        if summary['status'] == 'COMPLETED':
            canonical = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            original_tape = [dict(t=r['t'], robot_id=r['robot_id'], action=r['action'])
                             for r in read(raw/'decision-command-links.json')]
            write(output/'replayed-command-order.json', issued)
            summary['global_command_order'] = dict(original=canonical(original_tape), replay=canonical(issued))
            summary['commands'] = {r:dict(original=sha(raw/f'robots/{r}/commands.jsonl'),
                replay=sha(output/f'robots/{r}/commands.jsonl')) for r in ROBOTS}
            summary['command_trajectory_match'] = (all(x['original']==x['replay'] for x in summary['commands'].values())
                and summary['global_command_order']['original']==summary['global_command_order']['replay'])
            summary['evaluation_trajectories'] = {r:dict(original=sha(raw/f'eval_only/{r}/trajectory.jsonl'),
                replay=sha(output/f'eval_only/{r}/trajectory.jsonl')) for r in ROBOTS}
            summary['evaluation_trajectory_match'] = all(x['original']==x['replay'] for x in summary['evaluation_trajectories'].values())
            summary['video_sha256'] = sha(video.output)
        write(output.parent/'summary.json', summary)
        write(output.parent/'health.json', dict(status=summary['status'], wall_s=summary['wall_s']))
    print(json.dumps({k:summary.get(k) for k in ('condition','status','command_trajectory_match','evaluation_trajectory_match','error')}))
    return int(summary['status']=='HOST_ERROR')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--original', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--path-check', action='store_true')
    a = p.parse_args()
    from scripts.run_s3_x86_probe import archive_guard
    archive_guard(a.expected_source_sha, a.output)
    if os.environ.get('LP_NUM_THREADS') != '4':
        raise ValueError('original LP_NUM_THREADS=4 required')
    return run(a.original, a.output, a.expected_source_sha, path_check=a.path_check)


if __name__ == '__main__':
    raise SystemExit(main())
