"""Finite, opt-in single-cargo pick / hold / set-down diagnostic on gcp1.

Measurement only: no training RGB, no LLM, no transport / delivery claim.
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
        teacher_stability='off', reach_mode='box_station_v1', rgb_lift_mode='off'):
    if platform.system() != 'Linux' or execution_host != 'gcp1':
        raise RuntimeError('Linux gcp1 only; Mac physics/render disabled')
    if not 0 < cap_s <= 180 or profile != 'solo_visible_only_v1' or not hidden or not look:
        raise ValueError('finite opt-in solo profile with both required toggles')
    if teacher_stability not in ('off', 'align_relook_v1') or reach_mode not in ('box_station_v1', 'pad_window_v2'):
        raise ValueError('unknown solo stability/reach mode')
    if rgb_lift_mode not in ('off', 'solo_rgb_lift_v2', 'solo_rgb_lift_v3', 'solo_lift_lookback_v1'):
        raise ValueError('unknown solo RGB lift mode')
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
    out.mkdir(parents=True, exist_ok=False)
    write(out/'plan.json', plan)
    write(out/'RUN_META.json', {'class': 'dev', 'branch': 'claude/act-solo-teacher',
          'sha': sha, 'pr': plan.get('pr'), 'batch': plan['batch']})
    report = {'status': 'running', 'source_sha': sha, 'execution_host': host,
              'student_execution': False, 'recording_mode': 'success_measurement',
              'object_kind': plan['kind'], 'weld': 'off', 'training_rgb': False,
              'teacher_stability': teacher_stability, 'reach_mode': reach_mode,
              'rgb_lift_mode': rgb_lift_mode,
              'physical_success': None, 'placement_task': 'set down at own picked location',
              'plan_sha256': hashlib.sha256((out/'plan.json').read_bytes()).hexdigest()}
    write(out/'result.json', report)
    world, streams = None, []
    start = time.monotonic()
    audit, visibility_stats, score = InputAudit(), VisibilityStats(), Score()
    ops = primitives()
    try:
        # Scene hardware/camera/physics are exactly the existing pair setup.
        scene = make_scene({**plan, 'end_color_scene': 'off'})
        scene.config['setup_only']['spawns'].update(plan['spawns'])
        os.environ['UGRP_SIM_OBSERVER_WIDTH'] = '320'
        os.environ['UGRP_SIM_OBSERVER_HEIGHT'] = '240'
        world = build_world(scene, drive_profile=PROFILE, seed=plan['seed'], width=640,
                            height=480, render=True, warehouse_layout=scene.engine_layout,
                            warehouse_cargo_ids=None, roller_collision='mesh', idle_robot_contacts='off')
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
        # The map code's own-pose estimate error (frozen per episode, sigma 5 cm /
        # 2 deg, plan['handoff_pose_error']); the estimate is built here, by the
        # scene owner, when the set-down skill starts. The teacher never sees it.
        pose_error = plan['handoff_pose_error']
        relook = SoloLookaround(static, ops=ops)
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
            path = plan_path((0., 0.), goal[:2], (-2., 2., -2., 2.), observed_discs,
                             rects=observed_rects, radius=.17)
            if not path:
                return 0., 0., 0.
            point = next((p for p in path if math.hypot(*p) >= .06), goal[:2])
            cmd = proportional_drive((0., 0., 0.), goal[:2], point, goal[2])
            return cmd['forward'], cmd['left'], cmd['turn']

        teacher = SoloTeacher(plan['kind'], plan['role'], pwm, profile=profile,
                              held_object_hidden_v1=hidden, setdown_lookaround_v1=look,
                              lookaround=relook, route=route, ops=ops,
                              teacher_stability=teacher_stability, reach_mode=reach_mode,
                              rgb_lift_mode=rgb_lift_mode)
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
        trace = (out/'teacher-commands.jsonl').open('x'); streams.append(trace)
        ev = (out/'eval-only.jsonl').open('x'); streams.append(ev)
        (out/'review-own').mkdir()
        (out/'review-top').mkdir()
        origin = float(data.time)
        finished_t = None
        tick = 0
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

            measurement = audit.measure(teacher.phase, visible_n=visible_n, probe_N=probe_N,
                                        holding=teacher.holding, read_relative=read_relative)
            # Capture exact own-camera resolution transiently for control. Only
            # review frames at 1 Hz are persisted; they are never training input.
            jpg = base64.b64decode(port.capture()['image'])
            bgr = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
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
                # Set-down skill begins: hand the look-around the map code's pose estimate.
                g = truth_pose()
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
            views = [e for e in relook.events if e['event'] == 'view']
            if len(views) > look_state['last_view_n']:
                # A view was captured this tick: score the updated estimate against truth (eval only).
                row = {'t': now, **views[-1], **look_truth()}
                look_eval['views'].append(row)
                ev.write(json.dumps({'kind': 'lookaround_view', **row})+'\n')
                look_state['last_view_n'] = len(views)
            if complete and relook.armed and 'after' not in look_eval:
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
            forces = [0., 0.]; f = np.zeros(6)
            for i in range(data.ncon):
                g1, g2 = int(data.contact[i].geom1), int(data.contact[i].geom2)
                finger = g1 if g2 in target_set else g2 if g1 in target_set else None
                if finger in finger_ids:
                    mujoco.mj_contactForce(model, data, i, f)
                    forces[finger_ids[finger]] += abs(float(f[0]))
            pos = body.xpos.copy()
            base = world.robot(rid).base_xyz()      # evaluation-only record, never read by the teacher
            speed = 0. if last_eval_t is None else float(np.linalg.norm(pos-last_eval_pos)/(now-last_eval_t))
            tilt = math.degrees(math.acos(float(np.clip(rot[2, 2], -1., 1.))))
            row = {'min_z': min_z, 'support_z': 0., 'tilt_deg': tilt, 'finger_forces': forces,
                'speed': speed, 'open_issued': value['pwm']['1'] >= 1900,
                'placement_offset': float(np.linalg.norm(pos[:2]-initial_xy)), 'weld_active': False}
            score.add(now, **row)
            ev.write(json.dumps({'t': now, **row, 'cargo_xyz': pos.tolist(),
                     'base_xyz': list(map(float, base)), 'visible_n': visible_n, 'probe_N': probe_N,
                     'lookaround_estimate_xy': list(map(float, relook.loc.own.x[:2])) if relook.armed else None})+'\n')
            last_eval_pos, last_eval_t = pos, now
            if tick % 10 == 0:
                cv2.imwrite(str(out/'review-own'/f'{tick:06d}.jpg'), cv2.resize(bgr, (320, 240)))
                (out/'review-top'/f'{tick:06d}.jpg').write_bytes(world.render_team_jpeg(camera=static['top_cameras'][0]['name']))
                write(out/'progress.json', {'sim_s': now-origin, 'phase': teacher.phase, 'source_sha': sha})
                for stream in streams:
                    stream.flush()
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
        report['data_admitted'] = False
        write(out/'result.json', report)
    except BaseException as error:
        report.update(status='interrupted' if isinstance(error, KeyboardInterrupt) else 'HOST_ERROR',
                      error_type=type(error).__name__, error=str(error), wall_s=time.monotonic()-start,
                      input_audit=audit.record(), visibility=visibility_stats.record())
        write(out/'result.json', report)
        raise
    finally:
        for stream in streams:
            stream.close()
        if world is not None:
            world.close()
        compress_logs(out)
    return report


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
    p.add_argument('--cap-s', type=float, default=90.)
    a = p.parse_args()
    plan = json.loads(a.plan.read_text())['episodes'][a.episode]
    print(json.dumps(run(plan, a.out, execution_host=a.execution_host, profile=a.teacher_profile,
              hidden=a.held_object_hidden_v1, look=a.setdown_lookaround_v1, cap_s=a.cap_s,
              teacher_stability=a.teacher_stability, reach_mode=a.reach_mode,
              rgb_lift_mode=a.rgb_lift_mode)))


if __name__ == '__main__':
    main()
