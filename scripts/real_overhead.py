#!/usr/bin/env python3
"""Laptop side: measure the ceiling camera once, then record robot poses during a real trial.

    # once after installing the camera
    python3 scripts/real_overhead.py intrinsics photos/checker/*.jpg --board 9x6 --square-m 0.025 --out cam_int.json
    python3 scripts/real_overhead.py pose photos/floor.jpg --intrinsics cam_int.json \
        --floor-cards configs/real_robot/floor_cards.json --out configs/real_robot/ceiling_<date>.json
    # every trial
    python3 scripts/real_overhead.py record --calibration configs/real_robot/ceiling_<date>.json \
        --camera 0 --out runs/<trial>/overhead.jsonl --video runs/<trial>/overhead.mp4

Each record line: {"t": laptop monotonic s, "frame": n, "poses": {"r1": [x, y, yaw, card_side_m]}, "sync": bool}.
`t` is the same clock as the trial event log (both on the laptop), so they are compared directly.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from real_robot import overhead_real as orl  # noqa: E402


def cmd_intrinsics(a):
    import cv2
    bw, bh = (int(v) for v in a.board.lower().split('x'))
    imgs = [cv2.imread(str(p)) for p in a.photos]
    K, dist, rms, n = orl.calibrate_intrinsics([i for i in imgs if i is not None], (bw, bh), a.square_m)
    h, w = imgs[0].shape[:2]
    Path(a.out).write_text(json.dumps({'camera_matrix': K.tolist(), 'dist': dist.tolist(), 'rms_px': rms,
                                       'photos_used': n, 'image_size': [w, h], 'board': a.board,
                                       'square_m': a.square_m}, indent=1))
    print(f'rms {rms:.3f} px from {n} photos -> {a.out}')


def cmd_pose(a):
    import cv2
    intr = json.loads(Path(a.intrinsics).read_text())
    cards = {int(k): tuple(v) for k, v in json.loads(Path(a.floor_cards).read_text())['cards'].items()}
    img = cv2.imread(str(a.photo))
    rvec, tvec, rms, used = orl.calibrate_pose(img, intr['camera_matrix'], intr['dist'], cards)
    cam = orl.Camera(intr['camera_matrix'], intr['dist'], rvec, tvec)
    Path(a.out).write_text(json.dumps({'measured': True, 'camera_matrix': intr['camera_matrix'], 'dist': intr['dist'],
                                       'rvec': rvec.tolist(), 'tvec': tvec.tolist(), 'pose_rms_px': rms,
                                       'intrinsics_rms_px': intr['rms_px'], 'floor_cards_used': used,
                                       'camera_center_m': cam.center.tolist(), 'source': str(a.photo)}, indent=1))
    print(f'camera at {cam.center.round(3).tolist()} m, reprojection rms {rms:.2f} px, cards {used} -> {a.out}')


def cmd_record(a):
    import cv2
    reader = orl.RealOverheadReader(orl.Camera.load(a.calibration))
    cap = cv2.VideoCapture(int(a.camera) if str(a.camera).isdigit() else a.camera)
    out = open(a.out, 'a')
    writer, n, t_end = None, 0, time.monotonic() + a.seconds if a.seconds else None
    try:
        while t_end is None or time.monotonic() < t_end:
            ok, frame = cap.read()
            t = time.monotonic()
            if not ok:
                break
            n += 1
            poses, sync = reader.read(frame)
            out.write(json.dumps({'t': round(t, 4), 'frame': n, 'poses': {k: [round(v, 4) for v in p] for k, p in poses.items()},
                                  'sync': sync}) + '\n')
            if a.video:
                if writer is None:
                    h, w = frame.shape[:2]
                    writer = cv2.VideoWriter(a.video, cv2.VideoWriter_fourcc(*'mp4v'), a.video_fps, (w, h))
                cv2.putText(frame, f'{t:.2f}', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                writer.write(frame)
    except KeyboardInterrupt:
        pass
    finally:
        out.close()
        cap.release()
        if writer is not None:
            writer.release()
    print(f'{n} frames -> {a.out}')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest='cmd', required=True)
    i = s.add_parser('intrinsics'); i.add_argument('photos', nargs='+'); i.add_argument('--board', default='9x6')
    i.add_argument('--square-m', type=float, required=True); i.add_argument('--out', required=True)
    q = s.add_parser('pose'); q.add_argument('photo'); q.add_argument('--intrinsics', required=True)
    q.add_argument('--floor-cards', required=True); q.add_argument('--out', required=True)
    r = s.add_parser('record'); r.add_argument('--calibration', required=True); r.add_argument('--camera', default='0')
    r.add_argument('--out', required=True); r.add_argument('--video'); r.add_argument('--video-fps', type=float, default=15.)
    r.add_argument('--seconds', type=float, default=0., help='stop after this many seconds (0 = until Ctrl-C)')
    a = p.parse_args(argv)
    {'intrinsics': cmd_intrinsics, 'pose': cmd_pose, 'record': cmd_record}[a.cmd](a)


if __name__ == '__main__':
    main()
