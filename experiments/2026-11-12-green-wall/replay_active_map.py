"""Replay ras1 observations into ActiveMapper's observation grid."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import cv2
import numpy as np

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness.active_wall_mapping import ActiveMapper, VISUAL_MAPPING, inverse
from harness.ras1_place_observations import Ras1PlaceObservations
from harness.self_odom_grid import transform
from green_wall_mapper import Mapper, POSE, camera_geometry


def local_observation(wall, floor, pose):
    """Convert anchor-frame metres to the camera frame consumed by the grid."""
    to_camera = inverse(pose)
    return {
        'wall_xy': transform(np.asarray(wall).reshape(-1, 2), to_camera).tolist(),
        'floor_xy': transform(np.asarray(floor).reshape(-1, 2), to_camera).tolist(),
    }


def from_checkpoint(checkpoint, *, anchor):
    tracking = checkpoint['tracking']
    if not anchor and (tracking.get('reason') != 'ok'
                       or tracking.get('pose_status') != 'nominal_floor_pose'
                       or tracking.get('pose') is None):
        return None, None
    camera = np.asarray(checkpoint['camera_xy_cm'], float) / 100
    pose = [*camera, math.radians(checkpoint['yaw_deg'])]
    # The archival contact samples are relative to the camera but retain the
    # original anchor axes. Restore the anchor origin before applying SE(2).
    wall = np.asarray(checkpoint['contact_points_cm'], float).reshape(-1, 2) / 100 + camera
    return local_observation(wall, [], pose), pose


def from_rgb(mapper, image, height_m):
    """Reuse the ras1 rectification, masks and floor homography tracker."""
    anchor = mapper.previous is None
    views_before = len(mapper.views)
    _, tracking = mapper.update(image)
    visual = tracking.get('pose')
    if len(mapper.views) == views_before or (not anchor and visual is None):
        return None, None, tracking

    pose = [0., 0., 0.] if anchor else [
        visual['camera_x'] * height_m,
        visual['camera_y'] * height_m,
        math.radians(visual['yaw_deg']),
    ]
    wall = np.asarray(mapper.views[-1]['boundary_points']).reshape(-1, 2) * height_m
    # Use the same 12 px sampling as active_wall_vision. The floor mask
    # carries only visible gray pixels below the observed contact.
    y, x = np.nonzero(mapper.previous_floor[::12, ::12])
    pixels = np.column_stack((x, y)).astype(np.float32) * 12
    floor = np.empty((0, 2))
    if len(pixels):
        anchor_pixels = cv2.perspectiveTransform(pixels[:, None], mapper.to_anchor)[:, 0]
        floor = mapper.ground(anchor_pixels)
        # Match Mapper's existing forward projection envelope.
        floor = floor[np.isfinite(floor).all(1) & (np.linalg.norm(floor, axis=1) < 8)] * height_m
    if not len(wall):
        return None, None, tracking
    return local_observation(wall, floor, pose), pose, tracking


def read_frame(run_dir, checkpoint, frame_ledger):
    image_name = checkpoint['image']
    entry = frame_ledger[image_name]
    if Path(image_name).name != image_name or entry['t'] != checkpoint['t']:
        raise ValueError('INVALID_RAS1_FRAME_PROVENANCE')
    raw = (run_dir / image_name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != entry['sha256']:
        raise ValueError('RAS1_FRAME_HASH_MISMATCH')
    image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.shape != (480, 640, 3):
        raise ValueError('EXPECTED_NATIVE_RAS1_BGR')
    return image


def replay(run_dir, *, source='rgb'):
    if source not in ('rgb', 'checkpoints'):
        raise ValueError('UNKNOWN_RAS1_REPLAY_SOURCE')
    result_bytes = (run_dir / 'result.json').read_bytes()
    result = json.loads(result_bytes)
    checkpoints = result['checkpoints']
    if not checkpoints:
        raise ValueError('NO_RAS1_CHECKPOINTS')
    controller = ActiveMapper('ras1', checkpoints[0]['t'], POSE,
                              active_mapping=VISUAL_MAPPING)
    height_m = float(result['scale']['camera_height_cm']) / 100
    expected_height_m = float(camera_geometry()[0][2])
    if not math.isclose(height_m, expected_height_m, rel_tol=1e-6):
        raise ValueError('RAS1_REPLAY_SCALE_MISMATCH')
    if not result.get('floor_profile'):
        raise ValueError('RAS1_FIXED_FLOOR_PROFILE_REQUIRED')
    mapper = Mapper(result['floor_profile']) if source == 'rgb' else None
    places = (Ras1PlaceObservations(scale=result['scale'], floor_profile=result['floor_profile'])
              if source == 'checkpoints' else None)
    ledger = {}
    if source == 'rgb':
        for line in (run_dir / 'frames.jsonl').read_text().splitlines():
            row = json.loads(line)
            if row['image'] in ledger:
                raise ValueError('DUPLICATE_RAS1_FRAME')
            ledger[row['image']] = row

    traces = []
    for index, checkpoint in enumerate(checkpoints):
        servo = {int(k): v for k, v in checkpoint['commanded_arm_pose'].items()}
        if servo != POSE:
            raise ValueError('RAS1_CAMERA_POSE_CHANGED')
        rgb = None
        if source == 'rgb':
            image = read_frame(run_dir, checkpoint, ledger)
            observation, pose, tracking = from_rgb(mapper, image, height_m)
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        else:
            observation, pose = from_checkpoint(checkpoint, anchor=index == 0)
            tracking = checkpoint['tracking']
        # Only use the original, matched checkpoint path for an archived
        # PlaceMemory result. A failed RGB replay cannot borrow its pose.
        if places is not None:
            places.observe(checkpoint)
        _, trace = controller.receive(robot_id='ras1', t=checkpoint['t'], frame_id=index,
                                      rgb=rgb, servo=servo, observation=observation, visual_pose=pose)
        traces.append(dict(trace, image=checkpoint['image'], tracking_reason=tracking['reason'],
                           wall_points=len(observation['wall_xy']) if observation else 0,
                           floor_points=len(observation['floor_xy']) if observation else 0))

    grid = controller.grid
    cells = [
        dict(index=cell, state=grid.state(cell),
             wall_frames=sorted(grid.wall_frames.get(cell, ())),
             floor_frames=sorted(grid.floor_frames.get(cell, ())))
        for cell in sorted(grid.odds)
    ]
    output = dict(source=source, input_sha256=hashlib.sha256(result_bytes).hexdigest(),
                coordinate_frame='initial camera ground projection, +x forward, +y left',
                design_camera_height_m=height_m, metric_accuracy_verified=False,
                wall_geometry_confirmed=False, resolution_m=grid.resolution,
                updates=grid.revision, traces=traces, cells=cells)
    if places is not None:
        output['carry_place_observations'] = places.record()
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir', type=Path)
    parser.add_argument('--source', choices=('rgb', 'checkpoints'), default='rgb')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = replay(args.run_dir, source=args.source)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')


if __name__ == '__main__':
    main()
