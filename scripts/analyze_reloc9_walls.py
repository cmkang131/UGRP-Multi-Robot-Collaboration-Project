"""Saved own-frame wall-top audit. GT is used only AFTER image guard decisions."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import cv2
import numpy as np
from harness.reloc9_wall_guard import filter_observation
from harness.opencv_wall_observation import observations, DETECTOR
from harness.vision_pose_source_final import measured_column_model
from harness.zone_solo_cyan_amcl_sensor import endpoints
from harness.servo_camera_fk import transform_from_commands, OPTION
from scripts.analyze_reloc9_rotation import read, RAW

REPORTS = Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/gcp-reports/reloc8-0459c03c-66928f23-ops')


def wall_distance(points, static):
    distance = np.full(len(points), np.inf)
    for wall in static['obstacles']:
        if wall.get('kind') != 'wall':
            continue
        center, half = np.array(wall['center_m']), np.array(wall['half_extents_m'])
        a, b = center-half, center+half
        corners = [a, [b[0], a[1]], b, [a[0], b[1]]]
        for p, q in zip(corners, corners[1:]+corners[:1]):
            p, q = np.array(p), np.array(q); v = q-p
            projection = p+np.clip((points-p)@v/(v@v), 0, 1)[:, None]*v
            distance = np.minimum(distance, np.linalg.norm(points-projection, axis=1))
    return distance


def evaluate(runs):
    from harness.vision_loc_protocol import load_vis3
    from harness.own_image_gates import load
    vl, _ = load_vis3(); sources = []; rows = []
    for run in runs:
        commands = read(RAW/run/'raw/teacher-commands.jsonl', sources)
        ev = {round(r['t'], 6): r for r in read(RAW/run/'raw/eval-only.jsonl', sources)}
        static_path = RAW/run/'raw/carry-static-map.json'
        static = json.loads(static_path.read_bytes())
        sources.append(dict(path=str(static_path), sha256=hashlib.sha256(static_path.read_bytes()).hexdigest()))
        # Full review is preferred over duplicate first30 frames.
        directory = REPORTS/(run+'-review')/'own'
        for path in sorted(directory.glob('*.jpg')):
            i = int(path.stem)
            if not 0 < i < len(commands):
                continue
            row = commands[i]; servo = {int(k):v for k,v in commands[i-1]['command']['pwm'].items()}
            cam, reason = transform_from_commands(servo, camera_pose=OPTION)
            if cam is None:
                continue
            pitch = math.degrees(math.asin(cam[1][2, 2]))
            if abs(pitch+7.5) > 1.:
                continue
            # Only commanded, settled look views; no fabricated posture on an old frame.
            if i < 8 or any(commands[j]['command']['pwm'] != commands[i-1]['command']['pwm']
                            for j in range(i-8, i)):
                continue
            image = cv2.imread(str(path)); shape = image.shape
            image = cv2.resize(image, (640, 480)) if shape[:2] != (480, 640) else image
            cm = measured_column_model(vl.mp, {'origin_m':cam[0], 'rotation':cam[1]},
                vl.mp.column_positions(DETECTOR['columns'], int(DETECTOR['strip_half_px'])))
            obs = observations(vl, image, cm, load()['values'])
            guarded, audit = filter_observation(obs, vl.mp.undistort(image), cm, True)
            before, after = endpoints(cm, obs), endpoints(cm, guarded)
            # Evaluator truth is opened only after the guard has decided.
            truth_row = ev[round(row['t'], 6)]
            yaw = row['map_pose']['pose_estimate'][2]-truth_row['map_pose_error_yaw_rad']
            pose = [*truth_row['base_xyz'][:2], yaw]
            c,s = math.cos(yaw), math.sin(yaw)
            def quality(pts):
                world = np.array(pts).reshape(-1, 2)@np.array([[c,s],[-s,c]])+pose[:2]
                distance = wall_distance(world, static)
                tile = 16/28
                residual = abs((world+tile/2)%tile-tile/2)
                return dict(N=len(world), on_actual_wall_5cm_N=int((distance <= .05).sum()),
                    on_checker_line_2cm_N=int((residual.min(1) < .02).sum()))
            rows.append(dict(run=run, path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                t=row['t'], native_saved_resolution=[shape[1],shape[0]], commanded_pitch_deg=pitch,
                servo=servo, guard=audit, before=quality(before), after=quality(after)))
    total = {side:{k:sum(r[side][k] for r in rows) for k in ('N','on_actual_wall_5cm_N','on_checker_line_2cm_N')}
             for side in ('before','after')}
    return dict(schema='ugrp.reloc9_saved_walls.v1', frames=len(rows), totals=total, rows=rows, sources=sources,
        verified_scope='settled commanded -7.5deg saved OWN frames only; 320x240 previews resized for frozen 640x480 detector; NOT native full-bank recall',
        physics_calls=0, render_calls=0, texture_pr511='opinion only: keep guard as independent geometry check; texture may reduce checker aliases but cannot certify wall height; requires separate native RGB comparison')


def main():
    p=argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--runs', nargs='+', default=['solo-carry-93261-0459c03c','solo-carry-93262-0459c03c'])
    a=p.parse_args(); result=evaluate(a.runs)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open('x') as f:
        json.dump(result, f, indent=2, allow_nan=False); f.write('\n')
    print(json.dumps(dict(frames=result['frames'],totals=result['totals'])))


if __name__ == '__main__':
    main()
