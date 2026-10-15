"""warp1 lockstep episode adapter, derived from the frozen ACT11 solo runner.

Upstream teacher source: 6f057f7e97c1a3aec9e8c398b8d9068e27b25df8.
Only scheduling, host admission, RGB provider and evaluator contact provider
change. Teacher decisions/IK/visibility/route/Score remain frozen and scalar.
This transitional adapter does NOT claim a vectorized teacher or record/train
admission. C path files are untouched. All simulation is Linux gcp2-only.
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


def episode(plan, out, *, hooks, world_index, execution_host, profile='off', hidden=False, look=False, cap_s=90.,
        teacher_stability='off', reach_mode='box_station_v1', rgb_lift_mode='off',
        solo_lift_negative_probe_v1=False, solo_lift_lookback_margin_v1=False,
        training_rgb=False, solo_truth_free_lookaround_v1=False,
        recording_stage='pilot', recording_approval=None):
    if platform.system() != 'Linux' or execution_host != 'gcp2':
        raise RuntimeError('Linux gcp2 only; Mac physics/render disabled')
    if training_rgb:
        raise ValueError('warp1 HOLD_SCENE: training recording requires a new MJWarp gate and adapter admission')
    if not 0 < cap_s <= 180 or profile != 'solo_visible_only_v1' or not hidden or not look:
        raise ValueError('finite opt-in solo profile with both required toggles')
    if teacher_stability not in ('off', 'align_relook_v1') or reach_mode not in ('box_station_v1', 'pad_window_v2'):
        raise ValueError('unknown solo stability/reach mode')
    if rgb_lift_mode not in ('off', 'solo_rgb_lift_v2', 'solo_rgb_lift_v3', 'solo_lift_lookback_v1'):
        raise ValueError('unknown solo RGB lift mode')
    from harness.grasp_act_solo_recording import validate_recording, camera_config, SoloRecorder, validate_approval
    validate_recording(plan, training_rgb=training_rgb, truth_free_v1=solo_truth_free_lookaround_v1,
        negative=solo_lift_negative_probe_v1, stability=teacher_stability, reach=reach_mode,
        lift=rgb_lift_mode, margin=solo_lift_lookback_margin_v1)
    from scripts.grasp_act_host import require_run_root
    host = hooks.host
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

    sha = hooks.source_sha
    approval = validate_approval(recording_approval, stage=recording_stage, sha=sha, host=host) if training_rgb else None
    out.mkdir(parents=True, exist_ok=False)
    write(out/'plan.json', plan)
    write(out/'RUN_META.json', {'class': 'dev', 'branch': 'claude/warp-act', 'physics_backend': hooks.backend,
          'sha': sha, 'pr': plan.get('pr'), 'batch': plan['batch'],
          'negative_probe': bool(solo_lift_negative_probe_v1)})
    report = {'status': 'running', 'source_sha': sha, 'execution_host': host,
              'student_execution': False, 'physics_backend': hooks.backend,
              'batch_world': world_index, 'training_recording_supported': False,
              'recording_mode': 'training' if training_rgb else 'negative_probe_diagnostic' if solo_lift_negative_probe_v1 else 'success_measurement',
              'object_kind': plan['kind'], 'weld': 'off', 'training_rgb': bool(training_rgb),
              'recording_stage': recording_stage if training_rgb else None,
              'recording_approval': approval,
              'solo_truth_free_lookaround_v1': bool(solo_truth_free_lookaround_v1),
              'teacher_stability': teacher_stability, 'reach_mode': reach_mode,
              'rgb_lift_mode': rgb_lift_mode,
              'negative_probe': bool(solo_lift_negative_probe_v1),
              'solo_lift_lookback_margin_v1': bool(solo_lift_lookback_margin_v1),
              'gate_eligible': False,  # unapproved warp1 pilot, not a teacher gate
              'physical_success': None, 'placement_task': 'set down at own picked location',
              'plan_sha256': hashlib.sha256((out/'plan.json').read_bytes()).hexdigest()}
    if training_rgb:
        report.update(training_include=False, training_candidate=False, data_admitted=False,
                      training_exclusion_reason='not complete / awaiting qualification and dataset admission')
    write(out/'result.json', report)
    from collections import deque
    recent = deque(maxlen=100)  # recording-only 10 SIM s at the existing 10 Hz
    world, streams, recorder = None, [], None
    if training_rgb:
        (out/'teacher-raw').mkdir()
        (out/'evaluation').mkdir()
    start = time.monotonic()
    audit, visibility_stats, score = InputAudit(), VisibilityStats(), Score()
    ops = primitives()
    try:
        # Scene hardware/camera/physics are exactly the existing pair setup.
        scene = make_scene({**plan, 'end_color_scene': 'off'})
        scene.config['setup_only']['spawns'].update(plan['spawns'])
        os.environ['UGRP_SIM_OBSERVER_WIDTH'] = '320'
        os.environ['UGRP_SIM_OBSERVER_HEIGHT'] = '240'
        sampling = camera_config() if training_rgb else {'width': 640, 'height': 480}
        world,scene = hooks.make_world(plan,scene,build_world,bind_camera,drive_profile=PROFILE, seed=plan['seed'], width=sampling['width'],
                            height=sampling['height'], render=hooks.native_render, warehouse_layout=scene.engine_layout,
                            warehouse_cargo_ids=None, roller_collision='mesh', idle_robot_contacts='off')
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
        # Legacy look-around used live truth + frozen error as a map estimate.
        # The recording toggle replaces that path with a pose-free own-RGB scan.
        relook = SoloLookaround(static, ops=ops, truth_free_v1=solo_truth_free_lookaround_v1)
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
        disc_names, rect_names, route_rejections = [], [], []
        route_counts = {'entered': 0, 'passed': 0, 'rejected': 0}
        input_funnel = {'frames': 0, 'not_held': 0, 'visible_not_held': 0, 'measurements': 0}

        def route(goal, context):
            # Current visible wall measurements remain in the body frame;
            # an uncertain map prior cannot fabricate a registered self pose.
            route_counts['entered'] += 1
            path = plan_path((0., 0.), goal[:2], (-2., 2., -2., 2.), observed_discs,
                             rects=observed_rects, radius=.17)
            if not path:
                from harness.static_keepouts import rect_distance
                route_counts['rejected'] += 1
                gaps = [(math.hypot(goal[0]-x,goal[1]-y)-r-.17,n)
                        for (x,y,r),n in zip(observed_discs,disc_names)]
                gaps += [(rect_distance(goal[:2],rect)-.17,n) for rect,n in zip(observed_rects,rect_names)]
                gap,name = min(gaps) if gaps else (None,'none_observed')
                route_rejections.append({'t': float(data.time), 'category': 'no_visible_route',
                    'reason': 'frozen A* returned no path within its existing40000-node budget',
                    'blocking_object': name, 'minimum_gap_m': gap,
                    'minimum_gap_scope': 'nearest currently visible object at requested goal; not unique blocker attribution',
                    'goal_relative': list(goal), 'search_budget_nodes': 40000})
                return 0., 0., 0.
            route_counts['passed'] += 1
            point = next((p for p in path if math.hypot(*p) >= .06), goal[:2])
            cmd = proportional_drive((0., 0., 0.), goal[:2], point, goal[2])
            return cmd['forward'], cmd['left'], cmd['turn']

        teacher = SoloTeacher(plan['kind'], plan['role'], pwm, profile=profile,
                              held_object_hidden_v1=hidden, setdown_lookaround_v1=look,
                              lookaround=relook, route=route, ops=ops,
                              teacher_stability=teacher_stability, reach_mode=reach_mode,
                              rgb_lift_mode=rgb_lift_mode,
                              solo_lift_negative_probe_v1=solo_lift_negative_probe_v1,
                              solo_lift_lookback_margin_v1=solo_lift_lookback_margin_v1)
        if rgb_lift_mode == 'solo_lift_lookback_v1':
            from sim.grasp_act_solo_lookback import LookbackObserver
            lift_observer = LookbackObserver(plan['kind'])
        else:
            lift_observer = SoloLiftObserver(plan['kind'], mode=rgb_lift_mode) if rgb_lift_mode != 'off' else None
        if lift_observer is not None:
            (out/'lift-rgb').mkdir()

        def save_lift(tag, frame, now):
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
            observed_discs.clear(); disc_names.clear()
            base = world.robot(rid).base_xyz()
            a = float(world.robot(rid).base_rpy()[2]); c, s = math.cos(a), math.sin(a)
            for other in ('r1', 'r2', 'r3'):
                if other == rid:
                    continue
                obid = model.body(other+'__robot').id
                n, total = eyes.region_visible(data, rid, eyes._body_geoms(obid))
                if total and n >= math.ceil(total/3):
                    xy = data.body(other+'__robot').xpos[:2]-base[:2]
                    observed_discs.append((c*xy[0]+s*xy[1], -s*xy[0]+c*xy[1], .17)); disc_names.append(other+'__robot')
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
                    observed_discs.append((c*xy[0]+s*xy[1], -s*xy[0]+c*xy[1], radius)); disc_names.append(name)
            observed_rects.clear(); rect_names.clear()
            for g in range(model.ngeom):
                if 'wall' not in (model.geom(g).name or ''):
                    continue
                n, total = eyes.region_visible(data, rid, [g])
                if total and n >= math.ceil(total/3):
                    xy = data.geom_xpos[g, :2]-base[:2]
                    rot = data.geom_xmat[g].reshape(3, 3)
                    observed_rects.append((c*xy[0]+s*xy[1], -s*xy[0]+c*xy[1],
                        *map(float, model.geom_size[g, :2]), wrap(math.atan2(rot[1, 0], rot[0, 0])-a)))
                    rect_names.append(model.geom(g).name)

        previous = teacher._hold(float(data.time))
        trace = (out/('teacher-raw/commands.jsonl' if training_rgb else 'teacher-commands.jsonl')).open('x'); streams.append(trace)
        ev = (out/('evaluation/eval-only.jsonl' if training_rgb else 'eval-only.jsonl')).open('x'); streams.append(ev)
        if training_rgb:
            recorder = SoloRecorder(out, plan, previous)
        (out/'review-own').mkdir()
        (out/'review-top').mkdir()
        origin = float(data.time)
        finished_t = None
        negative_eval = {'N': 0, 'max_clearance_m': 0., 'max_pickup_offset_m': 0.}
        tick = 0
        yield {'kind': 'setup', 'world': world, 'port': port, 'gids': gids,
               'finger_ids': finger_ids, 'body_name': body_name, 'origin': origin}
        while float(data.time)-origin < cap_s-1e-8:
            if (out/'SUPERVISOR_STOP.json').exists():
                raise KeyboardInterrupt('supervisor stopped this run')
            now = float(data.time)
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

            input_funnel['frames'] += 1
            input_funnel['not_held'] += int(not teacher.holding)
            input_funnel['visible_not_held'] += int(not teacher.holding and visible)
            measurement = audit.measure(teacher.phase, visible_n=visible_n, probe_N=probe_N,
                                        holding=teacher.holding, read_relative=read_relative)
            input_funnel['measurements'] += int(measurement is not None)
            # Capture once: recording persists exactly these controller bytes.
            jpg = hooks.capture(world_index, world)
            recent.append((tick, jpg))
            hooks.record_state(world_index, tick, world)
            bgr = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
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
                    relook.arm()  # no setup pose, live truth or fabricated map estimate
                    look_eval['armed_t'] = now
                else:
                    # Preserved legacy comparison ONLY; forbidden for recording.
                    g = truth_pose(); pose_error = plan['handoff_pose_error']
                    relook.arm([g[0]+pose_error[0], g[1]+pose_error[1], g[2]+pose_error[2]])
                    look_eval['before'] = look_truth(); look_eval['armed_t'] = now
            if tick % 5 == 0:
                # Currently visible obstacles only (same one-third gate as the target),
                # refreshed at 2 Hz: it feeds the route planner, never a pose or a label.
                refresh_obstacles()
            phase_before = teacher.phase
            value, complete = teacher.step(now, measurement=measurement,
                        rgb_holding=rgb_result.get('answer', 'unknown'),
                        own_rgb=lambda: cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
            if recorder is not None:
                recorder.target(value, skill_after=teacher.skill, phase_after=teacher.phase, complete=complete)
            views = [e for e in relook.events if e['event'] == 'view']
            if len(views) > look_state['last_view_n']:
                # A view was captured this tick: score the updated estimate against truth (eval only).
                row = {'t': now, **views[-1], **(look_truth() if relook.loc is not None else {})}
                look_eval['views'].append(row)
                ev.write(json.dumps({'kind': 'lookaround_view', **row})+'\n')
                look_state['last_view_n'] = len(views)
            if complete and relook.loc is not None and 'after' not in look_eval:
                look_eval['after'] = look_truth(); look_eval['sim_s'] = now-look_eval['armed_t']
            apply(port, value, now, previous)
            if rgb_lift_mode == 'solo_lift_lookback_v1':
                if phase_before in ('align', 'approach') and teacher.phase == 'hover':
                    # Before hover/descent/close: the last visible pickup frame.
                    # Its camera pose is the PREVIOUS issued command, not the
                    # newly queued arm target and never teacher.grasp_xyz.
                    lift_observer.start(bgr, {**previous, 't': now}, save_lift)
                lift_observer.issue(value, teacher.phase)
            elif lift_observer is not None and phase_before == 'close' and teacher.phase == 'lift':
                # This frame was captured BEFORE issuing the raise. Commands
                # are the teacher's own outputs, not servo measurements.
                lift_observer.start(bgr, value, save_lift)
            previous = value
            trace.write(json.dumps({'t': now, 'phase': teacher.phase, 'command': value,
                                   'visible_target': measurement,
                'student_context': teacher.context(now), 'rgb_confirmation': rgb_result})+'\n')

            # Full truth owner, written only to eval-only.jsonl / Score.
            body = data.body(body_name); rot = body.xmat.reshape(3, 3)
            min_z = min(bottom_z('cylinder' if model.geom_type[g] == mujoco.mjtGeom.mjGEOM_CYLINDER else 'box',
                                data.geom_xpos[g], data.geom_xmat[g].reshape(3, 3), model.geom_size[g]) for g in gids)
            forces = hooks.forces(world_index, model, data, target_set, finger_ids)
            pos = body.xpos.copy()
            base = world.robot(rid).base_xyz()      # evaluation-only record, never read by the teacher
            speed = 0. if last_eval_t is None else float(np.linalg.norm(pos-last_eval_pos)/(now-last_eval_t))
            tilt = math.degrees(math.acos(float(np.clip(rot[2, 2], -1., 1.))))
            row = {'min_z': min_z, 'support_z': 0., 'tilt_deg': tilt, 'finger_forces': forces,
                'speed': speed, 'open_issued': value['pwm']['1'] >= 1900,
                'placement_offset': float(np.linalg.norm(pos[:2]-initial_xy)), 'weld_active': False,
                'negative_probe': bool(solo_lift_negative_probe_v1)}
            score.add(now, **{k: v for k, v in row.items() if k != 'negative_probe'})
            if solo_lift_negative_probe_v1 and rgb_result.get('evidence') == 'solo_lift_lookback_v1':
                negative_eval['N'] += 1
                negative_eval['max_clearance_m'] = max(negative_eval['max_clearance_m'], min_z)
                negative_eval['max_pickup_offset_m'] = max(negative_eval['max_pickup_offset_m'], row['placement_offset'])
            ev.write(json.dumps({'t': now, **row, 'cargo_xyz': pos.tolist(),
                     'base_xyz': list(map(float, base)), 'visible_n': visible_n, 'probe_N': probe_N,
                     'lookaround_estimate_xy': list(map(float, relook.loc.own.x[:2])) if relook.loc is not None else None})+'\n')
            last_eval_pos, last_eval_t = pos, now
            if tick % 5 == 0:  # recording-only 2 Hz full timeline, 10 Hz terminal ring
                cv2.imwrite(str(out/'review-own'/f'{tick:06d}.jpg'), cv2.resize(bgr, (320, 240)))
                # Overview is reconstructed on gcp2 from recorded states; never a control input.
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
            yield {'kind': 'step', 'world': world, 'port': port, 'command': value}
        report.update(status='cap_end' if teacher.result is None else 'complete',
            cap_end=teacher.result is None, sim_s=float(data.time)-origin, wall_s=time.monotonic()-start,
            teacher=teacher.diagnostic(), input_audit=audit.record(), visibility=visibility_stats.record(),
            lookaround={'localizer': relook.record(), 'evaluation': look_eval},
            lift_rgb_evidence_ticks=lift_evidence, **score.record(teacher.result == 'command_complete'))
        if lift_observer is not None:
            report[rgb_lift_mode.removeprefix('solo_')] = lift_observer.record()
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
    except GeneratorExit:
        report.update(status='setup_export_only' if not recent else 'supervisor_stop',
                      physical_success=None, gate_eligible=False)
        raise
    except BaseException as error:
        report.update(status='interrupted' if isinstance(error, KeyboardInterrupt) else 'HOST_ERROR',
                      error_type=type(error).__name__, error=str(error), wall_s=time.monotonic()-start,
                      input_audit=audit.record(), visibility=visibility_stats.record())
        write(out/'result.json', report)
        raise
    finally:
        # Flush the same input/rejection counters on setup errors and supervision,
        # before closing/compressing traces. Completion is a separate status.
        report.update(input_audit=audit.record(),visibility=visibility_stats.record())
        if 'input_funnel' in locals():
            write(out/'input-funnel.json', {'counts':input_funnel,
                'raw':str(out/('teacher-raw/commands.jsonl.zst' if training_rgb else 'teacher-commands.jsonl.zst')),
                'scope':'frames→not-held→currently-visible→lazy relative measurement',
                'run_status':report.get('status')})
            write(out/'route-rejections.json', {'counts':route_counts,'rows':route_rejections,
                'run_status':report.get('status'),
                'budget_basis':'frozen scripts.zone_teacher.plan_path default40000 nodes; no wall-clock planning cap'})
        folder = out/'failure-rgb-buffer'
        folder.mkdir(exist_ok=True)
        for index, jpg in recent:
            (folder/f'{index:06d}.jpg').write_bytes(jpg)
        report['failure_rgb_buffer'] = {'hz': 10, 'max_sim_s': 10, 'frames': len(recent),
            'bytes': sum(p.stat().st_size for p in folder.iterdir()), 'recording_only': True}
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
        write(out/'result.json', report)
        compress_logs(out)
    return report

