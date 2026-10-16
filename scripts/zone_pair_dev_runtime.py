"""Physical implementation of the explicit zone-pair-dev adapter.

Importing this module does not construct a world. Evaluation is an observer:
its return values never influence an actor, command, stage or termination.
"""
from __future__ import annotations

import base64
import copy
import errno
import itertools
import json
import math
import os
from pathlib import Path
import signal
import time

from scripts.run_zone_pair_dev import (CALIBRATION, EXPECTED, ORDER, PARTICIPANTS, ROOT, DevActor,
                                      WallLimit, applied_settings, sha_file, write_json, validate_scene, map_path)


class Jsonl:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open('x', buffering=1)

    def append(self, row):
        self.file.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')

    def close(self):
        self.file.close()


def endpoint(host, rid):
    return next((s['endpoints'][rid] for s in reversed(host.pairs.sessions) if rid in s['endpoints']), None)


def queue_snapshot(host):
    out = {}
    for rid in PARTICIPANTS:
        slot = host.robots[rid]
        # Finished jobs detach _pair; the dispatcher retains the real queues.
        ep = endpoint(host, rid)
        out[rid] = {'arm': len(ep.controller.arm.events) if ep else 0,
                    'carry': len(ep.controller.schedule) if ep else 0,
                    'port_buffer': len(ep.port.commands) if ep else 0,
                    'macro': sum(len(cmds) for _, cmds in slot.timeline), 'capture_after': slot.capture_after,
                    'servo_targets': len(slot.port._servo_targets),
                    'motor_nonzero': sum(v != 0 for v in slot.port._motor_commands)}
    return out


def flush_admission_audit(host, stream, cursors):
    """Write private receipts immediately after API calls, outside actor/STATUS logs."""
    for rid, slot in host.robots.items():
        rows = slot.executor.pair_admission_log
        for row in rows[cursors.get(rid, 0):]:
            stream.append(copy.deepcopy(row))
        cursors[rid] = len(rows)


class RecordedPort:
    """Host-only decorator: preserve each original own observation before validation."""
    def __init__(self, port, out):
        self.port, self.out, self.index = port, out, 0

    def __getattr__(self, name):
        return getattr(self.port, name)

    def capture(self):
        obs = self.port.capture()
        rid, i = self.port.robot_id, self.index
        image = self.out / 'frames' / rid / f'{i:05d}.jpg'
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(base64.b64decode(obs['image']))
        write_json(self.out / 'inputs' / rid / f'{i:05d}.json',
                   {**{k: v for k, v in obs.items() if k != 'image'},
                    'image_file': str(image.relative_to(self.out)), 'static_inputs': 'inputs/static.json'})
        self.index += 1
        return obs


class EvalObserver:
    """Contact counters on EVERY physics step, pose/force/geometry trace at 20 Hz."""
    def __init__(self, host, out, criteria):
        import mujoco
        self.host, self.out, self.criteria = host, out, criteria
        self.trace = Jsonl(out / 'eval_only/trace.jsonl')
        self.video_times = Jsonl(out / 'eval_only/video_frames.jsonl')
        self.next_sample = self.next_video = 0.
        self.writer = None
        self.video_count = 0
        self.last_t = None
        self.last_sample_t = None
        self.cargo = host.scene.cargo[0]
        self.body = host.world.data.body(self.cargo.body)
        self.bar = next(p for p in self.cargo.spec().parts if p.name == 'bar')
        self.cargo_geoms = {mujoco.mj_name2id(host.world.model, mujoco.mjtObj.mjOBJ_GEOM, self.cargo.geom(p.name))
                            for p in self.cargo.spec().parts if p.collision}
        self.r3_start = host._truth('r3')[:2]
        self.stats = {'physics_steps': 0, 'observation_start_s': None, 'observation_end_s': None,
                      'timestep_s': float(host.world.model.opt.timestep),
                      'max_step_gap_s': 0., 'invalid_step_intervals': 0,
                      'counts': {k: 0 for k in
                      ('robot_robot', 'robot_wall', 'beam_wall', 'robot_beam_approach', 'r3_interference')},
                      'max_eq_active': 0, 'r3_max_displacement_m': 0., 'r3_motion_commands': 0, 'r3_api_calls': 0}

    def states(self):
        return {r: endpoint(self.host, r).controller.state if endpoint(self.host, r) else 'bootstrap'
                for r in PARTICIPANTS}

    def tick(self, *, force_sample=False):
        import mujoco
        import numpy as np
        h, d, m = self.host, self.host.world.data, self.host.world.model
        now = float(d.time)
        new_observation = self.last_t != now
        if not new_observation and (not force_sample or self.last_sample_t == now):
            return
        if new_observation:
            if self.last_t is None:
                self.stats['observation_start_s'] = now
            else:
                gap = now - self.last_t
                self.stats['physics_steps'] += 1  # the initial observation is not an advanced physics step
                self.stats['max_step_gap_s'] = max(self.stats['max_step_gap_s'], gap)
                if abs(gap - self.stats['timestep_s']) > self.criteria['coverage_time_tolerance_s']:
                    self.stats['invalid_step_intervals'] += 1
            self.last_t = self.stats['observation_end_s'] = now
        states = self.states()
        forces = {r: [0., 0.] for r in PARTICIPANTS}
        hits = set()
        f6 = np.zeros(6)
        for i in range(d.ncon):
            c = d.contact[i]
            a, b = int(c.geom1), int(c.geom2)
            mujoco.mj_contactForce(m, d, i, f6)
            force = abs(float(f6[0]))
            for x, y in ((a, b), (b, a)):
                if y in self.cargo_geoms:
                    for rid in PARTICIPANTS:
                        for k in (0, 1):
                            if x in h._fingers[rid][k]:
                                forces[rid][k] += force
                if c.dist > 0 or force <= self.criteria['contact_force_epsilon_n']:
                    continue
                rid = next((r for r, geoms in h._own.items() if x in geoms), None)
                if rid is not None:
                    if any(y in h._own[r] for r in h._own if r != rid):
                        hits.add('robot_robot')
                    if y in h._wall:
                        hits.add('robot_wall')
                    if rid in PARTICIPANTS and y in self.cargo_geoms and states[rid] in ('bootstrap', 'approach', 'wait_approach'):
                        hits.add('robot_beam_approach')
                if x in self.cargo_geoms and y in h._wall:
                    hits.add('beam_wall')
                if x in h._own['r3'] and (y in self.cargo_geoms or any(y in h._own[r] for r in PARTICIPANTS)):
                    hits.add('r3_interference')
        if new_observation:
            for k in hits:
                self.stats['counts'][k] += 1
            self.stats['max_eq_active'] = max(self.stats['max_eq_active'], int(any(d.eq_active)))
            self.stats['r3_max_displacement_m'] = max(self.stats['r3_max_displacement_m'], math.dist(h._truth('r3')[:2], self.r3_start))
        if force_sample or now + 1e-9 >= self.next_sample:
            self.next_sample = now + self.criteria['gt_sample_period_s']
            self.last_sample_t = now
            mat = self.body.xmat.reshape(3, 3)
            corners = [(self.body.xpos + mat @ (np.array(self.bar.center) + np.array(signs) * self.bar.size)).tolist()
                       for signs in itertools.product((-1, 1), repeat=3)]
            plans = h.pairs.sessions[0]['plan'] if h.pairs.sessions else None
            go = {r: next((msg['sent_at_s'] for session in h.pairs.sessions for msg in session['channel'].log
                           if msg['robot_id'] == r and msg['state'] == 'approach_go_0'), None) for r in PARTICIPANTS}
            self.trace.append({'t': now, 'states': states,
                               'segments': {r: endpoint(h, r).controller.seg if endpoint(h, r) else None for r in PARTICIPANTS},
                               'beam_xyz': self.body.xpos.tolist(), 'beam_corners': corners,
                               'tilt_deg': math.degrees(math.acos(max(-1., min(1., float(mat[2, 2]))))),
                               'robots': {r: list(h._truth(r)) for r in h.robots}, 'finger_n': forces,
                               'approach_go_s': go, 'prestations': plans['prestations'] if plans else {}})
        if now + 1e-9 >= self.next_video:
            self.next_video = now + .2
            self.video(now)

    def video(self, now):
        import cv2
        import numpy as np
        # Original fixed observer camera. No TOP image reaches any executor.
        jpeg = self.host.world.render_team_jpeg(camera='cctv_warehouse')
        im = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if im is None:
            raise OSError('observer JPEG decode failed')
        if self.writer is None:
            height, width = im.shape[:2]
            self.writer = cv2.VideoWriter(str(self.out / 'eval_only/overview.mp4'), cv2.VideoWriter_fourcc(*'mp4v'), 5., (width, height))
            if not self.writer.isOpened():
                raise OSError('observer video encoder unavailable')
        self.writer.write(im)
        self.video_times.append({'frame': self.video_count, 'sim_s': now, 'camera': 'cctv_warehouse'})
        self.video_count += 1

    def close(self):
        # The last physics tick need not coincide with a 20 Hz sample. Record it
        # exactly without double-counting contacts or inventing a physics step.
        try:
            self.tick(force_sample=True)
        finally:
            self.trace.close()
            self.video_times.close()
            if self.writer is not None:
                self.writer.release()
        h = self.host
        self.stats['r3_motion_commands'] = sum(c['kind'] in ('arm', 'look', 'drive', 'mecanum') for c in h.robots['r3'].commands)
        self.stats['r3_api_calls'] = sum(a['robot_id'] == 'r3' for a in h.api_calls)
        write_json(self.out / 'eval_only/contacts.json', self.stats)


def make_scene(spec):
    """Reuse the standard Scene subclass, before world construction; no runtime correction."""
    from sim.zone_tagged_cargo_scene import TaggedCargoZoneScene
    from sim.zone_start_dock import MAP_ID
    scene_cls = TaggedCargoZoneScene
    if spec['map'] == MAP_ID:
        from sim.zone_dock_scene import DockTaggedCargoZoneScene
        scene_cls = DockTaggedCargoZoneScene
    scene = scene_cls.from_tagged_cargo(spec['map'], spec['seed'], cargo=spec['team_cargo'],
                                                  goal=spec['goal'], contact_profile='local_contact_fine')
    # ZoneScene's colour-goal factory needs one placeholder box. The pair-only
    # scene excludes it BEFORE XML generation/reset, not by hiding live objects.
    scene.config['setup_only']['objects'] = {}
    scene.inventory = []
    scene.config['pair_dev_cargo_only'] = True
    return scene


def run_physical(args, prereg, case, manifest):
    from harness.zone_own_team_host import OwnCamTeamHost
    from scripts.evaluate_zone_pair_dev import evaluate_run, evaluation_failure
    from sim.workflow_manager import source_fingerprint

    out = args.output
    streams = {name: Jsonl(out / f'{name}.jsonl') for name in ('commands', 'status', 'shutdown', 'events')}
    streams['admission'] = Jsonl(out / 'eval_only/pair_admission.jsonl')
    start = time.monotonic()
    host = observer = None
    wall = prereg['limits']['wall_s']
    def timeout(signum, frame):
        raise WallLimit('WALL_LIMIT')
    previous = {s: signal.getsignal(s) for s in (signal.SIGALRM, signal.SIGTERM, signal.SIGINT)}
    def interrupted(signum, frame):
        raise WallLimit(f'INTERRUPTED:{signum}')
    signal.signal(signal.SIGALRM, timeout)
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    signal.setitimer(signal.ITIMER_REAL, wall)

    class DevHost(OwnCamTeamHost):
        """Observer hooks preserve the production host's profile-defined step loop."""
        def __init__(self, *a, **kw):
            self.audit_index = {}
            self.admission_index = {}
            self.abort_index = {}
            self.abort_seen = False
            self.shutdown_at = None
            self.observer = None
            self.terminal_since = None
            self.injected = False
            self.actors = {r: DevActor(r, prereg['limits']['submit_at_s']) for r in PARTICIPANTS}
            super().__init__(*a, **kw)
            for slot in self.robots.values():
                slot.port = RecordedPort(slot.port, out)

        def call(self, rid, api, *args):
            try:
                return super().call(rid, api, *args)
            finally:
                flush_admission_audit(self, streams['admission'], self.admission_index)

        def aborted(self):
            if not self.abort_seen and getattr(self, 'pairs', None):
                for session in self.pairs.sessions:
                    wire = session['channel']
                    begin = self.abort_index.get(wire.task_id, 0)
                    self.abort_seen |= any(m['state'] == 'abort' for m in wire.log[begin:])
                    self.abort_index[wire.task_id] = len(wire.log)
            return self.abort_seen

        def _sink(self, rid, row):
            # Capture ordering at the command boundary, including the same SIM instant.
            streams['commands'].append({'robot_id': rid, 'after_abort': self.aborted(), **row})
            super()._sink(rid, row)

        def _pair_safety(self, now):
            super()._pair_safety(now)
            if self.pairs:
                for session in self.pairs.sessions:
                    wire = session['channel']
                    begin = self.audit_index.get(wire.task_id, 0)
                    for msg in wire.log[begin:]:
                        streams['status'].append(msg)
                    self.audit_index[wire.task_id] = len(wire.log)
            if self.aborted() and (self.shutdown_at is None or now - self.shutdown_at >= .05 - 1e-9):
                streams['shutdown'].append({'t': now, 'aborted': True, 'queues': queue_snapshot(self)})
                self.shutdown_at = now

        def _decide_raw(self, rid, now):
            if rid in self.actors and not self.closed:
                self.actors[rid].tick(self.robots[rid].executor, lambda api, *a: self.call(rid, api, *a), now)
            return super()._decide_raw(rid, now)

        def _contact_kinds(self, data):
            kinds = super()._contact_kinds(data)
            if self.observer is not None:
                self.observer.tick()   # return discarded; no GT goes into control
            return kinds

        def _physics_until(self, t_end):
            # Experimenter fault, triggered from r2's own STATUS only. No GT.
            if case['intervention'] == 'abort_after_carry_go' and not self.injected and self.pairs:
                go = next((m['sent_at_s'] for s in self.pairs.sessions for m in s['channel'].log
                           if m['robot_id'] == 'r2' and m['state'] == 'carry_go_0'), None)
                now = float(self.world.data.time)
                if go is not None and now >= go + .1:
                    write_json(out / 'intervention.json', {'t': now, 'kind': case['intervention'],
                                                         'queues_before': queue_snapshot(self)})
                    self.injected = True
                    self.call('r2', 'abort', 'dev_preregistered_abort')
            super()._physics_until(t_end)

        def done(self):
            # Host termination from API/job states; never from evaluation truth.
            all_terminal = all(a.submitted and self.robots[r].executor.job is None for r, a in self.actors.items())
            now = float(self.world.data.time)
            if all_terminal and self.terminal_since is None:
                self.terminal_since = now
            return self.terminal_since is not None and now - self.terminal_since >= prereg['limits']['post_terminal_s']

    def layer(host, kind, event, now):
        if event is not None:
            streams['events'].append(event)

    status_code = 0
    try:
        spec = {'map': prereg['environment']['map'], 'seed': case['seed'], 'goal': {'B': {'cyan': 1}},
                'pair_policy': case.get('pair_policy','v5h'),
                'team_cargo': [{'item_id': 'cargoX', 'kind': 'long_beam', 'pose': case['setup_beam_xyyaw']}],
                'pair_order_sheets': {'cargoX': case['coarse_order_sheet']}, 'order_sheet': copy.deepcopy(ORDER),
                'contact_profile': EXPECTED['contact_profile'], 'job_sim_limit_s': prereg['limits']['sim_s']}
        student = {'mode': 'm1', 'calibration': str(CALIBRATION.relative_to(ROOT)),
                   'skill_module': 'harness.wrist_zone_skill_v9', 'skill_class': 'WristZoneDeliveryV9'}
        # Retain the partially constructed object so an init failure can still
        # close its world/render worker, without attempting more physics.
        host = DevHost.__new__(DevHost)
        scene = make_scene(spec)
        validate_scene(prereg, scene)
        DevHost.__init__(host, spec, student, root=ROOT, study_layer=layer, frames_dir=out / 'frames', scene=scene)
        manifest['applied'] = applied_settings(host, validate=False)
        write_json(out / 'manifest.json', manifest)
        applied_settings(host, expected=prereg['environment'])
        import mujoco
        mujoco.mj_saveLastXML(str(out / 'eval_only/applied_model.xml'), host.world.model)
        manifest.update(state='running', simulator_start_s=float(host.world.data.time),
                        contact_record=host.contact_record, scene_xml_sha256=host.scene.manifest['scene_xml_sha256'],
                        applied_model_xml_sha256=sha_file(out / 'eval_only/applied_model.xml'))
        write_json(out / 'manifest.json', manifest)
        write_json(out / 'eval_only/scene.json', host.scene.record())
        observer = host.observer = EvalObserver(host, out, prereg['criteria'])
        observer.tick()
        result = host.run(prereg['limits']['sim_s'], done=host.done)
        manifest.update(state='completed', termination=result['outcome'])
        if result['outcome'] != 'STUDY_LAYER_DONE':
            manifest['state'] = 'limit_or_stopped'
        if case['intervention'] != 'none' and not host.injected:
            manifest['intervention_not_reached'] = True
    except WallLimit as exc:
        manifest.update(state='interrupted', termination=str(exc))
        status_code = 2
    except Exception as exc:
        manifest.update(state='host_error', host_error={'type': type(exc).__name__, 'message': str(exc),
                        'classification': 'HOST_ERROR', 'enospc': isinstance(exc, OSError) and exc.errno == errno.ENOSPC})
        status_code = 2
    finally:
        # External workflow timeout is the final backstop if native construction/close hangs.
        signal.setitimer(signal.ITIMER_REAL, 0)
        try:
            if host is not None and getattr(host, 'pairs', None) is not None and hasattr(host, 'closed'):
                if not host.closed:
                    host.close_episode(manifest.get('termination', 'HOST_ERROR'))
                manifest['sim_end_s'] = float(host.world.data.time)
                write_json(out / 'pair_records.json', host.pairs.records())
                write_json(out / 'api_calls.json', host.api_calls)
                write_json(out / 'robots.json', {r: {'frames': s.frames, 'cancellations': s.cancellations,
                           'jobs_done': s.executor.jobs_done, 'exception': s.exception} for r, s in host.robots.items()})
                write_json(out / 'eval_only/host.json', host.eval_only)
            if observer is not None:
                observer.close()
        finally:
            try:
                if host is not None and hasattr(host, 'world'):
                    host.close()
            finally:
                for s in streams.values():
                    s.close()
                for sig, handler in previous.items():
                    signal.signal(sig, handler)
        manifest['wall_s'] = time.monotonic() - start
        manifest['environment']['loadavg_at_end'] = list(os.getloadavg())
        manifest['source_after_sha256'] = source_fingerprint(ROOT)['sha256']
        manifest['source_changed'] = manifest['source_after_sha256'] != manifest['source']['execution_tree']['sha256']
        manifest['inputs_changed'] = (sha_file(map_path(prereg)) != manifest['inputs']['map']['sha256']
                                      or sha_file(CALIBRATION) != manifest['inputs']['calibration']['sha256']
                                      or sha_file(manifest['prereg']['path']) != manifest['prereg']['sha256'])
        if manifest['source_changed'] or manifest['inputs_changed']:
            manifest.update(state='host_error', host_error={'classification': 'HOST_ERROR', 'message': 'source or static inputs changed during run'})
            status_code = 2
        write_json(out / 'manifest.json', manifest)
        try:
            evaluation = evaluate_run(out)
        except (OSError, ValueError, KeyError) as exc:
            evaluation = evaluation_failure(manifest, exc)
        write_json(out / 'eval_only/result.json', evaluation)
        write_json(out / 'result.json', {'run_id': case['id'], 'labels': manifest['labels'], 'research_result': False,
                   'protocol_complete': manifest['state'] == 'completed', 'model_calls': 0,
                   'evaluation': 'eval_only/result.json', 'physical_success': None,
                   'video_review': 'pending', 'tensorboard': 'pending coordinator conversion and display'})
        # Includes every raw JPEG, metadata, STATUS, failure and video; never secrets/env dump.
        files = {str(p.relative_to(out)): {'bytes': p.stat().st_size, 'sha256': sha_file(p)}
                 for p in sorted(out.rglob('*')) if p.is_file() and p.name != 'artifacts.sha256.json'}
        write_json(out / 'artifacts.sha256.json', files)
    return status_code
