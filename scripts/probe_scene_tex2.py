#!/usr/bin/env python3
"""Finite gcp2 camera audit of scene materials; static setup/evaluation only.

No world/controller is constructed, no mj_step or model API is called.  The
production XML, calibrated intrinsics/raw-fisheye remap, v3 camera transform,
HIGH PWM conversion and sensor geom-group policy are reused.  Setup positions
and segmentation are written under eval_only and never enter perception.

Run only after the coordinator has copied the gcp2setup PASS record locally:
  MUJOCO_GL=osmesa python -m scripts.probe_scene_tex2 --execute \
    --source-sha <40-char-HEAD> --setup-proof <ops-alert-copy.md> --output <new-dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import traceback
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ''):
    sys.path.insert(0, str(ROOT))

PROFILES = ('floor_light_v1', 'floor_light_textured_v1', 'walls_floor_textured_v2')
POSES = ('drive', 'high', 'high_beam_peer_occluded')
POSITIVE_POSES = ('box_palette', 'beam_end_bands', 'paint_A', 'paint_B', 'paint_C')
ROBOTS = ('r1', 'r2')
# Native archived camera resolution, unchanged in sim/masterpi_camera_profile.
WIDTH, HEIGHT = 640, 480
# Same seed and distances as the recorded v1 image audit. They specify test
# coverage, not an admission/error threshold or a robot navigation decision.
SEED = 20261015
WALL_DISTANCES_M = (.75, 1.5)
# Matches natural_floor_slam.Options.features and the v1 offline audit.
ORB_FEATURES = 800
# Runtime camera JPEG quality used by probe_e2e_first_frame and v1 own-image audit.
JPEG_QUALITY = 90
# Exact existing RGB appearance from 870c0c59:sim/grasp_act_scene.py, COLORS.
# This fixture copies only the two original band RGBA values; it does not
# claim integration of the absent grasp_act_scene consumer/toggle.
END_COLOURS = {'band_neg': (.02, .95, .60, 1.), 'band_pos': (.02, .02, .95, 1.)}
END_COLOUR_SOURCE = '870c0c59f3c2eae556abaa809ac1eddf33dce5ca:sim/grasp_act_scene.py'
# Coordinator's explicit positive fixture coverage (2026-10-15): four original
# boxes at .75/.9 m, original beam at .75 m, paint A/B from x-1.5 m and C
# from y-1.5 m. These
# are authored evaluation setups, never acceptance thresholds or navigation.
PALETTE_FORWARD_M = (.75, .9)


def poses_for_view(view_index, selected=None):
    available = POSES + POSITIVE_POSES if view_index == 0 else POSES
    return available if selected is None else tuple(p for p in available if p in selected)


def planned_case_count(view_count, selected=None):
    return sum(len(poses_for_view(index, selected)) for index in range(view_count))


def paint_fixture_xyyaw(center, zone):
    # Explicit evaluation-only view amendment (2026-10-16): coordinator found
    # the western paint_C fixture occluded by the divider, with 0/8 visibility.
    # Move the observer, preserving the original region/camera/physics.
    distance = max(WALL_DISTANCES_M)
    return (center[0], center[1] - distance, math.pi / 2) if zone == 'C' else (center[0] - distance, center[1], 0.)


def pose_pwm_mode(pose):
    if pose not in POSES + POSITIVE_POSES:
        raise ValueError('UNKNOWN_STATIC_FIXTURE_POSE:' + pose)
    return 'FOLDED' if pose == 'drive' or pose in POSITIVE_POSES else 'HIGH'


def positive_targets(pose):
    if pose == 'box_palette':
        return ('box_cyan', 'box_red', 'box_green', 'box_yellow')
    if pose == 'beam_end_bands':
        return ('beam_neg', 'beam_pos')
    if pose.startswith('paint_'):
        return ('paint_zone_' + pose[-1],)
    return ()


def palette_layout(xyyaw, box_half_extents):
    """Four original box centers; spacing derives from their actual geometry."""
    if len(box_half_extents) != 4:
        raise ValueError('FOUR_ORIGINAL_PALETTE_BOXES_REQUIRED')
    x, y, yaw = xyyaw
    lateral = 2 * max(float(size[1]) for size in box_half_extents.values())
    result = {}
    for i, name in enumerate(sorted(box_half_extents)):
        forward = PALETTE_FORWARD_M[i // 2]
        left = lateral * (-1 if i % 2 == 0 else 1)
        result[name] = [x + math.cos(yaw) * forward - math.sin(yaw) * left,
                        y + math.sin(yaw) * forward + math.cos(yaw) * left, yaw]
    return result


def center_wall_gap(static, xy):
    gaps = []
    for wall in static['obstacles']:
        if not wall['id'].startswith('wall_'):
            continue
        yaw = wall.get('yaw_rad', 0.)
        c, s = math.cos(yaw), math.sin(yaw)
        dx, dy = np.asarray(xy) - np.asarray(wall['center_m'])
        local = np.array([c * dx + s * dy, -s * dx + c * dy])
        gaps.append(float(np.linalg.norm(np.maximum(np.abs(local) - wall['half_extents_m'], 0))))
    return min(gaps) if gaps else None


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def write(path, value, *, compact=False):
    """Write JSON, losslessly zstd-compressing records above the repo 64 KiB cap.

    The uncompressed bytes are removed only after decompression SHA matches;
    the returned path always names the surviving artifact, including .zst.
    """
    path = Path(path)
    raw = (json.dumps(value, ensure_ascii=False, indent=None if compact else 2,
                      separators=(',', ':') if compact else None, allow_nan=False) + '\n').encode()
    path.write_bytes(raw)
    # Repository TRACE_LIMIT; record storage size, never an experiment gate.
    if len(raw) <= 65536:
        return path
    target = path.with_name(path.name + '.zst')
    temporary = target.with_name(target.name + f'.tmp-{os.getpid()}')
    subprocess.run(['zstd', '-q', '-3', '-T1', '-o', str(temporary), '--', str(path)], check=True)
    restored = subprocess.check_output(['zstd', '-q', '-d', '-c', '--', str(temporary)])
    if sha256(restored) != sha256(raw):
        raise RuntimeError('ZSTD_RESTORED_SHA256_MISMATCH:' + str(path))
    # All paths are inside this run's newly-created output. Summary/index
    # updates atomically replace only this probe's earlier own artifact.
    temporary.replace(target)
    path.with_name(path.name + '.compression.json').write_text(json.dumps({
        'original_path': path.name, 'original_bytes': len(raw), 'original_sha256': sha256(raw),
        'compressed_path': target.name, 'compressed_bytes': target.stat().st_size,
        'compressed_sha256': sha256(target.read_bytes()), 'codec': 'zstd -3 -T1',
        'verified': 'decompressed_sha256'}, indent=2) + '\n')
    path.unlink()
    return target


def save_summary(output, summary):
    """Keep summary short; per-frame measurements and model arrays have files."""
    index = [{k: row.get(k) for k in ('id', 'frame_rendered', 'frame_analysed', 'physics_identical',
              'camera_identical', 'metrics_file', 'wall_orb', 'floor_orb', 'failure_reason')} for row in summary['frames']]
    # Compact index avoids repeating hundreds of HSV-source records in summary.
    index_path = write(output / 'frame-index.json', index, compact=True)
    value = {k: v for k, v in summary.items() if k != 'frames'}
    value.update(frame_count=len(index), frame_index={'path': index_path.name,
                 'sha256': sha256(index_path.read_bytes())})
    return write(output / 'summary.json', value)


def setup_proof(path):
    """A copied coordinator PASS is required even for this execution-only tool."""
    raw = Path(path).read_bytes()
    lines = [line for line in raw.decode().splitlines() if re.search(r'\bgcp2setup:', line)]
    if not lines or not re.search(r'\bgcp2setup:\s*PASS\b', lines[-1]):
        raise ValueError('GCP2SETUP_PASS_REQUIRED')
    return {'path': str(Path(path).resolve()), 'sha256': sha256(raw), 'pass_line': lines[-1]}


def validate_source(expected, *, root=ROOT):
    if not re.fullmatch(r'[0-9a-f]{40}', expected):
        raise ValueError('SOURCE_SHA_MUST_BE_40_LOWERCASE_HEX')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    if head != expected:
        raise ValueError('SOURCE_SHA_MISMATCH')
    changed = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'],
                                      cwd=root, text=True)
    if changed.strip():
        raise ValueError('TRACKED_SOURCE_MUST_BE_COMMITTED')
    return head


def _array_digest(value):
    array = np.ascontiguousarray(value)
    return sha256(str(array.dtype).encode() + repr(array.shape).encode() + array.tobytes())


def physics_fingerprint(model):
    """Hash compiled numeric physics fields, explicitly excluding render fields.

    MuJoCo material bindings (geom_matid), display groups/rgba and bounding
    metadata for rendering are not physical coefficients. Body/joint/dof,
    collision geom, contact pair, equality, tendon and actuator arrays plus
    solver options are included, with individual hashes for review.
    """
    prefixes = ('body_', 'jnt_', 'dof_', 'geom_', 'pair_', 'exclude_', 'eq_',
                'tendon_', 'wrap_', 'actuator_', 'sensor_', 'flex_', 'mesh_',
                'hfield_', 'skin_')
    omitted = {'geom_matid', 'geom_rgba', 'geom_group', 'geom_texcoord',
               'mesh_texcoord', 'mesh_texcoordadr', 'mesh_texcoordnum', 'mesh_facetexcoord',
               'skin_matid', 'skin_rgba', 'skin_group'}
    fields = {}
    for name in dir(model):
        if name.startswith(prefixes) or name in ('qpos0', 'qpos_spring', 'key_qpos', 'key_qvel',
                                                'key_act', 'key_ctrl', 'key_mpos', 'key_mquat'):
            value = getattr(model, name)
            if name not in omitted and isinstance(value, np.ndarray):
                fields[name] = _array_digest(value)
    for name in dir(model.opt):
        if name.startswith('_'):
            continue
        value = getattr(model.opt, name)
        if isinstance(value, (int, float, np.number, np.ndarray, list, tuple)):
            fields['opt.' + name] = _array_digest(np.asarray(value))
    if not fields:
        raise ValueError('NO_COMPILED_PHYSICS_FIELDS')
    return {'sha256': sha256(json.dumps(fields, sort_keys=True).encode()),
            'fields': fields, 'excluded_visual_fields': sorted(omitted)}


def camera_fingerprint(model):
    fields = {name: _array_digest(getattr(model, name)) for name in dir(model)
              if name.startswith('cam_') and isinstance(getattr(model, name), np.ndarray)}
    return {'sha256': sha256(json.dumps(fields, sort_keys=True).encode()), 'fields': fields}


def mask_score(predicted, expected):
    predicted, expected = np.asarray(predicted, bool), np.asarray(expected, bool)
    if predicted.shape != expected.shape:
        raise ValueError('MASK_SHAPE_MISMATCH')
    tp = int((predicted & expected).sum())
    fp = int((predicted & ~expected).sum())
    fn = int((~predicted & expected).sum())
    union = tp + fp + fn
    return {'tp': tp, 'fp': fp, 'fn': fn, 'true_pixels': int(expected.sum()),
            'predicted_pixels': int(predicted.sum()),
            'precision': tp / (tp + fp) if tp + fp else None,
            'recall': tp / (tp + fn) if tp + fn else None,
            'iou': tp / union if union else None,
            'pixel_accuracy': float((predicted == expected).mean())}


def surface_metrics(bgr, true_masks, predicted_masks=None):
    """Do not black out non-surface pixels: that would invent ORB edges."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    out = {}
    for label in ('wall', 'floor'):
        mask = np.asarray(true_masks[label], bool)
        keypoints = cv2.ORB_create(nfeatures=ORB_FEATURES).detect(gray, mask.astype(np.uint8) * 255)
        distance = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
        # ORB KeyPoint.size is its pyramid-scaled descriptor patch side.
        # The circumscribed circle covers every rotated square patch, hence
        # radius=size*sqrt(2)/2 introduces no fitted support-margin constant.
        interior = sum(distance[min(mask.shape[0] - 1, round(k.pt[1])),
                                min(mask.shape[1] - 1, round(k.pt[0]))] >= k.size * math.sqrt(2) / 2
                       for k in keypoints)
        row = {'eval_visible_pixels': int(mask.sum()), 'orb_count': len(keypoints),
               'orb_interior_descriptor_support_count': int(interior),
               'orb_per_1000_visible_pixels': 1000 * len(keypoints) / int(mask.sum()) if mask.any() else None,
               'orb_method': 'original grayscale + eval-only center mask; support may cross surface boundary'}
        if predicted_masks is not None:
            row['rgb_only_classification'] = mask_score(predicted_masks[label], mask)
        out[label] = row
    wall, floor = (np.asarray(true_masks[k], bool) for k in ('wall', 'floor'))
    if wall.any() and floor.any():
        # Float OpenCV Lab uses L 0..100, a/b around 0; Euclidean distance is dE76.
        lab = cv2.cvtColor(bgr.astype(np.float32) / 255., cv2.COLOR_BGR2LAB)
        centers = {k: np.median(lab[v], axis=0) for k, v in (('wall', wall), ('floor', floor))}
        out['wall_floor_colour_separation'] = {
            'median_Lab': {k: v.astype(float).tolist() for k, v in centers.items()},
            'median_delta_E76': float(np.linalg.norm(centers['wall'] - centers['floor'])),
            'median_delta_L': float(abs(centers['wall'][0] - centers['floor'][0]))}
    else:
        out['wall_floor_colour_separation'] = {'unmeasured_reason': 'WALL_OR_FLOOR_NOT_VISIBLE'}
    return out


def colour_range_masks(bgr, ranges):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    masks = {}
    for spec in ranges:
        mask = np.zeros(hsv.shape[:2], np.uint8)
        for lo, hi in spec['ranges']:
            mask |= cv2.inRange(hsv, np.asarray(lo, np.uint8), np.asarray(hi, np.uint8))
        masks[spec['label']] = mask > 0
    # Exact direct inequalities from the source-pinned legacy external table.
    # Keep RGB/PIL distinct from OpenCV HSV (PIL H has range 0..255).
    from PIL import Image
    b, g, r = bgr.astype(np.int16).transpose(2, 0, 1)
    masks['crate_blue'] = (b > 140) & (r < 90) & (g < 90)
    masks['crate_teal'] = (g > 140) & (b > 60) & (b < g) & (r < 90)
    masks['crate_pink'] = (r > 90) & (r > g + 25) & (b > g - 5) & (r > b)
    pil = np.asarray(Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)).convert('HSV'))
    masks['PIL_beam'] = (pil[..., 0] > 25) & (pil[..., 0] < 90) & (pil[..., 1] > 100) & (pil[..., 2] > 60)
    return masks


def colour_metrics(bgr, true_masks, ranges):
    masks = colour_range_masks(bgr, ranges)
    return {label: {'pixels': int(mask.sum()),
                    'surface_false_pixels': {k: int((mask & true_masks[k]).sum()) for k in ('wall', 'floor')},
                    'target_support_pixels': {k: int((mask & v).sum()) for k, v in true_masks.items()
                                              if k.startswith(('box_', 'beam_', 'paint_'))},
                    'mask_sha256': _array_digest(mask)} for label, mask in masks.items()}


def wall_views(static):
    """Deterministic map-authored fixture coverage, not a navigation search.

    Inspect two existing wall faces at the v1 audit's .75/1.5 m distances.
    The robot must fit inside map bounds; no wall or robot geometry is edited.
    Rejecting unsupported geometry is recorded rather than fabricating a view.
    """
    bounds = static['bounds_m']
    candidates = []
    for obstacle in static['obstacles']:
        if not obstacle['id'].startswith('wall_') or obstacle.get('yaw_rad', 0):
            continue
        center, half = np.array(obstacle['center_m']), np.array(obstacle['half_extents_m'])
        normal_axis = int(np.argmin(half))
        for sign in (-1, 1):
            normal = np.eye(2)[normal_axis] * sign
            for distance in WALL_DISTANCES_M:
                xy = center + normal * (half[normal_axis] + distance)
                if bounds[0] < xy[0] < bounds[1] and bounds[2] < xy[1] < bounds[3]:
                    # The shortest distance to every wall box must exceed the
                    # camera fixture's own selected wall distance. This rejects
                    # poses inside or closer to another obstruction, with no
                    # new clearance acceptance constant.
                    gaps = [float(np.linalg.norm(np.maximum(np.abs(xy - np.array(w['center_m'])) -
                                np.array(w['half_extents_m']), 0))) for w in static['obstacles']]
                    # 16 epsilon covers arithmetic roundoff from the handful
                    # of subtraction/norm operations; not a physical gap limit.
                    if min(gaps) >= distance - np.finfo(float).eps * 16:
                        candidates.append({'wall': obstacle['id'], 'distance_m': distance,
                                           'xyyaw': [float(xy[0]), float(xy[1]), math.atan2(-normal[1], -normal[0])],
                                           'minimum_wall_gap_m': min(gaps), 'span_m': float(max(half) * 2)})
    selected = []
    for distance in WALL_DISTANCES_M:
        options = [v for v in candidates if v['distance_m'] == distance]
        options.sort(key=lambda v: (v['wall'] in [x['wall'] for x in selected], -v['span_m'], v['wall'], v['xyyaw']))
        if options:
            selected.append(options[0])
    return selected


def _free_pose(model, data, body_name, xyz, yaw):
    body = model.body(body_name)
    if int(model.body_jntnum[body.id]) != 1:
        raise ValueError('FIXTURE_REQUIRES_ONE_FREE_JOINT:' + body_name)
    joint = int(model.body_jntadr[body.id])
    address = int(model.jnt_qposadr[joint])
    data.qpos[address:address + 7] = [*xyz, math.cos(yaw / 2), 0., 0., math.sin(yaw / 2)]
    address = int(model.jnt_dofadr[joint])
    data.qvel[address:address + 6] = 0


def default_free_z(model, body_name):
    body = model.body(body_name)
    joint = int(model.body_jntadr[body.id])
    return float(model.qpos0[int(model.jnt_qposadr[joint]) + 2])


def set_arm(model, data, robot_id, pwm, hardware):
    """Reuse only the pure production pulse conversion; construct no controller."""
    from sim.masterpi_dynamics_v2 import MasterPiDynamicsV2
    targets = MasterPiDynamicsV2.pulse_to_joint_targets(SimpleNamespace(physical_params=hardware), pwm)
    joints = {'yaw': ('arm_yaw',), 'shoulder': ('shoulder',), 'elbow': ('elbow',),
              'wrist': ('wrist_pitch',), 'gripper': ('left_gripper_close', 'right_gripper_close')}
    for name, value in targets.items():
        for joint_name in joints[name]:
            joint = model.joint(robot_id + '__' + joint_name)
            if int(model.jnt_limited[joint.id]):
                value = float(np.clip(value, *model.jnt_range[joint.id]))
            data.qpos[int(model.jnt_qposadr[joint.id])] = value


def fixture(model, data, scene, view, pose, hardware):
    import mujoco
    from harness.zone_pair_highpose import HIGH
    from scripts.zone_teacher import FOLDED
    from sim.zone_cargo import kind
    mujoco.mj_resetData(model, data)
    x, y, yaw = view['xyyaw']
    if pose == 'high_beam_peer_occluded' or pose in ('box_palette', 'beam_end_bands'):
        # A .75 m wall fixture cannot contain the entire paired formation.
        # Reuse the other already registered view distance (1.5 m) so the real
        # 0.60 m beam/peer remain in the room, rather than crossing a wall.
        backoff = max(WALL_DISTANCES_M) - view['distance_m']
        x -= math.cos(yaw) * backoff
        y -= math.sin(yaw) * backoff
    static = scene.config['static_map']
    if pose.startswith('paint_'):
        center = static['regions']['zone_' + pose[-1]]['center_m']
        x, y, yaw = paint_fixture_xyyaw(center, pose[-1])
    spawns = scene.config['setup_only']['spawns']
    for rid, spawn in spawns.items():
        _free_pose(model, data, rid + '__robot', spawn[:3], spawn[3])
    pwm = dict(FOLDED if pose_pwm_mode(pose) == 'FOLDED' else {**HIGH, 1: 1500})
    _free_pose(model, data, 'r1__robot', (x, y, spawns['r1'][2]), yaw)
    # Unloaded partner is the original authored spawn; the occlusion fixture
    # alone installs the symmetric physical long-beam carrying formation.
    for rid in ('r1', 'r2', 'r3'):
        set_arm(model, data, rid, pwm if rid in ROBOTS else FOLDED, hardware)
    mujoco.mj_forward(model, data)
    setup = {'pose': pose, 'view': view, 'pwm': pwm, 'test_setup_ground_truth': True,
             'source': 'HIGH: harness.zone_pair_highpose; drive: scripts.zone_teacher.FOLDED',
             'contact_or_grasp_success_claimed': False}
    setup['r1_fixture_xyyaw'] = [x, y, yaw]
    setup['pwm_mode'] = pose_pwm_mode(pose)
    setup['positive_colour_fixture'] = pose in POSITIVE_POSES
    setup['positive_expected_target_masks'] = list(positive_targets(pose))
    if pose == 'paint_C':
        setup['paint_evaluation_view'] = 'paint_C_south_1p5m_v1'
    setup['minimum_wall_gap_m'] = center_wall_gap(static, (x, y))
    setup['wall_gap_definition'] = 'horizontal robot/body center to original wall-box boundary; not body collision clearance'
    if pose == 'box_palette':
        boxes = scene.config['setup_only']['objects'].values()
        box_sizes = {item['body_name']: model.geom_size[model.geom(item['body_name'] + '_geom').id].tolist()
                     for item in boxes}
        layout = palette_layout((x, y, yaw), box_sizes)
        for name, (bx, by, byaw) in layout.items():
            _free_pose(model, data, name, (bx, by, default_free_z(model, name)), byaw)
        setup['palette_half_extents_m'] = box_sizes
        setup['palette_layout_xyyaw'] = layout
        setup['palette_colors_unchanged'] = True
    if pose == 'beam_end_bands':
        xyz = (x + PALETTE_FORWARD_M[0] * math.cos(yaw),
               y + PALETTE_FORWARD_M[0] * math.sin(yaw), default_free_z(model, 'cargo_tex2_beam'))
        _free_pose(model, data, 'cargo_tex2_beam', xyz, yaw + math.pi / 2)
        setup['floor_beam_xyz_yaw'] = [*xyz, yaw + math.pi / 2]
        setup['beam_geometry_and_colour_unchanged'] = True
    if pose in POSITIVE_POSES:
        mujoco.mj_forward(model, data)
    if pose == 'high_beam_peer_occluded':
        grip = (data.geom('r1__left_finger').xpos + data.geom('r1__right_finger').xpos) / 2
        grasp = next(g for g in kind('long_beam').grasps if g.role == 'end_neg')
        rotation = np.array([[math.cos(yaw), -math.sin(yaw), 0.],
                             [math.sin(yaw), math.cos(yaw), 0.], [0., 0., 1.]])
        center = grip - rotation @ np.asarray(grasp.grip_xyz)
        _free_pose(model, data, 'cargo_tex2_beam', center, yaw)
        partner = [2 * center[0] - x, 2 * center[1] - y, spawns['r2'][2]]
        _free_pose(model, data, 'r2__robot', partner, yaw + math.pi)
        setup['beam_center_xyz'] = center.tolist()
        setup['partner_xyz_yaw'] = [*partner, yaw + math.pi]
        setup['occluders'] = ['cargo_tex2_beam', 'r2__robot']
        mujoco.mj_forward(model, data)
    setup['actual_robot_xyz'] = {rid: data.body(rid + '__robot').xpos.tolist() for rid in spawns}
    object_names = [item['body_name'] for item in scene.config['setup_only']['objects'].values()] + ['cargo_tex2_beam']
    setup['actual_object_xyz'] = {name: data.body(name).xpos.tolist() for name in object_names}
    setup['object_center_wall_gap_m'] = {name: center_wall_gap(static, xyz[:2])
                                          for name, xyz in setup['actual_object_xyz'].items()}
    if float(data.time) != 0 or np.any(data.eq_active):
        raise RuntimeError('STATIC_STEP0_WELD_OFF_REQUIRED')
    setup['qpos_sha256'] = _array_digest(data.qpos)
    return pwm, setup


def scene_map_selection(static):
    """Use the existing preparation-only heldout adapter, never widen the
    final-provider allow-list just to inspect H1/H2 materials.
    """
    from harness import zone_heldout_maps as heldout
    if static['map_id'] in heldout.IDS:
        if heldout.load(static['map_id']) != static:
            raise ValueError('PINNED_HELDOUT_MAP_MISMATCH')
        return heldout.BASE_ID, static['map_id']
    return static['map_id'], 'off'


def build_model(map_path, profile_name):
    """Compile the registered map with production XML hooks, without reset/step."""
    import mujoco
    from sim.multi_masterpi_production import build_multi_robot_xml
    from sim.zone_final_v3_scene import FinalV3Scene
    from sim.zone_cargo import add_cargo_xml, instances
    from sim.masterpi_dynamics_v2 import load_fitted_hardware
    from sim.masterpi_model_v3 import v3_hardware
    from sim.masterpi_drive_friction_v7 import transform_xml, DriveParameters
    from sim import masterpi_camera_review_v3 as camera
    from sim.masterpi_camera_profile import mujoco_pixel_intrinsic
    from sim.render_profile_selection import for_name
    from sim.final_pair_highpose_nearclip import wrap, audit
    from sim.zone_heldout_scene import install as heldout_install
    static = json.loads(map_path.read_text())
    base_map, heldout_map = scene_map_selection(static)
    scene = FinalV3Scene.from_spec({'map': base_map, 'seed': SEED,
                                  'goal': {'A': {'cyan': 1, 'red': 1}, 'B': {'green': 1, 'yellow': 1}},
                                  'extra_boxes': {}, 'team_cargo': []}, 'cargo_noslip_v1')
    scene = heldout_install(scene, heldout_map=heldout_map)
    if scene.config['static_map'] != static:
        raise ValueError('PINNED_MAP_MISMATCH')
    cargo = instances([{'item_id': 'tex2_beam', 'kind': 'long_beam',
                        'pose': list(scene.config['static_map']['regions']['pickup']['center_m']) + [0.]}])
    transform = scene.transform

    def with_beam(xml):
        xml, _ = add_cargo_xml(transform(xml), cargo, mirror_pairs=True)
        return xml

    scene.transform = with_beam
    module = for_name(profile_name)
    scene = wrap(module.install(scene, profile_name))
    hardware, _ = load_fitted_hardware()
    xml = scene.robot_transform(scene.transform(build_multi_robot_xml(hardware)), hardware=hardware,
                                calibrated_keys=hardware)
    xml = camera.transform_xml(xml, profile_id=camera.PROFILE_ID)
    xml = transform_xml(xml, DriveParameters(), 'mesh', 'off')
    before_colours = xml
    tree = ET.fromstring(xml)
    for suffix, rgba in END_COLOURS.items():
        geom = tree.find(f".//geom[@name='cargo_tex2_beam__{suffix}']")
        if geom is None:
            raise ValueError('ONE_ORIGINAL_BEAM_BAND_REQUIRED:' + suffix)
        geom.set('rgba', ' '.join(map(str, rgba)))
    xml = ET.tostring(tree, encoding='unicode')
    scene.manifest['scene_tex2_eval_end_colour_fixture'] = {
        'version': 'tex2_eval_existing_teal_blue_bands_v1', 'source': END_COLOUR_SOURCE,
        'colours': END_COLOURS, 'appearance_only': True,
        'before_xml_sha256': sha256(before_colours.encode()), 'after_xml_sha256': sha256(xml.encode()),
        'integrated_grasp_act_scene_toggle_verified': False}
    model = mujoco.MjModel.from_xml_string(xml)
    hardware = v3_hardware(hardware)
    # Same non-fitted raw PWM yaw center as MasterPiDynamicsV2.__init__.
    hardware.setdefault('servo6_center_pwm', 1500.)
    for rid in ('r1', 'r2', 'r3'):
        cid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, rid + '__robot_cam')
        model.cam_pos[cid] = camera.POSITION_M
        model.cam_quat[cid] = camera.QUAT_WXYZ
        model.cam_resolution[cid] = (WIDTH, HEIGHT)
        model.cam_sensorsize[cid] = (WIDTH, HEIGHT)
        model.cam_intrinsic[cid] = mujoco_pixel_intrinsic(WIDTH, HEIGHT)
    return model, scene, hardware, xml, {
        'render_profile': module.verify_model(model, profile_name),
        'nearclip': audit(model, base_profile=profile_name), 'camera': camera.record()}


def geometry_groups(model, scene):
    import mujoco
    groups = {'wall': set(), 'floor': set(), 'beam': set(), 'peer_r1': set(), 'peer_r2': set()}
    box_kinds = {item['body_name'] + '_geom': item['kind']
                 for item in scene.config['setup_only']['objects'].values()}
    for gid in range(model.ngeom):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, gid) or ''
        if name.startswith('zone_wall_'):
            groups['wall'].add(gid)
        elif name == 'floor':
            groups['floor'].add(gid)
        elif name.startswith('cargo_tex2_beam__'):
            groups['beam'].add(gid)
            if 'band_' in name:
                groups.setdefault('beam_' + name.split('band_')[-1], set()).add(gid)
        elif name.startswith(('zone_zone_', 'zone_pickup')):
            groups.setdefault('paint_' + name.removeprefix('zone_'), set()).add(gid)
        elif name.startswith('cargo_box_') and name.endswith('_geom'):
            groups.setdefault('box_' + box_kinds[name], set()).add(gid)
        for rid in ROBOTS:
            if name.startswith(rid + '__'):
                groups['peer_' + rid].add(gid)
    return groups


def render_frame(renderer, model, data, rid, groups):
    import mujoco
    from sim.masterpi_camera_profile import raw_fisheye_remap
    option = mujoco.MjvOption()
    option.geomgroup[:] = 1
    option.geomgroup[4:6] = 0  # identical to MultiMasterPiProductionV2 sensor policy
    renderer.update_scene(data, camera=rid + '__robot_cam', scene_option=option)
    ideal = renderer.render().copy()
    renderer.enable_segmentation_rendering()
    try:
        renderer.update_scene(data, camera=rid + '__robot_cam', scene_option=option)
        seg = renderer.render().copy()
    finally:
        renderer.disable_segmentation_rendering()
    mx, my = raw_fisheye_remap(WIDTH, HEIGHT)
    rgb = cv2.remap(ideal, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    # Nearest-neighbor remap never interpolates truth IDs; outside sensor is -1.
    ids = np.where(seg[..., 1] == int(mujoco.mjtObj.mjOBJ_GEOM), seg[..., 0], -1).astype(np.float32)
    ids = cv2.remap(ids, mx, my, cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=-1).astype(np.int32)
    masks = {name: np.isin(ids, list(geoms)) for name, geoms in groups.items()}
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), masks


def detector_results(bgr, pwm):
    from harness.zone_color_boxes import detect_own, OWN_PROFILE_ZONE
    from harness.owncam_pair_beam_v2 import observe_beam
    # Actual legacy RGB-only detectors. Pixel HSV tables below additionally
    # cover zone paint and externally pinned colour end-bands; they must not be
    # called full geometry/shape detector verification.
    return {'boxes_own_zone_v2': detect_own(bgr, pwm, profile=OWN_PROFILE_ZONE),
            'beam_legacy_dark_band_v2': observe_beam(bgr, pwm)}


def boundary_metrics(bgr, pwm, true_masks, profile):
    """Frozen wall-band detector and v2-only candidate, with truth only scoring.

    The legacy analytic commanded-pose camera is intentionally identified in
    the output. This component regression is not admission of a new measured
    camera calibration or a pose/localization result.
    """
    from harness.vision_loc_protocol import load_vis3
    from harness.opencv_wall_observation import DETECTOR
    from harness.scene_tex2_perception import detect_boundaries
    vl, _ = load_vis3()
    mp = vl.mp
    columns = mp.column_positions(DETECTOR['columns'], DETECTOR['strip_half_px'])
    # Zero bias is the identity geometry correction, not an accuracy bound.
    camera = mp.column_model(pwm, 0., columns)
    und = mp.undistort(bgr)
    masks = {k: cv2.remap(v.astype(np.uint8), mp._UNDISTORT[0], mp._UNDISTORT[1],
                          cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT) > 0
             for k, v in true_masks.items() if k in ('wall', 'floor')}
    expected = []
    for u in columns:
        rows = np.flatnonzero(masks['wall'][:-1, u] & masks['floor'][1:, u])
        expected.append(rows.astype(float) + .5)
    scans = {'legacy_uniform_band': mp.detect_boundaries(und, camera, DETECTOR)}
    if profile == 'walls_floor_textured_v2':
        scans['v2_nominal_window_adapter'] = detect_boundaries(mp, und, camera, profile=profile, params=DETECTOR)
    scores = {}
    for name, scan in scans.items():
        candidates = np.isfinite(scan.vb)
        residuals = [float(np.min(abs(scan.vb[j, k] - expected[j]))) for j, k in zip(*np.nonzero(candidates))
                     if len(expected[j])]
        scores[name] = {'candidate_n': int(candidates.sum()),
                        'candidate_columns_n': int(candidates.any(axis=1).sum()),
                        'eval_visible_boundary_columns_n': sum(bool(len(e)) for e in expected),
                        'eval_candidates_without_visible_boundary_n': sum(int(candidates[j].sum())
                                                                 for j, e in enumerate(expected) if not len(e)),
                        'eval_nearest_boundary_residual_px': residuals,
                        'accuracy_threshold_added': False}
    return {'detectors': scores, 'camera_geometry': 'legacy analytic own-command FK, identity bias; not v3 calibrated',
            'qualification': 'detector-component regression only; no localization or new-camera calibration claim'}


def funnel(rows, expected_frames):
    """Cumulative counts; every failed event has category/object/gap fields."""
    stages = ('frame_rendered', 'frame_analysed', 'physics_identical', 'camera_identical')
    alive = list(rows)
    result = []
    for stage in stages:
        rejected = [r for r in alive if not r.get(stage, False)]
        passed = [r for r in alive if r.get(stage, False)]
        result.append({'stage': stage, 'input_n': len(alive), 'cumulative_pass_n': len(passed),
                       'rejected_n': len(rejected), 'rejections': [
                           {'frame': r['id'], 'category': r.get('failure_category', stage.upper() + '_FAILED'),
                            'blocking_object': r.get('blocking_object', 'not_applicable_static_material_probe'),
                            'minimum_gap_m': r.get('minimum_gap_m'),
                            'reason': r.get('failure_reason', stage.upper() + '_FAILED')} for r in rejected]})
        alive = passed
    return {'schema': 'ugrp.scene_tex2_funnel.v1', 'planned_frames': expected_frames,
            'recorded_frame_events': len(rows), 'stages': result,
            'scope': 'static camera audit, not a teacher gate or task-success funnel'}


def run(output, profiles, source_sha, proof, poses=None):
    import mujoco
    from scripts.generate_scene_textures import MAPS
    from scripts.audit_scene_textures import color_ranges
    from harness.scene_tex2_perception import surface_masks
    ranges, inventory, pinned = color_ranges()
    external_path = ROOT / 'experiments/2026-10-15-scene-tex2/color_external_sources.json'
    external = json.loads(external_path.read_text())
    for source_path, expected_sha in external['source_sha256'].items():
        if sha256((ROOT / source_path).read_bytes()) != expected_sha:
            raise ValueError('COLOUR_SOURCE_CHANGED:' + source_path)
    ranges += external['additional_hsv_ranges']
    output.mkdir(parents=True, exist_ok=False)
    (output / 'eval_only').mkdir()
    colour_sources = write(output / 'colour-sources.json', {'ranges': ranges, 'inventory': inventory,
                           'external_legacy': pinned, 'external_v2': external,
                           'external_v2_file_sha256': sha256(external_path.read_bytes()),
                           'opencv_hsv_ranges_n': len(ranges), 'direct_rgb_pil_ranges_n': 4})
    summary = {'schema': 'ugrp.scene_tex2_camera_probe.v1', 'status': 'RUNNING', 'source_sha': source_sha,
               'scope': 'static mj_forward-only evaluation; no step, controller, planner, model or grasp success',
               'host': platform.node(), 'platform': platform.platform(), 'mujoco': mujoco.__version__,
               'opencv': cv2.__version__, 'numpy': np.__version__, 'MUJOCO_GL': os.environ.get('MUJOCO_GL'),
               'setup_proof': proof, 'profiles': list(profiles), 'model_calls': 0, 'physics_steps': 0,
               'colour_sources': {'path': colour_sources.name, 'sha256': sha256(colour_sources.read_bytes())},
               'sim_s': 0., 'frames': [], 'models': [], 'unexecuted': [],
               'source_paths': [str(p) for p in MAPS], 'source_map_sha256': {p.name: sha256(p.read_bytes()) for p in MAPS},
               'baseline': profiles[0], 'acceptance_thresholds': 'none added; raw distributions and exact parity reported',
               'limits': ['static fixtures do not establish delivery, localization or physical grasp success',
                          'colour range masks do not replace full detector geometry checks',
                          'grasp_act_scene consumer/toggle absent; exact pinned end RGBA copied into eval fixture only',
                          'legacy black-band detector is reported independently of the pinned teal/blue HSV masks',
                          'positive targets with zero visible pixels remain unverified; negative detector parity cannot establish positive detection'],
               'reproduction_command': [sys.executable, '-m', 'scripts.probe_scene_tex2', '--execute',
                                        '--source-sha', source_sha, '--setup-proof', proof['path'],
                                        '--output', str(output), '--profiles', *profiles]}
    baseline_models, baseline_frames = {}, {}
    if poses is not None:
        summary['reproduction_command'] += ['--poses', *poses]
    expected_frames = sum(planned_case_count(len(wall_views(json.loads(path.read_text()))), poses) for path in MAPS) * len(ROBOTS) * len(profiles)
    summary['planned_frames'] = expected_frames
    summary['requested_poses'] = list(poses) if poses is not None else None
    summary['base_poses'] = [pose for pose in POSES if poses is None or pose in poses]
    summary['positive_poses_at_view0'] = [pose for pose in POSITIVE_POSES if poses is None or pose in poses]
    abort_remaining = False
    save_summary(output, summary)
    try:
        for map_path in MAPS:
            static = json.loads(map_path.read_text())
            views = wall_views(static)
            if len(views) != len(WALL_DISTANCES_M):
                summary['unexecuted'].append({'map': map_path.stem, 'category': 'FIXTURE_UNAVAILABLE',
                    'reason': 'MAP_HAS_NO_UNOBSTRUCTED_AXIS_ALIGNED_FACE_AT_REGISTERED_DISTANCE',
                    'blocking_object': 'static_map_wall_geometry', 'minimum_gap_m': None,
                    'distances_found_m': [v['distance_m'] for v in views]})
            for profile in profiles:
                renderer = None
                try:
                    model, scene, hardware, xml, audits = build_model(map_path, profile)
                    physics, camera = physics_fingerprint(model), camera_fingerprint(model)
                    if profile == profiles[0]:
                        baseline_models[map_path.name] = (physics, camera)
                    reference_physics, reference_camera = baseline_models[map_path.name]
                    model_row = {'map': map_path.stem, 'profile': profile,
                                 'scene_xml_sha256': sha256(xml.encode()),
                                 'physics': physics, 'camera': camera, 'audits': audits,
                                 'physics_identical': physics['sha256'] == reference_physics['sha256'],
                                 'camera_identical': camera['sha256'] == reference_camera['sha256']}
                    stem = map_path.stem + '--' + profile
                    audit_path = write(output / 'eval_only' / (stem + '-model-audit.json'), model_row)
                    summary['models'].append({**{k: model_row[k] for k in ('map', 'profile', 'physics_identical', 'camera_identical')},
                                              'audit_file': str(audit_path.relative_to(output))})
                    (output / 'eval_only' / (stem + '.xml')).write_text(xml)
                    write(output / 'eval_only' / (stem + '-manifest.json'), scene.manifest)
                    renderer = mujoco.Renderer(model, HEIGHT, WIDTH)
                    groups = geometry_groups(model, scene)
                    data = mujoco.MjData(model)
                    for vi, view in enumerate(views):
                        for pose in poses_for_view(vi, poses):
                            pwm, setup = fixture(model, data, scene, view, pose, hardware)
                            for rid in ROBOTS:
                                case = f'{map_path.stem}--view{vi}--{pose}--{rid}'
                                name = case + '--' + profile
                                row = {'id': name, 'case': case, 'map': map_path.stem, 'view': vi,
                                       'pose': pose, 'robot': rid, 'profile': profile,
                                       'physics_identical': model_row['physics_identical'],
                                       'camera_identical': model_row['camera_identical'], 'frame_rendered': False,
                                       'frame_analysed': False, 'minimum_gap_m': setup['minimum_wall_gap_m'],
                                       'positive_colour_fixture': pose in POSITIVE_POSES}
                                summary['frames'].append(row)
                                try:
                                    bgr, masks = render_frame(renderer, model, data, rid, groups)
                                    row['frame_rendered'] = True
                                    frame_path = output / (name + '.png')
                                    if not cv2.imwrite(str(frame_path), bgr):
                                        raise OSError('FRAME_PNG_WRITE_FAILED')
                                    jpeg = cv2.imencode('.jpg', bgr, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])[1].tobytes()
                                    (output / (name + '.jpg')).write_bytes(jpeg)
                                    row['png_sha256'] = sha256(frame_path.read_bytes())
                                    row['jpeg_sha256'] = sha256(jpeg)
                                    write(output / 'eval_only' / (name + '-setup.json'), setup)
                                    for label, mask in masks.items():
                                        cv2.imwrite(str(output / 'eval_only' / (name + '--' + label + '.png')),
                                                    mask.astype(np.uint8) * 255)
                                    encodings = {'png': bgr, 'jpeg': cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)}
                                    row['metrics'] = {}
                                    signatures = {}
                                    for encoding, image in encodings.items():
                                        # Apply the SAME v2-only candidate to
                                        # baseline images for comparison, solely
                                        # inside this evaluation tool. Baseline
                                        # consumers/defaults remain unmodified.
                                        predicted = surface_masks(image, 'walls_floor_textured_v2')
                                        predicted = {'wall': predicted['walls'], 'floor': predicted['floor']}
                                        detectors = detector_results(image, pwm)
                                        colours = colour_metrics(image, masks, ranges)
                                        metrics = {'surfaces': surface_metrics(image, masks, predicted),
                                                   'nominal_surface_classifier_profile': 'walls_floor_textured_v2',
                                                   'detectors': detectors, 'colour_ranges': colours,
                                                   'wall_band_detectors': boundary_metrics(image, pwm, masks, profile),
                                                   'eval_beam_pixels': int(masks['beam'].sum()),
                                                   'eval_target_visible_pixels': {label: int(mask.sum()) for label, mask in masks.items()
                                                                                if label.startswith(('box_', 'beam_', 'paint_'))},
                                                   'positive_fixture_expected_target_visible_pixels': {
                                                       label: int(masks[label].sum()) for label in positive_targets(pose)},
                                                   'eval_partner_pixels': int(masks['peer_' + ('r2' if rid == 'r1' else 'r1')].sum())}
                                        row['metrics'][encoding] = metrics
                                        signatures[encoding] = {'detectors': detectors, 'colours': colours}
                                    if profile == profiles[0]:
                                        baseline_frames[case] = signatures
                                    reference = baseline_frames.get(case)
                                    row['baseline_comparison'] = {'baseline': profiles[0],
                                        'detector_output_identical': {enc: signatures[enc]['detectors'] == reference[enc]['detectors']
                                                                    for enc in encodings} if reference else None,
                                        'range_mask_changed_pixels_not_available': 'mask hashes/pixel-support counts recorded per range',
                                        'colour_range_mask_identical': {enc: {label: colours['mask_sha256'] == reference[enc]['colours'][label]['mask_sha256']
                                            for label, colours in signatures[enc]['colours'].items()} for enc in encodings} if reference else None}
                                    row['frame_analysed'] = True
                                    metrics_path = write(output / (name + '-metrics.json'), row)
                                    row['metrics_file'] = metrics_path.name
                                    row['wall_orb'] = {enc: value['surfaces']['wall']['orb_count'] for enc, value in row['metrics'].items()}
                                    row['floor_orb'] = {enc: value['surfaces']['floor']['orb_count'] for enc, value in row['metrics'].items()}
                                    # Detailed records are saved above, never
                                    # repeated in the batch's short summary.
                                    row.pop('metrics')
                                    row.pop('baseline_comparison')
                                except Exception as exc:
                                    row.update(frame_analysed=False, failure_category='FRAME_ANALYSIS_HOST_ERROR',
                                               failure_reason=f'{type(exc).__name__}: {exc}')
                    save_summary(output, summary)
                except Exception as exc:
                    summary['unexecuted'].append({'map': map_path.stem, 'profile': profile,
                        'category': 'MODEL_HOST_ERROR', 'reason': f'{type(exc).__name__}: {exc}',
                        'blocking_object': 'model_compile_or_render_audit', 'minimum_gap_m': None,
                        'traceback': traceback.format_exc()})
                    # A broken shared model/audit path should be diagnosed
                    # before repeating the same host error on all maps.
                    abort_remaining = True
                finally:
                    if renderer is not None:
                        renderer.close()
                if abort_remaining:
                    break
            if abort_remaining:
                summary['unexecuted'].append({'category': 'PRIOR_MODEL_HOST_ERROR_STOP',
                    'reason': 'Remaining map/profile work stopped after model compile/audit failure; fix before resubmission',
                    'blocking_object': 'shared_model_compile_or_audit_path', 'minimum_gap_m': None,
                    'unexecuted_planned_frames_n': expected_frames - len(summary['frames'])})
                break
        summary['status'] = 'MEASURED_STATIC_ONLY' if (not summary['unexecuted'] and summary['frames'] and
            all(r['frame_analysed'] and r['physics_identical'] and r['camera_identical'] for r in summary['frames'])) else 'INCOMPLETE_OR_PARITY_FAIL'
    finally:
        table = funnel(summary['frames'], expected_frames)
        table.update(raw_path=str(output.resolve()), reproduction_command=summary['reproduction_command'],
                     unexecuted=summary['unexecuted'])
        rejection_path = write(output / 'rejection-table.json', table)
        summary['rejection_table'] = str(rejection_path.resolve())
        save_summary(output, summary)
        listed = {str(p.relative_to(output)): sha256(p.read_bytes()) for p in sorted(output.rglob('*'))
                  if p.is_file() and not p.name.startswith('SHA256SUMS.json')}
        # Hash values have fixed width, so updating summary contents cannot
        # change the manifest's storage choice; its file count is now frozen.
        manifest_bytes = (json.dumps(listed, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()
        manifest_name = 'SHA256SUMS.json' + ('.zst' if len(manifest_bytes) > 65536 else '')
        summary['sha256_manifest'] = str(output / manifest_name)
        save_summary(output, summary)
        manifest_path = write(output / 'SHA256SUMS.json', {str(p.relative_to(output)): sha256(p.read_bytes())
              for p in sorted(output.rglob('*')) if p.is_file() and not p.name.startswith('SHA256SUMS.json')})
        if str(manifest_path) != summary['sha256_manifest']:
            raise RuntimeError('MANIFEST_STORAGE_CHOICE_CHANGED')
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--profiles', nargs='+', choices=PROFILES, default=list(PROFILES))
    parser.add_argument('--poses', nargs='+', choices=POSES + POSITIVE_POSES, default=None)
    parser.add_argument('--setup-proof', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args(argv)
    # Before simulator import, compilation, assets, output creation or any SSH.
    if platform.system() != 'Linux':
        parser.error('Linux gcp2 only; Mac MuJoCo rendering/simulation is forbidden')
    if not args.execute:
        parser.error('--execute is required after gcp2setup PASS')
    if len(set(args.profiles)) != len(args.profiles):
        parser.error('duplicate profiles are not allowed')
    if args.poses is not None and len(set(args.poses)) != len(args.poses):
        parser.error('duplicate poses are not allowed')
    if args.profiles[0] != 'floor_light_v1':
        parser.error('first profile must be floor_light_v1 for exact baseline comparison')
    if args.output.exists():
        parser.error('output must be a new directory; preserve prior raw results')
    proof = setup_proof(args.setup_proof)
    validate_source(args.source_sha)
    subprocess.run(['zstd', '--version'], check=True, stdout=subprocess.DEVNULL)
    os.chdir(ROOT)  # pinned repository-relative texture paths
    result = run(args.output.resolve(), args.profiles, args.source_sha, proof, poses=args.poses)
    print(json.dumps({'status': result['status'], 'frames': len(result['frames']),
                      'unexecuted': len(result['unexecuted']), 'rejection_table': result['rejection_table'],
                      'sha256_manifest': result['sha256_manifest']}))
    return 0 if result['status'] == 'MEASURED_STATIC_ONLY' else 1


if __name__ == '__main__':
    raise SystemExit(main())
