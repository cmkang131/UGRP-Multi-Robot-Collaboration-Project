"""Read settled ugrp1 camera frames and verify the CarryNav local wall input."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import cv2
import numpy as np

from fixed_floor_motion import fixed_floor_pose, ground_points
from green_wall_mapper import D, K, camera_geometry, floor_tracks, masks
from wall_distance import distance_from_contact

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness.carry_nav_v1 import CarryNav
from harness.ras1_place_observations import Ras1PlaceObservations


def camera_model(path, fisheye_candidate):
    if fisheye_candidate:
        return K, cv2.fisheye.initUndistortRectifyMap(K, D, np.eye(3), K, (640, 480), cv2.CV_32FC1)
    data = json.loads(path.read_text())
    if data['model'] != 'opencv_pinhole':
        raise ValueError('expected an explicit OpenCV pinhole lens profile')
    k = np.asarray(data['K'], dtype=float)
    d = np.asarray(data['D'], dtype=float)
    return k, cv2.initUndistortRectifyMap(k, d, None, k, (640, 480), cv2.CV_32FC1)


def settled_frames(run_dir, captures, maps):
    last = {}
    for capture in captures:
        name = capture['name']
        if Path(name).name != name:
            raise ValueError('frame must be stored within the capture directory')
        blob = (run_dir / name).read_bytes()
        if hashlib.sha256(blob).hexdigest() != capture['sha256']:
            raise ValueError(f'frame hash differs: {name}')
        raw = cv2.imdecode(np.frombuffer(blob, dtype=np.uint8), cv2.IMREAD_COLOR)
        if raw is None or raw.shape != (480, 640, 3):
            raise ValueError(f'expected a 640x480 camera frame: {name}')
        image = cv2.remap(raw, *maps, cv2.INTER_LINEAR)
        _, floor, contacts = masks(image)
        last[capture['phase']] = (capture, cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), floor, contacts)
    return last


def replay(run_dir, lens_path, *, fisheye_candidate=False):
    record = json.loads((run_dir / 'result.json').read_text())
    if (record['device'] != 'ugrp1' or not record['stopped'] or record['errors'] or record['servo_writes']
            or record['final_arm_pose'] != record['expected_arm_pose']):
        raise ValueError('expected a stopped ugrp1 run with a fixed commanded arm posture')
    arm = record['expected_arm_pose']
    origin, axes = camera_geometry({int(key): value for key, value in arm.items()})
    height = float(origin[2] * 100)
    scale = dict(camera_height_cm=height, camera_origin_design_m=origin.tolist())
    intrinsics, maps = camera_model(lens_path, fisheye_candidate)
    frames = settled_frames(run_dir, record['captures'], maps)
    phases = ('initial', 'backward', 'forward')
    if tuple(frames) != phases:
        raise ValueError('expected settled initial, backward and forward frames in order')
    _, anchor, anchor_floor, _ = frames['initial']
    memory = Ras1PlaceObservations(scale=scale, floor_profile={'pose': arm}, source='ugrp1_fixed_camera')
    checkpoints = []
    initial_normal = None
    for phase, (capture, gray, floor, contact) in frames.items():
        if phase == 'initial':
            pose = dict(x=0., y=0., camera_x=0., camera_y=0., yaw_deg=0.)
            tracking = dict(reason='anchor')
        else:
            evidence, image = floor_tracks(anchor, gray, anchor_floor, floor)
            if evidence is None:
                checkpoints.append(dict(phase=phase, accepted=False, evidence=image))
                continue
            _, first, current = evidence
            pose, geometry = fixed_floor_pose(first, current, intrinsics, axes, origin / origin[2])
            if pose is None:
                checkpoints.append(dict(phase=phase, accepted=False, evidence=geometry))
                continue
            tracking = dict(reason='ok', pose_status='nominal_floor_pose', pose=pose,
                            method='fixed_floor_se2', floor_image_support=image, planar_support=geometry)

        yaw = math.radians(pose['yaw_deg'])
        rotation = np.array([[math.cos(yaw), -math.sin(yaw)], [math.sin(yaw), math.cos(yaw)]])
        shift = np.array([pose['camera_x'], pose['camera_y']])
        wall_points = ground_points(contact[::8], intrinsics, axes)
        wall_points = wall_points[np.linalg.norm(wall_points, axis=1) < 8]
        try:
            wall = distance_from_contact(wall_points @ rotation.T + shift, shift, height)
        except ValueError as error:
            checkpoints.append(dict(phase=phase, accepted=False, evidence=str(error)))
            continue
        ok = memory.observe(dict(t=capture['t'], tracking=tracking, commanded_arm_pose=arm,
                                 camera_xy_cm=(shift * height).tolist(), **wall))
        if not ok:
            checkpoints.append(dict(phase=phase, accepted=False, evidence='carry_memory_rejected'))
            continue

        nav = CarryNav(None, memory.places, memory.pose, [], 'through_door')
        if initial_normal is None:
            initial_normal = np.asarray(wall['wall_normal'])
        initial_points = np.asarray(wall['contact_points_cm']) + shift * height
        checkpoints.append(dict(phase=phase, accepted=True, tracking=tracking,
                                pose=memory.pose, wall_gap_design_cm=wall['wall_gap_cm'],
                                wall_offset_design_cm=float(np.median(initial_points @ initial_normal)),
                                wall_points_read_by_carry=len(nav._around())))
    observations = memory.record()
    if not checkpoints[-1]['accepted']:
        observations['visual_pose'] = None
    return dict(device='ugrp1', lens='ras1_fisheye_candidate' if fisheye_candidate else 'ugrp1_installed_pinhole',
                nominal_camera_height_cm=height, metric_accuracy_verified=False,
                checkpoints=checkpoints, carry_place_observations=observations)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('lens', type=Path)
    parser.add_argument('--ras1-fisheye-candidate', action='store_true')
    args = parser.parse_args()
    print(json.dumps(replay(args.run, args.lens, fisheye_candidate=args.ras1_fisheye_candidate), indent=2))
