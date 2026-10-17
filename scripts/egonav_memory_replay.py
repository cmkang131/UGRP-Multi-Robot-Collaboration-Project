#!/usr/bin/env python3
"""Render an ego-centric memory replay video from a recording-only trace.

Input is the output of ``scripts/egonav_gate.py --memory-trace`` (toggle
``egonav_memory_trace_v1``, default off): one JSON line per 10 Hz tick with
the robot-relative memory items and events, plus the whole-run own-RGB
frames.  The replay is visualization only; it is not a success criterion and
never feeds control.

Layout: left = ego-centric top-down view with the robot fixed at (0, 0)
facing +x; remembered landmarks keep their self-relative coordinates, so
they move opposite to the robot's real motion.  Right = own RGB frame.
Bottom = SIM time, memory count and the events of the tick.

1x SIM speed: the trace is 10 Hz and one output frame is emitted per tick at
``--fps 10``.  The GT pose printed in the corner is an evaluation-only label
from the trace; it is not used for drawing or control.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np

# 95% confidence radius of a 2-D Gaussian: sqrt(chi2.ppf(0.95, 2)).
CHI2_95_2D = 2.447746830680818

PANEL_W = 520
WIDTH = 960
HEIGHT = 560
PANEL_H = 480


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def uncertainty_radius(item: dict) -> float:
    radius = item.get('radius95_m')
    if radius is not None:
        try:
            value = float(radius)
            if math.isfinite(value) and value > 0:
                return value
        except (TypeError, ValueError):
            pass
    covariance = item.get('uncertainty_m2')
    if covariance is None:
        return 0.0
    matrix = np.asarray(covariance, dtype=float)
    if matrix.shape != (2, 2) or not np.all(np.isfinite(matrix)):
        return 0.0
    try:
        largest = float(np.linalg.eigvalsh(matrix)[-1])
    except np.linalg.LinAlgError:
        return 0.0
    return CHI2_95_2D * math.sqrt(max(0.0, largest))


def load_trace(path: Path) -> list[dict]:
    rows = []
    with path.open('r', encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    if not rows:
        raise SystemExit(f'empty trace: {path}')
    return rows


def view_range(rows: list[dict]) -> float:
    reach = 2.5
    for row in rows:
        for item in row.get('memories') or []:
            xy = item.get('relative_xy_m') or [0.0, 0.0]
            reach = max(reach, math.hypot(float(xy[0]), float(xy[1]))
                        + uncertainty_radius(item))
        observed = row.get('observation_relative_xy_m')
        if observed:
            reach = max(reach, math.hypot(float(observed[0]), float(observed[1])))
    return min(8.0, max(3.0, math.ceil(reach * 2.0) / 2.0))


def short(text: object, limit: int = 22) -> str:
    value = '-' if text is None else str(text)
    return value if len(value) <= limit else value[:limit - 1] + '~'


def draw_left(panel: np.ndarray, row: dict, scale: float) -> None:
    cx, cy = PANEL_W // 2, PANEL_H // 2 + 6
    panel[:] = (24, 22, 20)

    def to_px(x: float, y: float) -> tuple[int, int]:
        return int(round(cx + x * scale)), int(round(cy - y * scale))

    # 1 m grid (ego-centric metres).
    limit = int(math.ceil((PANEL_H / 2.0) / scale)) + 1
    for metre in range(-limit, limit + 1):
        px = int(round(cx + metre * scale))
        py = int(round(cy - metre * scale))
        colour = (70, 70, 70) if metre == 0 else (44, 44, 48)
        cv2.line(panel, (px, 0), (px, PANEL_H - 1), colour, 1)
        cv2.line(panel, (0, py), (PANEL_W - 1, py), colour, 1)
        if metre:
            cv2.putText(panel, f'{metre}m', (px + 3, cy - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (90, 90, 95), 1, cv2.LINE_AA)

    cv2.putText(panel, 'ego-centric memory (self-relative)',
                (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 220, 220), 1, cv2.LINE_AA)

    # Remembered landmarks: self-relative position, 95% uncertainty circle.
    for item in row.get('memories') or []:
        xy = item.get('relative_xy_m') or [0.0, 0.0]
        x, y = float(xy[0]), float(xy[1])
        px, py = to_px(x, y)
        radius = uncertainty_radius(item) * scale
        if radius >= 3:
            cv2.circle(panel, (px, py), int(round(radius)), (60, 170, 255), 1, cv2.LINE_AA)
        cv2.line(panel, (cx, cy), (px, py), (70, 110, 130), 1, cv2.LINE_AA)
        cv2.circle(panel, (px, py), 5, (0, 190, 255), -1, cv2.LINE_AA)
        age = item.get('age_s')
        age_text = '' if age is None else f' {float(age):.1f}s'
        cv2.putText(panel, short(item.get('kind')) + age_text, (px + 8, py - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 210, 255), 1, cv2.LINE_AA)
        cv2.putText(panel, short(item.get('id'), 20), (px + 8, py + 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.32, (170, 170, 170), 1, cv2.LINE_AA)

    observed = row.get('observation_relative_xy_m')
    if row.get('visible') and observed:
        ox, oy = to_px(float(observed[0]), float(observed[1]))
        cv2.drawMarker(panel, (ox, oy), (80, 255, 120), cv2.MARKER_TRIANGLE_UP, 12, 2)

    # Robot at the origin, facing +x.
    cv2.circle(panel, (cx, cy), 10, (255, 160, 60), -1, cv2.LINE_AA)
    cv2.arrowedLine(panel, (cx, cy), (cx + 26, cy), (80, 220, 255), 2, cv2.LINE_AA, tipLength=0.35)
    cv2.putText(panel, 'robot (0,0)', (cx - 38, cy + 26),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1, cv2.LINE_AA)

    pose = row.get('pose_eval_only') or [0.0, 0.0, 0.0]
    cv2.putText(panel, f'GT pose (eval only): x={pose[0]:.2f} y={pose[1]:.2f} yaw={pose[2]:.2f}',
                (10, PANEL_H - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.38,
                (140, 140, 140), 1, cv2.LINE_AA)


def draw_right(canvas: np.ndarray, frame: np.ndarray | None, row: dict,
               events: list[str]) -> None:
    x0 = PANEL_W + 10
    right_w = WIDTH - x0 - 10
    right_h = int(round(right_w * 480 / 640))
    cv2.putText(canvas, 'own RGB (robot camera)', (x0, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (230, 230, 230), 1, cv2.LINE_AA)
    if frame is not None:
        view = cv2.resize(frame, (right_w, right_h), interpolation=cv2.INTER_AREA)
        canvas[40:40 + right_h, x0:x0 + right_w] = view
    below = 40 + right_h + 24
    cv2.putText(canvas, 'visible now: ' + ('yes' if row.get('visible') else 'no'),
                (x0, below), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                (120, 255, 140) if row.get('visible') else (150, 150, 150), 1, cv2.LINE_AA)
    cv2.putText(canvas, 'events:', (x0, below + 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (220, 220, 220), 1, cv2.LINE_AA)
    for index, text in enumerate(events[-3:]):
        cv2.putText(canvas, text, (x0 + 8, below + 46 + 20 * index),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.36, (190, 190, 160), 1, cv2.LINE_AA)


def build(run: Path, world: int, out: Path, fps: int, width: int) -> dict:
    trace_path = run/'memory_trace'/f'world{world:02d}.jsonl'
    frame_dir = run/'frames'/f'world{world:02d}'
    rows = load_trace(trace_path)
    if not frame_dir.is_dir():
        raise SystemExit(f'missing frames: {frame_dir}')

    scale = (PANEL_H / 2.0 - 16) / view_range(rows)
    size = (width, HEIGHT)
    tempo = Path(tempfile.mkdtemp(prefix='egonav-replay-'))
    event_log: list[str] = []
    last_frame = None
    try:
        for index, row in enumerate(rows):
            tick = int(row['tick'])
            frame_path = frame_dir/f'{tick:04d}.jpg'
            if frame_path.is_file():
                last_frame = cv2.imread(str(frame_path))
            canvas = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
            canvas[:PANEL_H, :PANEL_W] = (24, 22, 20)
            left = canvas[:PANEL_H, :PANEL_W]
            draw_left(left, row, scale)
            for event in row.get('events') or []:
                event_log.append(f'{float(event["t"]):5.1f}s {short(event.get("reason"), 26)}')
            draw_right(canvas, last_frame, row, event_log)

            t = float(row['t'])
            cv2.rectangle(canvas, (0, PANEL_H), (WIDTH, HEIGHT), (16, 16, 18), -1)
            cv2.putText(canvas, f't = {t:5.1f} s   memories = {int(row.get("memory_count") or 0)}',
                        (12, PANEL_H + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.62,
                        (240, 240, 240), 1, cv2.LINE_AA)
            current = [short(e.get('reason'), 30) for e in (row.get('events') or [])]
            cv2.putText(canvas, 'now: ' + (', '.join(current) if current else '-'),
                        (12, PANEL_H + 56), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        (90, 220, 255) if current else (140, 140, 140), 1, cv2.LINE_AA)
            cv2.putText(canvas, f'SIM {t:5.1f}s / {fps} fps (1x)',
                        (WIDTH - 250, PANEL_H + 56), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                        (160, 160, 160), 1, cv2.LINE_AA)
            cv2.imwrite(str(tempo/f'{index:05d}.png'), canvas)

        out.parent.mkdir(parents=True, exist_ok=True)
        command = ['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(fps),
                   '-i', str(tempo/'%05d.png'), '-c:v', 'libx264',
                   '-pix_fmt', 'yuv420p', '-crf', '20', '-movflags', '+faststart',
                   str(out)]
        subprocess.run(command, check=True)
    finally:
        shutil.rmtree(tempo, ignore_errors=True)

    spawn = None
    setup_path = run/'setup.json'
    if setup_path.is_file():
        try:
            worlds = json.loads(setup_path.read_text()).get('worlds') or []
            spawn = worlds[world].get('r1') if world < len(worlds) else None
        except (OSError, ValueError, IndexError, KeyError):
            spawn = None
    meta = dict(
        source_run=str(run), world=world, spawn=spawn,
        kind='egonav_memory_replay_v1',
        note='visualization only; not a success criterion and not pooled with gate results',
        toggle='egonav_memory_trace_v1', fps=fps, width=width, height=HEIGHT,
        builder_sha256=sha256_file(Path(__file__).resolve()),
        frames=len(rows), sim_seconds=round((len(rows) - 1) / 10.0, 3),
        trace=str(trace_path), trace_rows=len(rows),
        trace_sha256=sha256_file(trace_path),
        mp4=str(out), mp4_sha256=sha256_file(out),
        mp4_bytes=out.stat().st_size)
    meta_path = out.with_suffix('.json')
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return meta


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--world', type=int, default=0)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--fps', type=int, default=10,
                        help='10 fps = 1x SIM speed (trace is 10 Hz)')
    parser.add_argument('--width', type=int, default=960)
    args = parser.parse_args()
    meta = build(args.run, args.world, args.out, args.fps, args.width)
    print(json.dumps(meta, ensure_ascii=False))


if __name__ == '__main__':
    main()
