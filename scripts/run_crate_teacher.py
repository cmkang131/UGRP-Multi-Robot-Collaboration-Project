"""Heavy-crate two-robot teacher run (success measurement; weld always OFF).

One episode = approach -> align -> grasp (READY/GO/ACK start with skew) -> second
READY/GO/ACK barrier -> simultaneous lift -> 3 s joint hold -> set-down (visible_only release
teacher, crate geometry) -> optional look-around (``setdown_lookaround_v1``).

Stages are reported separately so a set-down failure never contaminates the grasp rate:
``prefix_held`` (denominator = all episodes) and ``release_success`` (over held episodes
and over all episodes). Training RGB recording is OFF (success first, then recording;
user 2026-10-14). Truth is used only to gate what each own camera currently shows (and
for the relative pose of the visible things), for the evaluation record, and for the
demonstration assignment in the plan. The crate world pose never feeds a decision while held
(``--held-object hidden_v1`` makes a read an error; ``input_audit`` counts them).
Not run on the Mac (no physics there).
"""
from __future__ import annotations
import argparse, base64, io, json, math, os, platform, subprocess, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.run_grasp_act_teacher import write, apply, compress_logs
from scripts.run_grasp_act_release import (HeldAudit, HELD_OBJECT_MODES, Eyes, destination_slot_geoms, position_error,
                                           SUCCESS, DELIVERY_WAIT_S, ZONE_SLOT_MODES)
from sim.grasp_act_release_teacher import OBSERVE_MODES, REACH_MODES
from sim.cargo_teacher_profile import CRATE

LOOKAROUND_MODES = ('off', 'setdown_lookaround_v1')
RGB_LIFT_MODES = ('off', 'crate_rgb_lift_v1', 'crate_rgb_lift_v2', 'crate_rgb_lift_v3')
from sim.cargo_scene_version import VERSIONS as CARGO_SCENE_VERSIONS
from sim.crate_lift_pose import MODES as LIFT_POSE_MODES
HOLD_S = 3.
LIFT_FORCE_N = .5


def make_grasp_teacher(rid, end, pwm, *, teacher_stability='off', teacher_search='off', approach_goal_set='off', crate_lift_pose='off'):
    from sim.crate_grasp_teacher import CrateGraspTeacher
    return CrateGraspTeacher(rid, end, pwm, bounds=(-20, 20, -20, 20), profile=CRATE,
                             teacher_stability=teacher_stability, teacher_search=teacher_search,
                             approach_goal_set=approach_goal_set, crate_lift_pose=crate_lift_pose)


def run_meta(plan, sha, pr, crate_lift_pose):
    """Execution identity, also available to offline metadata tests."""
    return {'class': 'dev', 'pr': pr, 'branch': 'claude/act-crate-teacher', 'sha': sha,
            'batch': plan['batch'], 'cargo_scene_version': plan['cargo_scene_version'],
            'crate_lift_pose': crate_lift_pose, 'lug_color_scene': plan.get('lug_color_scene', 'off')}


def release_ready(command_complete, settled_s, verdicts):
    """Own issued lift + own RGB only; physical hold truth is evaluation-only."""
    return (all(command_complete.values()) and settled_s >= HOLD_S
            and set(verdicts) == set(command_complete)
            and all(v['verdict'] == 'confirmed' for v in verdicts.values()))


def grasp_inputs(read_measurements, *, holding, audit):
    """Do not even read held cargo measurements in the hidden profile."""
    if audit.mode == 'hidden_v1' and holding:
        return []
    rows = read_measurements()
    for m in rows:
        visible = m['visible_n'] >= (5 if m['kind'] == 'band' else max(1, math.ceil(m['probe_N']/3)))
        audit.measurement('grasp', m['id'], visible)
        if not visible:
            raise RuntimeError('invisible measurement delivered to crate teacher')
        if m['kind'] == 'band' or m['id'] == CRATE.item_id:
            audit.read(holding, 'grasp_cargo_measurement')
    return rows


def servo_load(world, rids):
    """Evaluation only: arm servo force / force limit per robot (saturation shows as |ratio| ~ 1)."""
    import mujoco
    out = {}
    for rid in rids:
        row = {}
        for name in ('shoulder', 'elbow', 'wrist'):
            aid = mujoco.mj_name2id(world.model, mujoco.mjtObj.mjOBJ_ACTUATOR, f'{rid}__servo_{name}')
            limit = float(world.model.actuator_forcerange[aid][1])
            row[name] = round(float(world.data.actuator_force[aid])/limit, 3)
        out[rid] = row
    return out


def own_rgb(port):
    import numpy as np
    from PIL import Image
    return np.array(Image.open(io.BytesIO(base64.b64decode(port.capture()['image']))).convert('RGB'))


def snapshot_cargo(world, inst, roles, scene, profile=CRATE):
    """Evaluation/teacher-input world dict (same shape as run_grasp_act_teacher.snapshot, crate ends)."""
    import numpy as np
    from types import SimpleNamespace
    from scripts.cargo_formation_teacher import FormationTeacher
    body = world.data.body(inst.body)
    rot = body.xmat.reshape(3, 3)
    pos = body.xpos
    yaw = math.atan2(rot[1, 0], rot[0, 0])
    ends = {end: (pos+rot@np.array([x, 0., .024])).tolist()
            for end, x in (('teal', -profile.grasp_m), ('blue', profile.grasp_m))}
    holder = SimpleNamespace(world=world, inst=inst, roles=roles)
    min_z = min(float((world.data.geom(inst.geom(p.name)).xpos
                       + world.data.geom(inst.geom(p.name)).xmat.reshape(3, 3)@np.array(
                           [sx*p.size[0], sy*p.size[1], sz*p.size[2]]))[2])
                for p in inst.spec().parts if p.collision for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1))
    objects = {}
    for c in scene.cargo:
        b = world.data.body(c.body)
        objects[c.item_id] = {
            'xy': list(map(float, b.xpos[:2])), 'radius': math.hypot(*c.spec().landing_half_extents_m),
            'top_z_bound_m': max(float(world.data.geom(c.geom(p.name)).xpos[2])
                                 + float(world.model.geom_rbound[world.model.geom(c.geom(p.name)).id])
                                 for p in c.spec().parts if p.collision)}
    for iid, c in scene.config['setup_only']['objects'].items():
        objects[iid] = {'xy': list(map(float, world.data.body(c['body_name']).xpos[:2])),
                        'radius': math.hypot(*c['half_extents_m'][:2]),
                        'top_z_bound_m': float(world.data.body(c['body_name']).xpos[2])
                        + math.sqrt(sum(float(x)**2 for x in c['half_extents_m']))}
    return {'objects': objects, 't': float(world.data.time),
            'beam': {'pose': [float(pos[0]), float(pos[1]), yaw], 'ends': ends, 'qpos': body.xquat.tolist(),
                     'min_z': min_z,
                     'tilt_deg': math.degrees(math.acos(float(np.clip(rot[2, 2], -1., 1.))))},
            'robots': {rid: {'pose': [*map(float, world.robot(rid).base_xyz()[:2]), float(world.robot(rid).base_rpy()[2])],
                             'xyz': list(map(float, world.robot(rid).base_xyz()))} for rid in ('r1', 'r2', 'r3')},
            'contacts': FormationTeacher.finger_forces(holder), 'joints': world.data.qpos.tolist()}


def own_end_world(world, inst, end, profile=CRATE):
    import numpy as np
    b = world.data.body(inst.body)
    rot = b.xmat.reshape(3, 3)
    return b.xpos+rot@np.array([-profile.landing_end_m if end == 'teal' else profile.landing_end_m, 0., 0.])


def held_lugs(world, inst, roles, profile=CRATE):
    """Evaluation only: which lug each gripper is nearest to (same-lug check)."""
    import numpy as np
    out = {}
    for rid in roles:
        g = world.data.site(f'{rid}__grip_site').xpos
        dist = {end: float(np.linalg.norm(g-world.data.geom_xpos[world.model.geom(name).id]))
                for end, name in zip(('teal', 'blue'), profile.band_geoms)}
        out[rid] = {'nearest_lug': min(dist, key=dist.get), 'distance_m': dist}
    return out


def run(plan, out, *, cap_s=90., grasp_cap_s=80., own_pose_source='commands', observe_mode='gaze_v2', render_dr='off',
        zone_slots='floor', reach_mode='calibrated_mid_v1', held_object='visible_v0', lookaround='off',
        execution_host=None, pr=None, crate_scene='catalogue_v1', rgb_lift='off',
        teacher_stability='off', teacher_search='off', approach_goal_set='off', crate_lift_pose='off'):
    for name, value, allowed in (('observe_mode', observe_mode, OBSERVE_MODES), ('zone_slots', zone_slots, ZONE_SLOT_MODES),
                                 ('reach_mode', reach_mode, REACH_MODES), ('lookaround', lookaround, LOOKAROUND_MODES)):
        if value not in allowed:
            raise ValueError(f'{name}: {value}')
    if rgb_lift not in RGB_LIFT_MODES:
        raise ValueError(f'rgb_lift: {rgb_lift}')
    # Validate modes before any physics or output creation.
    make_grasp_teacher('r1', 'teal', {1: 1500, 3: 820, 4: 2320, 5: 1320, 6: 1500},
                       teacher_stability=teacher_stability, teacher_search=teacher_search,
                       approach_goal_set=approach_goal_set, crate_lift_pose=crate_lift_pose)
    if crate_lift_pose != 'off' and (crate_scene != 'crate_mass_025_v1' or reach_mode != 'pad_window_v2'):
        raise ValueError('crate_lift_pose_margin_v1 requires crate_mass_025_v1 and pad_window_v2')
    if lookaround != 'off' and own_pose_source == 'commands':
        raise ValueError('lookaround requires a verified map localization; GT handoff anchors are forbidden')
    from sim.cargo_scene_version import check as check_cargo_scene
    plan = {**plan, 'cargo_scene_version': check_cargo_scene(crate_scene)}
    if plan.get('object_kind') != 'heavy_crate' or plan['target_item'] != CRATE.item_id:
        raise ValueError('heavy_crate plan required')
    if len(set(plan['roles'].values())) != 2 or set(plan['roles']) != {'r1', 'r2'}:
        raise ValueError('two robots on two different lugs required')
    audit = HeldAudit(held_object)
    if platform.system() == 'Darwin':
        raise RuntimeError('Mac physics/render disabled; use an admitted execution host')
    import numpy as np
    from PIL import Image
    from harness import grasp_act_contract as v5
    from harness.grasp_act_visible_world import VisibleWorld
    from harness.grasp_act_start_sync import GraspStartSync
    from harness.zone_scenario_feasibility import landing_fits
    from sim.crate_scene import make_crate_scene
    from sim.crate_release_teacher import CrateReleaseTeacher
    from sim.grasp_act_release_teacher import (PairReleaseCode, QuantizedWheels, BACKOFF_M, LOWER_Z_M, RAISE_Z_M,
                                               FOLDED_BACKOFF, OBSERVE_BACKOFF_M)
    from sim.grasp_act_visible_measurements import measurements
    from sim.visible_belief import relative, odometry
    from harness.visual_arm_v3 import solve_grip_site_ik, MOUNT_X_M
    from sim.masterpi_drive_friction_v7 import build_world, PROFILE
    from sim.grasp_act_port import DutyActPort
    from sim.s2_realism_camera_binding import bind_camera
    from sim.zone_cargo import place, CargoInstance
    from scripts.audit_grasp_act_visibility import BandVisibility
    out.mkdir(parents=True, exist_ok=False)
    write(out/'plan.json', plan)
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT):
        raise RuntimeError('committed source required')
    write(out/'RUN_META.json', run_meta(plan, sha, pr, crate_lift_pose))
    report = {'status': 'running', 'source_sha': sha, 'teacher': 'crate_visible_only_v1', 'object_kind': 'heavy_crate',
              'own_pose_source': own_pose_source, 'observe_mode': observe_mode, 'zone_slots': zone_slots,
              'reach_mode': reach_mode, 'held_object': held_object, 'lookaround': lookaround,
              'lug_color_scene': plan.get('lug_color_scene', 'off'), 'cargo_scene_version': plan['cargo_scene_version'],
              'rgb_lift': rgb_lift, 'assignment_source': plan['assignment_source'],
              'teacher_stability': teacher_stability, 'teacher_search': teacher_search, 'approach_goal_set': approach_goal_set,
              'crate_lift_pose': crate_lift_pose,
              'lift_confirmation': 'own issued lift + own RGB; unconfirmed/unknown stops before release',
              'execution_host': execution_host, 'weld': 'off', 'recording_mode': 'success_measurement',
              'student_execution': False, 'success_rule': SUCCESS,
              'grasp_criteria': {'min_z_m': .012, 'max_tilt_deg': 10., 'hold_s': HOLD_S, 'bilateral_n': LIFT_FORCE_N},
              'loadavg_at_start': os.getloadavg(), 'prefix_held': None, 'release_success': None}
    write(out/'result.json', report)
    world = None
    start = time.monotonic()
    streams = []
    origin = 0.
    try:
        os.environ['UGRP_SIM_OBSERVER_WIDTH'] = '320'
        os.environ['UGRP_SIM_OBSERVER_HEIGHT'] = '240'
        scene = make_crate_scene(plan)
        world = build_world(scene, drive_profile=PROFILE, seed=plan['seed'], width=320, height=240, render=True,
                            warehouse_layout=scene.engine_layout, warehouse_cargo_ids=None, roller_collision='mesh',
                            idle_robot_contacts='off')
        for controller in world.controllers.values():
            bind_camera(controller)
        scene.setup(world)
        from harness.render_randomization import draw as dr_draw, apply as dr_apply
        report['render_randomization'] = dr_apply(world.model, None if render_dr == 'off' else dr_draw(plan['seed'], world.model.nlight))
        place(world, [CargoInstance(CRATE.item_id, 'heavy_crate', tuple(plan['cargo_pose']))])
        (out/'scene.xml').write_text(world.scene_xml)
        write(out/'scene.json', scene.manifest)
        static = scene.config['static_map']
        zone = static['regions'][plan['destination_region']]
        rect = (*zone['center_m'], *zone['half_extents_m'])
        roles = plan['roles']
        ports = {rid: DutyActPort(world, rid, allow_reverse=True, allow_mecanum=True) for rid in roles}
        wheels = {rid: QuantizedWheels(port) for rid, port in ports.items()}
        for rid, port in ports.items():
            port.apply({'kind': 'look', 'pan_pulse': plan['initial_pan'][rid]}, float(world.data.time))
        timings = {'rgb': 0., 'eyes': 0., 'evaluation': 0., 'teacher': 0., 'physics': 0.}

        def advance(target):
            at = time.monotonic()
            while float(world.data.time) < target-1e-8:
                now = float(world.data.time)
                if world.data.eq_active.any():
                    raise RuntimeError('WELD_ACTIVE')
                for rid, port in ports.items():
                    port.tick(now)
                    wheels[rid].tick(now)
                world._physics_step_for(world.robot('r1'))
            timings['physics'] += time.monotonic()-at
        advance(float(world.data.time)+.5)
        origin = float(world.data.time)
        inst = next(x for x in scene.cargo if x.item_id == CRATE.item_id)
        band = BandVisibility(world.model, CRATE)
        region = plan['destination_region']
        slots = destination_slot_geoms([world.model.geom(g).name for g in range(world.model.ngeom)], region) if zone_slots == 'zone' else []
        report['zone_slot_geoms'] = [world.model.geom(g).name for g in slots]
        eyes = Eyes(band, world.model.geom('zone_'+region).id, slots)
        object_bodies = {c.item_id: c.body for c in scene.cargo}
        object_bodies.update({i: c['body_name'] for i, c in scene.config['setup_only']['objects'].items()})
        ev = (out/'eval-only.jsonl').open('w')
        streams.append(ev)
        labels = {rid: (out/f'teacher-{rid}.jsonl').open('w') for rid in roles}
        streams += labels.values()
        (out/'eval-overview').mkdir()
        for rid in roles:
            (out/'eval-own'/rid).mkdir(parents=True)

        def frames(i, tag):
            at = time.monotonic()
            overview = Image.new('RGB', (640, 480))
            for k, camera in enumerate(static['top_cameras'][:4]):
                f = Image.open(io.BytesIO(world.render_team_jpeg(camera=camera['name'])))
                overview.paste(f.resize((320, 240)), ((k % 2)*320, (k//2)*240))
            overview.save(out/'eval-overview'/f'{i:06d}-{tag}.jpg', quality=86)
            for rid in roles:
                jpg = base64.b64decode(ports[rid].capture()['image'])
                Image.open(io.BytesIO(jpg)).resize((320, 240)).save(out/'eval-own'/rid/f'{i:06d}-{tag}.jpg', quality=86)
            timings['rgb'] += time.monotonic()-at

        # ======================= stage 1: grasp, lift barrier, joint hold =======================
        import random as _random
        rng = _random.Random(plan['seed'])
        delays = {rid: (0. if k == 0 else rng.uniform(0, 1.5)) for k, rid in enumerate(roles)}
        start_sync = GraspStartSync(tuple(roles), delays)
        lift_sync = GraspStartSync(tuple(roles), {rid: 0. for rid in roles})
        report['grasp_start_delays_s'] = delays
        teachers, models, clocks, previous = {}, {}, {}, {}
        for rid, end in roles.items():
            pwm = {str(s): int(ports[rid]._servo_pulses[s]) for s in v5.SERVOS}
            previous[rid] = v5.command({'t': origin, 'wheels': [0.]*4, 'duration_s': [0.]*4, 'pwm': pwm})
            teachers[rid] = make_grasp_teacher(rid, end, pwm, teacher_stability=teacher_stability,
                                               teacher_search=teacher_search, approach_goal_set=approach_goal_set,
                                               crate_lift_pose=crate_lift_pose)
            models[rid] = VisibleWorld(rid, end, pose_source='issued', profile=CRATE)
            clocks[rid] = v5.IssuedClock()
        i = 0
        both_since = None
        all_done_since = None
        max_hold = 0.
        held = None
        release_authorized_at = None
        verdict = {}
        rgb_before = rgb_after = None
        from sim.crate_rgb_lift import LiftObserver
        lift_observers = {rid: LiftObserver(end, mode=rgb_lift if rgb_lift in ('crate_rgb_lift_v2', 'crate_rgb_lift_v3') else 'crate_rgb_lift_v2') for rid, end in roles.items()}
        lift_frames = {rid: {} for rid in roles}

        def lift_capture(rid, tag, now):
            # Review evidence, not training RGB. Same own camera as the teacher.
            import hashlib
            rgb = own_rgb(ports[rid])
            path = out/'eval-own'/rid/f'lift-v2-{tag}.png'
            Image.fromarray(rgb).save(path)
            lift_frames[rid][tag] = {'t': now, 'path': str(path.relative_to(out)),
                                    'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            return rgb

        lift_window_t0 = None
        lift_load = {}
        handoff_log = {}
        lugs_at_hold = None
        while float(world.data.time)-origin < grasp_cap_s-1e-8:
            now = float(world.data.time)
            at = time.monotonic()
            truth = snapshot_cargo(world, inst, roles, scene)
            truth['visibility'] = {rid: band.measure(world.data, rid, end) for rid, end in roles.items()}
            perceived = {}
            truth['visible_measurements'] = {}
            for rid, end in roles.items():
                # The synchronized lift needs only its already-issued arm sequence.
                # Hide all cargo measurements for both robots from the first lift command.
                holding = any(t.phase in ('lift', 'complete') for t in teachers.values())
                ms = grasp_inputs(lambda: measurements(world, band, rid, end, object_bodies), holding=holding, audit=audit)
                truth['visible_measurements'][rid] = ms
                v = truth['visibility'][rid]
                v['any_probe_visible'] = v['visible']
                v['visible'] = v['visible_probes'] >= 5
                perceived[rid] = models[rid].observe(ms, now)
            timings['evaluation'] += time.monotonic()-at
            if i % 10 == 0:
                frames(i, 'grasp')
                write(out/'progress.json', {'stage': 'grasp', 'sim_s': now-origin, 'wall_s': time.monotonic()-start,
                                            'phases': {r: t.phase for r, t in teachers.items()}, 'timings_s': timings})
                for stream in streams:
                    stream.flush()
            both = all(min(truth['contacts'][rid]) >= LIFT_FORCE_N for rid in roles) and truth['beam']['min_z'] >= .012 \
                and truth['beam']['tilt_deg'] <= 10.
            both_since = (now if both_since is None else both_since) if both else None
            held_s = 0. if both_since is None else now-both_since
            max_hold = max(max_hold, held_s)
            if held is None and held_s >= HOLD_S:
                held = now
                lugs_at_hold = held_lugs(world, inst, roles)
            ready = {rid: t.prepare_signal(perceived[rid], now) for rid, t in teachers.items()}
            permits = start_sync.tick(ready, now)
            lift_permits = lift_sync.tick({rid: t.lift_ready() for rid, t in teachers.items()}, now)
            for rid, t in teachers.items():
                at = time.monotonic()
                skill = 'wait' if ((t.phase == 'ready' and not permits[rid]) or (t.phase == 'closed' and not lift_permits[rid])) else 'grasp'
                elapsed = clocks[rid].observe((skill, t.end, t.handoff), now, previous[rid]['pwm'])
                t.skill_started = now-elapsed['skill_elapsed_s']
                clean, done = t.step(perceived[rid], now, permit_pick=permits[rid], permit_lift=lift_permits[rid])
                timings['teacher'] += time.monotonic()-at
                applied = json.loads(json.dumps(clean))
                v5.command(applied)
                apply(ports[rid], applied, now, previous[rid])
                previous[rid] = applied
                models[rid].issue(applied)
                t.remember_applied(applied)
                if t.handoff and rid not in handoff_log:
                    # evaluation only: how far the partner and each lug were when the teacher's own estimate said 'near'
                    other = [r for r in roles if r != rid][0]
                    handoff_log[rid] = {
                        't': now, 'partner_distance_m': math.dist(truth['robots'][rid]['pose'][:2], truth['robots'][other]['pose'][:2]),
                        'lug_distance_m': {e: math.dist(truth['robots'][rid]['pose'][:2], g[:2]) for e, g in truth['beam']['ends'].items()},
                        'own_end': t.end}
                labels[rid].write(json.dumps({
                    't': now, 'sample_id': f"{plan['episode_id']}:{i}:{rid}", 'object_kind': 'heavy_crate',
                    'role': CRATE.role_of(t.end), 'skill': skill, 'done': done, 'teacher_phase': t.phase,
                    'clean_teacher_command': clean, 'applied_command': applied, 'handoff': t.handoff,
                    'skill_elapsed_s': elapsed['skill_elapsed_s'], 'pwm_elapsed_s': elapsed['pwm_elapsed_s'],
                    'assignment_source': plan['assignment_source'],
                    'skill_instruction_source': 'GO_ACK_code_messages; demo own READY; runtime LLM skill'})+'\n')
            load_row = servo_load(world, roles)
            if lift_window_t0 is None and any(lift_permits.values()):
                lift_window_t0 = now                      # own lift permit tick: the lift window opens
            if lift_window_t0 is not None:
                for rid, row in load_row.items():
                    for name, ratio in row.items():
                        cell = lift_load.setdefault(rid, {}).setdefault(name, {'max_abs_ratio': 0., 't_at_max': None, 'saturated_samples': 0, 'samples': 0})
                        cell['samples'] += 1
                        cell['saturated_samples'] += int(abs(ratio) >= .98)
                        if abs(ratio) > cell['max_abs_ratio']:
                            cell['max_abs_ratio'], cell['t_at_max'] = abs(ratio), now-lift_window_t0
            ev.write(json.dumps({'stage': 'grasp', 't': now, 'crate': truth['beam'], 'contacts': truth['contacts'],
                                 'cargo_scene_version': plan['cargo_scene_version'], 'crate_lift_pose': crate_lift_pose,
                                 'lift_pose_selection': {r: t.lift_selection for r, t in teachers.items()},
                                 'robots': {r: truth['robots'][r] for r in roles}, 'held_s': held_s,
                                 'visible_probes': {r: truth['visibility'][r]['visible_probes'] for r in roles},
                                 # Exact inputs for offline decision replay. Keep these separate
                                 # from evaluation truth; never reconstruct missing inputs from GT.
                                 'visible_measurements': truth['visible_measurements'],
                                 'pick_permits': permits, 'lift_permits': lift_permits,
                                 'servo_load': load_row,
                                 'phases': {r: t.phase for r, t in teachers.items()}})+'\n')
            if rgb_lift in ('crate_rgb_lift_v2', 'crate_rgb_lift_v3'):
                for rid, t in teachers.items():
                    value = lift_observers[rid].observe(permit=lift_permits[rid], complete=t.command_complete,
                        command=previous[rid], capture=lambda tag, rid=rid: lift_capture(rid, tag, now))
                    if value is not None:
                        verdict[rid] = value
            elif rgb_lift == 'crate_rgb_lift_v1':
                # own frames: one at the first tick any robot has its own lift permit, one when every robot's own
                # lift sequence has completed (own commands only); no evaluator state
                if rgb_before is None and any(lift_permits.values()):
                    rgb_before = {rid: own_rgb(ports[rid]) for rid in roles}
                if rgb_before is not None and rgb_after is None and all(t.command_complete for t in teachers.values()):
                    rgb_after = {rid: own_rgb(ports[rid]) for rid in roles}
                    from sim.crate_rgb_lift import confirm
                    verdict = {rid: confirm(rgb_before[rid], rgb_after[rid], roles[rid]) for rid in roles}
            if all(t.command_complete for t in teachers.values()):
                all_done_since = now if all_done_since is None else all_done_since
                if release_ready({r: t.command_complete for r, t in teachers.items()}, now-all_done_since, verdict):
                    release_authorized_at = now
                    break
                if now-all_done_since >= 6.+HOLD_S:
                    break
            if any(t.outcome not in (None, 'success') for t in teachers.values()):
                break
            i += 1
            advance(origin+i*.1)
        grasp_end = float(world.data.time)
        from scripts.run_grasp_act_teacher import finalize_outcomes
        finalize_outcomes(teachers, strict=True, joint_held=held is not None)
        outcomes = {rid: t.outcome for rid, t in teachers.items()}
        report['search_handoff'] = 'search_timeout_handoff' in outcomes.values()
        report['search_handoff_n'] = sum(v == 'search_timeout_handoff' for v in outcomes.values())
        report['peer_search_handoff_n'] = sum(v == 'peer_search_handoff' for v in outcomes.values())
        report['prefix_held'] = held is not None
        report['release_authorized_by_own_inputs'] = release_authorized_at is not None
        report['prefix'] = {
            'held_sim_s': None if held is None else held-origin, 'sim_s': grasp_end-origin, 'outcomes': outcomes,
            'servo_load_lift_window': {'window': 'own lift permit tick .. end of the grasp stage (lift + hold)', 't0_sim_s': None if lift_window_t0 is None else lift_window_t0-origin,
                                       'per_robot': lift_load, 'ratio': 'actuator force / force limit; evaluation only'},
            'max_stable_hold_s': max_hold, 'lift_protocol': lift_sync.events, 'start_protocol': start_sync.events,
            'lugs_at_hold': lugs_at_hold, 'handoff': handoff_log,
            'assigned': dict(roles), 'distinct_lugs_at_hold': (None if lugs_at_hold is None else
                {'ok': len({v['nearest_lug'] for v in lugs_at_hold.values()}) == 2 and all(lugs_at_hold[r]['nearest_lug'] == roles[r] for r in roles)}),
            'teachers': {rid: t.diagnostic() for rid, t in teachers.items()}}
        if rgb_lift != 'off':
            verdict = {rid: verdict.get(rid, {'verdict': 'undetermined', 'reason': 'frames not captured'})
                       for rid in roles}
            # evaluation-only truth next to it so the agreement can be counted
            unknown = sum(v['verdict'] == 'undetermined' for v in verdict.values())
            report['prefix']['rgb_lift'] = {'rule': rgb_lift, 'per_robot': verdict,
                                            'undetermined_n': unknown, 'N': len(roles),
                                            'undetermined_rate': unknown/len(roles), 'frames': lift_frames,
                                            'evaluation_truth': {'held_by_gt': held is not None, 'max_stable_hold_s': max_hold,
                                                                 'scope': 'evaluation only; RGB thresholds provisional'}}
        if release_authorized_at is None:
            report.update(status='complete', release_success=None, release_outcome='lift_not_confirmed_by_own_inputs')
            return report

        # ======================= stage 2: set-down (visible_only release teacher) =======================
        for port in ports.values():
            port.stop()
        rel = {}
        for rid, end in roles.items():
            # Unanchored command odometry cannot be converted to the static map
            # by adding noise to GT. No map prior until a real localization exists.
            estimate = None if own_pose_source == 'commands' else [*world.robot(rid).base_xyz()[:2],
                                                                    float(world.robot(rid).base_rpy()[2])]
            pwm = {int(s): int(ports[rid]._servo_pulses[s]) for s in v5.SERVOS}
            rel[rid] = CrateReleaseTeacher(rid, end, pwm, handoff_pose_estimate=estimate, zone_rect=rect,
                                           own_pose_source=own_pose_source, reach_mode=reach_mode)
        R = tuple(roles)
        code = PairReleaseCode(R)
        release_t0 = float(world.data.time)
        st = {'phase': 'look', 'since': release_t0, 'iter': 0, 'steps': 0, 'search': 0, 'sched': {}, 'plan': {}, 'go': None,
              'after_visible': False, 'choice': None}
        b0 = world.data.body(inst.body)
        report['release_start'] = {'crate_to_zone_center_m': float(math.dist(b0.xpos[:2], rect[:2]))}

        def pose_of(rid):
            return [*map(float, world.robot(rid).base_xyz()[:2]), float(world.robot(rid).base_rpy()[2])]

        def observe(rid, now, fine):
            at = time.monotonic()
            data = world.data
            pose = pose_of(rid)
            t = rel[rid]
            if t.holding and held_object == 'hidden_v1':
                (ex, ey), (ox, oy), _ = t.end_and_outward(now)
                c_, s_ = math.cos(pose[2]), math.sin(pose[2])
                e = np.array([pose[0]+c_*ex-s_*ey, pose[1]+s_*ex+c_*ey, 0.])
                out_dir = np.array([c_*ox-s_*oy, s_*ox+c_*oy, 0.])
            else:
                audit.read(t.holding, 'scan_axis')
                audit.read(t.holding, 'scan_end')
                b = data.body(inst.body)
                axis = b.xmat.reshape(3, 3)[:, 0]
                out_dir = -axis if roles[rid] == 'teal' else axis
                e = own_end_world(world, inst, roles[rid])
            lat = np.array([-out_dir[1], out_dir[0], 0.])
            scan = []
            for s_ in np.arange(-.25, .2501, .01 if fine else .05):
                for l_ in (-CRATE.scan_lateral_m, CRATE.scan_lateral_m):
                    p = e+s_*out_dir+l_*lat
                    p = (float(p[0]), float(p[1]), .0012)
                    c = eyes.classify(data, rid, p)
                    if c is not None:
                        scan.append([*relative(pose, p[:2])[:2], c])
                        audit.measurement(st['phase'], 'scan_point', True)
            m = band.measure(data, rid, roles[rid])
            obs = {'scan': scan, 'own_band_visible': m['visible_probes'] >= 3, 'band': None}
            if obs['own_band_visible'] and not (t.holding and held_object == 'hidden_v1'):
                audit.read(t.holding, 'band_pose')
                audit.measurement(st['phase'], 'own_band_pose', m['visible_probes'] >= 3)
                gid = band.bands[roles[rid]]
                g = data.geom_xpos[gid]
                rot = data.body(inst.body).xmat.reshape(3, 3)
                obs['band'] = relative(pose, (float(g[0]), float(g[1])), math.atan2(rot[1, 0], rot[0, 0]))
            obs['partner_visible'] = any(band.body_visible(data, rid, p+'__robot') for p in roles if p != rid)
            timings['eyes'] += time.monotonic()-at
            return obs

        def post(tag, now):
            for rid, t in rel.items():
                code.post(rid, {**(t.last_report or {}), 'phase': tag}, now)

        def ready_to(tag, now):
            code.deliver(now)
            return code.ready(tag, st['since'])

        def schedule(rid, seq, t0):
            st['sched'][rid] = [(t0+dt, p) for dt, p in seq]

        def run_sched(now):
            for rid, seq in st['sched'].items():
                while seq and seq[0][0] <= now+1e-9:
                    _, pose = seq.pop(0)
                    for sid, v in pose.items():
                        if rel[rid].pwm.get(sid) != v:
                            ports[rid].apply({'kind': 'look', 'pan_pulse': v} if sid == 6 else {'kind': 'arm', 'servo_id': sid, 'pulse': v}, now)
                            rel[rid].pwm[sid] = v
            return any(st['sched'].values())

        def run_plan(now):
            busy = False
            for rid, p in st['plan'].items():
                if p:
                    w, d = p.pop(0)
                    wheels[rid].command(w, d, now)
                    busy = True
            return busy

        def every(seq_fn, interval):
            return [(interval*(k+1), p) for k, p in enumerate(seq_fn)]

        def start_lower(now):
            for rid, t in rel.items():
                schedule(rid, every(t.arm_waypoints(LOWER_Z_M, 8), .2), now+.2)
            st.update(phase='lower', since=now, go=now+.2, end=now+.2+1.6+.6)

        def start_shift(now, s):
            st['plan'] = {rid: t.shift_plan(s, 1. if rid == R[0] else -1.) for rid, t in rel.items()}
            st.update(phase='shift', since=now, go=now+.2)

        # own pose estimate for the look-around (map frame, own commands only; truth only scores it)
        la = None
        if lookaround != 'off':
            from sim import crate_lookaround as cl
            lam = cl.load_module()
            la = {'mod': lam, 'est': {}, 'plans': {}, 'script': {}, 'log': {}, 'landmarks': cl.landmarks_from_map(static)}
            for rid in roles:
                base = world.robot(rid).base_xyz()
                err = plan['handoff_pose_error'][rid]
                la['est'][rid] = lam.OwnPose([float(base[0])+err[0], float(base[1])+err[1],
                                              float(world.robot(rid).base_rpy()[2])+err[2]])
        nrng = np.random.default_rng(plan['seed']+1)
        k = 0
        outcome = None
        done_at = None
        while float(world.data.time)-origin < grasp_end-origin+cap_s:
            now = float(world.data.time)
            tick_t = now
            ph = st['phase']
            age = now-st['since']
            fine = ph in ('look', 'observe')
            for rid, t in rel.items():
                t.phase = ph
                t.perceive(observe(rid, now, fine), now)
            if ph == 'look' and age >= .6:
                for t in rel.values():
                    t.report(now, 'look')
                post('look', now)
                st.update(phase='await_look', since=now)
            elif ph == 'await_look' and ready_to('look', now):
                choice = code.decide(now, require_seen=False)
                st['choice'] = choice
                if choice['action'] == 'lower' or st['steps'] >= 8:
                    start_lower(now)
                else:
                    st['steps'] += 1
                    start_shift(now, choice['shift_m'])
            elif ph == 'shift' and now >= st['go']-1e-9:
                if not run_plan(now):
                    if st['after_visible']:
                        st['after_visible'] = False
                        start_lower(now)
                    else:
                        st.update(phase='look', since=now)
            elif ph == 'lower':
                run_sched(now)
                if now >= st['end']-1e-9:
                    for t in rel.values():
                        t.last_report = {'kind': 'lowered'}
                    post('lowered', now)
                    st.update(phase='await_open', since=now)
            elif ph == 'await_open' and ready_to('lowered', now):
                st.update(phase='open', since=now, go=now+.2, opened=False)
            elif ph == 'open' and now >= st['go']-1e-9:
                if not st['opened']:
                    for rid, t in rel.items():
                        ports[rid].apply({'kind': 'arm', 'servo_id': 1, 'pulse': 2000}, now)
                        t.pwm[1] = 2000
                    st['opened'] = True
                if now-st['go'] >= 1.2 and observe_mode == 'backoff_v3':
                    for rid, t in rel.items():
                        t.released_here(now)
                        schedule(rid, every(t.arm_waypoints(RAISE_Z_M, 3), .2), now)
                    st['plan'] = {rid: t.shift_plan(OBSERVE_BACKOFF_M, -1.) for rid, t in rel.items()}
                    st.update(phase='observe_back', since=now, go=now+.8, settle=None, search=0)
                elif now-st['go'] >= 1.2:
                    for rid, t in rel.items():
                        t.released_here(now)
                        seq = every(t.arm_waypoints(RAISE_Z_M, 3), .2)
                        schedule(rid, seq+[(1.0, t.gaze_target(now))], now)
                    st.update(phase='observe_move', since=now, end=now+1.0+.8, search=0)
            elif ph == 'observe_back':
                run_sched(now)
                if now >= st['go']-1e-9 and not run_plan(now):
                    if st['settle'] is None:
                        st['settle'] = now+.3
                    elif now >= st['settle']-1e-9:
                        for rid, t in rel.items():
                            schedule(rid, [(0., t.gaze_target(now))], now)
                        st.update(phase='observe_move', since=now, end=now+.8)
            elif ph == 'observe_move':
                run_sched(now)
                if now >= st['end']-1e-9:
                    st.update(phase='observe', since=now)
            elif ph == 'observe' and age >= .6:
                reports = {rid: t.report(now, 'observe') for rid, t in rel.items()}
                blind = [rid for rid, r in reports.items() if r['kind'] == 'prior']
                if blind and st['search'] < 4:
                    st['search'] += 1
                    offset = (250, -250, 500, -500)[st['search']-1]
                    for rid in blind:
                        target = dict(rel[rid].gaze_target(now))
                        target[6] = max(500, min(2500, target[6]+offset))
                        schedule(rid, [(0., target)], now)
                    st.update(phase='observe_move', since=now, end=now+.8)
                else:
                    post('observe', now)
                    st.update(phase='await_observe', since=now)
            elif ph == 'await_observe' and ready_to('observe', now):
                choice = code.decide(now, require_seen=True)
                st['choice'] = choice
                if choice['action'] == 'lower' and observe_mode == 'backoff_v3':
                    for rid in rel:
                        schedule(rid, [(0., FOLDED_BACKOFF)], now)
                    st.update(phase='lookaround' if la else 'done', since=now)
                    done_at = now
                elif choice['action'] == 'lower':
                    for rid, t in rel.items():
                        schedule(rid, [(0., {3: 820, 4: 2320})], now)
                    st['plan'] = {rid: t.shift_plan(BACKOFF_M, -1.) for rid, t in rel.items()}
                    st.update(phase='back_off', since=now, go=now+.6)
                else:
                    st['iter'] += 1
                    if st['iter'] > 3:
                        outcome = 'release_iteration_cap'
                        break
                    for rid, t in rel.items():
                        audit.pick('approach', rid, now, t)
                    st['plan'] = {rid: t.approach_plan(now) for rid, t in rel.items()}
                    for rid, pl in st['plan'].items():
                        if pl:
                            schedule(rid, [(0., {kk: int(v) for kk, v in solve_grip_site_ik((MOUNT_X_M+rel[rid].reach_mid(), 0., .095)).items() if kk in (3, 4, 5, 6)})], now)
                    moving = any(st['plan'].values())
                    st.update(phase='approach', since=now, go=now+(.8 if moving else 0.), settle=None, moving=moving)
            elif ph == 'approach':
                run_sched(now)
                if now >= st['go']-1e-9 and not run_plan(now):
                    if st['settle'] is None:
                        st['settle'] = now+(.3 if st['moving'] else 0.)
                    if now >= st['settle']-1e-9:
                        dur = 0.
                        try:
                            for rid, t in rel.items():
                                audit.pick('repick', rid, now, t)
                                seq, d = t.pick_schedule(now)
                                schedule(rid, seq, now+.2)
                                dur = max(dur, d)
                        except ValueError as error:
                            report['repick_error'] = str(error)
                            outcome = 'repick_unreachable'
                            break
                        st.update(phase='repick', since=now, end=now+.2+dur)
            elif ph == 'repick':
                run_sched(now)
                if now >= st['end']-1e-9:
                    for t in rel.values():
                        t.holding = True
                    st['after_visible'] = True
                    start_shift(now, st['choice']['shift_m'])
            elif ph == 'back_off':
                run_sched(now)
                if now >= st['go']-1e-9 and not run_plan(now):
                    for rid, t in rel.items():
                        schedule(rid, [(0., FOLDED_BACKOFF)], now)
                    st.update(phase='lookaround' if la else 'done', since=now)
                    done_at = now
            elif ph == 'lookaround':
                run_sched(now)
                if not _lookaround_step(world, la, rel, roles, eyes, ports, wheels, st, now, nrng, cl, plan, lookaround_log=report.setdefault('lookaround', {})):
                    st.update(phase='done', since=now)
            elif ph == 'done':
                run_sched(now)
                if age >= DELIVERY_WAIT_S:
                    outcome = 'teacher_done'
                    break
            for rid, t in rel.items():
                labels[rid].write(json.dumps({
                    't': now, 'skill': 'release', 'object_kind': 'heavy_crate', 'role': CRATE.role_of(roles[rid]),
                    'teacher_phase': st['phase'], 'wheels': list(wheels[rid].levels), 'wheel_until': list(wheels[rid].until),
                    'pwm': {str(s): t.pwm[s] for s in v5.SERVOS}, 'holding_belief': t.holding,
                    'done': st['phase'] == 'done', 'report': t.last_report})+'\n')
            if k % 10 == 0:
                frames(k, 'release-'+st['phase'])
            issued = {rid: (list(wheels[rid].levels),
                            max([max(0., min(.1, u-tick_t)) if lv else 0. for lv, u in zip(wheels[rid].levels, wheels[rid].until)]))
                      for rid in rel}
            before = {rid: pose_of(rid) for rid in rel} if own_pose_source == 'truth_comparison' else None
            k += 1
            advance(tick_t+.1)
            for rid, t in rel.items():
                if la is not None:
                    dx, dy, da = odometry(*issued[rid])
                    la['est'][rid].propagate(dx, dy, da)
                if own_pose_source == 'commands':
                    t.dead_reckon(*issued[rid])
                else:
                    after = pose_of(rid)
                    dx, dy, da = relative(before[rid], after[:2], after[2])
                    t.belief.propagate(dx, dy, da)
            truth = snapshot_cargo(world, inst, roles, scene)
            ev.write(json.dumps({'stage': 'release', 't': float(world.data.time), 'phase': st['phase'], 'crate': truth['beam'],
                                 'cargo_scene_version': plan['cargo_scene_version'], 'crate_lift_pose': crate_lift_pose,
                                 'contacts': truth['contacts'], 'robots': {r: truth['robots'][r] for r in roles}})+'\n')
        report['release_outcome'] = outcome or 'release_timeout'

        # ======================= evaluation (truth) =======================
        checks = []
        for j in range(int((SUCCESS['settle_s']+.5)/.1)):
            now = float(world.data.time)
            b = world.data.body(inst.body)
            rot = b.xmat.reshape(3, 3)
            yaw = math.atan2(rot[1, 0], rot[0, 0])
            forces = snapshot_cargo(world, inst, roles, scene)['contacts']
            fit = landing_fits('heavy_crate', (float(b.xpos[0]), float(b.xpos[1]), yaw), rect)
            tilt = max(abs(math.degrees(math.asin(max(-1, min(1, rot[2, 0]))))), abs(math.degrees(math.atan2(rot[2, 1], rot[2, 2]))))
            clear = []
            for rid in roles:
                g = world.data.site(f'{rid}__grip_site').xpos
                a = b.xpos+rot@np.array([-CRATE.landing_end_m, 0, 0])
                c = b.xpos+rot@np.array([CRATE.landing_end_m, 0, 0])
                u = (c-a)/np.linalg.norm(c-a)
                q = a+u*max(0., min(2*CRATE.landing_end_m, float((g-a)@u)))
                clear.append(float(np.linalg.norm(g-q)))
            checks.append({'t': now, 'fit': fit, 'z': float(b.xpos[2]), 'tilt_deg': tilt, 'contact_n': {r: list(forces[r]) for r in roles},
                           'grip_to_crate_m': clear, 'open_pwm': {r: rel[r].pwm[1] for r in roles},
                           'crate_xy_yaw': [float(b.xpos[0]), float(b.xpos[1]), yaw]})
            advance(now+.1)

        def good(r, prev):
            speed = 0. if prev is None else math.dist(r['crate_xy_yaw'][:2], prev['crate_xy_yaw'][:2])/.1
            return (r['fit'] and r['z'] < SUCCESS['on_floor_z_m'] and r['tilt_deg'] < SUCCESS['tilt_deg'] and speed < SUCCESS['speed_m_s']
                    and all(max(v) < 1e-6 for v in r['contact_n'].values()) and all(p >= SUCCESS['open_pwm'] for p in r['open_pwm'].values())
                    and min(r['grip_to_crate_m']) >= SUCCESS['clear_m'])
        streak = 0
        best = 0
        for idx, r in enumerate(checks):
            streak = streak+1 if good(r, checks[idx-1] if idx else None) else 0
            best = max(best, streak)
        last = checks[-1]
        report['evaluation_position_error'] = position_error(last['crate_xy_yaw'], rect, half_len=CRATE.landing_end_m)
        reasons = [n for n, v in (('not_in_zone', not last['fit']), ('not_on_floor', last['z'] >= SUCCESS['on_floor_z_m']),
                                  ('tilt', last['tilt_deg'] >= SUCCESS['tilt_deg']),
                                  ('finger_contact', any(max(v) > 1e-6 for v in last['contact_n'].values())),
                                  ('gripper_closed', any(p < SUCCESS['open_pwm'] for p in last['open_pwm'].values())),
                                  ('gripper_not_clear', min(last['grip_to_crate_m']) < SUCCESS['clear_m'])) if v]
        report.update(release_success=best*.1 >= SUCCESS['settle_s']-1e-6 and report['release_outcome'] == 'teacher_done',
                      release_failure_reasons=reasons if reasons else ([] if report['release_outcome'] == 'teacher_done' else [report['release_outcome']]),
                      evaluation_last=last, evaluation_settled_s=best*.1, code_decisions=code.log, shift_steps=st['steps'],
                      iterations=st['iter'], release_teachers={rid: t.diagnostic() for rid, t in rel.items()},
                      release_sim_s=(done_at or float(world.data.time))-release_t0, status='complete')
        return report
    except BaseException as error:
        report.update(status='HOST_ERROR' if not isinstance(error, KeyboardInterrupt) else 'interrupted',
                      error_type=type(error).__name__, error=str(error))
        raise
    finally:
        report['wall_s'] = time.monotonic()-start
        report['sim_s'] = None if world is None else float(world.data.time)-origin
        report['loadavg_at_end'] = os.getloadavg()
        report['input_audit'] = audit.record()
        if isinstance(report.get('release_teachers'), dict):
            report['input_audit']['visibility_by_phase'] = {r: t.get('visible_counts_by_phase') for r, t in report['release_teachers'].items()}
            report['input_audit']['max_destination_blind_s_by_phase'] = {r: t.get('max_destination_blind_s_by_phase') for r, t in report['release_teachers'].items()}
        # Grasp-stage decision inputs are relative visible measurements and own commands only (VisibleWorld).
        report['input_audit']['grasp_stage_inputs'] = 'VisibleWorld(visible relative measurements + issued commands); no world crate pose'
        report['input_audit']['scope'] = 'grasp and release decision inputs; GT hold and handoff distances evaluation only'
        report['input_audit']['release_map_prior'] = 'disabled without verified map localization' if own_pose_source == 'commands' else 'truth_comparison'
        try:
            report['timings_s'] = timings
        except NameError:
            pass
        write(out/'result.json', report)
        for s in streams:
            s.close()
        if world is not None:
            world.close()
        compress_logs(out)


def _lookaround_step(world, la, rel, roles, eyes, ports, wheels, st, now, nrng, cl, plan, lookaround_log):
    """One tick of ``setdown_lookaround_v1``; returns True while still running.

    Plan (once): ``plan_views`` from each robot's own pose estimate (map pose after the set-down,
    moved only by own commands). Execute: rotate (if the plan asks), pan, dwell, then for every
    expected landmark that really is in view (ray check by the evaluation owner) feed its
    body-frame bearing (+1.5 deg noise) to the EKF. Truth only gates visibility, supplies the
    bearings of the visible landmarks, and scores pose error before/after (evaluation only).
    """
    import numpy as np
    lam = la['mod']
    steps = st.setdefault('la', {})
    if not steps:
        pred = cl.visible_predictor()
        for rid in roles:
            est = la['est'][rid]
            p = lam.plan_views(tuple(est.x), est.P, la['landmarks'], pred)
            steps[rid] = {'script': cl.execution_script(p), 'idx': 0, 'stage': 'start', 'until': now, 'yaw_done_deg': 0.,
                          'plan': p, 'seen': set()}
            lookaround_log[rid] = {'planned_views': len(steps[rid]['script']), 'expected_landmarks': p['expected_landmarks'],
                                   'expected_gain_nats': p['expected_gain_nats'], 'rotated': p['rotated'],
                                   'est_before': list(map(float, est.x)),
                                   'error_before_m': float(math.hypot(*(est.x[:2]-np.array(world.robot(rid).base_xyz()[:2])))),
                                   'seen_landmarks': [], 'accepted_updates': 0, 'rejected_updates': 0}
    busy = False
    for rid, s in steps.items():
        if s['idx'] >= len(s['script']):
            continue
        busy = True
        v = s['script'][s['idx']]
        if now < s['until']-1e-9:
            continue
        if s['stage'] == 'start':
            dyaw = math.radians(v['body_yaw_deg']-s['yaw_done_deg'])
            if abs(dyaw) > 1e-6:
                st.setdefault('plan', {})[rid] = cl.rotation_plan(dyaw)
                s['yaw_done_deg'] = v['body_yaw_deg']
                s['stage'] = 'rotating'
            else:
                s['stage'] = 'pan'
        if s['stage'] == 'rotating':
            if st['plan'].get(rid):
                w, d = st['plan'][rid].pop(0)
                wheels[rid].command(w, d, now)
                continue
            s['stage'] = 'pan'
        if s['stage'] == 'pan':
            ports[rid].apply({'kind': 'look', 'pan_pulse': cl.pan_pulse(v['pan_deg'])}, now)
            rel[rid].pwm[6] = cl.pan_pulse(v['pan_deg'])
            s['stage'] = 'dwell'
            s['until'] = now+cl.DWELL_S
            continue
        if s['stage'] == 'dwell':
            est = la['est'][rid]
            data = world.data
            pose = [*map(float, world.robot(rid).base_xyz()[:2]), float(world.robot(rid).base_rpy()[2])]
            lms = {l['id']: l for l in la['landmarks']}
            for lid in v['landmarks']:
                lm = lms[lid]
                point = np.array([lm['xy'][0], lm['xy'][1], .05])
                if eyes.visible(data, rid, point):
                    bearing = lam.predicted_bearing(pose, lm['xy'])+float(nrng.normal(0, lam.BEARING_SIGMA_RAD))
                    ok = est.update_bearing(lm['xy'], lam.wrap(bearing), label=lid)
                    s['seen'].add(lid)
                    lookaround_log[rid]['accepted_updates' if ok else 'rejected_updates'] += 1
            s['idx'] += 1
            s['stage'] = 'start'
    done = not busy
    if done:
        for rid, s in steps.items():
            est = la['est'][rid]
            truth_xy = np.array(world.robot(rid).base_xyz()[:2])
            lookaround_log[rid].update(
                seen_landmarks=sorted(s['seen']), n_seen=len(s['seen']), est_after=list(map(float, est.x)),
                error_after_m=float(math.hypot(*(est.x[:2]-truth_xy))),
                scope='landmark visibility gated by ray check; bearings are truth of visible landmarks + noise '
                      '(visible_only convention); recognizer-based count not available (확인 안 됨)')
    return not done


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--episode', type=int, default=0)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--cap-s', type=float, default=90., help='set-down stage cap (SIM seconds)')
    p.add_argument('--grasp-cap-s', type=float, default=80., help='approach/grasp/lift stage cap (SIM seconds)')
    p.add_argument('--own-pose-source', choices=('commands', 'truth_comparison'), default='commands')
    p.add_argument('--observe-mode', choices=OBSERVE_MODES, default='gaze_v2')
    p.add_argument('--render-dr', choices=('off', 'on_v1'), default='off')
    p.add_argument('--zone-slots', choices=ZONE_SLOT_MODES, default='floor')
    p.add_argument('--reach-mode', choices=REACH_MODES, default='calibrated_mid_v1')
    p.add_argument('--held-object', choices=HELD_OBJECT_MODES, default='visible_v0')
    p.add_argument('--setdown-lookaround', choices=LOOKAROUND_MODES, default='off',
                   help='setdown_lookaround_v1: look at static-map landmarks after the set-down (needs sim/active_lookaround.py)')
    p.add_argument('--crate-scene', choices=tuple(CARGO_SCENE_VERSIONS), default='catalogue_v1',
                   help='cargo scene version: catalogue_v1 = crate 0.900 kg (old), crate_mass_030_v1 = 0.300 kg '
                        '(user 2026-10-14; real_v1 elbow limit). Versions are never pooled.')
    p.add_argument('--crate-lift-pose', choices=LIFT_POSE_MODES, default='off',
                   help='crate_lift_pose_margin_v1: retain >=10%% static elbow margin at 0.125 kg/arm; no candidate stops')
    p.add_argument('--rgb-lift', choices=RGB_LIFT_MODES, default='off',
                   help='authorize release only after own-RGB confirmation; v2 uses lug/body co-motion; provisional thresholds')
    p.add_argument('--teacher-stability', choices=('off', 'align_relook_v1'), default='off')
    p.add_argument('--teacher-search', choices=('off', 'search_body_scan_v1', 'search_body_scan_v2', 'search_reacquire_v1'), default='off')
    p.add_argument('--approach-goal-set', choices=('off', 'approach_goal_set_v1'), default='off')
    p.add_argument('--execution-host', choices=('azure', 'gcp1'), default='gcp1')
    p.add_argument('--pr', type=int, default=None)
    a = p.parse_args()
    if not (0 < a.cap_s <= 180 and 0 < a.grasp_cap_s <= 180):
        raise ValueError('finite caps required')
    from scripts.grasp_act_host import identity
    host = identity(a.execution_host)
    plan = json.loads(a.plan.read_text())['episodes'][a.episode]
    print(json.dumps(run(plan, a.out, cap_s=a.cap_s, grasp_cap_s=a.grasp_cap_s, own_pose_source=a.own_pose_source,
                         observe_mode=a.observe_mode, render_dr=a.render_dr, zone_slots=a.zone_slots, reach_mode=a.reach_mode,
                         held_object=a.held_object, lookaround=a.setdown_lookaround, execution_host=host, pr=a.pr,
                         crate_scene=a.crate_scene, rgb_lift=a.rgb_lift,
                         teacher_stability=a.teacher_stability, teacher_search=a.teacher_search,
                         approach_goal_set=a.approach_goal_set, crate_lift_pose=a.crate_lift_pose),
                     ensure_ascii=False, default=str))


if __name__ == '__main__':
    main()
