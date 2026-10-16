"""Render a recorded run from the observer view, optionally with speech bubbles.

Observer-only post-run picture: it sets recorded qpos kinematically (no physics
step) and draws on the rendered *observer* frame. Nothing here is read by an
actor, controller or referee. Robot head positions come from the recorded
ground-truth free-joint qpos, which is fine for a picture for humans.

    python -m scripts.render_speech_bubble_video RUN_DIR OUT.mp4 \\
        --observer-overlay speech_bubbles_v1 --speed 4 --window 0:80

``--observer-overlay`` defaults to off; then the video has no bubbles. A
``.png`` output renders one still at ``--still-sim-s`` instead of a video.

While the models answer, the recorded SIM clock stands still (several messages
share one ``sim_time_s``). The video holds the scene at that SIM time and lets
the bubbles appear one after another (``--beat-seconds``), then lingers
(``--linger-seconds``). This changes only the video clock; the log is untouched.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re
import subprocess

from harness.communication_overlay import KOREAN_FONTS
from harness.speech_bubble_overlay import (
    SPEECH_BUBBLES_V1, ObserverCamera, SpeechBubbleOverlay, head_point, load_conversation,
    load_font, normalize_observer_overlay, presentation_timeline)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VIEW = {'lookat': [2.2, -2., .1], 'distance': 7.5, 'azimuth': 90, 'elevation': -60}


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _source_identity() -> dict:
    try:
        sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        dirty = bool(subprocess.check_output(['git', 'status', '--porcelain', '--', 'harness', 'scripts'],
                                             cwd=ROOT, text=True).strip())
        return {'git_sha': sha, 'dirty': dirty}
    except (OSError, subprocess.CalledProcessError):
        return {'git_sha': None, 'dirty': None}


def parse_window(text: str):
    match = re.fullmatch(r'\s*([0-9.]+)\s*:\s*([0-9.]+)\s*', text)
    if not match or float(match[2]) <= float(match[1]):
        raise argparse.ArgumentTypeError('window must be START:END in SIM seconds, END > START')
    return float(match[1]), float(match[2])


def parse_size(text: str):
    match = re.fullmatch(r'(\d+)x(\d+)', text)
    if not match or int(match[1]) < 160 or int(match[2]) < 120:
        raise argparse.ArgumentTypeError('size must be WIDTHxHEIGHT, at least 160x120')
    return int(match[1]), int(match[2])


def robot_slots(model) -> dict:
    """Robot id -> qpos address of its base free joint (x, y, z come first)."""
    import mujoco
    slots = {}
    for index in range(model.njnt):
        match = re.fullmatch(r'(r\d+)__base_free', model.joint(index).name or '')
        if match and model.jnt_type[index] == mujoco.mjtJoint.mjJNT_FREE:
            slots[match[1]] = int(model.jnt_qposadr[index])
    if not slots:
        raise ValueError('model has no r<N>__base_free robot joints')
    return slots


def _hud(frame, lines, font_paths):
    from PIL import Image, ImageDraw
    import numpy as np
    size = max(12, frame.shape[1]//58)
    font, _ = load_font(tuple(font_paths), size)
    image = Image.fromarray(frame).convert('RGBA')
    layer = Image.new('RGBA', image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    width = int(max(draw.textlength(line, font=font) for line in lines)) + size
    draw.rectangle([0, 0, width, int(size*1.5*len(lines)) + size//2], fill=(14, 18, 24, 170))
    for number, line in enumerate(lines):
        draw.text((size//2, size//4 + int(size*1.5*number)), line, font=font, fill=(236, 240, 246, 255))
    return np.asarray(Image.alpha_composite(image, layer).convert('RGB'))


class _Scene:
    """Kinematic observer replay: set recorded qpos, forward, render."""

    def __init__(self, run_dir, size, zoom=1.):
        import mujoco
        from scripts.dispatch_replay import frame_at, load
        self.mujoco, self.frame_at = mujoco, frame_at
        self.model, self.states, self.labels, self.manifest = load(run_dir)
        self.data = mujoco.MjData(self.model)
        self.times = self.states['time'].tolist()
        self.slots = robot_slots(self.model)
        view_path = Path(run_dir)/'replay'/'view.json'
        self.view = {**DEFAULT_VIEW, **(json.loads(view_path.read_text()) if view_path.is_file() else {})}
        self.view['distance'] = float(self.view['distance'])/zoom
        width, height = size
        self.model.vis.global_.offwidth = max(self.model.vis.global_.offwidth, width)
        self.model.vis.global_.offheight = max(self.model.vis.global_.offheight, height)
        self.renderer = mujoco.Renderer(self.model, height, width)
        self.width, self.height = width, height
        cam = mujoco.MjvCamera()
        cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        cam.lookat[:] = self.view['lookat']
        cam.distance, cam.azimuth, cam.elevation = (self.view['distance'], self.view['azimuth'],
                                                    self.view['elevation'])
        self.cam = cam
        self.observer = ObserverCamera.free(
            lookat=self.view['lookat'], distance=self.view['distance'], azimuth=self.view['azimuth'],
            elevation=self.view['elevation'], fovy_deg=float(self.model.vis.global_.fovy),
            width=width, height=height)

    def frame(self, sim_t):
        mujoco = self.mujoco
        index = self.frame_at(self.times, sim_t)
        self.data.qpos[:] = self.states['qpos'][index]
        if self.model.nmocap:
            self.data.mocap_pos[:] = self.states['mocap_pos'][index]
            self.data.mocap_quat[:] = self.states['mocap_quat'][index]
        self.data.time = self.times[index]
        mujoco.mj_forward(self.model, self.data)
        self.renderer.update_scene(self.data, camera=self.cam)
        # Match the native replay window: no shadows or reflections.
        self.renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = 0
        self.renderer.scene.flags[mujoco.mjtRndFlag.mjRND_REFLECTION] = 0
        pixels = self.renderer.render().copy()
        heads = {rid: head_point(self.states['qpos'][index][adr:adr + 3]) for rid, adr in self.slots.items()}
        return pixels, heads, self.times[index]

    def close(self):
        self.renderer.close()


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('run_dir', type=Path, help='run output directory with replay/ and team/conversation.jsonl')
    parser.add_argument('output', type=Path, help='new .mp4 (video) or .png (one still)')
    parser.add_argument('--observer-overlay', default='none',
                        help="'none' (default, no bubbles) or 'speech_bubbles_v1'")
    parser.add_argument('--speed', type=float, default=4., help='SIM seconds per video second')
    parser.add_argument('--fps', type=float, default=20.)
    parser.add_argument('--size', type=parse_size, default=(1280, 720))
    parser.add_argument('--zoom', type=float, default=1., help='move the observer camera closer (distance / zoom)')
    parser.add_argument('--window', type=parse_window, action='append',
                        help='SIM START:END to include; repeat for several; default whole replay')
    parser.add_argument('--bubble-seconds', type=float, default=5., help='bubble life on the video clock')
    parser.add_argument('--beat-seconds', type=float, default=2., help='gap between messages sent at one SIM instant')
    parser.add_argument('--linger-seconds', type=float, default=2.5, help='hold after the last message of an instant')
    parser.add_argument('--no-dialogue-pause', action='store_true', help='never freeze the scene for messages')
    parser.add_argument('--receipts', action='store_true', help="small '받음' chip on receivers")
    parser.add_argument('--max-video-seconds', type=float, default=60.)
    parser.add_argument('--still-sim-s', type=float, help='SIM time for a .png still')
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        overlay_id = normalize_observer_overlay(args.observer_overlay)
    except ValueError as error:
        build_parser().error(str(error))
    if args.output.exists():
        build_parser().error(f'{args.output} already exists')
    still = args.output.suffix.lower() == '.png'
    messages = []
    conversation = Path(args.run_dir)/'team'/'conversation.jsonl'
    if overlay_id == SPEECH_BUBBLES_V1:
        if not conversation.is_file():
            build_parser().error(f'no {conversation}; nothing to show as speech bubbles')
        messages = load_conversation(conversation)
    if not .25 <= args.zoom <= 8:
        build_parser().error('--zoom must be within 0.25..8')
    scene = _Scene(args.run_dir, args.size, args.zoom)
    try:
        overlay = (SpeechBubbleOverlay(messages, show_s=args.bubble_seconds, receipts=args.receipts)
                   if overlay_id else None)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if still:
            if args.still_sim_s is None:
                build_parser().error('--still-sim-s is required for a .png output')
            pixels, heads, sim = scene.frame(args.still_sim_s)
            if overlay:
                # Live-view semantics: the bubble clock is the SIM clock.
                pixels = overlay.render(pixels, sim, scene.observer, heads)
            pixels = _hud(pixels, [f'SIM {sim:.1f}s'], KOREAN_FONTS)
            from PIL import Image
            Image.fromarray(pixels).save(args.output)
            print(json.dumps({'still': str(args.output), 'sim_s': sim, 'overlay': overlay_id}))
            return 0
        windows = args.window or [(scene.times[0], scene.times[-1])]
        frames, retimed, offset = [], [], 0.
        for start, end in windows:
            part, moved = presentation_timeline(
                messages, start_s=start, end_s=end, speed=args.speed, fps=args.fps,
                beat_s=args.beat_seconds, linger_s=args.linger_seconds,
                pause_for_dialogue=not args.no_dialogue_pause)
            frames += [(sim, clock + offset) for sim, clock in part]
            retimed += [replace(m, start_s=m.start_s + offset) for m in moved]
            offset = (frames[-1][1] if frames else offset) + args.bubble_seconds + 1.
        duration = len(frames)/args.fps
        if duration > args.max_video_seconds:
            build_parser().error(f'video would be {duration:.1f}s, over --max-video-seconds '
                                 f'{args.max_video_seconds:g}; narrow --window or raise --speed')
        if overlay:
            overlay.messages = retimed
        width, height = args.size
        command = ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                   '-s', f'{width}x{height}', '-r', f'{args.fps:g}', '-i', '-', '-an',
                   '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p',
                   '-movflags', '+faststart', str(args.output)]
        process = subprocess.Popen(command, stdin=subprocess.PIPE)
        previous_sim, ok = None, False
        try:
            for index, (sim_t, clock) in enumerate(frames):
                pixels, heads, shown_sim = scene.frame(sim_t)
                if overlay:
                    pixels = overlay.render(pixels, clock, scene.observer, heads)
                holding = previous_sim is not None and sim_t == previous_sim
                previous_sim = sim_t
                lines = [f'SIM {shown_sim:6.1f}s  x{args.speed:g}']
                if holding:
                    lines = [f'SIM {shown_sim:6.1f}s  대화 중 (시뮬레이션 일시정지)']
                pixels = _hud(pixels, lines, KOREAN_FONTS)
                process.stdin.write(pixels.tobytes())
            ok = True
        finally:
            process.stdin.close()
            code = process.wait(timeout=120)
        if not ok or code:
            raise RuntimeError(f'ffmpeg failed with exit code {code}')
        record = {
            'scope': 'observer-only post-run kinematic replay with presentation overlay; '
                     'never actor, controller or referee input',
            'observer_overlay': overlay_id, 'source': _source_identity(),
            'head_positions': 'recorded ground-truth base qpos (presentation only)',
            'run_dir': str(Path(args.run_dir).resolve()),
            'replay_states_sha256': _sha(Path(args.run_dir)/'replay'/'states.npz'),
            'conversation_sha256': _sha(conversation) if conversation.is_file() else None,
            'video': str(args.output.resolve()), 'video_sha256': _sha(args.output),
            'frames': len(frames), 'fps': args.fps,
            'duration_s': duration, 'speed': args.speed, 'windows': windows, 'zoom': args.zoom,
            'camera_view': scene.view,
            'dialogue_pause': not args.no_dialogue_pause,
            'bubble_seconds': args.bubble_seconds, 'receipts': args.receipts,
            'schedule': [{'seq': m.seq, 'sender': m.sender, 'recipients': list(m.recipients),
                          'logged_sim_time_s': m.sim_time_s, 'video_onset_s': round(m.start_s, 3)}
                         for m in retimed],
        }
        args.output.with_suffix('.render.json').write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'video': str(args.output), 'frames': len(frames), 'duration_s': round(duration, 2),
                          'messages': len(retimed), 'overlay': overlay_id}, ensure_ascii=False))
        return 0
    finally:
        scene.close()


if __name__ == '__main__':
    raise SystemExit(main())
