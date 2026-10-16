"""Offline S2 visibility candidate. Own PWM + fixed geometry + own RGB only.

ROS robot_self_filter's ray/body SHADOW rule, with conservative local boxes
instead of measured joint TF. No simulator is instantiated or stepped. Cargo
pose cannot be recovered from PWM; only its own-RGB cyan silhouette is masked.
"""
from functools import lru_cache
import copy
import math
import xml.etree.ElementTree as ET
import cv2
import numpy as np
from scipy.spatial.transform import Rotation
from harness.visual_arm import SERVO_DEVIATION, PULSE_PER_DEGREE
from sim.masterpi_camera_profile import scaled_camera_matrix
from sim.masterpi_camera_review_v3 import POSITION_M, QUAT_WXYZ
from sim.masterpi_camera_review_v1 import quat_matrix

OPTION = 'command_geometry_v1'
PARAMS = dict(rows_px=[4, 470], prior_visible_probability=.95,
              robot_padding_m=.002, cargo_padding_px=2, min_columns=6)
LOCAL_OPTICAL = quat_matrix(QUAT_WXYZ) @ np.diag([1., -1., -1.])
K = scaled_camera_matrix(640, 480)
K_INV = np.linalg.inv(K)


def numbers(s):
    return np.fromstring(s, sep=' ')


def rotation(el):
    if 'quat' in el.attrib:
        return quat_matrix(numbers(el.get('quat')))
    return Rotation.from_euler('xyz', numbers(el.get('euler', '0 0 0'))).as_matrix()


@lru_cache(maxsize=1)
def fixed_robot():
    # The XML string builder supplies fixed drawing geometry, never MjModel/Data.
    from sim.masterpi_model_v3 import build_v3_xml
    root = ET.fromstring(build_v3_xml())
    meshes = {m.get('name'): numbers(m.get('vertex')).reshape(-1, 3)
              for m in root.findall('./asset/mesh')}
    return root.find('./worldbody/body[@name="robot"]'), meshes


def commanded_joints(pose):
    p = {int(k): float(v) for k, v in pose.items()}
    nominal = lambda k: p[k] - SERVO_DEVIATION.get(k, 0)
    return dict(arm_yaw=math.radians((p[6]-1500)/PULSE_PER_DEGREE),
        shoulder=math.radians(90-(nominal(5)-1500)/PULSE_PER_DEGREE),
        elbow=-math.radians((nominal(4)-1500)/PULSE_PER_DEGREE),
        wrist_pitch=math.radians((nominal(3)-1500)/PULSE_PER_DEGREE),
        closure=np.clip((2000-p.get(1, 1500))/500, 0, 1)*.016)


def robot_boxes(pose, camera=None, padding=PARAMS['robot_padding_m']):
    """(category, center, orientation, half extents), conservative visual boxes.

    Jaw boxes sweep the full open-to-command range. Wheel rotation is unknown;
    fixed wheel envelopes cover all roller angles. The wrist is rigid to the
    calibrated camera; other links use commanded FK (unmeasured compliance).
    """
    root, meshes = fixed_robot(); joints = commanded_joints(pose); boxes = []
    def walk(body, parent_o, parent_r):
        name = body.get('name'); r = parent_r @ rotation(body)
        o = parent_o + parent_r @ numbers(body.get('pos', '0 0 0'))
        for j in body.findall('joint'):
            if j.get('type') == 'hinge':
                r = r @ Rotation.from_rotvec(numbers(j.get('axis'))*joints.get(j.get('name'), 0)).as_matrix()
        if name == 'gripper' and camera is not None:
            r = np.asarray(camera._rot) @ LOCAL_OPTICAL.T
            o = np.asarray(camera.origin) - r @ np.asarray(POSITION_M)
        if name.startswith('wheel_'):
            boxes.append(('chassis', o, parent_r, np.array([.036, .021, .036])+padding))
            return
        category = 'gripper' if name in ('gripper', 'left_jaw', 'right_jaw') else ('chassis' if name == 'robot' else 'arm')
        for g in body.findall('geom'):
            if not g.get('name', '').startswith('v3_') or g.get('group') == '5':
                continue
            if g.get('rgba', '1 1 1 1').split()[-1] == '0':
                continue
            gr = rotation(g); center = numbers(g.get('pos', '0 0 0'))
            kind = g.get('type'); size = numbers(g.get('size', '0'))
            if kind == 'mesh':
                v = meshes[g.get('mesh')]; lo, hi = v.min(0), v.max(0)
                center = center + gr @ ((lo+hi)/2); half = (hi-lo)/2
            elif 'fromto' in g.attrib:
                ends = numbers(g.get('fromto')).reshape(2, 3)
                center = ends.mean(0); half = abs(ends[1]-ends[0])/2+size[0]; gr = np.eye(3)
            elif kind == 'box':
                half = size
            elif kind == 'sphere':
                half = np.full(3, size[0])
            elif kind in ('cylinder', 'capsule'):
                half = np.array([size[0], size[0], size[1]+(size[0] if kind == 'capsule' else 0)])
            else:
                raise ValueError(f'unsupported fixed visual geometry {kind}')
            if name in ('left_jaw', 'right_jaw'):
                sign = -1 if name == 'left_jaw' else 1
                delta = np.array([0, sign*joints['closure']/2, 0])
                center = center + delta
                half = half + abs(gr.T@delta)
            boxes.append((category, o+r@center, r@gr, half+padding))
        for child in body.findall('body'):
            walk(child, o, r)
    walk(root, np.zeros(3), np.eye(3))
    return boxes


def box_depth(origin, rays, center, axes, half):
    """Ray/OBB slab intersection; ray parameter (optical depth for z=1 rays)."""
    p = (np.asarray(origin)-center) @ axes
    d = np.asarray(rays) @ axes
    parallel = abs(d) < 1e-12
    safe = np.where(parallel, 1., d)
    a, b = (-half-p)/safe, (half-p)/safe
    low = np.where(parallel, -np.inf, np.minimum(a, b)).max(-1)
    high = np.where(parallel, np.inf, np.maximum(a, b)).min(-1)
    invalid = (parallel & (abs(p)>half)).any(-1)
    hit = ~invalid & (high >= np.maximum(low, 1e-6))
    return np.where(hit, np.maximum(low, 0.), np.inf)


def shadow_depths(origin, rays, boxes):
    out = {k: np.full(np.asarray(rays).shape[:-1], np.inf) for k in ('gripper', 'arm', 'chassis')}
    for category, center, axes, half in boxes:
        np.minimum(out[category], box_depth(origin, rays, center, axes, half), out=out[category])
    return out


def pixel_rays(cm, columns, rows):
    u, v = np.broadcast_arrays(np.asarray(columns), np.asarray(rows))
    return np.stack([u, v, np.ones_like(u)], -1) @ K_INV.T @ cm._rot.T


class Visibility:
    def __init__(self):
        self.cache = {}; self.cargo = None
        self.audit = dict(option=OPTION, parameters=copy.deepcopy(PARAMS), rows=[],
                          gt_inputs=False, limitations='command FK and conservative visual boxes; cargo RGB misses possible')

    def on_rgb(self, rgb):
        from harness import vision_loc_protocol as vp
        from harness.zone_solo_cyan_scene_change import cyan
        if rgb is None:
            self.cargo = None; return
        vl = vp.load_vis3()[0]
        image = cv2.remap(rgb, *vl.mp._UNDISTORT, cv2.INTER_LINEAR)
        # scene_change.cyan accepts BGR, as does the saved detector.
        m = cyan(cv2.cvtColor(image, cv2.COLOR_RGB2BGR)).astype(np.uint8)
        radius = PARAMS['cargo_padding_px']
        self.cargo = cv2.dilate(m, np.ones((2*radius+1, 2*radius+1), np.uint8)).astype(bool)

    def depth_image(self, cm, pose):
        key = (tuple(sorted((int(k), int(v)) for k, v in pose.items())), cm.origin.tobytes(), cm._rot.tobytes(), cm.columns.tobytes())
        if key not in self.cache:
            rays = pixel_rays(cm, cm.columns[None, :], np.arange(480)[:, None])
            depth = shadow_depths(cm.origin, rays, robot_boxes(pose, cm))
            self.cache[key] = np.minimum.reduce(list(depth.values()))
        return self.cache[key]

    def apply(self, pf, obs, pose, t):
        cm = pf.column_model_for(pose); rows, _ = pf.expected(pf.px, pose)
        finite = np.isfinite(rows); rr = np.rint(np.where(finite, rows, 0)).astype(int).clip(0, 479)
        cols = np.arange(len(obs.columns)); low, high = PARAMS['rows_px']
        in_view = finite & (rows >= low) & (rows <= high)
        depths = self.depth_image(cm, pose)
        # For visible predicted floor points cm alpha+t*beta gives optical depth.
        trace = cm.t_of_row(rows); optical = cm.alpha[:, 2]+trace*cm.beta[:, 2]
        clear = depths[rr, cols] > optical
        cargo_clear = np.ones_like(clear)
        if self.cargo is not None:
            cargo_clear = ~self.cargo[rr, obs.columns.astype(int)]
        probability = pf._weights() @ (in_view & clear & cargo_clear)
        keep = probability >= PARAMS['prior_visible_probability']
        dr = np.rint(np.nan_to_num(obs.b_lo)).astype(int).clip(0, 479)
        dt = cm.t_of_row(obs.b_lo); dd = cm.alpha[:, 2]+dt*cm.beta[:, 2]
        detected_clear = depths[dr, cols] > dd
        if self.cargo is not None:
            detected_clear &= ~self.cargo[dr, obs.columns.astype(int)]
        keep &= detected_clear & (obs.b_kind == 1)
        masked = copy.deepcopy(obs)
        masked.b_kind[~keep] = 0; masked.t_kind[:] = 0
        self.audit['rows'].append(dict(t=float(t), detected=int((obs.b_kind == 1).sum()),
            kept=int(keep.sum()), prior_view_columns=int((pf._weights() @ in_view >= .95).sum()),
            detected_self_shadow=int(((obs.b_kind == 1) & (depths[dr, cols] <= dd)).sum()),
            detected_cargo_shadow=int(((obs.b_kind == 1) & ~detected_clear & (depths[dr, cols] > dd)).sum())))
        return masked if keep.sum() >= PARAMS['min_columns'] else None
