"""GCP3 MJWarp cross-room Stage A probe; default-off skill modules.

Stage A: an unloaded solo robot starts west of the divider, crosses the 0.50 m
door and searches for zone B on the far side (180 SIM s cap).  Controller
inputs: own raw fisheye RGB, issued wheel/servo commands, egocentric memory.
Every controller call goes through a boundary audit that rejects ground-truth,
world-pose, static-map, spawn and top-camera keys and counts the attempts in
episode records (not runner-written constants).  Ground truth is written only
to eval-only artifacts and to the final arrival verdict.  See
experiments/2026-10-18-crossroom-carry/README.md.
"""
import argparse
from collections import deque
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
HZ = 10.
DT = 1. / HZ


def dump(p, v):
    Path(p).write_text(json.dumps(v, indent=2, allow_nan=False) + '\n')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def vendor_root():
    return ROOT / 'experiments/2026-10-18-crossroom-carry/vendor'


def register_vendor():
    """Register byte-vendored reuse under its original module names."""
    # The vendored modules import harness/sim at load time, before the
    # renderer/legacy paths are installed by prefixed_paths.  Keep the clone
    # root importable so a plain ``python scripts/visgoal_probe.py`` works.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    v = vendor_root()
    load_module('sim.grasp_act_solo_lookback', v / 'grasp_act_solo_lookback.py')
    load_module('sim.destination_visual_acquire', v / 'destination_visual_acquire.py')
    load_module('harness.scene_colour_boundary', v / 'scene_colour_boundary.py')
    load_module('harness.rovio_feature_statistics', v / 'rovio_feature_statistics.py')
    load_module('harness.egomem_object_association', v / 'egomem_object_association.py')
    load_module('harness.egocentric_landmark_memory', v / 'egocentric_landmark_memory.py')
    load_module('harness.mapbuild_command_prior', v / 'mapbuild_command_prior.py')
    load_module('sim.solo_carry_obstacles', v / 'solo_carry_obstacles.py')
    # The Stage A policy is the visgoal C build (commit c390105c2), byte-copied
    # here because PR #582 is a draft and main has no common base yet.
    load_module('sim.visual_goal_search', v / 'visual_goal_search.py')


def duty(drive):
    f, l, t = drive
    desired = [f - l - t, f + l + t, f + l - t, f - l + t]
    scale = max(.35, max(map(abs, desired)))
    duration = [DT * abs(v) / scale for v in desired]
    return [0. if dd < .001 else math.copysign(.35, v) for v, dd in zip(desired, duration)], \
           [0. if dd < .001 else dd for dd in duration]


def command_delta(command):
    a, b, c, d = [w * min(dt, t) for w, dt, t in zip(command['wheels'],
                                                   command['duration_s'],
                                                   [DT] * 4)]
    gain = .0325 * 150 * 2 * math.pi / 60
    return [gain * (a + b + c + d) / 4, gain * (-a + b + c - d) / 4,
            gain * (-a + b - c + d) / (4 * .1255)]


@contextmanager
def prefixed_paths(renderer, legacy):
    sys.path[:0] = [str(ROOT), str(ROOT / 'scripts'), str(renderer),
                    str(renderer / 'scripts'), str(legacy), str(legacy / 'scripts')]
    import sim, harness, scripts
    sim.__path__[:0] = [str(renderer / 'sim'), str(legacy / 'sim')]
    harness.__path__.extend([str(legacy / 'harness'), str(renderer / 'harness')])
    scripts.__path__.append(str(renderer / 'scripts'))
    old = os.getcwd()
    os.chdir(renderer)
    try:
        yield
    finally:
        os.chdir(old)


def make_model(renderer, legacy, plan):
    with prefixed_paths(renderer, legacy):
        import mujoco
        import numpy as np
        import cv2
        from types import SimpleNamespace
        from sim.multi_masterpi_production import build_multi_robot_xml
        from sim.masterpi_dynamics_v2 import load_fitted_hardware
        from sim.masterpi_model_v3 import v3_hardware
        from sim.masterpi_drive_friction_v7 import transform_xml, DriveParameters
        from sim.masterpi_camera_profile import mujoco_pixel_intrinsic
        from sim import masterpi_camera_review_v3 as camera
        from sim.zone_cargo_contact import apply as cargo_contact
        from scripts import probe_scene_tex2 as st
        from harness.active_camera import SEARCH
        cv2.setNumThreads(1)
        vendor = vendor_root()
        scene_factory = load_module('visgoal_scene', vendor / 'warp_act_scene.py')
        native = load_module('visgoal_native', vendor / 'warp_native_contact.py')
        if sha(vendor / 'warp_native_contact.py') != \
                'a5c8d370755034b9f9615f66a94b87883327b7d7ecc4e13082eac2c2d4751c6a':
            raise ValueError('NATIVE_OWNER_BYTES_REQUIRED')
        plan.setdefault('end_color_scene', 'grasp_act_teal_blue_v1')
        plan.setdefault('scenario_id', 's1_normal_mixed_v7')
        scene = scene_factory.make_scene(plan)
        hardware, _ = load_fitted_hardware()
        xml = cargo_contact(scene.transform(build_multi_robot_xml(hardware)), 'cargo_noslip_v1')
        xml = scene.robot_transform(xml, hardware=hardware, calibrated_keys=hardware)
        xml = native.apply(transform_xml(xml, DriveParameters(), 'mesh', 'off'),
                           'warp_native_contact_v1')
        m = mujoco.MjModel.from_xml_string(xml)
        for rid in ('r1', 'r2', 'r3'):
            cid = m.camera(rid + '__robot_cam').id
            m.cam_pos[cid] = camera.POSITION_M
            m.cam_quat[cid] = camera.QUAT_WXYZ
            m.cam_resolution[cid] = (640, 480)
            m.cam_sensorsize[cid] = (640, 480)
            m.cam_intrinsic[cid] = mujoco_pixel_intrinsic(640, 480)
        hardware = v3_hardware(hardware)
        hardware.setdefault('servo6_center_pwm', 1500.)
        return m, hardware, xml, scene


def reset_episode(m, hardware, plan, st, SEARCH, mujoco):
    import numpy as np
    d = mujoco.MjData(m)
    mujoco.mj_resetData(m, d)
    for rid, spawn in plan['spawns'].items():
        st._free_pose(m, d, rid + '__robot', spawn[:3], spawn[3])
        st.set_arm(m, d, rid, SEARCH, hardware)
    mujoco.mj_forward(m, d)
    return d


def overlap_check(m, d, mujoco, check, option):
    floor = {m.geom(i).name for i in range(m.ngeom)
             if int(m.geom_type[i]) == int(mujoco.mjtGeom.mjGEOM_PLANE)
             and any(word in m.geom(i).name.lower() for word in ('floor', 'ground'))}
    cargo = {m.body(i).name for i in range(1, m.nbody)
             if int(m.body_jntnum[i])
             and int(m.jnt_type[int(m.body_jntadr[i])]) == int(mujoco.mjtJoint.mjJNT_FREE)
             and not m.body(i).name.startswith(('r1__', 'r2__', 'r3__'))}
    wall = {m.geom(i).name for i in range(m.ngeom) if 'wall' in m.geom(i).name.lower()}
    return check(m, d, floor_geoms=floor, cargo_bodies=cargo, wall_geoms=wall,
                 option=option)


def json_safe(obj):
    import numpy as np
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()
                if k not in ('labels', 'mask')}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    return obj


AUDIT_KEY_COUNTERS = (
    ('held_world_reads', ('world',)),
    ('static_map_control', ('static_map', 'map_pose', 'known_map')),
    ('spawn_control', ('spawn',)),
    ('truth_control', ('gt_', 'truth')),
    ('top_camera_frames', ('top_camera',)),
    ('invisible_measurements', ('invisible_',)),
)


class InputAudit:
    """Controller-boundary input audit.

    Every controller call's arguments are scanned for ground-truth / world-pose
    / static-map / spawn / top-camera keys.  The counters are incremented by
    actual detected attempts at this boundary, so a zero means "no such key was
    passed in these calls", not a constant written by the runner.  A forbidden
    key fails the episode as ``input_audit_fail``.
    """

    def __init__(self):
        self.calls = 0
        self.violations = []
        self.counts = {name: 0 for name, _ in AUDIT_KEY_COUNTERS}
        self.checks = []

    def _walk(self, obj, where, depth=0):
        if depth > 6:
            return
        if isinstance(obj, dict):
            for key, value in obj.items():
                name = str(key).lower()
                for counter, needles in AUDIT_KEY_COUNTERS:
                    if any(needle in name for needle in needles):
                        self.counts[counter] += 1
                        self.violations.append(
                            dict(where=where, key=str(key), depth=depth))
                        break
                self._walk(value, where + '.' + str(key), depth + 1)
        elif isinstance(obj, (list, tuple)):
            for i, value in enumerate(obj[:64]):
                self._walk(value, where + f'[{i}]', depth + 1)

    def scan(self, where, kwargs):
        self.calls += 1
        self._walk(kwargs, where)
        self.checks.append(where)

    def summary(self):
        return dict(version='controller_boundary_v1',
                    calls=self.calls,
                    counters=dict(self.counts),
                    violations=self.violations[:10],
                    passed=not self.violations)


def run(a):
    if not a.enabled:
        raise ValueError('EXPLICIT_ENABLED_REQUIRED')
    if not platform.node().startswith('ugrp-act-l4-gcp3'):
        raise ValueError('EXPLICIT_GCP3_ONLY')
    lease = Path('/home/ugrp/ugrp-sim/leases') / (a.lease_name + '.json')
    if not lease.is_file():
        raise ValueError('OWN_LEASE_REQUIRED')
    q = json.loads(a.queue.read_text())
    # Default-off correction for the uncalibrated right turn.  Calibration r2
    # records only the left pulse; the exact mirrored right pulse otherwise
    # falls back to the analytic wheel model, which over-predicted yaw
    # 1.55-1.66x on the recorded gate-r1/r8 raw (scripts/visgoal_yaw_audit.py).
    # The queue's ``toggles`` object declares the candidate (stack_values is
    # reserved for current_stack rule ids); the CLI flag can only add it, and
    # the applied value is recorded in stack.json.
    pulse_mirror = bool(a.mirror_pulse or
                        q.get('toggles', {}).get('visgoal_mirror_pulse_v1') == 'on')
    # Candidate C (default off): a lawnmower search that does not close in
    # place, plus the arrival aim moved inward past the remembered point.
    # Basis and budget are in sim/visual_goal_search.py (EXPANDING_LEG_TICKS,
    # ARRIVAL_AIM_INSET_M) from the gate-r4 raw.
    expanding_search = bool(
        q.get('toggles', {}).get('visgoal_expanding_search_v1') == 'on')
    # The visgoal candidate C run (2026-10-18) measured that C's 0.142 m
    # arrival-aim inset broke the arrival declaration (0/16 declared; all
    # eight east episodes ended physically inside zone B but never declared).
    # Stage A therefore separates the two changes: the expanding search is on
    # and the arrival aim stays at the r4 declaration (inset 0).  Both are the
    # queue's toggles and are recorded in stack.json; the vendored policy is
    # unchanged.
    arrival_aim_on = bool(
        q.get('toggles', {}).get('visgoal_arrival_aim_inset_v1') == 'on')
    # Cross-room flow: Stage A (unloaded) and Stage B (loaded, single red box)
    # are separate conditions; each has its own queue and is never pooled.
    stage = str(q.get('stage', a.stage or 'A_unloaded'))
    if stage not in ('A_unloaded', 'B_loaded', 'B_loaded_mask_off',
                      'B_loaded_mask_on', 'A_unloaded_fix',
                      'A_unloaded_fix2', 'A_unloaded_fix3'):
        raise ValueError('CROSSROOM_STAGE_UNKNOWN')
    carry_loaded = stage in ('B_loaded', 'B_loaded_mask_off',
                             'B_loaded_mask_on')
    carry_mask_on = stage == 'B_loaded_mask_on'
    # Loaded wall-line v1 (default off; design outputs/reports/crossroom-stageB-fix.md
    # section 2).  Admitted only for the loaded stages: an unloaded queue that
    # asks for it is rejected, never silently ignored.
    loaded_wallline_mod = load_module(
        'crossroom_loaded_wallline',
        ROOT / 'experiments/2026-10-18-crossroom-carry/scripts/loaded_wallline.py')
    loaded_wallline_on = loaded_wallline_mod.admit(q.get('toggles', {}), stage)
    if (loaded_wallline_on
            and int(a.nworld or q.get('worlds_per_batch', 1)) <= 1):
        # The cargo band + wall rows are only produced by the batch runner that
        # also places the cargo; the single-world path cannot honour the toggle.
        raise ValueError('CROSSROOM_LOADED_WALLLINE_BATCH_ONLY')
    fix_stage = stage in ('A_unloaded_fix', 'A_unloaded_fix2',
                          'A_unloaded_fix3')
    fix_stage_v2 = stage in ('A_unloaded_fix2', 'A_unloaded_fix3')
    fix_stage_v3 = stage == 'A_unloaded_fix3'
    fix_toggles = ({k: q.get('toggles', {}).get(k) == 'on'
                    for k in ('crossroom_gap_twosided_v1',
                              'crossroom_door_align_v1',
                              'crossroom_paint_area_v1',
                              'crossroom_contacts_v1',
                              'crossroom_gap_twosided_v2_v1',
                              'crossroom_paint_area_v2_v1',
                              'crossroom_approach_escape_v1',
                              'crossroom_gap_v3_v1',
                              'crossroom_zone_edge_v1')}
                   if fix_stage else {})
    target_zone = str(q.get('destination_zone', 'B'))
    if target_zone != 'B':
        raise ValueError('CROSSROOM_ZONE_B_ONLY')
    loaded_scene = None
    if carry_loaded:
        if q.get('toggles', {}).get('crossroom_carry_scene_v1') != 'on':
            raise ValueError('CROSSROOM_CARRY_SCENE_TOGGLE_REQUIRED')
        loaded_scene = json.loads((ROOT / q['loaded_scene']).read_text())
        if loaded_scene.get('scenario_id') != 'crossroom_carry_scene_v1':
            raise ValueError('CROSSROOM_LOADED_SCENE_ID')
    # Stage B carries the box from t=0: the gripper command is closed while the
    # control tape runs. Stage A keeps the calibrated open gripper pose.
    gripper_pwm = int(q.get('gripper_pwm_closed', 1500)) if carry_loaded else 2000
    if stage in ('B_loaded_mask_off', 'B_loaded_mask_on'):
        want = 'off' if stage.endswith('_off') else 'on'
        if str(q.get('toggles', {}).get('crossroom_carry_mask_v1')) != want:
            raise ValueError('CARRY_MASK_TOGGLE_MISMATCH')
    zone_x0, zone_x1, zone_y0, zone_y1 = 4.30, 4.90, -2.80, -1.40

    def scene_plan(plan):
        if carry_loaded:
            # Reduced single-box scene has no long_beam, so the beam end-colour
            # profile (which requires exactly one beam band) must stay off.
            return {**plan, 'scenario_id': loaded_scene,
                    'end_color_scene': 'off'}
        return {**plan, 'scenario_id': 's1_normal_mixed_v7',
                'end_color_scene': 'grasp_act_teal_blue_v1'}

    def zone_margin(x, y):
        return min(x - zone_x0, zone_x1 - x, y - zone_y0, zone_y1 - y)
    # The queue declares ``physics_backend: mjwarp_batch_v1``.  The earlier
    # runner executed one world at a time (nworld=1), which measured 9.78
    # wall/SIM and even four separate processes only reached ~7.8; the GPU
    # kernels of one small world underfill an L4.  nworld starts every selected
    # episode in one MJWarp data batch (one 400-step graph launch per control
    # tick).  Per-world perception/control/command bytes are unchanged; the
    # batch is a new execution condition and is not pooled with sequential
    # runs.
    a.nworld = int(a.nworld or q.get('worlds_per_batch', 1))
    import subprocess
    if subprocess.call(['git', '-C', str(ROOT), 'cat-file', '-e',
                         q['source_sha'] + '^{commit}'],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL):
        raise ValueError('PINNED_SOURCE_REQUIRED')
    if not a.preflight and not Path(q['rejection_table']).is_file():
        raise ValueError('PRIOR_FUNNEL_REQUIRED')
    for name, expected in q.get('input_sha256', {}).items():
        if sha(ROOT / name) != expected:
            raise ValueError('PINNED_INPUT_CHANGED:' + name)
    if a.output.exists():
        raise ValueError('OUTPUT_MUST_NOT_EXIST')
    a.output.mkdir(parents=True)
    (a.output / 'own-rgb').mkdir()
    dump(a.output / 'queue.json', q)
    register_vendor()
    carry_mod = None
    if carry_loaded:
        carry_mod = load_module(
            'crossroom_carry_state',
            ROOT / 'experiments/2026-10-18-crossroom-carry/scripts/carry_state_own.py')
    fix_mod = paint_filter_mod = contact_mod = None
    if fix_stage or loaded_wallline_on:
        fix_mod = load_module(
            'crossroom_vgs_fix',
            ROOT / 'experiments/2026-10-18-crossroom-carry/scripts/vgs_fix.py')
    if fix_stage:
        paint_filter_mod = load_module(
            'crossroom_paint_filter',
            ROOT / 'experiments/2026-10-18-crossroom-carry/scripts/paint_area_filter.py')
        contact_mod = load_module(
            'crossroom_contact_recorder',
            ROOT / 'experiments/2026-10-18-crossroom-carry/scripts/contact_recorder.py')
    setups = json.loads(a.setups.read_text())['episodes']
    if a.episodes:
        keep = {int(x) for x in a.episodes.split(',')}
        setups = [e for i, e in enumerate(setups) if i in keep]
    if a.preflight:
        # Stage A preflight covers one near-wall (N) start and one far-wall
        # (F) start; every Stage A start is west of the divider.
        a.sim_cap = min(a.sim_cap, 60.)
        if not a.episodes:
            setups = [setups[0]] + ([setups[8]] if len(setups) > 8 else [])
    with prefixed_paths(a.renderer, a.legacy):
        import numpy as np
        import cv2
        import mujoco
        import mujoco_warp as mjw
        import warp as wp
        from types import SimpleNamespace
        from sim.masterpi_dynamics_v2 import MasterPiDynamicsV2
        from sim.masterpi_camera_profile import raw_fisheye_remap
        from scripts.warp5_render import Renderer
        from scripts.simalt_physics_compare import unused_efm
        from scripts import probe_scene_tex2 as st
        core = load_module('visgoal_warp_act_core', vendor_root() / 'warp_act_core.py')
        control_tape, runtime_sleep_policy = core.control_tape, core.runtime_sleep_policy
        from harness.active_camera import SEARCH
        from harness.rbpf_rejection import motion_variance
        from harness.mapbuild_command_prior import CommandPrior, OPTION as PRIOR
        from harness.egocentric_landmark_memory import LandmarkMemory, MemoryOptions, OPTION as MEMORY
        from sim.visual_goal_search import (VisualGoalSearch, Options as SkillOptions,
                                            OPTION as SKILL, MIN_COLOUR_PIXELS,
                                            EXPANDING_OPTION, EXPANDING_LEG_TICKS,
                                            ARRIVAL_AIM_INSET_M,
                                            detect_paint, wall_points, component_clear,
                                            signed_turn_wheels, mirrored_pulse_delta,
                                            MIRROR_OPTION as MIRROR)
        from sim.destination_visual_acquire import floor_patch
        from sim.solo_carry_obstacles import detections as obstacle_detections
        from sim.grasp_act_solo_lookback import project as fk_project
        from harness.scene_colour_boundary import surface_masks
        cv2.setNumThreads(1)
        if a.implementation != 'legacy_v1':
            raise ValueError('VISGOAL_LEGACY_MEMORY_ONLY')
        plan0 = scene_plan(setups[0])
        m, hardware, xml, scene = make_model(a.renderer, a.legacy, plan0)
        if int(m.opt.noslip_iterations) != 0:
            raise ValueError('NOSLIP0_REQUIRED')
        box_qadr = None
        box_body_name = None
        if carry_loaded:
            placements = loaded_scene['eval']['setup']['placements']
            if len(placements) != 1 or placements[0]['kind'] != 'red':
                raise ValueError('CROSSROOM_SINGLE_RED_BOX_REQUIRED')
            box_body_name = 'cargo_' + placements[0]['item_id']
            box_qadr = int(m.jnt_qposadr[m.joint(box_body_name + '_free').id])
        if carry_loaded and a.nworld <= 1:
            raise ValueError('CARRY_BATCH_ONLY')

        def place_loaded_start(d, plan):
            """Setup-only: put the single red box in the closed gripper and settle 1 SIM s.

            No teacher, no weld: the arm is posed with the calibrated SEARCH
            joints, the gripper servo is commanded closed, the box free joint is
            placed at the gripper site, and the CPU solver settles the grasp for
            1 Sim s before the batch starts.  t=0 afterwards is a normal
            physics rollout with the gripper closed on the tape.
            """
            import numpy as np
            st.set_arm(m, d, 'r1', {**SEARCH, 1: gripper_pwm}, hardware)
            mujoco.mj_forward(m, d)
            gs = d.site_xpos[m.site('r1__grip_site').id].copy()
            adr_r = int(m.jnt_qposadr[int(m.body_jntadr[m.body('r1__robot').id])])
            w, x, y, z = d.qpos[adr_r + 3:adr_r + 7]
            yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
            st._free_pose(m, d, box_body_name,
                          (float(gs[0]), float(gs[1]), float(gs[2])), yaw)
            mujoco.mj_forward(m, d)
            ctrl = np.zeros(m.nu)
            for i in range(m.nu):
                if '__servo_' in m.actuator(i).name:
                    ctrl[i] = d.qpos[int(m.jnt_qposadr[int(m.actuator_trnid[i, 0])])]
            closed = MasterPiDynamicsV2.pulse_to_joint_targets(
                SimpleNamespace(physical_params=hardware), {1: gripper_pwm})['gripper']
            for i in range(m.nu):
                if m.actuator(i).name in ('r1__servo_gripper_left',
                                          'r1__servo_gripper_right'):
                    ctrl[i] = closed
            d.ctrl[:] = ctrl
            start_box = d.qpos[box_qadr:box_qadr + 3].copy()
            settle_steps = int(round(1.0 / float(m.opt.timestep)))
            for _ in range(settle_steps):
                mujoco.mj_step(m, d)
            disp = float(np.linalg.norm(d.qpos[box_qadr:box_qadr + 3] - start_box))
            gs_after = d.site_xpos[m.site('r1__grip_site').id].copy()
            rel = float(np.linalg.norm(d.qpos[box_qadr:box_qadr + 3] - gs_after))
            d.ctrl[:] = 0.
            return dict(box_displacement_m=round(disp, 5),
                        box_to_grip_site_m=round(rel, 5),
                        box_pose_eval_only=[float(v) for v in d.qpos[box_qadr:box_qadr + 3]],
                        gripper_closed_joint_target=float(closed),
                        settle_steps=settle_steps)
        en = mujoco.mjtSleepPolicy
        m.tree_sleep_policy[:] = runtime_sleep_policy(
            m.tree_sleep_policy.copy(), auto=int(en.mjSLEEP_AUTO),
            auto_never=int(en.mjSLEEP_AUTO_NEVER), auto_allowed=int(en.mjSLEEP_AUTO_ALLOWED),
            never=int(en.mjSLEEP_NEVER), allowed=int(en.mjSLEEP_ALLOWED))
        dump(a.output / 'scene.json', scene.manifest)
        dump(a.output / 'stack.json', {'stack_values': q['stack_values'], 'flow': q['flow'],
                                       'source_sha': q['source_sha'],
                                       'worlds_per_batch': a.nworld,
                                       'visgoal_mirror_pulse_v1':
                                           'on' if pulse_mirror else 'off',
                                       EXPANDING_OPTION:
                                           'on' if expanding_search else 'off',
                                       'expanding_leg_ticks': (list(EXPANDING_LEG_TICKS)
                                                               if expanding_search else None),
                                       'visgoal_arrival_aim_inset_v1':
                                           'on' if arrival_aim_on else 'off',
                                       'arrival_aim_inset_m': (ARRIVAL_AIM_INSET_M
                                                               if arrival_aim_on else 0.),
                                       'crossroom_stage': stage,
                                       'carry_mask_on': carry_mask_on,
                                       'loaded_wallline_v1': ('on'
                                                              if loaded_wallline_on
                                                              else 'off'),
                                       'loaded_wallline_inputs': (
                                           'own_rgb_cargo_band_top+own_rgb_'
                                           'wall_support_row' if loaded_wallline_on
                                           else None),
                                       'destination_zone': target_zone,
                                       'fix_stage': fix_stage,
                                       'fix_stage_v2': fix_stage_v2,
                                       'fix_stage_v3': fix_stage_v3,
                                       'fix_toggles': fix_toggles,
                                       'carry_loaded': carry_loaded,
                                       'gripper_pwm_closed': (gripper_pwm
                                                              if carry_loaded else None),
                                       'loaded_scene': (q.get('loaded_scene')
                                                        if carry_loaded else None),
                                       'cargo_own_thresholds': (carry_mod.thresholds()
                                                                if carry_loaded else None),
                                       'sim_cap_s': float(a.sim_cap),
                                       'toggles': q.get('toggles', {}),
                                       'input_audit': 'controller_boundary_v1'})
        (a.output / 'scene.xml').write_text(xml)
        calibration = json.loads((vendor_root() / 'walls_floor_contrast_v5_indigo110_s80-calibration.json').read_text())
        command_calibration = json.loads((vendor_root() / 'own-command-calibration-r2.json').read_text())
        own_prior = CommandPrior(command_calibration, option=PRIOR)
        from sim.spawn_overlap_check import check, OPTION as OVERLAP
        hue_band = (104, 120)  # PAINT_HUE['B']: appearance only, no zone position.

        def make_skill():
            opts = SkillOptions(
                expanding_search=expanding_search,
                arrival_aim_inset_m=(ARRIVAL_AIM_INSET_M if arrival_aim_on else 0.))
            if loaded_wallline_on and fix_mod is not None:
                # crossroom_loaded_wallline_v1: the only difference from the
                # loaded baseline is this subclass + its own-RGB band input.
                return fix_mod.LoadedWallLineSearch(
                    option=SKILL, options=opts, loaded_wallline=True)
            if fix_mod is not None and (fix_toggles.get('crossroom_gap_twosided_v1')
                                        or fix_toggles.get('crossroom_door_align_v1')):
                return fix_mod.FixedVisualGoalSearch(
                    option=SKILL, options=opts,
                    gap_twosided=fix_toggles.get('crossroom_gap_twosided_v1', False),
                    door_align=fix_toggles.get('crossroom_door_align_v1', False),
                    two_sided_v2=(fix_stage_v2 and not fix_stage_v3
                                  and fix_toggles.get(
                                      'crossroom_gap_twosided_v2_v1', False)),
                    gap_v3=(fix_stage_v3 and fix_toggles.get(
                        'crossroom_gap_v3_v1', False)),
                    zone_edge_check=(fix_stage_v3 and fix_toggles.get(
                        'crossroom_zone_edge_v1', False)),
                    approach_escape_s=(15.0 if (fix_stage_v2 and fix_toggles.get(
                        'crossroom_approach_escape_v1', False)) else 0.))
            return VisualGoalSearch(option=SKILL, options=opts)

        def run_batch(plans):
            """Run every selected start as one MJWarp nworld batch.

            Each world executes the identical per-episode perception/control
            code with its own camera frame and command tape; only the physics
            graph is shared (one 400-step capture launch per 0.1 s tick).
            Ground truth stays eval-only, as in the sequential runner.
            """
            G = len(plans)
            if a.nworld != G:
                raise ValueError('NWORLD_MUST_EQUAL_SELECTED_EPISODES')
            batch_start = time.monotonic()
            worlds, rejected = [], []
            for episode_index, plan in enumerate(plans):
                plan = scene_plan(plan)
                out = a.output / 'episodes' / f'e{episode_index:02d}'
                out.mkdir(parents=True)
                (out / 'frames').mkdir()
                d = reset_episode(m, hardware, plan, st, SEARCH, mujoco)
                # Admission is evaluated on the authored start state (robots,
                # peers and scene cargo at their setup positions).  The loaded
                # placement then puts the single box in the closed gripper; that
                # setup-only grasp is validated separately by
                # stageB_settle_check.py and must not fail the start admission
                # (the jaws intentionally touch the box).
                admission = overlap_check(m, d, mujoco, check, OVERLAP)
                dump(out / 'admission.json', admission)
                if not admission['accepted']:
                    ep = dict(episode=episode_index, status='START_REJECTED',
                              admission=admission)
                    dump(out / 'episode.json', ep)
                    rejected.append(ep)
                    continue
                loaded = place_loaded_start(d, plan) if carry_loaded else None
                loaded_admission = (overlap_check(m, d, mujoco, check, OVERLAP)
                                    if carry_loaded else None)
                # Setup-only initial state; no pose ever enters the skill.
                dump(out / 'setup-eval-only.json',
                     dict(evaluation_only=True, spawns=plan['spawns'],
                          carry_stage=stage,
                          loaded_start_setup_only=loaded,
                          loaded_state_admission_for_reference=(loaded_admission),
                          gripper_pwm_closed=(gripper_pwm if carry_loaded else None),
                          cargo_own_thresholds=(carry_mod.thresholds()
                                                if carry_loaded else None)))
                ctrl = np.zeros(m.nu)
                for i in range(m.nu):
                    if '__servo_' in m.actuator(i).name:
                        ctrl[i] = d.qpos[int(m.jnt_qposadr[int(m.actuator_trnid[i, 0])])]
                d.ctrl[:] = ctrl
                worlds.append(dict(episode=episode_index, plan=plan, out=out,
                                   ctrl=ctrl, data=d))
            if not worlds:
                return rejected
            G = len(worlds)

            def stack_state():
                for name in ('qpos', 'qvel', 'act', 'ctrl', 'qacc_warmstart',
                             'qfrc_applied', 'xfrc_applied', 'mocap_pos',
                             'mocap_quat', 'eq_active', 'time'):
                    target = getattr(wd, name, None)
                    if target is None or not isinstance(target, wp.array):
                        continue
                    values = np.stack([np.asarray(getattr(s['data'], name))
                                       for s in worlds])
                    if values.size:
                        wp.copy(target, wp.array(values, dtype=target.dtype))
                wp.synchronize()

            wp.init()
            wm = mjw.put_model(m)
            with unused_efm(m, worlds[0]['data']):
                wd = mjw.put_data(m, worlds[0]['data'], nworld=G,
                                  nconmax=512, njmax=2048)
            stack_state()
            # Compile once, then discard the warm-up state before any rollout.
            mjw.step(wm, wd)
            wp.synchronize()
            with unused_efm(m, worlds[0]['data']):
                wd = mjw.put_data(m, worlds[0]['data'], nworld=G,
                                  nconmax=512, njmax=2048)
            stack_state()
            steps = round(DT / m.opt.timestep)
            tape = wp.zeros((steps, G, m.nu), dtype=float)
            step_index = wp.zeros(1, dtype=int)

            @wp.kernel
            def issue(tape: wp.array3d(dtype=float), index: wp.array(dtype=int),
                      out: wp.array2d(dtype=float)):
                w, j = wp.tid()
                out[w, j] = tape[index[0], w, j]

            @wp.kernel
            def advance(index: wp.array(dtype=int)):
                index[0] = index[0] + 1

            with wp.ScopedCapture() as cap:
                for _ in range(steps):
                    wp.launch(issue, dim=(G, m.nu), inputs=[tape, step_index, wd.ctrl])
                    mjw.step(wm, wd)
                    wp.launch(advance, dim=1, inputs=[step_index])
            rc = Renderer(m, wm, wd, [('r1', 'r1__robot_cam', (640, 480))],
                          enabled=True, texture_after_lighting=True)
            contact_rec = (contact_mod.ContactRecorder(m, G)
                           if fix_stage and fix_toggles.get('crossroom_contacts_v1')
                           else None)
            contact_error = None
            mx, my = raw_fisheye_remap(640, 480)
            servos = (1, 3, 4, 5, 6)
            jointnames = {1: ('left_gripper_close', 'right_gripper_close'),
                          3: ('wrist_pitch',), 4: ('elbow',), 5: ('shoulder',), 6: ('arm_yaw',)}
            sidnames = {1: 'gripper', 3: 'wrist', 4: 'elbow', 5: 'shoulder', 6: 'yaw'}
            lookup = np.empty((5, 2001))
            servo_ids = []
            for k, sid in enumerate(servos):
                joints = [m.joint('r1__' + j).id for j in jointnames[sid]]
                ids = [i for i in range(m.nu) if int(m.actuator_trnid[i, 0]) in joints]
                servo_ids.append(ids)
                for pwm in range(500, 2501):
                    targets = MasterPiDynamicsV2.pulse_to_joint_targets(
                        SimpleNamespace(physical_params=hardware), {sid: pwm})
                    jid = joints[0]
                    v = targets[sidnames[sid]]
                    lookup[k, pwm - 500] = float(np.clip(v, *m.jnt_range[jid])) \
                        if m.jnt_limited[jid] else v
            wheel_ids = [m.actuator('r1__wheel_' + n + '_drive').id
                         for n in ('fl', 'fr', 'rl', 'rr')]
            drive = __import__('sim.masterpi_drive_friction_v7',
                               fromlist=['DriveParameters']).DriveParameters()
            body = m.body('r1__robot').id
            adr = int(m.jnt_qposadr[int(m.body_jntadr[body])])
            states = []
            for w, row in enumerate(worlds):
                memory = LandmarkMemory(option=MEMORY,
                                        options=MemoryOptions(implementation=a.implementation))
                states.append(dict(
                    episode=row['episode'], plan=row['plan'], out=row['out'],
                    ctrl=row['ctrl'], skill=make_skill(),
                    memory=memory, audit=InputAudit(),
                    found=False, declared=False, declared_t=None,
                    status='cap_end', error=None, colour_seen=False,
                    start_visibility=None, start_paint_reason=None,
                    labels=[], trace=[], commands=[], ring=deque(maxlen=101),
                    previous=None, last_servo=None, rotation_cmd=0.,
                    rotation_gt=0., last_yaw=None, arrived_gt=False,
                    arrive_pose=None, inside_at_declared=None,
                    obstacle_cache=[],
                    obstacle_ticks=0, wall_zero_ticks=0, wall_points_total=0,
                    box_share_sum=0.0, box_share_max=0.0, box_share_n=0,
                    cargo=(carry_mod.CarryStateOwn() if carry_loaded else None),
                    cargo_at_start=None, cargo_at_cross=None,
                    cargo_at_arrival=None, cargo_state_counts={},
                    cargo_band_top=None, cargo_band_full=None,
                    box_at_declared=None, box_final=None, cargo_own=None,
                    ncon_last=None, nacon_global_last=None, paint_filter_counts={},
                    crossed=False, last_base_x=None,
                    applied=np.array(
                        [[gripper_pwm if sid == 1 else SEARCH[sid]
                          for sid in servos]], float),
                    relay=np.zeros((1, 4), int), active=True,
                    last_qp=None, mem=None))
            TICKS = int(round(a.sim_cap * HZ)) + 1
            tape_np = np.zeros((steps, G, m.nu), np.float32)
            for tick in range(TICKS):
                t = tick / HZ
                if (a.output / 'SUPERVISOR_STOP.json').exists():
                    for s in states:
                        if s['active']:
                            s['status'] = 'SUPERVISOR_STOP'
                            s['active'] = False
                    break
                qp_all = wd.qpos.numpy()
                overflow = wd.overflow.numpy()
                images = rc.render()
                rgb_all = images['r1'][0]
                rows = []
                for w, s in enumerate(states):
                    if not s['active']:
                        rows.append(dict(
                            ctrl=s['ctrl'], wheels=[0., 0., 0., 0.],
                            deadlines=[-1.] * 4, applied=s['applied'][0],
                            target=[gripper_pwm if x == 1 else SEARCH[x] for x in servos],
                            servo_active=[False] * 5, now=t, servo_time=t))
                        continue
                    qp = qp_all[w]
                    try:
                        if not np.isfinite(qp).all() or bool(overflow[w]):
                            raise RuntimeError('NONFINITE_OR_CAPACITY')
                        raw = np.clip(rgb_all[w], 0, 255).astype(np.uint8)
                        im = cv2.remap(raw, mx, my, cv2.INTER_LINEAR,
                                       borderMode=cv2.BORDER_CONSTANT)
                        out = s['out']
                        file = out / 'frames' / f'{tick:05d}.jpg'
                        cv2.imwrite(str(file), cv2.cvtColor(im, cv2.COLOR_RGB2BGR),
                                    [cv2.IMWRITE_JPEG_QUALITY, 90])
                        bgr = cv2.imread(str(file))
                        if carry_loaded:
                            s['cargo_own'] = s['cargo'].update(t, bgr, gripper_pwm)
                            px = int(s['cargo_own'].get('pixels') or 0)
                            share = px / float(640 * 480)
                            s['box_share_sum'] += share
                            s['box_share_n'] += 1
                            s['box_share_max'] = max(s['box_share_max'], share)
                            if tick == 0:
                                s['cargo_at_start'] = s['cargo_own']['state']
                            st_count = s['cargo_state_counts']
                            st_count[s['cargo_own']['state']] = st_count.get(
                                s['cargo_own']['state'], 0) + 1
                        servo = {sid: int(v) for sid, v in
                                 zip(servos, np.rint(s['applied'][0]))}
                        delta_nom = np.asarray(command_delta(s['previous'])) \
                            if s['previous'] else np.zeros(3)
                        cov_nom = np.diag(motion_variance(delta_nom))
                        prior = own_prior.predict(delta_nom, cov_nom, s['previous'],
                                                  servo, s['last_servo'], DT)
                        if (pulse_mirror and
                                prior.get('source') == 'nominal_6f_unqualified_native'):
                            mirrored = mirrored_pulse_delta(
                                s['previous'], command_calibration, servo,
                                s['last_servo'], DT)
                            if mirrored is not None:
                                prior = mirrored
                        delta = np.asarray(prior['delta'])
                        cov = np.asarray(prior['covariance'])
                        if tick % 3 == 0:
                            s['obstacle_cache'], _ = obstacle_detections(
                                bgr, servo,
                                **({'held_kind': 'red',
                                    'grasp_pwm': gripper_pwm}
                                   if carry_mask_on else {}))
                        paint = detect_paint(
                            bgr, servo, hue_band,
                            saturation_min=s['skill'].options.paint_saturation_min)
                        walls = wall_points(bgr, servo, calibration)
                        s['wall_points_total'] += len(walls)
                        if not walls:
                            s['wall_zero_ticks'] += 1
                        # crossroom_loaded_wallline_v1 (default off): the only
                        # new control input is the own-RGB cargo band top and
                        # the supporting pixel row of each own-RGB wall point.
                        loaded_kwargs = {}
                        if loaded_wallline_on:
                            carry_state = (s['cargo_own'] or {}).get(
                                'state', 'uncertain')
                            band_comp = carry_mod.full_frame_red_component(bgr)
                            band_top = loaded_wallline_mod.band_top_for_state(
                                carry_state, band_comp.get('band_top_row'))
                            if walls:
                                xy = np.asarray(
                                    [p['relative_xy_m'] for p in walls], float)
                                px, front = fk_project(
                                    np.column_stack(
                                        [xy, np.zeros(len(xy), float)]), servo)
                                walls = loaded_wallline_mod.attach_rows(
                                    walls, px[:, 1], front)
                            s['cargo_band_top'] = band_top
                            s['cargo_band_full'] = dict(
                                pixels=band_comp.get('pixels'),
                                largest=band_comp.get('largest'),
                                bbox_xywh=band_comp.get('bbox_xywh'),
                                band_top_row=band_comp.get('band_top_row'),
                                state=carry_state)
                            loaded_kwargs = dict(
                                cargo_held=(carry_state == 'held'),
                                cargo_band_top=band_top)
                        if s['obstacle_cache']:
                            s['obstacle_ticks'] += 1
                        if tick == 0:
                            pm = (paint.get('mask') if paint.get('mask') is not None
                                  else np.zeros(bgr.shape[:2], np.uint8))
                            cv2.imwrite(str(out / 'paint-mask.png'),
                                        (pm * 255).astype(np.uint8))
                            wm_tmp, _ = surface_masks(bgr, calibration)
                            cv2.imwrite(str(out / 'wall-mask.png'),
                                        (wm_tmp['wall'] * 255).astype(np.uint8))
                            dump(out / 'tick0-perception.json',
                                 {k: v for k, v in paint.items()
                                  if k not in ('labels', 'mask')
                                  and not isinstance(v, np.ndarray)})
                        patch = None
                        patch_rec = None
                        paint_clear = component_clear(paint)
                        need_patch = (paint_clear is not None and
                                      (paint.get('nearest_range_m', 99.) <= 1.8
                                       or s['skill'].stage in ('target', 'approach')))
                        if need_patch:
                            patch, patch_rec = floor_patch(
                                bgr, servo, 'B', (1.5, 1.5),
                                clear=paint_clear, excluded=None)
                        paint_filter_info = None
                        if (fix_stage and fix_toggles.get('crossroom_paint_area_v1')
                                and paint_filter_mod is not None
                                and paint.get('pixels', 0) >= MIN_COLOUR_PIXELS):
                            if (fix_stage_v2 and fix_toggles.get(
                                    'crossroom_paint_area_v2_v1')):
                                paint, paint_filter_info = (
                                    paint_filter_mod.filter_paint_v2(paint, patch_rec))
                            else:
                                paint, paint_filter_info = (
                                    paint_filter_mod.filter_paint(paint, patch_rec))
                            counts = s['paint_filter_counts']
                            key = paint_filter_info.get('action', 'unknown')
                            counts[key] = counts.get(key, 0) + 1
                            if key == 'rejected':
                                patch, patch_rec = None, None
                        audit = s['audit']
                        audit.scan('memory_observation',
                                   dict(t=t, patch=patch, patch_rec=patch_rec or {}))
                        obs = s['skill'].memory_observation(t, patch, patch_rec or {})
                        audit.scan('memory_step',
                                   dict(t=t, delta=delta.tolist(), cov=cov.tolist(),
                                        observations=[obs] if obs else []))
                        mem = s['memory'].step(t, delta, cov, [obs] if obs else [])
                        audit.scan('skill_control',
                                   dict(t=t, paint=paint, walls=walls,
                                        obstacles=s['obstacle_cache'],
                                        memories=mem['memories'],
                                        patch_ok=patch is not None, patch_xy=patch,
                                        **loaded_kwargs))
                        action = s['skill'].control(
                            t, paint=paint, walls=walls,
                            obstacles=s['obstacle_cache'],
                            memories=mem['memories'],
                            patch_ok=patch is not None, patch_xy=patch,
                            **loaded_kwargs)
                        if audit.violations:
                            raise RuntimeError('INPUT_AUDIT_FAIL')
                        if action['found']:
                            s['found'] = True
                        just_declared = bool(action['arrived'] and not s['declared'])
                        if just_declared:
                            s['declared'] = True
                            s['declared_t'] = t
                            s['status'] = 'ARRIVED_DECLARED'
                        if action['stop'] and not s['declared']:
                            s['status'] = 'STOPPED_NO_ARRIVAL'
                        # EVALUATION ONLY: pose/yaw/visibility never enter control.
                        box_pose = None
                        if carry_loaded:
                            bq = np.asarray(qp_all[w][box_qadr:box_qadr + 7], float)
                            bw, bx_, by_, bz_ = bq[3:7]
                            byaw = math.atan2(2 * (bw * bz_ + bx_ * by_),
                                              1 - 2 * (by_ * by_ + bz_ * bz_))
                            box_pose = [float(bq[0]), float(bq[1]),
                                        float(bq[2]), float(byaw)]
                            s['box_final'] = box_pose
                            bx_new = float(qp[adr])
                            if (not s['crossed'] and s['last_base_x'] is not None
                                    and s['last_base_x'] < 2.175 and bx_new > 2.225):
                                s['crossed'] = True
                                s['cargo_at_cross'] = s['cargo_own']['state']
                            s['last_base_x'] = bx_new
                        ww, xx, yy, zz = qp[adr + 3:adr + 7]
                        yaw = math.atan2(2 * (ww * zz + xx * yy),
                                         1 - 2 * (yy * yy + zz * zz))
                        if s['last_yaw'] is not None:
                            s['rotation_gt'] += abs(math.atan2(
                                math.sin(yaw - s['last_yaw']),
                                math.cos(yaw - s['last_yaw'])))
                        s['last_yaw'] = yaw
                        s['rotation_cmd'] += abs(float(delta[2]))
                        inside = bool(4.3 <= qp[adr] <= 4.9 and
                                      -2.8 <= qp[adr + 1] <= -1.4)
                        if inside:
                            s['arrived_gt'] = True
                            s['arrive_pose'] = [float(qp[adr]),
                                                float(qp[adr + 1]), float(yaw)]
                        if just_declared:
                            s['inside_at_declared'] = bool(inside)
                            if carry_loaded:
                                s['cargo_at_arrival'] = s['cargo_own']['state']
                                s['box_at_declared'] = box_pose
                        s['colour_seen'] = s['skill'].colour_seen
                        if tick == 0:
                            s['start_paint_reason'] = paint.get('reason')
                            s['start_visibility'] = (
                                int(paint.get('pixels', 0))
                                if paint.get('reason') ==
                                'destination_colour_observed' else 0)
                        s['labels'].append(dict(
                            t=t, frame_id=tick,
                            pose=[float(qp[adr]), float(qp[adr + 1]), float(yaw)],
                            inside_zone_B=inside,
                            box_pose_eval_only=box_pose,
                            obstacles_n=len(s['obstacle_cache']),
                            walls_n=len(walls),
                            box_occlusion_share=round(s['box_share_sum'] /
                                                      s['box_share_n'], 4)
                            if s['box_share_n'] else None,
                            ncon_eval_only=s.get('ncon_last'),
                            nacon_global_eval_only=s.get('nacon_global_last'),
                            start_paint_pixels=s['start_visibility']))
                        s['ring'].append(tick)
                        paint_log = {k: v for k, v in paint.items()
                                     if k not in ('labels', 'mask')
                                     and not isinstance(v, np.ndarray)}
                        s['trace'].append(dict(
                            t=t, frame_id=tick, stage=action['stage'],
                            cargo_own=s.get('cargo_own'),
                            cargo_band_top=s.get('cargo_band_top'),
                            cargo_band_full=s.get('cargo_band_full'),
                            loaded_wallline=(s['skill'].loaded_debug()
                                             if hasattr(s['skill'], 'loaded_debug')
                                             else None),
                            paint=paint_log, walls=len(walls),
                            obstacles=s['obstacle_cache'],
                            patch=None if patch is None else np.asarray(patch).tolist(),
                            patch_record=patch_rec,
                            paint_filter=paint_filter_info,
                            memory=mem['memories'], memory_events=mem['events'],
                            action=action, command_motion_source=prior['source'],
                            command_delta=delta.tolist(),
                            command_covariance=cov.tolist(), servo=servo,
                            rgb=str(file.relative_to(out)), frame_sha256=sha(file)))
                        if tick == 0 and s['start_visibility'] is None:
                            s['start_visibility'] = 0
                        s['last_servo'] = servo
                        s['last_qp'] = qp.copy()
                        s['mem'] = mem
                        if s['declared_t'] is not None and t - s['declared_t'] >= 1.0:
                            s['active'] = False
                            rows.append(dict(
                                ctrl=s['ctrl'], wheels=[0., 0., 0., 0.],
                                deadlines=[-1.] * 4, applied=s['applied'][0],
                                target=[gripper_pwm if x == 1 else SEARCH[x] for x in servos],
                                servo_active=[False] * 5, now=t, servo_time=t))
                            continue
                        if action['exact_turn']:
                            wheels = signed_turn_wheels(
                                action['exact_turn'], command_calibration['wheels'])
                            duration = list(command_calibration['duration_s'])
                        else:
                            wheels, duration = duty([action['forward'],
                                                     action['left'], action['turn']])
                            if action['stop']:
                                wheels, duration = [0., 0., 0., 0.], [0., 0., 0., 0.]
                        cmd = dict(t=t, wheels=wheels, duration_s=duration,
                                   pwm={sid: (gripper_pwm if sid == 1 else SEARCH[sid]) for sid in servos})
                        s['commands'].append(cmd)
                        s['previous'] = cmd
                        rows.append(dict(
                            ctrl=s['ctrl'], wheels=wheels,
                            deadlines=[t + v if v else -1 for v in duration],
                            applied=s['applied'][0],
                            target=[gripper_pwm if x == 1 else SEARCH[x] for x in servos],
                            servo_active=[False] * 5, now=t, servo_time=t))
                        if tick % 100 == 0:
                            dump(out / 'progress.json',
                                 dict(t=t, stage=action['stage'],
                                      found=s['found'], declared=s['declared'],
                                      source_sha=q['source_sha'],
                                      wall_s=time.monotonic() - batch_start))
                    except BaseException as exc:
                        s['error'] = repr(exc)
                        s['status'] = ('input_audit_fail'
                                       if s['audit'].violations else 'HOST_ERROR')
                        s['active'] = False
                        rows.append(dict(
                            ctrl=s['ctrl'], wheels=[0., 0., 0., 0.],
                            deadlines=[-1.] * 4, applied=s['applied'][0],
                            target=[gripper_pwm if x == 1 else SEARCH[x] for x in servos],
                            servo_active=[False] * 5, now=t, servo_time=t))
                if not any(s['active'] for s in states):
                    break
                tape_np, cmd_state = control_tape(
                    rows, np.stack([s['relay'][0] for s in states]),
                    dt=float(m.opt.timestep), steps=steps, lookup=lookup,
                    wheel_ids=wheel_ids, servo_ids=servo_ids,
                    start_fraction=drive.start_fraction,
                    kinetic_fraction=drive.kinetic_fraction,
                    torque_cap_nm=drive.torque_cap_nm)
                for w, s in enumerate(states):
                    s['applied'] = cmd_state['applied'][w][None, :].copy()
                    s['relay'] = cmd_state['relay'][w][None, :].copy()
                wp.copy(tape, wp.array(tape_np, dtype=float))
                step_index.zero_()
                wp.capture_launch(cap.graph)
                if contact_rec is not None:
                    try:
                        cinfo = contact_rec.update(wd, t)
                    except Exception as exc:  # eval-only recorder must not kill the run
                        contact_error = repr(exc)
                        contact_rec = None
                        cinfo = None
                    if cinfo:
                        ncon = cinfo.get('counts')
                        gcount = cinfo.get('global_nacon')
                        for w, s in enumerate(states):
                            s['ncon_last'] = (ncon[w] if ncon is not None
                                              and w < len(ncon) else None)
                            s['nacon_global_last'] = gcount
            results = list(rejected)
            for s in states:
                out = s['out']
                ep = dict(
                    episode=s['episode'], status=s['status'], error=s['error'],
                    frames=len(s['commands']),
                    sim_s=(len(s['commands']) - 1) / HZ if s['commands'] else 0.,
                    wall_s=time.monotonic() - batch_start,
                    source_sha=q['source_sha'], skill=SKILL,
                    found=s['found'], colour_seen=s['colour_seen'],
                    arrived_declared=s['declared'],
                    arrival_verdict_gt_inside_zone_B=s['inside_at_declared'],
                    entered_zone_gt_any=s['arrived_gt'],
                    arrive_pose_eval_only=s['arrive_pose'],
                    rotation_cmd_rad=s['rotation_cmd'],
                    rotation_gt_rad_eval_only=s['rotation_gt'],
                    start_visibility_pixels=s['start_visibility'],
                    start_paint_reason=s['start_paint_reason'],
                    final_pose_eval_only=([float(s['last_qp'][adr]),
                                           float(s['last_qp'][adr + 1])]
                                          if s['last_qp'] is not None else None),
                    spawn_eval_only=s['plan']['spawns']['r1'],
                    camera_frames=len(s['labels']),
                    memory_landmarks=(len(s['mem']['memories'])
                                      if s['mem'] is not None else 0),
                    terminal_ring=dict(
                        hz=10, indices=list(s['ring']),
                        bytes=sum((out / 'frames' / f'{i:05d}.jpg').stat().st_size
                                  for i in s['ring'])),
                    static_map_control=0, spawn_control=0, truth_control=0,
                    top_camera_frames=0, held_world_reads=0, initial_prior='none',
                    noslip_iterations=int(m.opt.noslip_iterations),
                    worlds_per_batch=G, crossroom_stage=stage,
                    carry_mask_on=carry_mask_on,
                    destination_zone=target_zone,
                    input_audit=s['audit'].summary(),
                    carry_loaded=carry_loaded,
                    cargo_held_at_start=s.get('cargo_at_start'),
                    cargo_held_at_cross=s.get('cargo_at_cross'),
                    cargo_held_at_arrival=s.get('cargo_at_arrival'),
                    cargo_state_counts=s.get('cargo_state_counts'),
                    cargo_own_thresholds=(carry_mod.thresholds()
                                          if carry_loaded else None),
                    cargo_own_summary=(s['cargo'].summary()
                                       if s.get('cargo') is not None else None),
                    box_final_pose_eval_only=s.get('box_final'),
                    box_at_declared_eval_only=s.get('box_at_declared'),
                    cargo_in_zone_at_declared_gt=(bool(
                        zone_margin(s['box_at_declared'][0], s['box_at_declared'][1]) >= 0.)
                        if s.get('box_at_declared') else None),
                    cargo_zone_margin_at_declared_gt=(round(zone_margin(
                        s['box_at_declared'][0], s['box_at_declared'][1]), 4)
                        if s.get('box_at_declared') else None),
                    cargo_in_zone_final_gt=(bool(
                        zone_margin(s['box_final'][0], s['box_final'][1]) >= 0.)
                        if s.get('box_final') else None),
                    cargo_zone_margin_final_gt=(round(zone_margin(
                        s['box_final'][0], s['box_final'][1]), 4)
                        if s.get('box_final') else None),
                    fix_toggles=fix_toggles,
                    fix_stage_v2=fix_stage_v2,
                    fix_stage_v3=fix_stage_v3,
                    fix_summary=(s['skill'].fix_summary()
                                 if hasattr(s['skill'], 'fix_summary') else None),
                    contact_summary=(contact_rec.summary()
                                     if contact_rec is not None else None),
                    obstacle_detection_ticks=s.get('obstacle_ticks'),
                    wall_zero_ticks=s.get('wall_zero_ticks'),
                    wall_points_total=s.get('wall_points_total'),
                    box_occlusion_share_mean=(round(s['box_share_sum'] /
                                                     s['box_share_n'], 5)
                                              if s.get('box_share_n') else None),
                    box_occlusion_share_max=(round(s.get('box_share_max', 0.0), 5)),
                    contact_record_error=contact_error,
                    paint_filter_counts=s.get('paint_filter_counts'),
                    rejection_table=str(a.output / 'rejection_table.json'))
                dump(out / 'episode.json', ep)
                with (out / 'trace.jsonl').open('w') as fh:
                    for row in s['trace']:
                        fh.write(json.dumps(json_safe(row), allow_nan=False) + '\n')
                dump(out / 'commands.json', s['commands'])
                dump(out / 'eval-only.json', dict(evaluation_only=True,
                                                  frames=s['labels']))
                dump(out / 'events.json', s['skill'].events)
                dump(out / 'SHA256SUMS.json',
                     {str(p.relative_to(out)): sha(p)
                      for p in out.rglob('*') if p.is_file()})
                results.append(ep)
                dump(a.output / 'summary.json',
                     dict(status='running', episodes=results, n=len(results),
                          source_sha=q['source_sha'], raw=str(a.output),
                          worlds_per_batch=G))
            return sorted(results, key=lambda e: e['episode'])

        summaries = []
        if a.nworld > 1:
            summaries = run_batch(setups)
        for episode_index, plan in enumerate(setups if a.nworld <= 1 else []):
            plan = scene_plan(plan)
            out = a.output / 'episodes' / f'e{episode_index:02d}'
            out.mkdir(parents=True)
            (out / 'frames').mkdir()
            d = reset_episode(m, hardware, plan, st, SEARCH, mujoco)
            admission = overlap_check(m, d, mujoco, check, OVERLAP)
            dump(out / 'admission.json', admission)
            if not admission['accepted']:
                summaries.append(dict(episode=episode_index, status='START_REJECTED',
                                      admission=admission))
                dump(out / 'episode.json', summaries[-1])
                continue
            for rid, spawn in plan['spawns'].items():
                pass
            # Setup-only initial state; no pose ever enters the skill.
            dump(out / 'setup-eval-only.json', dict(evaluation_only=True, spawns=plan['spawns']))
            ctrl = np.zeros((1, m.nu))
            for i in range(m.nu):
                if '__servo_' in m.actuator(i).name:
                    ctrl[0, i] = d.qpos[int(m.jnt_qposadr[int(m.actuator_trnid[i, 0])])]
            d.ctrl[:] = ctrl[0]
            wp.init()
            wm = mjw.put_model(m)
            with unused_efm(m, d):
                wd = mjw.put_data(m, d, nworld=1, nconmax=512, njmax=2048)
            mjw.step(wm, wd)
            wp.synchronize()
            with unused_efm(m, d):
                wd = mjw.put_data(m, d, nworld=1, nconmax=512, njmax=2048)
            if int(wm.opt.noslip_iterations) != 0:
                raise ValueError('NOSLIP0_REQUIRED')
            tape = wp.zeros((round(DT / m.opt.timestep), 1, m.nu), dtype=float)
            step_index = wp.zeros(1, dtype=int)

            @wp.kernel
            def issue(tape: wp.array3d(dtype=float), index: wp.array(dtype=int),
                      out: wp.array2d(dtype=float)):
                i, j = wp.tid()
                out[i, j] = tape[index[0], i, j]

            @wp.kernel
            def advance(index: wp.array(dtype=int)):
                index[0] = index[0] + 1

            with wp.ScopedCapture() as cap:
                for _ in range(round(DT / m.opt.timestep)):
                    wp.launch(issue, dim=(1, m.nu), inputs=[tape, step_index, wd.ctrl])
                    mjw.step(wm, wd)
                    wp.launch(advance, dim=1, inputs=[step_index])
            rc = Renderer(m, wm, wd, [('r1', 'r1__robot_cam', (640, 480))],
                          enabled=True, texture_after_lighting=True)
            mx, my = raw_fisheye_remap(640, 480)
            servos = (1, 3, 4, 5, 6)
            jointnames = {1: ('left_gripper_close', 'right_gripper_close'),
                          3: ('wrist_pitch',), 4: ('elbow',), 5: ('shoulder',), 6: ('arm_yaw',)}
            sidnames = {1: 'gripper', 3: 'wrist', 4: 'elbow', 5: 'shoulder', 6: 'yaw'}
            lookup = np.empty((5, 2001))
            servo_ids = []
            for k, sid in enumerate(servos):
                joints = [m.joint('r1__' + j).id for j in jointnames[sid]]
                ids = [i for i in range(m.nu) if int(m.actuator_trnid[i, 0]) in joints]
                servo_ids.append(ids)
                for pwm in range(500, 2501):
                    targets = MasterPiDynamicsV2.pulse_to_joint_targets(
                        SimpleNamespace(physical_params=hardware), {sid: pwm})
                    jid = joints[0]
                    v = targets[sidnames[sid]]
                    lookup[k, pwm - 500] = float(np.clip(v, *m.jnt_range[jid])) \
                        if m.jnt_limited[jid] else v
            wheel_ids = [m.actuator('r1__wheel_' + n + '_drive').id
                         for n in ('fl', 'fr', 'rl', 'rr')]
            applied = np.array([[SEARCH[s] for s in servos]], float)
            relay = np.zeros((1, 4), int)
            drive = __import__('sim.masterpi_drive_friction_v7', fromlist=['DriveParameters']).DriveParameters()
            memory = LandmarkMemory(option=MEMORY, options=MemoryOptions(implementation=a.implementation))
            if fix_mod is not None and (fix_toggles.get('crossroom_gap_twosided_v1')
                                        or fix_toggles.get('crossroom_door_align_v1')):
                skill = fix_mod.FixedVisualGoalSearch(
                    option=SKILL if a.enabled else 'off', options=SkillOptions(
                        expanding_search=expanding_search,
                        arrival_aim_inset_m=(ARRIVAL_AIM_INSET_M
                                             if arrival_aim_on else 0.)),
                    gap_twosided=fix_toggles.get('crossroom_gap_twosided_v1', False),
                    door_align=fix_toggles.get('crossroom_door_align_v1', False),
                    two_sided_v2=(fix_stage_v2 and not fix_stage_v3
                                  and fix_toggles.get(
                                      'crossroom_gap_twosided_v2_v1', False)),
                    gap_v3=(fix_stage_v3 and fix_toggles.get(
                        'crossroom_gap_v3_v1', False)),
                    zone_edge_check=(fix_stage_v3 and fix_toggles.get(
                        'crossroom_zone_edge_v1', False)),
                    approach_escape_s=(15.0 if (fix_stage_v2 and fix_toggles.get(
                        'crossroom_approach_escape_v1', False)) else 0.))
            else:
                skill = VisualGoalSearch(
                    option=SKILL if a.enabled else 'off',
                    options=SkillOptions(
                        expanding_search=expanding_search,
                        arrival_aim_inset_m=(ARRIVAL_AIM_INSET_M
                                             if arrival_aim_on else 0.)))
            body = m.body('r1__robot').id
            adr = int(m.jnt_qposadr[int(m.body_jntadr[body])])
            frames = []
            trace = []
            commands = []
            labels = []
            ring = deque(maxlen=101)
            previous = None
            last_servo = None
            status = 'cap_end'
            error = None
            found = False
            declared = False
            declared_t = None
            arrived_gt = False
            arrive_pose = None
            inside_at_declared = None
            colour_seen = False
            start_visibility = None
            start_paint_reason = None
            rotation_cmd = 0.
            rotation_gt = 0.
            last_yaw = None
            start = time.monotonic()
            obstacle_cache = []
            audit = InputAudit()
            tick = 0
            try:
                for tick in range(int(round(a.sim_cap * HZ)) + 1):
                    t = tick / HZ
                    if (out / 'SUPERVISOR_STOP.json').exists():
                        status = 'SUPERVISOR_STOP'
                        break
                    qp = wd.qpos.numpy()[0].copy()
                    if not np.isfinite(qp).all() or np.any(wd.overflow.numpy()):
                        raise RuntimeError('NONFINITE_OR_CAPACITY')
                    images = rc.render()
                    raw = np.clip(images['r1'][0][0], 0, 255).astype(np.uint8)
                    im = cv2.remap(raw, mx, my, cv2.INTER_LINEAR,
                                   borderMode=cv2.BORDER_CONSTANT)
                    file = out / 'frames' / f'{tick:05d}.jpg'
                    cv2.imwrite(str(file), cv2.cvtColor(im, cv2.COLOR_RGB2BGR),
                                [cv2.IMWRITE_JPEG_QUALITY, 90])
                    bgr = cv2.imread(str(file))
                    servo = {s: int(v) for s, v in zip(servos, np.rint(applied[0]))}
                    delta_nom = np.asarray(command_delta(previous)) if previous else np.zeros(3)
                    cov_nom = np.diag(motion_variance(delta_nom))
                    prior = own_prior.predict(delta_nom, cov_nom, previous, servo, last_servo, DT)
                    if (pulse_mirror and
                            prior.get('source') == 'nominal_6f_unqualified_native'):
                        mirrored = mirrored_pulse_delta(
                            previous, command_calibration, servo, last_servo, DT)
                        if mirrored is not None:
                            prior = mirrored
                    delta = np.asarray(prior['delta'])
                    cov = np.asarray(prior['covariance'])
                    if tick % 3 == 0:
                        obstacle_cache, _ = obstacle_detections(bgr, servo)
                    paint = detect_paint(bgr, servo, hue_band,
                                         saturation_min=skill.options.paint_saturation_min)
                    walls = wall_points(bgr, servo, calibration)
                    if tick == 0:
                        pm = (paint.get('mask') if paint.get('mask') is not None
                              else np.zeros(bgr.shape[:2], np.uint8))
                        cv2.imwrite(str(out / 'paint-mask.png'),
                                    (pm * 255).astype(np.uint8))
                        wm_tmp, _ = surface_masks(bgr, calibration)
                        cv2.imwrite(str(out / 'wall-mask.png'),
                                    (wm_tmp['wall'] * 255).astype(np.uint8))
                        dump(out / 'tick0-perception.json',
                             {k: v for k, v in paint.items()
                              if k not in ('labels', 'mask') and not isinstance(v, np.ndarray)})
                    patch = None
                    patch_rec = None
                    # The vendored floor_patch uses S>=30, which also matches
                    # the v5 blue floor.  Restrict its fitted segment to the
                    # calibrated high-saturation component; never fit without
                    # a visible destination-colour component.
                    paint_clear = component_clear(paint)
                    need_patch = (paint_clear is not None and
                                  (paint.get('nearest_range_m', 99.) <= 1.8
                                   or skill.stage in ('target', 'approach')))
                    if need_patch:
                        patch, patch_rec = floor_patch(
                            bgr, servo, 'B', (1.5, 1.5),
                            clear=paint_clear, excluded=None)
                    audit.scan('memory_observation',
                               dict(t=t, patch=patch, patch_rec=patch_rec or {}))
                    obs = skill.memory_observation(t, patch, patch_rec or {})
                    audit.scan('memory_step',
                               dict(t=t, delta=delta.tolist(), cov=cov.tolist(),
                                    observations=[obs] if obs else []))
                    mem = memory.step(t, delta, cov, [obs] if obs else [])
                    audit.scan('skill_control',
                               dict(t=t, paint=paint, walls=walls,
                                    obstacles=obstacle_cache,
                                    memories=mem['memories'],
                                    patch_ok=patch is not None, patch_xy=patch))
                    action = skill.control(t, paint=paint, walls=walls,
                                           obstacles=obstacle_cache,
                                           memories=mem['memories'],
                                           patch_ok=patch is not None,
                                           patch_xy=patch)
                    if audit.violations:
                        raise RuntimeError('INPUT_AUDIT_FAIL')
                    if action['found']:
                        found = True
                    just_declared = bool(action['arrived'] and not declared)
                    if just_declared:
                        declared = True
                        declared_t = t
                        status = 'ARRIVED_DECLARED'
                    if action['stop'] and not declared:
                        status = 'STOPPED_NO_ARRIVAL'
                    # EVALUATION ONLY: pose/yaw/visibility never enter control.
                    w, x, y, z = qp[adr + 3:adr + 7]
                    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
                    if last_yaw is not None:
                        rotation_gt += abs(math.atan2(math.sin(yaw - last_yaw),
                                                      math.cos(yaw - last_yaw)))
                    last_yaw = yaw
                    rotation_cmd += abs(float(delta[2]))
                    inside = bool(4.3 <= qp[adr] <= 4.9 and -2.8 <= qp[adr + 1] <= -1.4)
                    if inside:
                        arrived_gt = True
                        arrive_pose = [float(qp[adr]), float(qp[adr + 1]), float(yaw)]
                    if just_declared:
                        inside_at_declared = bool(inside)
                    colour_seen = skill.colour_seen
                    if tick == 0:
                        start_paint_reason = paint.get('reason')
                        start_visibility = (int(paint.get('pixels', 0))
                                            if paint.get('reason') ==
                                            'destination_colour_observed' else 0)
                    labels.append(dict(t=t, frame_id=tick,
                                       pose=[float(qp[adr]), float(qp[adr + 1]), float(yaw)],
                                       inside_zone_B=inside,
                                       start_paint_pixels=start_visibility))
                    ring.append(tick)
                    paint_log = {k: v for k, v in paint.items()
                                 if k not in ('labels', 'mask') and not isinstance(v, np.ndarray)}
                    trace.append(dict(t=t, frame_id=tick, stage=action['stage'],
                                      paint=paint_log, walls=len(walls),
                                      obstacles=obstacle_cache,
                                      patch=None if patch is None else np.asarray(patch).tolist(),
                                      patch_record=patch_rec,
                                      memory=mem['memories'], memory_events=mem['events'],
                                      action=action, command_motion_source=prior['source'],
                                      command_delta=delta.tolist(),
                                      command_covariance=cov.tolist(),
                                      servo=servo, rgb=str(file.relative_to(out)),
                                      frame_sha256=sha(file)))
                    if tick == 0 and start_visibility is None:
                        start_visibility = 0
                    last_servo = servo
                    if declared_t is not None and t - declared_t >= 1.0:
                        break
                    if action['exact_turn']:
                        # The r2 calibration stores the positive-yaw pulse.
                        # Negating the wheel PWM signs gives the right turn;
                        # using the same signs for both made the bearing loop
                        # diverge (e13 preflight r2 stayed in approach).
                        wheels = signed_turn_wheels(
                            action['exact_turn'], command_calibration['wheels'])
                        duration = list(command_calibration['duration_s'])
                    else:
                        wheels, duration = duty([action['forward'], action['left'],
                                                 action['turn']])
                        if action['stop']:
                            wheels, duration = [0., 0., 0., 0.], [0., 0., 0., 0.]
                    cmd = dict(t=t, wheels=wheels, duration_s=duration,
                               pwm={s: SEARCH[s] for s in servos})
                    commands.append(cmd)
                    previous = cmd
                    values, cmd_state = control_tape(
                        [dict(ctrl=ctrl[0], wheels=wheels,
                              deadlines=[t + v if v else -1 for v in duration],
                              applied=applied[0], target=[SEARCH[s] for s in servos],
                              servo_active=[False] * 5, now=t, servo_time=t)],
                        relay, dt=float(m.opt.timestep),
                        steps=round(DT / m.opt.timestep), lookup=lookup,
                        wheel_ids=wheel_ids, servo_ids=servo_ids,
                        start_fraction=drive.start_fraction,
                        kinetic_fraction=drive.kinetic_fraction,
                        torque_cap_nm=drive.torque_cap_nm)
                    applied = cmd_state['applied']
                    relay = cmd_state['relay']
                    wp.copy(tape, wp.array(values, dtype=float))
                    step_index.zero_()
                    wp.capture_launch(cap.graph)
                    if tick % 100 == 0:
                        dump(out / 'progress.json',
                             dict(t=t, stage=action['stage'], found=found,
                                  declared=declared, source_sha=q['source_sha'],
                                  wall_s=time.monotonic() - start))
            except BaseException as exc:
                error = repr(exc)
                status = 'input_audit_fail' if audit.violations else 'HOST_ERROR'
                raise
            finally:
                ep = dict(episode=episode_index, status=status, error=error,
                          frames=len(commands), sim_s=(len(commands) - 1) / HZ if commands else 0.,
                          wall_s=time.monotonic() - start,
                          source_sha=q['source_sha'], skill=SKILL,
                          found=found, colour_seen=colour_seen,
                          arrived_declared=declared,
                          arrival_verdict_gt_inside_zone_B=inside_at_declared,
                          entered_zone_gt_any=arrived_gt,
                          arrive_pose_eval_only=arrive_pose,
                          rotation_cmd_rad=rotation_cmd, rotation_gt_rad_eval_only=rotation_gt,
                          start_visibility_pixels=start_visibility,
                          start_paint_reason=start_paint_reason,
                          final_pose_eval_only=[float(locals()['qp'][adr]),
                                                float(locals()['qp'][adr + 1])]
                          if 'qp' in locals() else None,
                          spawn_eval_only=plan['spawns']['r1'],
                          camera_frames=len(labels),
                          memory_landmarks=len(mem['memories']) if 'mem' in dir() else 0,
                          terminal_ring=dict(hz=10, indices=list(ring),
                                             bytes=sum((out / 'frames' / f'{i:05d}.jpg').stat().st_size
                                                       for i in ring)),
                          static_map_control=0, spawn_control=0, truth_control=0,
                          top_camera_frames=0, held_world_reads=0, initial_prior='none',
                          noslip_iterations=int(m.opt.noslip_iterations),
                          crossroom_stage=stage, carry_mask_on=carry_mask_on,
                          destination_zone=target_zone,
                          input_audit=audit.summary(),
                          rejection_table=str(a.output / 'rejection_table.json'))
                dump(out / 'episode.json', ep)
                with (out / 'trace.jsonl').open('w') as fh:
                    for row in trace:
                        fh.write(json.dumps(json_safe(row), allow_nan=False) + '\n')
                dump(out / 'commands.json', commands)
                dump(out / 'eval-only.json', dict(evaluation_only=True, frames=labels))
                dump(out / 'events.json', skill.events)
                dump(out / 'SHA256SUMS.json',
                     {str(p.relative_to(out)): sha(p) for p in out.rglob('*') if p.is_file()})
                summaries.append(ep)
                dump(a.output / 'summary.json',
                     dict(status='running', episodes=summaries, n=len(summaries),
                          source_sha=q['source_sha'], raw=str(a.output)))
                # Free per-episode GPU objects before the next start.
                del rc, wd
                try:
                    import gc
                    gc.collect()
                except Exception:
                    pass
        # Aggregate summary and a prior-funnel shaped table for the next run.
        ok_found = sum(1 for e in summaries if e.get('found'))
        ok_colour = sum(1 for e in summaries if e.get('colour_seen'))
        ok_decl = sum(1 for e in summaries if e.get('arrived_declared'))
        ok_gt = sum(1 for e in summaries
                    if e.get('arrival_verdict_gt_inside_zone_B'))
        invisible = sum(1 for e in summaries
                        if (e.get('start_visibility_pixels') or 0) < 120)
        reasons = {}
        for e in summaries:
            if e.get('status') not in ('ARRIVED_DECLARED',):
                reasons[e.get('status', 'UNKNOWN')] = reasons.get(e.get('status', 'UNKNOWN'), 0) + 1
        gates = []
        left = len(summaries)
        for gate, passed in [('starts', left), ('found_metric_or_arrived', ok_found),
                             ('colour_seen', ok_colour),
                             ('arrived_declared', ok_decl), ('arrived_gt', ok_gt)]:
            # Counts, not bool(passed): the r3 preflight runner collapsed every
            # non-zero gate to 1, so the 16-start funnel could not be read n/N.
            passed = int(passed) if left else 0
            gates.append(dict(stage=gate, input_n=left, cumulative_pass_n=passed,
                              rejected_n=int(left) - passed))
            left = passed
        summary = dict(status='DONE', n=len(summaries), source_sha=q['source_sha'],
                       found_n=ok_found, colour_seen_n=ok_colour,
                       arrived_declared_n=ok_decl, arrived_gt_n=ok_gt,
                       initially_invisible_n=invisible,
                       episodes=summaries, raw=str(a.output),
                       rejection_table=str(a.output / 'rejection_table.json'),
                       stack_values=q['stack_values'], flow=q['flow'],
                       sim_s_total=sum(e.get('sim_s', 0.) for e in summaries),
                       static_map_control=0, truth_control=0, top_camera_frames=0)
        dump(a.output / 'summary.json', summary)
        dump(a.output / 'rejection_table.json',
             dict(unit='episode', funnel=gates, reasons=reasons,
                  invisible_starts=invisible, raw=str(a.output),
                  reproduction=sys.argv, blocked_object='not_observed',
                  minimum_gap_m=None, gap_status='not_measured'))
        dump(a.output / 'SHA256SUMS.json',
             {str(p.relative_to(a.output)): sha(p) for p in a.output.rglob('*') if p.is_file()})
        dump(a.output / 'EXIT', dict(status='PREFLIGHT_DONE' if a.preflight else 'DONE',
                                     error=None))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--enabled', action='store_true')
    p.add_argument('--mirror-pulse', action='store_true')
    p.add_argument('--preflight', action='store_true')
    p.add_argument('--implementation', default='legacy_v1')
    p.add_argument('--lease-name', default='crossroom-stageA')
    p.add_argument('--stage', default='A_unloaded')
    p.add_argument('--sim-cap', type=float, default=120.)
    p.add_argument('--episodes', default='')
    p.add_argument('--nworld', type=int, default=None)
    for key in ('queue', 'renderer', 'legacy', 'setups', 'output'):
        p.add_argument('--' + key, type=Path, required=True)
    run(p.parse_args())
