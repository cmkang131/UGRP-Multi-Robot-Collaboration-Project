"""Finite, opt-in single-cargo pick / hold / set-down diagnostic on gcp1.

Default is measurement only. Training RGB is an explicit, audited profile.
The scene owner may know setup and evaluation truth. SoloTeacher receives
only currently visible relative target measurements, own RGB judgments and
issued commands. This runner never forwards its Score back to the teacher.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run(plan, out, *, execution_host, profile='off', hidden=False, look=False, cap_s=90.,
        teacher_stability='off', reach_mode='box_station_v1', rgb_lift_mode='off',
        solo_lift_negative_probe_v1=False, solo_lift_lookback_margin_v1=False,
        training_rgb=False, solo_truth_free_lookaround_v1=False,
        recording_stage='pilot', recording_approval=None, solo_carry_to_zone_v1=False, failure_rgb_buffer=False):
    if platform.system() != 'Linux' or execution_host != 'gcp1':
        raise RuntimeError('Linux gcp1 only; Mac physics/render disabled')
    if not 0 < cap_s <= (300 if solo_carry_to_zone_v1 else 180) or profile != 'solo_visible_only_v1' or not hidden or not look:
        raise ValueError('finite opt-in solo profile with both required toggles')
    if teacher_stability not in ('off', 'align_relook_v1') or reach_mode not in ('box_station_v1', 'pad_window_v2'):
        raise ValueError('unknown solo stability/reach mode')
    if rgb_lift_mode not in ('off', 'solo_rgb_lift_v2', 'solo_rgb_lift_v3', 'solo_lift_lookback_v1'):
        raise ValueError('unknown solo RGB lift mode')
    validate_negative_probe(plan, solo_lift_negative_probe_v1, rgb_lift_mode)
    validate_carry(plan, enabled=solo_carry_to_zone_v1, training_rgb=training_rgb,
                   truth_free=solo_truth_free_lookaround_v1, lift=rgb_lift_mode,
                   negative=solo_lift_negative_probe_v1)
    from harness.grasp_act_solo_recording import validate_recording, camera_config, SoloRecorder, validate_approval
    validate_recording(plan, training_rgb=training_rgb, truth_free_v1=solo_truth_free_lookaround_v1,
        negative=solo_lift_negative_probe_v1, stability=teacher_stability, reach=reach_mode,
        lift=rgb_lift_mode, margin=solo_lift_lookback_margin_v1)
    from scripts.grasp_act_host import identity, require_run_root
    host = identity(execution_host)
    require_run_root(out)
    from scripts.run_grasp_act_teacher import write, apply, compress_logs
    from sim.grasp_act_solo_teacher import SoloTeacher, InputAudit, VisibilityStats, primitives
    from sim.grasp_act_solo_lookaround import SoloLookaround
    from sim.grasp_act_solo_rgb import lift_answer, SoloLiftObserver
    from sim.grasp_act_solo_evaluation import Score, bottom_z
    from sim.grasp_act_scene import make_scene
    from sim.grasp_act_port import DutyActPort
    from sim.masterpi_drive_friction_v7 import build_world, PROFILE
    from sim.s2_realism_camera_binding import bind_camera
    from scripts.audit_grasp_act_visibility import BandVisibility
    from scripts.zone_teacher import plan_path, proportional_drive
    from sim.active_lookaround import wrap
    import cv2
    import mujoco
    import numpy as np

    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT):
        raise RuntimeError('committed source required (tracked files clean)')
    approval = validate_approval(recording_approval, stage=recording_stage, sha=sha, host=host) if training_rgb else None
    out.mkdir(parents=True, exist_ok=False)
    write(out/'plan.json', plan)
    write(out/'RUN_META.json', {'class': 'dev', 'branch': 'claude/map-carry-zone' if solo_carry_to_zone_v1 else 'claude/act-solo-teacher',
          'sha': sha, 'pr': plan.get('pr'), 'batch': plan['batch'],
          'negative_probe': bool(solo_lift_negative_probe_v1)})
    report = {'status': 'running', 'source_sha': sha, 'execution_host': host,
              'student_execution': False,
              'recording_mode': 'training' if training_rgb else 'negative_probe_diagnostic' if solo_lift_negative_probe_v1 else 'success_measurement',
              'object_kind': plan['kind'], 'weld': 'off', 'training_rgb': bool(training_rgb),
              'recording_stage': recording_stage if training_rgb else None,
              'recording_approval': approval,
              'solo_truth_free_lookaround_v1': bool(solo_truth_free_lookaround_v1),
              'teacher_stability': teacher_stability, 'reach_mode': reach_mode,
              'rgb_lift_mode': rgb_lift_mode,
              'negative_probe': bool(solo_lift_negative_probe_v1),
              'solo_lift_lookback_margin_v1': bool(solo_lift_lookback_margin_v1),
              'gate_eligible': not solo_lift_negative_probe_v1 and not training_rgb,
              'physical_success': None, 'placement_task': 'set down at own picked location',
              'plan_sha256': hashlib.sha256((out/'plan.json').read_bytes()).hexdigest()}
    if solo_carry_to_zone_v1:
        report.update(solo_carry_to_zone_v1=True, gate_eligible=False,
                      placement_task='carry to authored destination zone',
                      scenario_version='v7' if plan.get('reloc14_scene_v7') else 'v6',
                      pool_with_previous_results=False,
                      destination_zone=plan['destination_zone'], research_result=False)
    if training_rgb:
        report.update(training_include=False, training_candidate=False, data_admitted=False,
                      training_exclusion_reason='not complete / awaiting qualification and dataset admission')
    write(out/'result.json', report)
    world, streams, recorder = None, [], None
    if training_rgb:
        (out/'teacher-raw').mkdir()
        (out/'evaluation').mkdir()
    start = time.monotonic()
    audit, visibility_stats, score = InputAudit(), VisibilityStats(), Score()
    from harness.failure_rgb_buffer import FailureRGBBuffer
    failure_frames=FailureRGBBuffer(out/'failure-rgb') if failure_rgb_buffer else None
    ops = primitives()
    try:
        # Scene hardware/camera/physics are exactly the existing pair setup.
        scene = make_scene({**plan, 'end_color_scene': 'off'})
        scene.config['setup_only']['spawns'].update(plan['spawns'])
        os.environ['UGRP_SIM_OBSERVER_WIDTH'] = '320'
        os.environ['UGRP_SIM_OBSERVER_HEIGHT'] = '240'
        sampling = camera_config() if training_rgb else {'width': 640, 'height': 480}
        world = build_world(scene, drive_profile=PROFILE, seed=plan['seed'], width=sampling['width'],
                            height=sampling['height'], render=True, warehouse_layout=scene.engine_layout,
                            warehouse_cargo_ids=None, roller_collision='mesh', idle_robot_contacts='off')
        if plan.get('render_profile') == 'floor_light_textured_v1':
            from sim.grasp_act_scene import audit_render
            write(out/'texture-audit.json',audit_render(world.model,plan))
        for controller in world.controllers.values():
            bind_camera(controller)
        scene.setup(world)
        (out/'scene.xml').write_text(world.scene_xml)
        write(out/'scene.json', scene.manifest)
        rid, item = plan['robot_id'], plan['item_id']
        if plan['kind'] in ('cyan', 'red', 'green', 'yellow'):
            body_name = scene.config['setup_only']['objects'][item]['body_name']
            body_origin_z = .016
        else:
            inst = next(c for c in scene.cargo if c.item_id == item and c.kind == plan['kind'])
            body_name, body_origin_z = inst.body, 0.
        model, data = world.model, world.data
        if training_rgb:
            cid = world.controllers[rid].robot_cam_cid
            write(out/'evaluation'/'camera-runtime.json', {
                'pos': model.cam_pos[cid].tolist(), 'quat': model.cam_quat[cid].tolist(),
                'intrinsic': model.cam_intrinsic[cid].tolist(), 'resolution': model.cam_resolution[cid].tolist(),
                'scope': 'runtime camera configuration only; excluded from student observations'})

        # Generalize the pair's calibrated ray/FOV adapter without its two
        # mandatory beam-band IDs. Only its geometry methods are reused.
        class ObjectEyes(BandVisibility):
            def __init__(self):
                from sim.masterpi_camera_profile import scaled_camera_matrix, CAMERA_FISHEYE_D
                self.np, self.model = np, model
                self.K, self.D = scaled_camera_matrix(640, 480), np.array(CAMERA_FISHEYE_D)
                self.groups = np.array([1, 1, 1, 1, 0, 0], dtype=np.uint8)
                self.near = float(model.vis.map.znear*model.stat.extent)
                self.cameras = {r: model.camera(r+'__robot_cam').id for r in ('r1', 'r2', 'r3')}
                self.body_gids = {}

        eyes = ObjectEyes()
        bid = model.body(body_name).id
        gids = [g for g in range(model.ngeom) if model.geom_bodyid[g] == bid and model.geom_contype[g]]
        if not gids:
            raise ValueError('production cargo collision geoms required')
        target_set = set(gids)
        finger_ids = {model.geom(rid+'__'+s+'_finger').id: i for i, s in enumerate(('left', 'right'))}
        initial_xy = data.body(body_name).xpos[:2].copy()  # EVALUATION ONLY
        last_eval_pos, last_eval_t = None, None
        static = scene.config['static_map']
        carry = None
        if solo_carry_to_zone_v1:
            from sim.solo_carry_to_zone import CarryToZone
            from sim.grasp_act_solo_evaluation import ZoneScore
            from harness.zone_final_environment import digest
            if digest(static) != plan['static_map_sha256']:
                raise ValueError('carry static map/scene hash mismatch')
            carry = CarryToZone(static, plan['destination_zone'], start=plan['task_start'],
                                now=float(data.time), robot_id=rid,
                                recovery_profile=plan.get('carry5_profile', 'off'),
                                drive_model_deadband_v1=plan.get('drive_model_deadband_v1', False),
                                carry5_rank_aware_views_v1=plan.get('carry5_rank_aware_views_v1', False),
                                carry5_trim_yaw_calibration_v1=plan.get('carry5_trim_yaw_calibration_v1', False),
                                trim_calibration=plan.get('trim_calibration'),
                                carry7_robust_recovery_v1=plan.get('carry7_robust_recovery_v1', False),
                                reloc9_rotation_calibration_v1=plan.get('reloc9_rotation_calibration_v1', False),
                                reloc10_rotation_calibration_v1=plan.get('reloc10_rotation_calibration_v1', False),
                                reloc12_carry_reacquire_v1=plan.get('reloc12_carry_reacquire_v1', False),
                                carry_pose_budget_recal_v1=plan.get('carry_pose_budget_recal_v1', False),
                                reloc14_carry_budget_v1=plan.get('reloc14_carry_budget_v1', False),
                                reloc14_compute_budget_v1=plan.get('reloc14_compute_budget_v1', False),
                                reloc14_carry_tracking_v1=plan.get('reloc14_carry_tracking_v1', False),
                                reloc15_rgb_heading_v1=plan.get('reloc15_rgb_heading_v1', False),
                                carry_pose_budget_xy_reserve0_v1=plan.get('carry_pose_budget_xy_reserve0_v1', False))
            if carry.loc.drive_model_enabled:
                ops.delta = carry.loc.cached_delta
                ops.propagate = carry.loc.propagate_point
            score = ZoneScore(carry.region, active_recovery=carry.active_recovery)
            write(out/'carry-static-map.json', static)
        # Legacy look-around used live truth + frozen error as a map estimate.
        # Recording uses a pose-free scan; carry2 shares only its command belief.
        relook = SoloLookaround(static, ops=ops, truth_free_v1=solo_truth_free_lookaround_v1,
                                command_pose=carry.loc if carry is not None else None,
                                carry5=carry is not None and carry.active_recovery,
                                carry5_rank_aware_views_v1=plan.get('carry5_rank_aware_views_v1', False),
                                carry7_robust_recovery_v1=plan.get('carry7_robust_recovery_v1', False),
                                active_relocalization=plan.get('active_relocalization', 'off'),
                                reloc9_wall_height_guard_v1=plan.get('reloc9_wall_height_guard_v1', False))
        look_eval = {'views': []}

        def truth_pose():
            base = world.robot(rid).base_xyz()
            return [float(base[0]), float(base[1]), float(world.robot(rid).base_rpy()[2])]

        def look_truth():
            # Evaluation only: estimate error against truth and FK camera vs rendered camera.
            g = truth_pose(); x = relook.loc.own.x
            out = {'error_xy_m': float(math.hypot(x[0]-g[0], x[1]-g[1])),
                   'error_yaw_deg': float(math.degrees(wrap(x[2]-g[2]))), 'truth': g}
            ctrl = world.controllers[rid]; cid = ctrl.robot_cam_cid; c_, s_ = math.cos(g[2]), math.sin(g[2])
            b_ = world.robot(rid).base_xyz()
            cp = np.array([data.cam_xpos[cid][0]-b_[0], data.cam_xpos[cid][1]-b_[1], data.cam_xpos[cid][2]])
            cz = data.cam_xmat[cid].reshape(3, 3)@np.array([0., 0., -1.])
            rot_b = np.array([[c_, s_, 0.], [-s_, c_, 0.], [0., 0., 1.]])
            body_o, body_z = rot_b@cp, rot_b@cz
            fk, _ = relook.loc.camera.pose({s: teacher.sink.pwm[s] for s in (1, 3, 4, 5, 6)})
            if fk is not None:
                out['camera_fk_origin_error_m'] = float(np.linalg.norm(fk[0]-body_o))
                out['camera_fk_axis_error_deg'] = float(math.degrees(math.acos(max(-1., min(1., float(fk[1][:, 2]@body_z))))))
            return out
        port = DutyActPort(world, rid, allow_reverse=True, allow_mecanum=True)
        pwm = {s: int(port._servo_pulses[s]) for s in (1, 3, 4, 5, 6)}
        observed_discs, observed_rects = [], []

        def route(goal, context):
            # Current visible wall measurements remain in the body frame;
            # an uncertain map prior cannot fabricate a registered self pose.
            discs, rects = observed_discs, observed_rects
            if carry is not None and carry.active_recovery:
                target = None if teacher.target is None else teacher.target['xyz'][:2]
                return carry.pickup_route(goal, target, teacher.spec.kind, carry.loc.now)
            if carry is not None:
                x, y, a = carry.loc.pose; c, s = math.cos(a), math.sin(a)
                from scripts.zone_teacher import PeerDisc
                discs = [PeerDisc((c*(ox-x)+s*(oy-y), -s*(ox-x)+c*(oy-y), r))
                         for ox, oy, r in carry.obstacles.discs(carry.loc.now)]
                # The local teacher already has this currently visible target.
                # Its relative measurement is never forwarded to map memory.
                if teacher.target is not None:
                    tx, ty = teacher.target['xyz'][:2]
                    discs = [d for d in discs if math.dist(d[:2], (tx, ty)) > .12]
                rects = [(c*(ox-x)+s*(oy-y), -s*(ox-x)+c*(oy-y), hx, hy, angle-a)
                         for ox, oy, hx, hy, angle in carry.rects]
            path = plan_path((0., 0.), goal[:2], (-2., 2., -2., 2.), discs,
                             rects=rects, radius=.17)
            if not path:
                return 0., 0., 0.
            point = next((p for p in path if math.hypot(*p) >= .06), goal[:2])
            cmd = proportional_drive((0., 0., 0.), goal[:2], point, goal[2])
            return cmd['forward'], cmd['left'], cmd['turn']

        teacher = SoloTeacher(plan['kind'], plan['role'], pwm, profile=profile,
                              held_object_hidden_v1=hidden, setdown_lookaround_v1=look,
                              lookaround=relook, route=route, ops=ops,
                              teacher_stability=teacher_stability, reach_mode=reach_mode,
                              rgb_lift_mode=rgb_lift_mode,
                              solo_lift_negative_probe_v1=solo_lift_negative_probe_v1,
                              solo_lift_lookback_margin_v1=solo_lift_lookback_margin_v1,
                              solo_carry_to_zone_v1=solo_carry_to_zone_v1, carry=carry,
                              reloc9_reacquisition_v1=plan.get('reloc9_reacquisition_v1', False))
        if rgb_lift_mode == 'solo_lift_lookback_v1':
            from sim.grasp_act_solo_lookback import LookbackObserver
            lift_observer = LookbackObserver(plan['kind'], propagate=ops.propagate) if carry is not None and carry.active_recovery else LookbackObserver(plan['kind'])
        else:
            lift_observer = SoloLiftObserver(plan['kind'], mode=rgb_lift_mode) if rgb_lift_mode != 'off' else None
        if lift_observer is not None:
            (out/'lift-rgb').mkdir()

        lift_reference_index = 0

        def save_lift(tag, frame, now):
            if carry is not None and carry.active_recovery:
                tag = f'grasp-{lift_reference_index:02d}-'+tag
            path = out/'lift-rgb'/f'{tag}.png'
            if not cv2.imwrite(str(path), frame):
                raise RuntimeError('failed to save own lift RGB evidence')
            return {'path': str(path.relative_to(out)), 't': now,
                    'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                    'pixel_sha256': hashlib.sha256(frame.tobytes()).hexdigest(),
                    'shape': list(frame.shape)}
        lift_evidence = {}
        look_state = {'last_view_n': 0}
        def refresh_obstacles():
            observed_discs.clear()
            base = world.robot(rid).base_xyz()
            a = float(world.robot(rid).base_rpy()[2]); c, s = math.cos(a), math.sin(a)
            for other in ('r1', 'r2', 'r3'):
                if other == rid:
                    continue
                obid = model.body(other+'__robot').id
                n, total = eyes.region_visible(data, rid, eyes._body_geoms(obid))
                if total and n >= math.ceil(total/3):
                    xy = data.body(other+'__robot').xpos[:2]-base[:2]
                    observed_discs.append((c*xy[0]+s*xy[1], -s*xy[0]+c*xy[1], .17))
            # Every other cargo and visible wall uses the same current gate.
            bodies = {x.item_id: x.body for x in scene.cargo}
            bodies.update({i: x['body_name'] for i, x in scene.config['setup_only']['objects'].items()})
            for iid, name in bodies.items():
                if iid == item:
                    continue
                obid = model.body(name).id
                og = eyes._body_geoms(obid)
                n, total = eyes.region_visible(data, rid, og)
                if total and n >= math.ceil(total/3):
                    xy = data.body(name).xpos[:2]-base[:2]
                    radius = max((float(np.linalg.norm(data.geom_xpos[g, :2]-data.body(name).xpos[:2]))
                                  + float(model.geom_rbound[g]) for g in og), default=.2)
                    observed_discs.append((c*xy[0]+s*xy[1], -s*xy[0]+c*xy[1], radius))
            observed_rects.clear()
            for g in range(model.ngeom):
                if 'wall' not in (model.geom(g).name or ''):
                    continue
                n, total = eyes.region_visible(data, rid, [g])
                if total and n >= math.ceil(total/3):
                    xy = data.geom_xpos[g, :2]-base[:2]
                    rot = data.geom_xmat[g].reshape(3, 3)
                    observed_rects.append((c*xy[0]+s*xy[1], -s*xy[0]+c*xy[1],
                        *map(float, model.geom_size[g, :2]), wrap(math.atan2(rot[1, 0], rot[0, 0])-a)))

        previous = teacher._hold(float(data.time))
        trace = (out/('teacher-raw/commands.jsonl' if training_rgb else 'teacher-commands.jsonl')).open('x'); streams.append(trace)
        ev = (out/('evaluation/eval-only.jsonl' if training_rgb else 'eval-only.jsonl')).open('x'); streams.append(ev)
        if training_rgb:
            recorder = SoloRecorder(out, plan, previous)
        (out/'review-own').mkdir()
        if not plan.get('reloc10_own_review_only_v1', False):
            (out/'review-top').mkdir()
        origin = float(data.time)
        reloc10_loop_wall = time.monotonic()
        finished_t = None
        negative_eval = {'N': 0, 'max_clearance_m': 0., 'max_pickup_offset_m': 0.}
        tick = 0
        while float(data.time)-origin < cap_s-1e-8:
            if (out/'SUPERVISOR_STOP.json').exists():
                raise KeyboardInterrupt('supervisor stopped this run')
            now = float(data.time)
            if plan.get('reloc10_own_review_only_v1', False) and now-origin >= 30.-1e-8 and 'first30' not in report:
                report['first30'] = dict(elapsed_sim_s=now-origin, wall_elapsed_s=time.monotonic()-reloc10_loop_wall,
                    wall_per_sim=(time.monotonic()-reloc10_loop_wall)/(now-origin), top_capture=False)
                write(out/'first30.json', report['first30'])
            if data.eq_active.any():
                raise RuntimeError('WELD_ACTIVE')
            visible_n, probe_N = eyes.region_visible(data, rid, gids)
            visible = probe_N > 0 and visible_n >= math.ceil(probe_N/3)
            visibility_stats.add(now, teacher.phase, visible)

            def read_relative():
                # Reached only when currently visible AND not held. Coordinates
                # are confined to this adapter; only body-frame pose leaves it.
                b = data.body(body_name)
                rot = b.xmat.reshape(3, 3)
                point = b.xpos+rot@np.array([0., 0., teacher.spec.grip_z_m-body_origin_z])
                base = world.robot(rid).base_xyz()
                a = float(world.robot(rid).base_rpy()[2]); c, s = math.cos(a), math.sin(a)
                dx, dy = point[0]-base[0], point[1]-base[1]
                return {'xyz': [float(c*dx+s*dy), float(-s*dx+c*dy), float(point[2])],
                        'yaw': wrap(math.atan2(rot[1, 0], rot[0, 0])-a)}

            measurement = audit.measure(teacher.phase, visible_n=visible_n, probe_N=probe_N,
                                        holding=teacher.holding, read_relative=read_relative)
            # Capture once: recording persists exactly these controller bytes.
            jpg = base64.b64decode(port.capture()['image'])
            bgr = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
            if failure_frames is not None:
                failure_frames.add(now,jpg,camera=rid+'/robot_cam')
            map_evidence = None
            if carry is not None:
                if tick:
                    carry.issue(previous, now-float(previous['t']))
                carry.observe_own(bgr, now, camera=rid+'/robot_cam')
                map_evidence = {'t': now, **carry.loc.record()}
            if recorder is not None:
                recorder.observe(now, jpg, bgr, skill=teacher.skill, phase=teacher.phase, previous=previous)
            rgb_result = {'answer': 'unknown'}
            if teacher.phase in ('verify_lift', 'hold'):
                if lift_observer is not None:
                    rgb_result = lift_observer.observe(bgr, {**previous, 't': now},
                                                      complete=True, save=save_lift)
                else:
                    answer, rec = lift_answer(bgr, teacher.sink.pwm, plan['kind'], teacher.low,
                                              teacher.grasp_xyz[:2])
                    rgb_result = {**rec, 'answer': answer}
                evidence = rgb_result['evidence']
                lift_evidence[evidence] = lift_evidence.get(evidence, 0)+1
            elif teacher.phase == 'lift' and lift_observer is not None:
                lift_observer.observe(bgr, {**previous, 't': now}, complete=False, save=save_lift)
            if teacher.phase == 'lower' and not relook.armed:
                if solo_truth_free_lookaround_v1:
                    relook.arm()  # carry shares command prior; legacy scan has no global prior
                    look_eval['armed_t'] = now
                else:
                    # Preserved legacy comparison ONLY; forbidden for recording.
                    g = truth_pose(); pose_error = plan['handoff_pose_error']
                    relook.arm([g[0]+pose_error[0], g[1]+pose_error[1], g[2]+pose_error[2]])
                    look_eval['before'] = look_truth(); look_eval['armed_t'] = now
            if carry is not None and (tick % 5 == 0 or teacher.holding != carry.obstacles.holding):
                # Carry sees own RGB only, including while holding. No scene
                # visibility gate or truth coordinates enter this memory.
                grasp_pwm = {1: 1500, **teacher.low} if teacher.low is not None else None
                carry.refresh_obstacles(bgr, teacher.sink.pwm, now, holding=teacher.holding,
                                        kind=plan['kind'], grasp_pwm=grasp_pwm)
            if tick % 5 == 0 and carry is None:
                # Currently visible obstacles only (same one-third gate as the target),
                # refreshed at 2 Hz: it feeds the route planner, never a pose or a label.
                refresh_obstacles()
            phase_before = teacher.phase
            place_visible = (carry.place_visible(bgr, teacher.sink.pwm, teacher.low, plan['kind'])
                             if carry is not None and teacher.phase == 'zone_place_view' else False)
            value, complete = teacher.step(now, measurement=measurement,
                        rgb_holding=rgb_result.get('answer', 'unknown'),
                        own_rgb=lambda: cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), place_visible=place_visible)
            if recorder is not None:
                recorder.target(value, skill_after=teacher.skill, phase_after=teacher.phase, complete=complete)
            views = [e for e in relook.events if e['event'] == 'view']
            if len(views) > look_state['last_view_n']:
                # A view was captured this tick: score the updated estimate against truth (eval only).
                row = {'t': now, **views[-1], **(look_truth() if relook.loc is not None else {})}
                look_eval['views'].append(row)
                ev.write(json.dumps({'kind': 'lookaround_view', **row})+'\n')
                look_state['last_view_n'] = len(views)
            if carry is not None and carry.active_recovery and relook.armed:
                look_eval.setdefault('armed_t', relook.events[0]['t'] if relook.events else now)
            if complete and relook.loc is not None and 'after' not in look_eval:
                look_eval['after'] = look_truth(); look_eval['sim_s'] = now-look_eval['armed_t']
            apply(port, value, now, previous)
            if rgb_lift_mode == 'solo_lift_lookback_v1':
                if phase_before in ('align', 'approach') and teacher.phase == 'hover':
                    # Before hover/descent/close: the last visible pickup frame.
                    # Its camera pose is the PREVIOUS issued command, not the
                    # newly queued arm target and never teacher.grasp_xyz.
                    if carry is not None and carry.active_recovery:
                        lift_reference_index += 1
                        lift_observer = LookbackObserver(plan['kind'], propagate=ops.propagate)
                    lift_observer.start(bgr, {**previous, 't': now}, save_lift)
                lift_observer.issue(value, teacher.phase)
            elif lift_observer is not None and phase_before == 'close' and teacher.phase == 'lift':
                # This frame was captured BEFORE issuing the raise. Commands
                # are the teacher's own outputs, not servo measurements.
                lift_observer.start(bgr, value, save_lift)
            previous = value
            trace.write(json.dumps({'t': now, 'phase': teacher.phase, 'command': value,
                                   'visible_target': measurement,
                'student_context': teacher.context(now), 'rgb_confirmation': rgb_result,
                **({'map_pose': map_evidence, 'destination_floor_visible': place_visible,
                    'pickup_search': teacher.pickup_search.record(),
                    'carry_obstacles': carry.obstacles.record(),
                    'phase_before': phase_before} if carry is not None else {})})+'\n')

            # Full truth owner, written only to eval-only.jsonl / Score.
            body = data.body(body_name); rot = body.xmat.reshape(3, 3)
            min_z = min(bottom_z('cylinder' if model.geom_type[g] == mujoco.mjtGeom.mjGEOM_CYLINDER else 'box',
                                data.geom_xpos[g], data.geom_xmat[g].reshape(3, 3), model.geom_size[g]) for g in gids)
            forces = [0., 0.]; f = np.zeros(6)
            finger_contacts = False
            for i in range(data.ncon):
                g1, g2 = int(data.contact[i].geom1), int(data.contact[i].geom2)
                finger = g1 if g2 in target_set else g2 if g1 in target_set else None
                if finger in finger_ids:
                    finger_contacts = True
                    mujoco.mj_contactForce(model, data, i, f)
                    forces[finger_ids[finger]] += abs(float(f[0]))
            pos = body.xpos.copy()
            base = world.robot(rid).base_xyz()      # evaluation-only record, never read by the teacher
            speed = 0. if last_eval_t is None else float(np.linalg.norm(pos-last_eval_pos)/(now-last_eval_t))
            tilt = math.degrees(math.acos(float(np.clip(rot[2, 2], -1., 1.))))
            row = {'min_z': min_z, 'support_z': 0., 'tilt_deg': tilt, 'finger_forces': forces,
                'speed': speed, 'open_issued': value['pwm']['1'] >= 1900,
                'placement_offset': float(np.linalg.norm(pos[:2]-initial_xy)), 'weld_active': False,
                'negative_probe': bool(solo_lift_negative_probe_v1)}
            score_row = {k: v for k, v in row.items() if k != 'negative_probe'}
            if carry is not None:
                # Full 3-D collision-box corners projected into the zone plane;
                # COM-inside alone would accept a box straddling the boundary.
                corners = []
                for g in gids:
                    r = data.geom_xmat[g].reshape(3, 3)
                    for sx in (-1, 1):
                        for sy in (-1, 1):
                            for sz in (-1, 1):
                                p = data.geom_xpos[g]+r@(model.geom_size[g]*[sx, sy, sz])
                                corners.append(p[:2].tolist())
                score.add(now, phase=phase_before, footprint_xy=corners, finger_contacts=finger_contacts, **score_row)
                estimate = carry.loc.pose
                row.update(footprint_xy=corners, evaluation_phase=phase_before, finger_contacts=finger_contacts,
                    map_pose_error_xy_m=math.dist(estimate[:2], base[:2]) if estimate is not None else None,
                    map_pose_error_yaw_rad=wrap(estimate[2]-float(world.robot(rid).base_rpy()[2])) if estimate is not None else None)
            else:
                score.add(now, **score_row)
            if solo_lift_negative_probe_v1 and rgb_result.get('evidence') == 'solo_lift_lookback_v1':
                negative_eval['N'] += 1
                negative_eval['max_clearance_m'] = max(negative_eval['max_clearance_m'], min_z)
                negative_eval['max_pickup_offset_m'] = max(negative_eval['max_pickup_offset_m'], row['placement_offset'])
            ev.write(json.dumps({'t': now, **row, 'cargo_xyz': pos.tolist(),
                     'base_xyz': list(map(float, base)), 'visible_n': visible_n, 'probe_N': probe_N,
                     'lookaround_estimate_xy': list(map(float, relook.loc.own.x[:2])) if relook.loc is not None else None})+'\n')
            last_eval_pos, last_eval_t = pos, now
            if tick % 10 == 0:
                cv2.imwrite(str(out/'review-own'/f'{tick:06d}.jpg'), cv2.resize(bgr, (320, 240)))
                if not plan.get('reloc10_own_review_only_v1', False):
                    (out/'review-top'/f'{tick:06d}.jpg').write_bytes(world.render_team_jpeg(camera=static['top_cameras'][0]['name']))
                write(out/'progress.json', {'sim_s': now-origin, 'phase': teacher.phase, 'source_sha': sha})
                for stream in streams:
                    stream.flush()
                if recorder is not None:
                    recorder.flush()
                    write(out/'recording-progress.json', recorder.record())
            if teacher.result not in (None, 'command_complete'):
                break
            if complete:
                finished_t = now if finished_t is None else finished_t
                if now-finished_t >= 2.:
                    break
            tick += 1
            until = origin+tick*.1
            while float(data.time) < until-1e-8:
                port.tick(float(data.time))
                world._physics_step_for(world.robot(rid))
        report.update(status='complete', sim_s=float(data.time)-origin, wall_s=time.monotonic()-start,
            teacher=teacher.diagnostic(), input_audit=audit.record(), visibility=visibility_stats.record(),
            lookaround={'localizer': relook.record(), 'evaluation': look_eval},
            lift_rgb_evidence_ticks=lift_evidence, **score.record(teacher.result == 'command_complete'))
        if lift_observer is not None:
            report[rgb_lift_mode.removeprefix('solo_')] = lift_observer.record()
        if carry is not None:
            report['termination_reason'] = teacher.result or 'sim_cap'
            report['termination_category'] = 'cap_end' if teacher.result is None else teacher.result
        if solo_lift_negative_probe_v1:
            phases = {e['to'] for e in teacher.events}
            counts = lift_observer.answer_counts
            report['negative_probe_evaluation'] = {
                'intervention': 'open_after_close_before_lift',
                'yes_ticks': counts['yes'], 'no_ticks': counts['no'], 'unknown_ticks': counts['unknown'],
                'no_pretend_setdown': not bool(phases & {'hold', 'lookback_return', 'lower', 'open', 'backoff', 'lookaround', 'complete'}),
                'rgb_probe_passed': bool(lift_observer.completed_at is not None and counts['yes'] == 0
                                         and teacher.result == 'rgb_lift_unconfirmed'),
                'evaluation_only': True, 'gate_eligible': False, 'training_eligible': False}
            probe = report['negative_probe_evaluation']
            probe['cargo_remains_at_pickup'] = bool(negative_eval['N'] > 0 and negative_eval['max_clearance_m'] <= .005
                                                  and negative_eval['max_pickup_offset_m'] <= .05)
            probe['cargo_eval'] = negative_eval
            probe['passed'] = probe['rgb_probe_passed'] and probe['no_pretend_setdown'] and probe['cargo_remains_at_pickup']
        report['data_admitted'] = False
        if recorder is not None:
            report['recording'] = recorder.record()
            report['training_include'] = False
            report['training_candidate'] = bool(report['physical_success'] and recorder.local_started and approval)
            report['training_exclusion_reason'] = 'pending independent dataset admission' if report['training_candidate'] else 'pilot / failure / unqualified source or absent own-RGB handoff'
        write(out/'result.json', report)
    except BaseException as error:
        report.update(status='interrupted' if isinstance(error, KeyboardInterrupt) else 'HOST_ERROR',
                      error_type=type(error).__name__, error=str(error), wall_s=time.monotonic()-start,
                      input_audit=audit.record(), visibility=visibility_stats.record())
        write(out/'result.json', report)
        raise
    finally:
        if failure_frames is not None:
            report['failure_rgb_buffer']=failure_frames.flush(report.get('status','interrupted'))
            write(out/'result.json',report)
        if recorder is not None:
            recorder.flush()
            if 'recording' not in report:
                report.update(recording=recorder.record(), training_include=False, training_candidate=False,
                              data_admitted=False, training_exclusion_reason='incomplete / HOST_ERROR')
                write(out/'result.json', report)
            recorder.close()
        for stream in streams:
            stream.close()
        if world is not None:
            world.close()
        compress_logs(out)
    return report


def validate_negative_probe(plan, enabled, rgb_lift_mode):
    """Reject diagnostic interventions in gate/training runs before any world exists."""
    diagnostic = plan.get('split') == 'solo_lift_negative_probe'
    if diagnostic != bool(enabled) or bool(plan.get('negative_probe', False)) != bool(enabled):
        raise ValueError('negative probe requires its dedicated diagnostic split and explicit matching toggle')
    if enabled:
        from harness.grasp_act_seed_splits import check_range
        from sim.grasp_act_solo_teacher import BOX_KINDS
        check_range('solo_lift_negative_probe', plan['seed'], 1)
        if plan['kind'] not in BOX_KINDS or rgb_lift_mode != 'solo_lift_lookback_v1':
            raise ValueError('negative probe requires box cargo and the unchanged lookback judge')


def validate_carry(plan, *, enabled, training_rgb, truth_free, lift, negative):
    if bool(plan.get('solo_carry_to_zone_v1', False)) != bool(enabled):
        raise ValueError('carry plan requires matching explicit toggle')
    if not enabled:
        return
    from harness.grasp_act_seed_splits import check_range
    from sim.grasp_act_solo_teacher import BOX_KINDS
    from harness.zone_environment_registry import load_scenario
    check_range('solo_carry_diagnostic_v1', plan['seed'], 1)
    if (training_rgb or negative or not truth_free or lift != 'solo_lift_lookback_v1'
            or plan.get('split') != 'solo_carry_diagnostic_v1' or plan['kind'] not in BOX_KINDS
            or not (plan['scenario_id'].endswith('_v6') or plan.get('reloc14_scene_v7') is True and plan['scenario_id'].endswith('_v7')) or plan.get('gate_eligible') is not False):
        raise ValueError('carry diagnostic requires v6 box, truth-free lookaround, RGB lift, training off')
    from harness.zone_final_environment import resolve
    from sim.solo_carry_pose import task_start
    if (plan.get('carry_pose_profile') != 'own_command_v2' or plan.get('amcl_option') != 'off'
            or plan.get('task_start') != task_start(resolve(plan['map_id'])[0])):
        raise ValueError('carry2 requires declared task start and own commands; top RGB forbidden (#366)')
    from sim.solo_pickup_search import PROFILE as SEARCH_PROFILE
    if plan.get('pickup_search_profile') != SEARCH_PROFILE:
        raise ValueError('carry3 requires explicit static pickup search profile')
    if plan.get('carry5_profile', 'off') not in ('off', 'carry5_active_localization_v1'):
        raise ValueError('unknown carry5 profile')
    if plan.get('carry5_profile') == 'carry5_active_localization_v1' and plan.get('drive_model_deadband_v1') is not True:
        raise ValueError('carry5 requires the merged shared drive_model_deadband_v1')
    if plan.get('render_profile','floor_light_v1') not in ('floor_light_v1','floor_light_textured_v1'):
        raise ValueError('unknown carry render profile')
    for option in ('carry5_rank_aware_views_v1', 'carry5_trim_yaw_calibration_v1', 'carry7_robust_recovery_v1',
                   'reloc9_rotation_calibration_v1', 'reloc9_wall_height_guard_v1', 'reloc9_reacquisition_v1', 'reloc10_rotation_calibration_v1', 'reloc10_own_review_only_v1', 'reloc12_carry_reacquire_v1', 'carry_pose_budget_recal_v1', 'carry_pose_budget_xy_reserve0_v1', 'reloc14_carry_budget_v1', 'reloc14_compute_budget_v1', 'reloc14_scene_v7', 'reloc14_carry_tracking_v1', 'reloc15_rgb_heading_v1'):
        if type(plan.get(option, False)) is not bool:
            raise ValueError(option+' must be bool')
        if plan.get(option) and plan.get('carry5_profile') != 'carry5_active_localization_v1':
            raise ValueError(option+' requires carry5 recovery')
    if plan.get('carry7_robust_recovery_v1') and plan.get('carry5_rank_aware_views_v1') is not True:
        raise ValueError('carry7 requires carry6 rank-aware views')
    if plan.get('reloc9_reacquisition_v1') and not plan.get('carry7_robust_recovery_v1'):
        raise ValueError('reloc9 search requires carry7 safety')
    from harness.active_relocalization import validate
    validate(plan.get('active_relocalization', 'off'))
    if plan.get('active_relocalization', 'off') != 'off' and plan.get('carry7_robust_recovery_v1') is not True:
        raise ValueError('RELOC8_REQUIRES_CARRY7_SAFETY')
    if plan.get('carry5_trim_yaw_calibration_v1'):
        from sim.solo_carry6 import validate_calibration
        validate_calibration(plan.get('trim_calibration'))
    scenario = load_scenario(plan['scenario_id'])
    version = 'v7' if plan.get('reloc14_scene_v7', False) else 'v6'
    source = ROOT/f'configs/zone_study_scenarios_{version}'/f"{plan['scenario_id']}.json"
    if version == 'v7' and any(p['kind']=='heavy_crate' for p in scenario['eval']['setup']['placements']):
        raise ValueError('reloc14 v7 forbids heavy_crate')
    if hashlib.sha256(source.read_bytes()).hexdigest() != plan['scenario_source_sha256']:
        raise ValueError('carry scenario hash mismatch')
    placement = next(p for p in scenario['eval']['setup']['placements'] if p['item_id'] == plan['item_id'])
    order = next(o for o in scenario['orders'] if o['order_id'] == placement['order_id'])
    if placement['kind'] != plan['kind'] or order['destination_zone'] != plan['destination_zone']:
        raise ValueError('carry order/box/destination mismatch')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--episode', type=int, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--execution-host', choices=('gcp1',), required=True)
    p.add_argument('--teacher-profile', choices=('off', 'solo_visible_only_v1'), default='off')
    p.add_argument('--held-object-hidden-v1', action='store_true')
    p.add_argument('--setdown-lookaround-v1', action='store_true')
    p.add_argument('--teacher-stability', choices=('off', 'align_relook_v1'), default='off')
    p.add_argument('--reach-mode', choices=('box_station_v1', 'pad_window_v2'), default='box_station_v1')
    p.add_argument('--rgb-lift-mode', choices=('off', 'solo_rgb_lift_v2', 'solo_rgb_lift_v3', 'solo_lift_lookback_v1'), default='off')
    p.add_argument('--solo-lift-negative-probe-v1', action='store_true',
                   help='diagnostic only: open before lifting; forbidden in gates and training')
    p.add_argument('--solo-lift-lookback-margin-v1', action='store_true',
                   help='box-only static retreat margin (150 mm); RGB judgment unchanged')
    p.add_argument('--cap-s', type=float, default=90.)
    p.add_argument('--training-rgb', action='store_true')
    p.add_argument('--solo-carry-to-zone-v1', action='store_true', help='diagnostic only, default off')
    p.add_argument('--solo-truth-free-lookaround-v1', action='store_true',
                   help='pose-free fixed own-RGB sweep; required for training, default OFF')
    p.add_argument('--failure-rgb-buffer', action='store_true', help='record-only 10Hz last 10 SIM seconds')
    p.add_argument('--recording-stage', choices=('pilot', 'batch'), default='pilot')
    p.add_argument('--recording-approval', type=Path)
    a = p.parse_args()
    plan = json.loads(a.plan.read_text())['episodes'][a.episode]
    print(json.dumps(run(plan, a.out, execution_host=a.execution_host, profile=a.teacher_profile,
              hidden=a.held_object_hidden_v1, look=a.setdown_lookaround_v1, cap_s=a.cap_s,
              teacher_stability=a.teacher_stability, reach_mode=a.reach_mode,
              rgb_lift_mode=a.rgb_lift_mode,
              solo_lift_negative_probe_v1=a.solo_lift_negative_probe_v1,
              solo_lift_lookback_margin_v1=a.solo_lift_lookback_margin_v1,
              training_rgb=a.training_rgb, solo_truth_free_lookaround_v1=a.solo_truth_free_lookaround_v1,
              recording_stage=a.recording_stage, recording_approval=a.recording_approval,
              failure_rgb_buffer=a.failure_rgb_buffer,
              solo_carry_to_zone_v1=a.solo_carry_to_zone_v1)))


if __name__ == '__main__':
    main()
