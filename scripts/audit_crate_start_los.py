"""Plan-generation-only assigned-lug LOS; static kinematics/rays, no physics/render.

Reuses the 422cc0ad static rotation audit's PWM, camera binding, 1-degree
grid and BandVisibility first-hit test. Never called by a teacher/controller.
"""
from __future__ import annotations

import hashlib
import math
from collections import Counter

import mujoco
import numpy as np

from scripts.audit_grasp_act_visibility import BandVisibility
from scripts.audit_masterpi_v3_static import START_PWM, set_static_pwm
from sim.cargo_teacher_profile import CRATE
from sim.crate_scene import make_crate_scene
from sim import masterpi_camera_review_v3 as camera
from sim.masterpi_drive_friction_v7 import DriveParameters, transform_xml
from sim.multi_masterpi_production import build_multi_robot_xml
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher
from sim.zone_cargo_contact import apply
from sim.warehouse_mission import cargo_specs_for_seed, terrain_specs_for_seed, WAREHOUSE_ZONES

OPTION = 'start_assigned_los_v1'
MIN_PROBES = 5
PITCHES = VisibleOnlyGraspTeacher.SEARCH_V2_CIRCLE_PITCHES


def free(model, data, name, xyz, yaw):
    bid = model.body(name).id
    adr = int(model.jnt_qposadr[model.body_jntadr[bid]])
    data.qpos[adr:adr+7] = [*xyz, math.cos(yaw/2), 0., 0., math.sin(yaw/2)]


def kin(model, data):
    mujoco.mj_kinematics(model, data)
    mujoco.mj_camlight(model, data)


def scan(model, data, band, rid, role, q, *, stop_at_gate=False):
    """Frozen other bodies; yaw -180..179 at each implemented search pitch.

    Early exit returns a >=5 witness, not a claimed global maximum. Failed
    starts always exhaust all 1080 views. Full mode retains the prior audit.
    """
    counts = []
    adr = int(model.jnt_qposadr[model.body_jntadr[model.body(rid+'__robot').id]])
    for w, e in PITCHES:
        data.qpos[:] = q
        set_static_pwm(model, data, rid, {**START_PWM, 3: w, 4: e, 6: 1500})
        mx = anyn = gate = views = 0
        witness = None
        occ = Counter()
        for deg in range(-180, 180):
            angle = math.radians(deg)
            data.qpos[adr+3:adr+7] = [math.cos(angle/2), 0., 0., math.sin(angle/2)]
            kin(model, data)
            value = band.measure(data, rid, role)
            n = value['visible_probes']
            views += 1
            anyn += n > 0
            gate += n >= MIN_PROBES
            occ.update(value['occluders'])
            if n > mx:
                mx = n
                witness = {'yaw_deg': deg, 'visible_probes': n,
                           'camera_xyz': data.cam_xpos[band.cameras[rid]].tolist()}
            if stop_at_gate and gate:
                break
        counts.append({'pitch': [w, e], 'max_seen': mx, 'views': views,
                       'any_angles': anyn, 'gate5_angles': gate, 'witness': witness,
                       'occluders': dict(occ)})
        if stop_at_gate and gate:
            break
    return {'pitch_results': counts, 'any': any(x['max_seen'] > 0 for x in counts),
            'gate5': any(x['max_seen'] >= MIN_PROBES for x in counts),
            'step_deg': 1, 'exhaustive': sum(x['views'] for x in counts) == 1080}


class CrateStartLOS:
    def __init__(self):
        self.models = {}

    def _model(self, episode):
        # Match the runner's standard XML path without constructing its world,
        # controller, reset, mj_forward, physics step or any renderer.
        key = (episode['scenario_id'], episode['seed'],
               episode.get('cargo_scene_version', 'crate_mass_030_v1'))
        if key not in self.models:
            scene = make_crate_scene({**episode, 'cargo_scene_version': key[2]})
            xml = build_multi_robot_xml(None,
                warehouse_specs=cargo_specs_for_seed(episode['seed']),
                warehouse_terrain=terrain_specs_for_seed(episode['seed']),
                warehouse_zones=WAREHOUSE_ZONES)
            xml = transform_xml(scene.robot_transform(apply(scene.transform(xml), 'cargo_noslip_v1')),
                                DriveParameters())
            model = mujoco.MjModel.from_xml_string(xml)
            for rid in ('r1', 'r2', 'r3'):
                cid = model.camera(rid+'__robot_cam').id
                model.cam_pos[cid] = camera.POSITION_M
                model.cam_quat[cid] = camera.QUAT_WXYZ
            self.models[key] = (scene, model, mujoco.MjData(model), BandVisibility(model, CRATE),
                                hashlib.sha256(xml.encode()).hexdigest())
        return self.models[key]

    def check(self, episode, *, exhaustive=False):
        scene, model, data, band, digest = self._model(episode)
        data.qpos[:] = model.qpos0
        for rid, pose in episode['spawns'].items():
            free(model, data, rid+'__robot', pose[:3], pose[3])
            set_static_pwm(model, data, rid, {**START_PWM, 6: episode['initial_pan'].get(rid, 1500)})
        for obj in scene.config['setup_only']['objects'].values():
            free(model, data, obj['body_name'], obj['position_m'], 0.)
        for cargo in scene.cargo:
            x, y, yaw = cargo.pose
            free(model, data, 'cargo_'+cargo.item_id, [x, y, .0005], yaw)
        x, y, yaw = episode['cargo_pose']
        free(model, data, 'cargo_'+CRATE.item_id, [x, y, .0005], yaw)
        data.eq_active[:] = 0
        kin(model, data)
        q = data.qpos.copy()
        robots = {}
        for rid, role in episode['roles'].items():
            data.qpos[:] = q
            robots[rid] = {'role': role, **scan(model, data, band, rid, role, q,
                                              stop_at_gate=not exhaustive)}
        return {'robots': robots, 'accepted': all(r['gate5'] for r in robots.values()),
                'scene_xml_sha256': digest, 'mj_step_calls': 0, 'render_calls': 0}


def summarize(rows):
    n = len(rows)
    return {'N': n, 'both_pass': sum(r['accepted'] for r in rows),
            'rejected': sum(not r['accepted'] for r in rows),
            'rejection_rate': sum(not r['accepted'] for r in rows)/n if n else 0.,
            'per_robot': {rid: {'pass': sum(r['robots'][rid]['gate5'] for r in rows),
                               'rejected': sum(not r['robots'][rid]['gate5'] for r in rows), 'N': n,
                               'rejection_rate': sum(not r['robots'][rid]['gate5'] for r in rows)/n if n else 0.}
                          for rid in ('r1', 'r2')}}
