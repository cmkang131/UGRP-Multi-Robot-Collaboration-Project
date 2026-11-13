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

import importlib.util as _ilu
# solo_green_v1 hook (default off): loaded by file path, stdlib only, before the dependency_modules() swap.
_SOLO_APPEARANCE_SPEC = _ilu.spec_from_file_location('solo_appearance_v1', str(Path(__file__).resolve().parent / 'solo_appearance_v1.py'))
solo_appearance_v1 = _ilu.module_from_spec(_SOLO_APPEARANCE_SPEC)
_SOLO_APPEARANCE_SPEC.loader.exec_module(solo_appearance_v1)
from harness import grasp_act_contract as c
from harness.grasp_act_data import sha256, write_json, write_summary
from harness.grasp_act_policy import ChunkExecutor
from harness.grasp_act_inference import private_url
from harness.grasp_act_rollout import OwnHistory, SoloSequence, SoloScore, InputAudit, evaluation_gates, GraspTransitionRule
from scripts.grasp_act_training_guard import ROOT, require_gcp, source_sha


def _load_gaze_class():
    # Resolved before dependency_modules() swaps `harness` for the frozen scene
    # package, which has no gaze_correction module. Only called with the flag on.
    from harness.gaze_correction import GazeCorrection
    return GazeCorrection


_gaze_class = None


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


def reached_cap(sim_s, cap_s, *, sequence_finished):
    # Preserve the existing half-control-tick timestamp comparison. A done
    # request alone does not complete SoloSequence's existing settle window.
    return not sequence_finished and sim_s >= cap_s-c.PERIOD_S/2


def run(plan, protocol, model, output, *, actor_python, cap_s=60., n_action_steps=c.CHUNK,
        temporal_ensemble_coeff=None, actor_threads=1, teacher_start_v1=False,
        diagnostic_observer_factory=None, actor_server_url=None,
        grasp_transition_rule=False, gaze_code_v1=False, approach_code_v1=False, release_code_v1=False,
        approach_survey_v1=False, carry_test_v1=False):
    if actor_threads not in (1, 2, 4, 8, 16):
        raise ValueError('bounded actor thread setting required')
    ChunkExecutor(None, n_action_steps=n_action_steps, temporal_ensemble_coeff=temporal_ensemble_coeff)
    if approach_survey_v1 and approach_code_v1:
        raise ValueError('approach_survey_v1 and approach_code_v1 are mutually exclusive')
    # approach_survey_v1 spends about 12 s looking around and up to 70 s squaring up, before ACT starts.
    if not 0 < cap_s <= (320. if approach_survey_v1 else 90.):
        raise ValueError('finite <=90 SIM seconds required (<=320 with approach_survey_v1)')
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
    # Opt-in code-side gaze correction. The import is inside the opt-in branch
    # so the default (off) path keeps exactly its previous dependencies, and
    # the rule is a post-processing step on the ACT action: the wheels and the
    # gripper servos stay with ACT.
    gaze = None
    if gaze_code_v1:
        gaze = _gaze_class()
    # Opt-in code-side approach servo (approach_code_v1), DEFAULT OFF. Switched on by the CLI flag
    # or by the plan key 'approach_code_v1': true. The module is imported only when on (cv2 lazily).
    approach = None
    survey_select = {}
    if approach_survey_v1:
        # approach_survey_v1 (DEFAULT OFF): look around, approach from the observed list, square up. It takes
        # precedence over the plan key approach_code_v1, so the real-position start hint is never built.
        import importlib.util as _ilu
        _sspec = _ilu.spec_from_file_location('approach_survey_v1', str(Path(__file__).resolve().parent.parent / 'harness' / 'approach_survey_v1.py'))
        approach_servo_v1 = _ilu.module_from_spec(_sspec)
        _sspec.loader.exec_module(approach_servo_v1)
        approach = approach_servo_v1.SurveyApproach(c, lambda entries: survey_select['fn'](entries))
        approach_servo_v1.D_STOP_M = approach.D_STOP_M
    elif approach_code_v1 or plan.get('approach_code_v1') is True:
        # Loaded by file path: run() executes inside the frozen-dependency import scope, where the
        # package name 'harness' resolves to the pinned teacher package (no approach module there).
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location('approach_servo_v1', str(Path(__file__).resolve().parent.parent / 'harness' / 'approach_servo_v1.py'))
        approach_servo_v1 = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(approach_servo_v1)
        approach = approach_servo_v1.ApproachServo(plan['object_kind'], c, approach_servo_v1.plan_handoff_hint(plan))
    report['gaze_correction'] = {
        'enabled': bool(gaze_code_v1),
        'applied': False,
        'inputs': 'own RGB cyan blob centroid and own issued command only; '
                  'no simulator evaluation value, no ground truth, no teacher',
        'servos': ['3', '4', '6'],
        'skill_scope': 'grasp (approach) only; the arm is handed back to ACT after '
                       'three consecutive ticks with all four ACT wheels at zero',
        'rule': 'target on the right -> servo 6 down; target below -> servo 3 down '
                'and servo 4 up; inside the central window -> unchanged',
    }
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
        scene = solo_appearance_v1.apply_plan(scene, plan)  # solo_green_v1; no key = no change
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
                    'pwm': ({str(s): int(port._servo_pulses[s]) for s in c.SERVOS} if teacher_start_v1 and not approach_survey_v1 else
                            {'1': 2000, '3': 740, '4': 2320, '5': 1320, '6': 1500})}
        if not teacher_start_v1 or approach_survey_v1:
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
        if approach_survey_v1:
            # Evaluation side only: which observed entry is the designated box. Same rule as the approach probe
            # (same kind, global greedy by distance, within 0.15 m). Only the integer index goes to the student.
            _objects = scene.config['setup_only']['objects']
            _bodies = {k: world.model.body(v['body_name']).id for k, v in _objects.items() if 'body_name' in v}
            def _select(entries):
                xyz = world.robot(rid).base_xyz()
                yaw = float(world.robot(rid).base_rpy()[2])
                co, si = math.cos(yaw), math.sin(yaw)
                pairs = []
                for index, entry in enumerate(entries):
                    for key, bid in _bodies.items():
                        if _objects[key]['kind'] != entry['kind']:
                            continue
                        dx = float(world.data.xpos[bid][0] - xyz[0])
                        dy = float(world.data.xpos[bid][1] - xyz[1])
                        gap = math.hypot(entry['x'] - (co * dx + si * dy), entry['y'] - (-si * dx + co * dy))
                        if gap <= 0.15:
                            pairs.append((gap, index, key))
                used_i, used_k, chosen = set(), set(), None
                for gap, index, key in sorted(pairs):
                    if index not in used_i and key not in used_k:
                        used_i.add(index)
                        used_k.add(key)
                        if key == plan['item_id']:
                            chosen = index
                write_json(output / 'survey-select.json', {'entries': entries, 'selected_index': chosen,
                           'matched_pairs': len(used_i), 'threshold_m': 0.15,
                           'note': 'evaluation-side matching; only the index is passed to the student'})
                return chosen
            survey_select['fn'] = _select
        history = OwnHistory(rid, f'student-{plan["seed"]}', previous)
        (output / 'rgb' / rid).mkdir(parents=True)
        if actor_server_url:
            report['execution']['actor_server_url']=private_url(actor_server_url)
            report['execution']['inference_device']='cuda_l4_batch1_v1'
            write_summary(output / 'summary.json', report)
        worker = subprocess.Popen([actor_python, '-m', 'scripts.grasp_act_student_worker', '--model', str(model), '--threads', str(actor_threads)]+
            (['--server-url',actor_server_url] if actor_server_url else []),
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
        # Offline replay diagnostics only. The observer receives the selected
        # command and has no return path into the executor or sequence.
        diagnostic_observer = (diagnostic_observer_factory(world, port, obj, previous, scene)
                               if diagnostic_observer_factory else None)
        # Evaluation-only funnel. Existing frozen teacher boundaries: approach
        # .08m, box alignment .008m/.04rad (6f057f7e SoloTeacher._seek/Cargo).
        # Finger load/lift use the unchanged LiftScore criteria. None feed policy.
        funnel = {'frames': 0, 'valid_inputs': 0, 'actions': 0, 'approach': 0,
                  'alignment': 0, 'grasp': 0, 'lift_confirmation': 0}
        first_pass = {}
        minimum_external_contact = None
        # Approach variant: the grasp-end rule is armed only when the approach ARRIVED (handover). On a timeout or
        # an exhausted search it stays off, because the rule would fire on an empty grasp. Recorded in the summary.
        rule_state = {'wanted': bool(grasp_transition_rule) and approach is not None, 'armed_at_handover': False,
                      'note': 'on from start' if (grasp_transition_rule and approach is None) else
                              ('off' if approach is None else 'pending handover')}
        sequence = SoloSequence(with_release, grasp_rule=bool(grasp_transition_rule) and approach is None)
        # Experimental release replay (release_code_v1), DEFAULT OFF: on by the CLI flag or the plan key.
        release_on = bool(release_code_v1 or plan.get('release_code_v1') is True)
        release_mod, release_code = None, None
        if release_on:
            import importlib.util as _ilu
            _rspec = _ilu.spec_from_file_location('release_code_v1', str(Path(__file__).resolve().parent.parent / 'harness' / 'release_code_v1.py'))
            release_mod = _ilu.module_from_spec(_rspec)
            _rspec.loader.exec_module(release_mod)
        # release_code_v1 hold (scene 90711): the last 45 issued servo PWM rows; the hold is their median.
        issued_hist, hold_pwm = [], None
        # carry_test_v1 (DEFAULT OFF, development check): between the lift and the release replay the base
        # backs up, turns and drives forward with the grasp posture held, to see whether the box stays in
        # the gripper while the robot moves. Fixed own commands only; nothing is observed or corrected.
        carry_plan, carry_i = [], 0
        if carry_test_v1:
            if not release_on:
                raise ValueError('carry_test_v1 needs release_code_v1')
            carry_plan = ([([-.35] * 4, .10)] * 20 + [([0.] * 4, 0.)] * 5 +
                          [([-.35, .35, -.35, .35], .10)] * 30 + [([0.] * 4, 0.)] * 5 +
                          [([.35] * 4, .10)] * 40 + [([0.] * 4, 0.)] * 10)
        hold_state = {'rows': 0, 'pwm': None}
        # Evaluation-only private handles; these never leave the simulation owner.
        body = world.model.body(obj['body_name']).id
        gids = [g for g in range(world.model.ngeom) if world.model.geom_bodyid[g] == body and world.model.geom_contype[g]]
        fingers = {world.model.geom(rid + '__' + side + '_finger').id: i for i, side in enumerate(('left', 'right'))}
        origin, tick = float(world.data.time), 0
        sequence_finished = False
        with (output / 'student-inputs.jsonl').open('x') as inputs, (output / 'commands.jsonl').open('x') as commands, (output / 'eval-only.jsonl').open('x') as evaluations:
            while float(world.data.time) - origin < cap_s - 1e-8:
                if (output / 'SUPERVISOR_STOP.json').exists():
                    raise KeyboardInterrupt('supervisor stop')
                if time.monotonic() - begin > (5400 if approach_survey_v1 else 1800):
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
                # While the approach servo owns the tick, ACT is not called (no chunk is consumed)
                # and the learned done bit is ignored. The first ACT call is on the tick after arrival.
                code = approach.step(jpeg, now) if approach is not None and not approach.arrived else None
                if approach_survey_v1 and approach.arrived and 'act_clock' not in rule_state:
                    # The actor reads two own clocks: time since the skill started and time since the issued arm
                    # posture last changed. The taught skill has no look-around and no squaring-up stage, so at the
                    # handover those clocks read 50-110 s and 12-60 s, and the actor's done output goes above its
                    # threshold before any grasp (replayed: 0.71 at 51 s / 18 s, 0.03 at 25 s / 2 s). The skill clock
                    # is therefore restarted so that it counts the approach stage only, and the posture clock starts
                    # at the handover. Both are the robot's own clocks; nothing external is read.
                    _clock = c.IssuedClock()
                    _clock.skill = (sequence.skill, plan['object_kind'], plan['role'], 'none')
                    _clock.started = now + c.PERIOD_S - approach.approach_seconds()
                    history.clock = _clock
                    rule_state['act_clock'] = {'rebased_at_s': now - origin, 'skill_clock_counts': 'approach stage only',
                                               'approach_s': approach.approach_seconds(), 'posture_clock': 'restarts at the handover'}
                if code is not None:
                    value, done, source = code, False, 'code'
                elif carry_plan and sequence.skill == 'release' and carry_i < len(carry_plan):
                    _w, _d = carry_plan[carry_i]
                    carry_i += 1
                    value = c.command({'t': now, 'wheels': list(_w), 'duration_s': [_d if w else 0. for w in _w],
                                       'pwm': dict(hold_pwm if hold_pwm is not None else previous['pwm'])})
                    done, source = False, 'carry_code'
                elif release_on and sequence.skill == 'release':
                    # Release skill: the teacher's median table owns the tick (ACT is not called).
                    if release_code is None:
                        release_code = release_mod.ReleaseCodeV1(c, previous['pwm'])
                    value, done = release_code.step(now)
                    source = 'release_code'
                elif release_on and sequence.skill == 'grasp' and sequence.rule is not None and sequence.rule.fired:
                    # release_code_v1 hold (scene 90711): from the tick the grasp-end rule fired until the release
                    # replay starts, ACT is not used. Servos 1,3,4,5,6 hold the median of the issued PWM of the last 45
                    # rows before the rule fired; the wheels stay at zero (the contract checks the row).
                    if hold_pwm is None:
                        hold_pwm = {}
                        for s in ('1', '3', '4', '5', '6'):
                            vals = sorted(r[s] for r in issued_hist) or [previous['pwm'][s]]
                            m = len(vals)
                            hold_pwm[s] = int(round(vals[m // 2] if m % 2 else 0.5 * (vals[m // 2 - 1] + vals[m // 2])))
                        hold_state['pwm'] = dict(hold_pwm)
                    value = c.command({'t': now, 'wheels': [0.0] * 4, 'duration_s': [0.0] * 4, 'pwm': dict(hold_pwm)})
                    done = False
                    source = 'release_hold'
                    hold_state['rows'] += 1
                else:
                    value, done = executor.step(obs, jpegs)
                    source = 'act'
                if release_on:
                    issued_hist.append({s: int(value['pwm'][s]) for s in ('1', '3', '4', '5', '6')})
                    issued_hist = issued_hist[-45:]
                if gaze is not None and sequence.skill == 'grasp' and source == 'act':
                    # Code-side gaze correction (opt-in). It replaces the PWM of
                    # the gaze servos 3, 4 and 6 of this tick and leaves the
                    # wheels and servos 1 and 5 untouched. The corrected row is
                    # what the port applies and what is recorded as the robot's
                    # own issued command, so the ACT input history matches what
                    # the robot really commanded.
                    value = gaze.apply(value, jpeg)
                if diagnostic_observer is not None:
                    diagnostic_observer(obs, jpeg, value, done)
                funnel['actions'] += 1
                row = {'command': value, 'skill': obs['skill'], 'done_requested': done}
                if approach is not None or release_on:
                    row['source'] = source
                commands.write(json.dumps(row) + '\n')
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
                    gaps = [float(mujoco.mj_geomDistance(world.model, world.data, finger, g,
                                float(world.model.stat.extent), None)) for finger in fingers for g in gids]
                    evaluation.update(station_error_m=station_error, yaw_error_rad=yaw_error,
                                      target_finger_min_gap_m=min(gaps), target_object=plan['item_id'])
                    if approach is not None:
                        # Evaluation-only diagnostic (approach on): base pose for the post-hoc check of which
                        # box was acquired. The approach servo never reads these values.
                        evaluation.update(base_x=float(base[0]), base_y=float(base[1]), base_yaw=yaw)
                    contacts=[]
                    for contact in world.data.contact[:world.data.ncon]:
                        a,b=int(contact.geom1),int(contact.geom2)
                        names=[world.model.geom(g).name or str(g) for g in (a,b)]
                        if sum(n.startswith(rid+'__') for n in names)!=1:continue
                        external=names[1] if names[0].startswith(rid+'__') else names[0]
                        if 'floor' in external or 'ground' in external:continue
                        contacts.append({'object':external,'gap_m':float(contact.dist)})
                    evaluation['external_contacts']=contacts
                    if contacts:
                        contact=min(contacts,key=lambda x:x['gap_m'])
                        if minimum_external_contact is None or contact['gap_m']<minimum_external_contact['gap_m']:
                            minimum_external_contact=contact
                velocity = np.zeros(6)
                mujoco.mj_objectVelocity(world.model, world.data, mujoco.mjtObj.mjOBJ_BODY, body, velocity, 0)
                linear_speed = float(np.linalg.norm(velocity[3:]))
                score.add(now, skill=obs['skill'], linear_speed=linear_speed,
                          **{k: evaluation[k] for k in ('clearance', 'tilt', 'forces', 'weld')})
                if teacher_start_v1:
                    passed=evaluation_gates(evaluation,stable_lift=score.lift.record()['lift_success'])
                    predecessor=True
                    for stage,ok in passed.items():
                        ok=predecessor and ok
                        funnel[stage] += int(ok)
                        if ok:first_pass.setdefault(stage,now)
                        predecessor=stage in first_pass
                evaluations.write(json.dumps({'t': now, 'skill': obs['skill'],
                    'linear_speed': linear_speed, **evaluation}, allow_nan=False) + '\n')
                if tick % 10 == 0:
                    for stream in (inputs, commands, evaluations):
                        stream.flush()
                    write_json(output / 'progress.json', {'sim_s': now-origin, 'done_requested': done,
                               'inference_calls': len(latencies)})
                # Student done + fixed clock window are the ONLY phase/stop inputs.
                # Evaluation truth never enters the sequence or the worker.
                # With the rule enabled the sequence additionally reads the
                # robot's OWN issued command row (wheels and commanded PWM) and
                # the clock. It never reads contact force, tilt, clearance,
                # ground truth or weld.
                if rule_state['wanted'] and sequence.rule is None and approach is not None and approach.arrived:
                    # Drive-record distance to the stop point at the handover (the approach's own odometry; never ground
                    # truth). A near-range handover arms the rule only within 0.10 m of the stop point (|d - D_STOP| <= 0.10).
                    d_drive = approach.trace[-1]['d_est_m'] if approach.trace else None
                    near_stop = d_drive is not None and abs(d_drive - approach_servo_v1.D_STOP_M) <= 0.10
                    if approach.reason in ('arrived', 'settled') or (approach.reason == 'handover_near_no_blob' and near_stop):
                        sequence.rule = GraspTransitionRule()
                        rule_state['armed_at_handover'] = True
                        rule_state['note'] = ('armed: approach %s' % approach.reason if approach.reason in ('arrived', 'settled') else
                                              'armed: approach %s, drive-record d_est %.3f m within 0.10 m of the stop point'
                                              % (approach.reason, d_drive))
                    else:
                        rule_state['note'] = 'off: approach %s%s' % (approach.reason, '' if d_drive is None else
                                                                   ' (drive-record d_est %.3f m)' % d_drive)
                    rule_state['wanted'] = False
                # approach_survey_v1: once the own-command rule is armed, the rule alone ends the grasp skill.
                # The learned done bit fired 0.6 s after the handover in one development run (90802) and the
                # release started before any grasp; such rows are counted and ignored during the grasp skill.
                if approach_survey_v1 and done and sequence.skill == 'grasp' and sequence.rule is not None:
                    rule_state['learned_done_ignored_rows'] = rule_state.get('learned_done_ignored_rows', 0) + 1
                    done = False
                if sequence.update(now, done, issued=value):
                    sequence_finished = True
                    break
                tick += 1
                until = origin + tick * c.PERIOD_S
                while float(world.data.time) < until - 1e-8:
                    t = float(world.data.time)
                    port.tick(t)
                    port._set_motors(tuple(w if t < deadline else 0. for w, deadline in zip(value['wheels'], deadlines)))
                    world._physics_step_for(world.robot(rid))
        report['release_code_v1'] = dict(
            release_code.record() if release_code is not None else
            {'enabled': release_on, 'started': False, 'source': 'teacher median table, 140 demos'},
            hold_between=dict(hold_state),
            status='release replay')
        if approach is not None:
            report['approach_survey_v1' if approach_survey_v1 else 'approach_code_v1'] = approach.record()
            write_json(output / 'approach-trace.json', approach.trace)
            if approach_survey_v1:
                write_json(output / 'alignment-trace.json', approach.alignment_trace())
        report.update(status='complete', complete=True, sim_s=float(world.data.time)-origin,
            done_requested=bool(sequence.done_times), done_times=sequence.done_times,
            **score.record(sequence.done_times, with_release=with_release),
            inference_latency_s={'n': len(latencies), 'median': float(np.median(latencies)) if latencies else None,
                                 'p95': float(np.percentile(latencies, 95)) if latencies else None},
            skill_completion_success=None)
        if carry_test_v1:
            report['carry_test_v1'] = {'enabled': True, 'rows_issued': carry_i, 'rows_planned': len(carry_plan),
                                       'plan': 'back 20 pulses, turn 30 pulses, forward 40 pulses (0.10 s at 0.35), posture held'}
        if approach is not None:
            report['grasp_rule_at_handover'] = dict(rule_state)
        if sequence.rule is not None:
            # Distinguish a rule completion from a learned done bit. With the
            # rule OFF this block does not run at all, so the report keeps the
            # exact shape it had before the rule existed.
            report['grasp_transition_rule'] = {
                'enabled': True,
                'inputs': 'own issued commands (wheels, commanded PWM) and the clock only',
                'completion_cause': dict(sequence.done_causes),
                'fired': bool(sequence.rule.fired),
                'fired_at_sim_s': sequence.rule.fire_t,
                'constants': {'end_pwm': sequence.rule.end_pwm,
                              'tolerance_pwm': sequence.rule.tolerance_pwm,
                              'hold_rows': sequence.rule.hold_rows},
                'evidence_episodes': 1,
                'note': 'a rule completion is NOT a learned done bit; the release '
                        'skill still completes only through the learned done bit'}
        report['cap_end'] = reached_cap(report['sim_s'], cap_s, sequence_finished=sequence_finished)
        report['termination'] = 'cap_end' if report['cap_end'] else 'student_done'
        if teacher_start_v1:
            missing = next((s for s in ('approach', 'alignment', 'grasp', 'lift_confirmation') if s not in first_pass), None)
            report.update(failure_stage=missing, funnel=funnel, first_pass_sim_t=first_pass)
            write_json(output / 'funnel.json', {'schema': 'ugrp.act14.funnel.v1', 'counts': funnel,
                'cumulative_run_pass': {s: int(s in first_pass) for s in ('approach','alignment','grasp','lift_confirmation')},
                'first_pass_sim_t': first_pass, 'failure_stage': missing,
                'rejection': None if missing is None else {'category': missing+'_not_passed',
                    'blocking_object': minimum_external_contact['object'] if minimum_external_contact else 'none_observed',
                    'target_object': plan['item_id'],
                    'minimum_gap_m': minimum_external_contact['gap_m'] if minimum_external_contact else None,
                    'target_finger_min_gap_m': evaluation.get('target_finger_min_gap_m'),
                    'scope': 'observed non-floor external contacts; no collision cause inferred'},
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
        if gaze is not None:
            report['gaze_correction'].update(gaze.record())
            report['gaze_correction']['applied'] = bool(gaze.corrected)
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
    p.add_argument('--actor-server-url', help='opt-in private L4, own-input-only inference')
    p.add_argument('--teacher-start-v1', action='store_true')
    # In this copy the own-command grasp-end rule is ON by default. summary.json records grasp_transition_rule.
    p.add_argument('--grasp-transition-rule', action='store_true', default=True,
                   help='opt-in: complete the grasp skill from the robot\'s own issued '
                        'commands (wheels still + grasp end posture held 45 rows) '
                        'instead of the learned done bit. Default off.')
    p.add_argument('--carry-test-v1', action='store_true',
                   help='development check (default off): drive with the box held between the lift and the release')
    p.add_argument('--approach-survey-v1', action='store_true',
                   help='opt-in (default off): look around, approach the indexed observed box, square up, then ACT')
    p.add_argument('--approach-code-v1', action='store_true',
                   help='opt-in (default off): code-side approach servo to the stop reference, then ACT')
    p.add_argument('--gaze-code-v1', action='store_true',
                   help='opt-in: the code owns the gaze during the approach and steers '
                        'the cyan target of the own RGB frame back to the optical '
                        'centre (servo 6 pan, servo 3/4 tilt). The wheels and the '
                        'gripper stay with ACT and the arm is handed back to ACT '
                        'after three consecutive ticks with all four ACT wheels at '
                        'zero. Default off.')
    p.add_argument('--release-code-v1', action='store_true',
                   help='EXPERIMENTAL opt-in (default off): replay the teacher median release table (87 rows, 140 demos) '
                        'as the release skill commands instead of ACT. Also on by plan key release_code_v1.')
    p.add_argument('--scene-source', type=Path, help='frozen 6f057f7e scene/physics package; no teacher policy')
    a = p.parse_args()
    from contextlib import nullcontext
    from scripts.run_grasp_act_recovery import dependency_modules
    if a.teacher_start_v1 != bool(a.scene_source):
        p.error('--teacher-start-v1 requires the exact frozen --scene-source')
    if a.gaze_code_v1:
        global _gaze_class
        _gaze_class = _load_gaze_class()
    with dependency_modules(a.scene_source) if a.scene_source else nullcontext():
        run(json.loads(a.plan.read_text()), json.loads(a.protocol.read_text()), a.model, a.output,
            actor_python=a.actor_python, cap_s=a.cap_s, n_action_steps=a.n_action_steps,
            temporal_ensemble_coeff=a.temporal_ensemble_coeff, actor_threads=a.actor_threads,
            teacher_start_v1=a.teacher_start_v1, actor_server_url=a.actor_server_url,
            grasp_transition_rule=a.grasp_transition_rule, gaze_code_v1=a.gaze_code_v1,
            approach_code_v1=a.approach_code_v1, release_code_v1=a.release_code_v1,
            approach_survey_v1=a.approach_survey_v1, carry_test_v1=a.carry_test_v1)


if __name__ == '__main__':
    main()
