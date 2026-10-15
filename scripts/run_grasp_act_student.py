"""GCP-only staged solo student evaluation. No teacher/IK/GT policy correction.

This is a component probe, not navigation or E2E completion. The setup
owner reads static initial poses; the isolated worker sees only the v6 contract.
Evaluation truth is written after action selection and cannot change commands.
"""
from __future__ import annotations
import argparse
import base64
import json
import math
from pathlib import Path
import selectors
import subprocess
import time

import sys

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness import grasp_act_contract as c
from harness.grasp_act_data import sha256, write_json, write_summary
from harness.grasp_act_policy import ChunkExecutor
from harness.grasp_act_rollout import OwnHistory, SoloSequence, SoloScore, InputAudit
from scripts.grasp_act_training_guard import ROOT, require_gcp, source_sha


def validate_plan(plan, protocol, *, teacher_start_v1=False):
    if (plan['seed'] not in protocol['closed_loop_seeds'] or plan['skill'] not in ('grasp', 'grasp_release')
            or plan['object_kind'] not in ('cyan', 'red', 'green', 'yellow')
            or plan['role'] != 'west' or plan['robot_id'] not in ('r1', 'r2', 'r3')):
        raise ValueError('pilot supports registered fresh-seed solo boxes only')
    if set(protocol['closed_loop_seeds']) & set(protocol['train_seeds'] + protocol['validation_seeds']):
        raise ValueError('closed-loop seed leak')
    distance = math.dist(plan['spawns'][plan['robot_id']][:2], plan['target_setup_xy'])
    # ACT14 reuses the frozen 6f057f7e make_solo_teacher_plan.START_RANGE_M;
    # this is setup parity, not a new acceptance tolerance. Legacy stays default.
    low, high = (.6, 1.1) if teacher_start_v1 else (.4, .8)
    if not low <= distance <= high:
        raise ValueError('staged near-field initial distance must be 0.4..0.8 m')


def response(process, timeout=120.):
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        if not selector.select(timeout):
            raise TimeoutError('student inference timeout')
    line = process.stdout.readline()
    if not line:
        raise RuntimeError('student worker exited')
    return json.loads(line)


def run(plan, protocol, model, output, *, actor_python, cap_s=60., n_action_steps=c.CHUNK,
        temporal_ensemble_coeff=None, actor_threads=1, teacher_start_v1=False):
    if actor_threads not in (1, 2, 4, 8, 16):
        raise ValueError('bounded actor thread setting required')
    ChunkExecutor(None, n_action_steps=n_action_steps, temporal_ensemble_coeff=temporal_ensemble_coeff)
    if not 0 < cap_s <= 90.:
        raise ValueError('finite <=90 SIM seconds required')
    host, source = require_gcp(training=False), source_sha()
    validate_plan(plan, protocol, teacher_start_v1=teacher_start_v1)
    with_release = plan['skill'] == 'grasp_release'
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'running', 'complete': False, 'host': host, 'source_sha': source,
        'seed': plan['seed'], 'model_sha256': sha256(model / 'model.safetensors'),
        'student_execution': True, 'teacher_assisted': False, 'weld': 'off',
        'teacher_start_v1': teacher_start_v1,
        'scope': 'staged solo grasp/lift/setdown at pickup_site; no navigation/E2E claim' if with_release
                 else 'staged near-field solo grasp; no navigation/release/E2E claim',
        'object_kind': plan['object_kind'], 'requested_sequence': plan['skill'],
        'input_audit': {'forbidden_input_fields': 0, 'teacher_input_fields': 0, 'requests': 0},
        'execution': {'actor_threads': actor_threads, 'chunk_size': c.CHUNK, 'n_action_steps': n_action_steps,
                      'temporal_ensemble_coeff': temporal_ensemble_coeff,
                      'ensemble_mode': 'off' if temporal_ensemble_coeff is None else
                          'dense_v1' if n_action_steps == 1 else 'strided_v1'},
        'completion_confirmation': 'unknown', 'gate_promotion_authorized_if_all_conditions_pass': False}
    write_summary(output / 'summary.json', report)
    write_json(output / 'plan.json', plan)
    write_json(output / 'RUN_META.json', {'class': 'dev', 'sha': source})
    world = worker = port = prediction_log = None
    begin = time.monotonic()
    try:
        import numpy as np
        import mujoco
        from sim.zone_scenario_scene import ScenarioFinalV3Scene
        from sim.render_profile import install
        from sim.final_pair_highpose_nearclip import wrap
        from sim import masterpi_camera_review_v3 as camera
        from sim.s2_servo_stiffness import transform_xml as stiffness
        from sim.s2_realism_camera_binding import bind_camera
        from sim.masterpi_drive_friction_v7 import build_world, PROFILE
        from sim.camera_robot_port import CameraRobotPort
        # Compose existing main Scene hooks, with the same solo recording
        # hardware/camera/render/stiffness settings. No teacher branch imports.
        scene = wrap(install(ScenarioFinalV3Scene.from_scenario(plan['scenario_id'], plan['seed']), 'floor_light_v1'))
        scene.config['setup_only']['spawns'] = plan['spawns']
        obj = scene.config['setup_only']['objects'][plan['item_id']]
        if obj['kind'] != plan['object_kind'] or obj['position_m'][:2] != plan['target_setup_xy']:
            raise ValueError('static task object mismatch')
        original = scene.robot_transform
        def transform(xml, **kwargs):
            xml = camera.transform_xml(original(xml, **kwargs), profile_id=camera.PROFILE_ID)
            for rid in ('r1', 'r2', 'r3'):
                xml = stiffness(xml, servo_stiffness='real_v1', robot_id=rid)
            return xml
        scene.robot_transform = transform
        world = build_world(scene, drive_profile=PROFILE, seed=plan['seed'], width=640, height=480,
            render=True, warehouse_layout=scene.engine_layout, warehouse_cargo_ids=None,
            roller_collision='mesh', idle_robot_contacts='off')
        for controller in world.controllers.values():
            bind_camera(controller)
        scene.setup(world)
        (output / 'scene.xml').write_text(world.scene_xml)
        write_json(output / 'scene.json', scene.manifest)
        rid = plan['robot_id']
        port = CameraRobotPort(world, rid)
        # Own issued initial PWM, never measured qpos. Same fixed camera/arm fold
        # commands as the observed recording's initialization.
        previous = {'t': float(world.data.time), 'wheels': [0.] * 4, 'duration_s': [0.] * 4,
                    'pwm': ({str(s): int(port._servo_pulses[s]) for s in c.SERVOS} if teacher_start_v1 else
                            {'1': 2000, '3': 740, '4': 2320, '5': 1320, '6': 1500})}
        if not teacher_start_v1:
            for s in c.SERVOS:
                port.apply({'kind': 'look', 'pan_pulse': previous['pwm'][str(s)]} if s == 6 else
                           {'kind': 'arm', 'servo_id': s, 'pulse': previous['pwm'][str(s)]}, previous['t'])
            settle = float(world.data.time) + 1.
            while float(world.data.time) < settle - 1e-8:
                port.tick(float(world.data.time))
                world._physics_step_for(world.robot(rid))
        previous['t'] = float(world.data.time)
        write_json(output / 'initial-issued.json', previous)
        cid = world.controllers[rid].robot_cam_cid
        write_json(output / 'camera-runtime.json', {k: getattr(world.model, 'cam_'+k)[cid].tolist()
                   for k in ('pos', 'quat', 'intrinsic', 'resolution')})
        history = OwnHistory(rid, f'student-{plan["seed"]}', previous)
        (output / 'rgb' / rid).mkdir(parents=True)
        worker = subprocess.Popen([actor_python, '-m', 'scripts.grasp_act_student_worker', '--model', str(model), '--threads', str(actor_threads)],
            cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        if response(worker) != {'ready': True}:
            raise RuntimeError('student worker did not load')
        latencies = []
        prediction_log = (output / 'chunk-predictions.jsonl').open('x')
        audit = InputAudit()
        report['input_audit'] = audit.record
        def predict(observation, jpegs):
            audit.accept(observation)
            request = {'observation': observation, 'jpegs': [base64.b64encode(x).decode() for x in jpegs]}
            start = time.monotonic()
            worker.stdin.write(json.dumps(request, allow_nan=False) + '\n')
            worker.stdin.flush()
            result = response(worker)
            latencies.append(time.monotonic() - start)
            if set(result) != {'chunk'}:
                raise ValueError('student response whitelist mismatch')
            prediction_log.write(json.dumps({'sample_id': observation['sample_id'], 't': observation['t'],
                'chunk': result['chunk']}, allow_nan=False) + '\n')
            prediction_log.flush()
            return result['chunk']
        executor = ChunkExecutor(predict, n_action_steps=n_action_steps, temporal_ensemble_coeff=temporal_ensemble_coeff)
        score = SoloScore()
        # Evaluation-only funnel. Existing frozen teacher boundaries: approach
        # .08m, box alignment .008m/.04rad (6f057f7e SoloTeacher._seek/Cargo).
        # Finger load/lift use the unchanged LiftScore criteria. None feed policy.
        funnel = {'frames': 0, 'valid_inputs': 0, 'actions': 0, 'approach': 0,
                  'alignment': 0, 'grasp': 0, 'lift_confirmation': 0}
        first_pass = {}
        sequence = SoloSequence(with_release)
        # Evaluation-only private handles; these never leave the simulation owner.
        body = world.model.body(obj['body_name']).id
        gids = [g for g in range(world.model.ngeom) if world.model.geom_bodyid[g] == body and world.model.geom_contype[g]]
        fingers = {world.model.geom(rid + '__' + side + '_finger').id: i for i, side in enumerate(('left', 'right'))}
        origin, tick = float(world.data.time), 0
        with (output / 'student-inputs.jsonl').open('x') as inputs, (output / 'commands.jsonl').open('x') as commands, (output / 'eval-only.jsonl').open('x') as evaluations:
            while float(world.data.time) - origin < cap_s - 1e-8:
                if (output / 'SUPERVISOR_STOP.json').exists():
                    raise KeyboardInterrupt('supervisor stop')
                if time.monotonic() - begin > 1800:
                    raise TimeoutError('rollout wall cap')
                now = float(world.data.time)
                jpeg = base64.b64decode(port.capture()['image'])
                obs, jpegs, rel = history.observe(now, jpeg, skill=sequence.skill,
                    object_kind=plan['object_kind'], role=plan['role'],
                    destination_zone='pickup_site' if sequence.skill == 'release' else 'none')
                (output / rel).write_bytes(jpeg)
                c.validate_observation(obs)
                funnel['frames'] += 1
                funnel['valid_inputs'] += 1
                inputs.write(json.dumps(obs) + '\n')
                value, done = executor.step(obs, jpegs)
                funnel['actions'] += 1
                commands.write(json.dumps({'command': value, 'skill': obs['skill'], 'done_requested': done}) + '\n')
                # Match recording's independent normalized wheel pulses exactly.
                port._command_expires_at = port._drive_expires_at = None
                port._set_motors(tuple(value['wheels']))
                deadlines = [now + d for d in value['duration_s']]
                for s in c.SERVOS:
                    pwm = value['pwm'][str(s)]
                    if pwm != previous['pwm'][str(s)]:
                        port.apply({'kind': 'look', 'pan_pulse': pwm} if s == 6 else
                                   {'kind': 'arm', 'servo_id': s, 'pulse': pwm}, now)
                history.issue(value)
                previous = value
                clearance = min(float(world.data.geom_xpos[g, 2] - np.abs(world.data.geom_xmat[g].reshape(3, 3)[2]) @ world.model.geom_size[g]) for g in gids)
                rotation = world.data.xmat[body].reshape(3, 3)
                tilt = math.degrees(math.acos(float(np.clip(rotation[2, 2], -1, 1))))
                forces, force = [0., 0.], np.zeros(6)
                for i in range(world.data.ncon):
                    contact = world.data.contact[i]
                    a, b = int(contact.geom1), int(contact.geom2)
                    finger = a if b in gids else b if a in gids else None
                    if finger in fingers:
                        mujoco.mj_contactForce(world.model, world.data, i, force)
                        forces[fingers[finger]] += abs(float(force[0]))
                evaluation = {'clearance': clearance, 'tilt': tilt, 'forces': forces,
                              'weld': bool(world.data.eq_active.any())}
                if teacher_start_v1:
                    from harness.visual_arm_v3 import MOUNT_X_M
                    target = world.data.xpos[body]
                    base = world.robot(rid).base_xyz()
                    yaw = float(world.robot(rid).base_rpy()[2])
                    object_yaw = math.atan2(rotation[1, 0], rotation[0, 0])
                    station = target[:2] - (MOUNT_X_M + .152) * np.array([math.cos(object_yaw), math.sin(object_yaw)])
                    station_error = float(np.linalg.norm(station - np.asarray(base[:2])))
                    yaw_error = abs(math.atan2(math.sin(object_yaw-yaw), math.cos(object_yaw-yaw)))
                    passed = {'approach': station_error <= .08,
                              'alignment': station_error <= .008 and yaw_error <= .04,
                              'grasp': min(forces) >= .5,
                              'lift_confirmation': score.lift.record()['lift_success']}
                    predecessor = True
                    for stage in ('approach', 'alignment', 'grasp', 'lift_confirmation'):
                        ok = predecessor and passed[stage]
                        funnel[stage] += int(ok)
                        if ok: first_pass.setdefault(stage, now)
                        predecessor = stage in first_pass
                    gaps = [float(mujoco.mj_geomDistance(world.model, world.data, finger, g,
                                float(world.model.stat.extent), None)) for finger in fingers for g in gids]
                    evaluation.update(station_error_m=station_error, yaw_error_rad=yaw_error,
                                      target_finger_min_gap_m=min(gaps), target_object=plan['item_id'])
                velocity = np.zeros(6)
                mujoco.mj_objectVelocity(world.model, world.data, mujoco.mjtObj.mjOBJ_BODY, body, velocity, 0)
                linear_speed = float(np.linalg.norm(velocity[3:]))
                score.add(now, skill=obs['skill'], linear_speed=linear_speed,
                          **{k: evaluation[k] for k in ('clearance', 'tilt', 'forces', 'weld')})
                evaluations.write(json.dumps({'t': now, 'skill': obs['skill'],
                    'linear_speed': linear_speed, **evaluation}, allow_nan=False) + '\n')
                if tick % 10 == 0:
                    for stream in (inputs, commands, evaluations):
                        stream.flush()
                    write_json(output / 'progress.json', {'sim_s': now-origin, 'done_requested': done,
                               'inference_calls': len(latencies)})
                # Student done + fixed clock window are the ONLY phase/stop inputs.
                # Evaluation truth never enters the sequence or the worker.
                if sequence.update(now, done):
                    break
                tick += 1
                until = origin + tick * c.PERIOD_S
                while float(world.data.time) < until - 1e-8:
                    t = float(world.data.time)
                    port.tick(t)
                    port._set_motors(tuple(w if t < deadline else 0. for w, deadline in zip(value['wheels'], deadlines)))
                    world._physics_step_for(world.robot(rid))
        report.update(status='complete', complete=True, sim_s=float(world.data.time)-origin,
            done_requested=bool(sequence.done_times), done_times=sequence.done_times,
            **score.record(sequence.done_times, with_release=with_release),
            inference_latency_s={'n': len(latencies), 'median': float(np.median(latencies)),
                                 'p95': float(np.percentile(latencies, 95))},
            skill_completion_success=None)
        report['cap_end'] = not bool(sequence.done_times) and report['sim_s'] >= cap_s - c.PERIOD_S / 2
        report['termination'] = 'cap_end' if report['cap_end'] else 'student_done'
        if teacher_start_v1:
            missing = next((s for s in ('approach', 'alignment', 'grasp', 'lift_confirmation') if s not in first_pass), None)
            report.update(failure_stage=missing, funnel=funnel, first_pass_sim_t=first_pass)
            write_json(output / 'funnel.json', {'schema': 'ugrp.act14.funnel.v1', 'counts': funnel,
                'cumulative_run_pass': {s: int(s in first_pass) for s in ('approach','alignment','grasp','lift_confirmation')},
                'first_pass_sim_t': first_pass, 'failure_stage': missing,
                'rejection': None if missing is None else {'category': missing+'_not_passed',
                    'blocking_object': 'none_observed', 'target_object': plan['item_id'],
                    'minimum_gap_m': evaluation.get('target_finger_min_gap_m'),
                    'scope': 'target finger gap only; no collision cause inferred'},
                'source': str(output / 'eval-only.jsonl'), 'reproduce': 'python -m scripts.analyze_grasp_act_act14 --root '+str(output)})
    except BaseException as exc:
        report.update(status='interrupted' if isinstance(exc, KeyboardInterrupt) else 'HOST_ERROR',
                      complete=False, error_type=type(exc).__name__)
        raise
    finally:
        if prediction_log is not None:
            prediction_log.close()
        if port is not None:
            port.stop()
        if worker is not None:
            worker.terminate()
            try:
                worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                worker.kill(); worker.wait(timeout=5)
        if world is not None:
            world.close()
        report['wall_s'] = time.monotonic() - begin
        report['artifacts'] = {str(p.relative_to(output)): sha256(p) for p in output.rglob('*')
                               if p.is_file() and p.name != 'summary.json'}
        write_summary(output / 'summary.json', report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--protocol', type=Path, required=True)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--actor-python', required=True)
    p.add_argument('--cap-s', type=float, default=60.)
    p.add_argument('--n-action-steps', type=int, default=c.CHUNK)
    p.add_argument('--temporal-ensemble-coeff', type=float)
    p.add_argument('--actor-threads', type=int, choices=(1, 2, 4, 8, 16), default=1)
    p.add_argument('--teacher-start-v1', action='store_true')
    p.add_argument('--scene-source', type=Path, help='frozen 6f057f7e scene/physics package; no teacher policy')
    a = p.parse_args()
    from contextlib import nullcontext
    from scripts.run_grasp_act_recovery import dependency_modules
    if a.teacher_start_v1 != bool(a.scene_source):
        p.error('--teacher-start-v1 requires the exact frozen --scene-source')
    with dependency_modules(a.scene_source) if a.scene_source else nullcontext():
        run(json.loads(a.plan.read_text()), json.loads(a.protocol.read_text()), a.model, a.output,
            actor_python=a.actor_python, cap_s=a.cap_s, n_action_steps=a.n_action_steps,
            temporal_ensemble_coeff=a.temporal_ensemble_coeff, actor_threads=a.actor_threads,
            teacher_start_v1=a.teacher_start_v1)


if __name__ == '__main__':
    main()
