"""Replay archived own inputs with exclusive timers; no truth/controller feedback.

The source adapter is exported from Git. Profiling and timing both require the
shared host lock. This is an offline diagnostic, not an online wall/SIM claim.
"""
from __future__ import annotations

import argparse
import base64
from collections import defaultdict
from contextlib import contextmanager, nullcontext
import cProfile
import hashlib
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import pstats
import subprocess
import sys
import time
import re
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = ('physics', 'render', 'pf_update', 'posterior_summary', 'scan_match',
              'map_insert', 'path_plan', 'graph', 'vision', 'record_io', 'controller_other', 'setup_proof')


def split_timing(value):
    """Preserve actual latency telemetry separately; never change numeric state."""
    telemetry = {}
    def visit(item, path=''):
        if isinstance(item, dict):
            result = {}
            for key, child in item.items():
                pointer = path + '/' + str(key).replace('~', '~0').replace('/', '~1')
                if key == 'inference_wall_ms':
                    telemetry[pointer] = child
                else:
                    result[key] = visit(child, pointer)
            return result
        if isinstance(item, (list, tuple)):
            return [visit(child, path + '/' + str(index)) for index, child in enumerate(item)]
        return item
    return visit(value), telemetry


def write(path, value, *, ensure_ascii=True):
    import numpy as np
    def default(item):
        if isinstance(item, np.ndarray):
            return item.tolist()
        if isinstance(item, np.generic):
            return item.item()
        raise TypeError(type(item).__name__)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=ensure_ascii, allow_nan=False, default=default) + '\n')


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def rows(path):
    return [json.loads(row) for row in path.read_text().splitlines()]


def source_check(expected):
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == expected
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip(), 'DIRTY_SOURCE'


def ancestor(pid, parent):
    """A managed CLI may add an intermediate subprocess/session."""
    for _ in range(64):
        if pid == parent:
            return True
        if pid <= 1:
            return False
        pid = int(subprocess.check_output(['ps', '-o', 'ppid=', '-p', str(pid)], text=True))
    return False


def acquire_slot(expected, purpose, *, lock_owner_pid=None, wait_s=7200):
    """Atomic finite wait, or borrow this queue driver's verified ancestor lock."""
    from scripts import agent_lock
    source_check(expected)
    if lock_owner_pid is not None:
        held = agent_lock.status(agent_lock.DEFAULT_ROOT)
        assert held and held['pid'] == lock_owner_pid and held['pid_alive']
        assert held['owner'] == 'codex' and held['branch'] == 'codex/sim-speed-ctrl'
        assert held['timing_sensitive'] and ancestor(os.getpid(), lock_owner_pid)
        return held, False
    deadline = time.monotonic() + wait_s
    announced = False
    while True:
        try:
            held = agent_lock.acquire(agent_lock.DEFAULT_ROOT, owner='codex', branch='codex/sim-speed-ctrl',
                purpose=purpose, pid=os.getpid(), expected_minutes=90, timing_sensitive=True)
            break
        except RuntimeError as exc:
            if not str(exc).startswith('lock held:') or time.monotonic() >= deadline:
                raise
            if not announced:
                print('Waiting for the exclusive host slot (finite; no process interruption)', flush=True)
                announced = True
            time.sleep(2)
    try:
        source_check(expected)
    except BaseException:
        agent_lock.release(agent_lock.DEFAULT_ROOT, owner='codex')
        raise
    return held, True


class Timers:
    """Nested measurements form a partition; inclusive values are separate."""
    def __init__(self, clock=time.perf_counter):
        self.clock = clock
        self.stack = []
        self.total = defaultdict(lambda: dict(calls=0, exclusive_s=0., inclusive_s=0.))

    @contextmanager
    def span(self, name):
        frame = [self.clock(), 0.]
        self.stack.append(frame)
        try:
            yield
        finally:
            elapsed = self.clock() - frame[0]
            self.stack.pop()
            row = self.total[name]
            row['calls'] += 1
            row['inclusive_s'] += elapsed
            row['exclusive_s'] += elapsed - frame[1]
            if self.stack:
                self.stack[-1][1] += elapsed

    def wrapper(self, function, name):
        def observed(*args, **kwargs):
            with self.span(name):
                return function(*args, **kwargs)
        return observed

    def aliases(self, function, name):
        replacement = self.wrapper(function, name)
        for key, module in list(sys.modules.items()):
            if key.startswith(('harness.', 'scripts.')):
                for attribute, value in list(vars(module).items()):
                    if value is function:
                        setattr(module, attribute, replacement)

    def method(self, cls, name, category):
        setattr(cls, name, self.wrapper(getattr(cls, name), category))

    def snapshot(self):
        return {k: dict(self.total[k]) for k in CATEGORIES}

    def profile_frame(self, index, count):
        if getattr(self, 'profiler', None) is not None:
            window = self.profile_window
            selected = index < window or index >= count - window
            if selected != self.profile_active:
                (self.profiler.enable if selected else self.profiler.disable)()
                self.profile_active = selected


def verify_inputs(raw, robots):
    manifest = json.loads((raw / 'artifacts.sha256.json').read_text())
    if 'files' in manifest:
        manifest = manifest['files']
    used = ['bundle.json']
    for rid in robots:
        used += [f'robots/{rid}/frames.jsonl', f'robots/{rid}/commands.jsonl']
    used += ['student_record.json'] if len(robots) > 1 else ['own-inputs.json', 'own-controller.jsonl']
    for name in used:
        assert name in manifest and sha(raw / name) == manifest[name], ('INPUT_HASH', name)
    return {name: manifest[name] for name in used}


def recorded_control_prefix(captured, inputs, completed_ids, original):
    """Replay completed logged callbacks, never invent a missing sensor input.

    The archived runner logs own-inputs inside receive(), after estimation.
    HOST_BUDGET can therefore leave a captured, interrupted tail whose partial
    terminal state cannot be reconstructed from the completed callback ledger.
    """
    ids = [x['frame_id'] for x in captured]
    logged = [x['frame_id'] for x in inputs]
    if not logged or len(set(ids)) != len(ids) or len(set(logged)) != len(logged):
        raise ValueError('INVALID_CONTROLLER_INPUT_LEDGER')
    if logged != completed_ids or logged[-1] not in ids:
        raise ValueError('INCOMPLETE_CONTROLLER_CALLBACK_LEDGER')
    end = ids.index(logged[-1]) + 1
    if ids[10:end] != logged:
        raise ValueError('NON_PREFIX_CONTROLLER_INPUT_LEDGER')
    excluded = captured[end:]
    failure = original.get('failure') or {}
    if excluded and not (len(excluded) == 1 and original.get('status') == 'HOST_ERROR'
                         and failure.get('type') == 'TimeoutError'
                         and str(failure.get('message', '')).startswith('HOST_BUDGET')):
        raise ValueError('UNEXPLAINED_CAPTURE_WITHOUT_COMPLETED_CALLBACK')
    audit = dict(captured_frames=len(captured), replay_frames=end,
        setup_frames=10, completed_controller_inputs=len(logged),
        excluded_interrupted_captures=[{k: x[k] for k in ('frame_id', 'sim_time', 'sha256')} for x in excluded],
        scope=('completed recorded callback prefix; interrupted terminal state not reconstructed'
               if excluded else 'all captured frames and completed callbacks'),
        original_status=original.get('status'))
    return captured[:end], audit


def attach_timers(timer, kind):
    if kind == 's3':
        from harness import zone_solo_cyan_augmented_start as a, zone_solo_cyan_best_cluster as b
        from harness import owncam_localizer as own, zone_solo_cyan_amcl_sensor as sensor
        from harness import zone_solo_cyan_landmarks as landmarks, opencv_wall_observation as vision
        timer.aliases(a.belief_report, 'posterior_summary')
        timer.aliases(b.extract, 'posterior_summary')
        timer.aliases(b.connected_labels, 'posterior_summary')
        timer.method(own.OwnCamLocalizer, 'estimate', 'posterior_summary')
        timer.method(own.OwnCamLocalizer, 'predict_to', 'pf_update')
        timer.method(a.Policy, 'measure', 'pf_update')
        timer.aliases(sensor.likelihood, 'pf_update')
        timer.aliases(landmarks.landmark_likelihood, 'pf_update')
        timer.method(vision.OpenCVObserver, 'observe', 'vision')
        timer.aliases(vision.observations, 'vision')
    else:
        from harness import self_map_rbpf as r, self_pose_graph as g, wall_confidence as w
        from harness.self_odom_grid import OdomGrid
        from harness.public_navigation_monitor import MonitorNavigator
        for f, category in [(r.improved_proposal, 'scan_match'), (w.weighted_insert, 'map_insert'),
                            (g.match_loop, 'scan_match')]:
            timer.aliases(f, category)
        assert isinstance(r.GridField, type), 'GRID_FIELD_PUBLIC_CLASS_API'
        timer.method(r.GridField, '__init__', 'scan_match')
        timer.method(OdomGrid, 'insert', 'map_insert')
        timer.method(r.RaoBlackwellizedGrid, 'propagate', 'pf_update')
        old = r.CloudOdometry.covariance
        r.CloudOdometry.covariance = property(timer.wrapper(old.fget, 'posterior_summary'))
        timer.method(MonitorNavigator, 'update', 'path_plan')


def frame(raw, value):
    import numpy as np
    from PIL import Image
    jpeg = (raw / value['path']).read_bytes()
    assert hashlib.sha256(jpeg).hexdigest() == value['sha256'], 'FRAME_HASH'
    obs = {k: v for k, v in value.items() if k not in ('path', 'commanded_servo')}
    obs['image'] = base64.b64encode(jpeg).decode()
    return obs, np.asarray(Image.open(io.BytesIO(jpeg)).convert('RGB'))


def s3(raw, out, timer):
    from harness import zone_s3_motion_contract as contract
    from harness.zone_s3_motion_runtime import Runtime
    from harness.zone_s3_no_prior import IntegratedTrial, ROBOTS
    from harness.zone_pair_highpose_exact_speedups import install
    bundle = json.loads((raw / 'bundle.json').read_text())
    frames = {r: rows(raw / f'robots/{r}/frames.jsonl') for r in ROBOTS}
    commands = {r: rows(raw / f'robots/{r}/commands.jsonl') for r in ROBOTS}
    issued = defaultdict(list)
    for rid in ROBOTS:
        for row in commands[rid][1:]:
            issued[round(row['t'], 9)].append((rid, {k: v for k, v in row.items() if k != 't'}))
    _, undo = install(bundle['speedups'])
    scenario, mapped, sheet = contract.inputs()
    rt = Runtime(contract.hp.resolve(bundle['map_id'])[0], sheet['orders'], contract.ROOT / bundle['calibration'],
                 bundle['calibration_sha256'], seed=bundle['seed'], config=bundle['controller_config'])
    first = frames['r1'][0]['sim_time']
    rt.initial_commands(first, {r: {int(k): v for k, v in commands[r][0]['pulses'].items()} for r in ROBOTS})
    trial = IntegratedTrial(scenario, seed=bundle['seed'], links=rt.links, map_bundle=mapped,
                           horizon_s=first + bundle['case_cap_s'], code_sha=bundle['source_sha'],
                           pair_records=rt.pair.team.records)
    rt.trial = trial
    trial.begin(first)
    for own in rt.localizers.values():
        pf = own.pose.provider.loc._pf
        for name in ('apply_scan', 'predict_to'):
            if hasattr(pf, name):
                setattr(pf, name, timer.wrapper(getattr(pf, name), 'pf_update'))
    generated, states, trend = [], [], []
    failure = None
    try:
        for index, row in enumerate(frames['r1']):
            timer.profile_frame(index, len(frames['r1']))
            now = row['sim_time']
            with timer.span('record_io'):
                batch = {r: frame(raw, frames[r][index]) for r in ROBOTS}
            with timer.span('controller_other'):
                rt.on_frames(now, batch)
                actions = rt.step(now)
                generated.append((now, actions))
                for r, action in issued[round(now, 9)]:
                    rt.on_command(r, now, action)
            for rid, own in rt.localizers.items():
                pf = own.pose.provider.loc._pf
                states.append(dict(t=now, rid=rid, particles=hashlib.sha256(pf.px.tobytes()).hexdigest(),
                                   weights=hashlib.sha256(pf.logw.tobytes()).hexdigest(), rng=pf.rng.bit_generator.state))
            trend.append(dict(t=now, particles=[len(x.pose.provider.loc._pf.px) for x in rt.localizers.values()],
                              timers=timer.snapshot()))
            if index % 100 == 0:
                print(json.dumps(dict(kind='s3', frame=index, sim=now)), flush=True)
    except Exception as exc:
        failure = dict(type=type(exc).__name__, message=str(exc))
    finally:
        with timer.span('record_io'):
            write(out / 'commands.json', generated)
            write(out / 'state.json', dict(states=states, poses={r: x.pose_log for r, x in rt.localizers.items()}))
            record, telemetry = split_timing(rt.record())
            write(out / 'record.json', record, ensure_ascii=False)
            write(out / 'timing-provenance.json', dict(schema='ugrp.replay_timing_provenance.v1',
                scope='actual local provider latency, excluded from behavior bytes only',
                fields=telemetry), ensure_ascii=False)
        rt.close()
        undo()
    return dict(frames=len(trend), available_frames=len(frames['r1']), start=first,
                end=frames['r1'][-1]['sim_time'], failure=failure, trend=trend)


def egomap(raw, out, timer):
    import numpy as np
    from harness.active_camera import SEARCH
    from harness.active_wall_vision import observe
    from scripts.run_own_map_return_repeat import actor
    from scripts import run_goal_route_continuous as base
    bundle = json.loads((raw / 'bundle.json').read_text())
    captured = rows(raw / 'robots/r3/frames.jsonl')
    inputs = json.loads((raw / 'own-inputs.json').read_text())
    with (raw / 'own-controller.jsonl').open() as stream:
        completed_ids = [json.loads(line)['frame_id'] for line in stream if line.strip()]
    original = json.loads((raw / 'result.json').read_text()) if (raw / 'result.json').exists() else {}
    frames, input_selection = recorded_control_prefix(captured, inputs, completed_ids, original)
    commands = rows(raw / 'robots/r3/commands.jsonl')
    issued = defaultdict(list)
    for row in commands[1:]:
        issued[round(row['t'], 9)].append(row)
    ranges = {x['frame_id']: x['own_range'] for x in inputs}
    start = bundle.get('start_sim_s', frames[0]['sim_time'])
    explorer = actor('r3', start, SEARCH, active_mapping='frontier_rbpf_v1', active_loop='information_gain_v1',
                     seed=bundle['task']['seed'], active_recovery='nav2_frontier_v1',
                     navigation_map='public_ros_v8', motion_model='s2_pulse_v122_rotL_v1')
    base.base.install_profile(explorer.memory.self_map, profile='egomap27_wide')
    controller = base.controller(explorer)
    g = explorer.memory.self_map
    g._observe = timer.wrapper(g._observe, 'pf_update')
    timer.method(type(explorer.memory), 'finalize_pose_graph', 'graph')
    generated, state, traces, trend = [], [], [], []
    streams = {}
    last_snapshot = None
    def append(name, value):
        if name not in streams:
            streams[name] = (out / name).open('x', buffering=65536)
        streams[name].write(json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n')
    for index, row in enumerate(frames):
        timer.profile_frame(index, len(frames))
        now = row['sim_time']
        with timer.span('record_io'):
            obs, rgb = frame(raw, row)
        if index >= 10:
            with timer.span('controller_other'):
                detection = observe(rgb, SEARCH, body_settling=.7)
                command, trace = controller.receive(robot_id='r3', t=now, frame_id=obs['frame_id'], rgb=rgb,
                    servo=SEARCH, observation=detection, frame_sha256=row['sha256'],
                    own_range=ranges[obs['frame_id']])
                generated.append(command)
                traces.append(trace)
            with timer.span('record_io'):
                append('own-controller.jsonl', trace)
                append('own-contacts.jsonl', dict(t=now, frame_id=obs['frame_id'], **detection))
                append('frontend-covariances.jsonl', dict(t=now, frame_id=obs['frame_id'],
                    pose=list(g.odom.pose), covariance=g.odom.covariance.tolist()))
                revision = (g.revision, g.best, g.resamples)
                if revision != last_snapshot:
                    append('online-maps.jsonl', dict(t=now, frame_id=obs['frame_id'],
                        view='online_frontend', grid=g.export(), ledger=g.ledger))
                    last_snapshot = revision
            # The original runner records the observation BEFORE issuing and
            # remembering its command. Keep that boundary for archival parity.
            with timer.span('controller_other'):
                for issued_command in issued[round(now, 9)]:
                    controller.command(issued_command)
            state.append(dict(t=now, poses=hashlib.sha256(g.poses.tobytes()).hexdigest(),
                weights=hashlib.sha256(g.weights.tobytes()).hexdigest(),
                pending_cov=hashlib.sha256(g.pending_cov.tobytes()).hexdigest(), rng=g.rng.bit_generator.state))
        trend.append(dict(t=now, cells=sum(len(m.cells) for m in g.maps), particles=len(g.poses),
                          ledger=len(g.ledger), record_bytes=sum(s.tell() for s in streams.values()),
                          timers=timer.snapshot()))
        if index % 100 == 0:
            print(json.dumps(dict(kind='egomap', frame=index, sim=now, cells=trend[-1]['cells'])), flush=True)
    with timer.span('record_io'):
        for stream in streams.values():
            stream.close()
        for name, value in [('commands', generated), ('traces', traces), ('state', state),
            ('route-map', controller.snapshot()), ('frontend-grid', g.export()), ('frontend-ledger', g.ledger),
            ('decisions', g.decisions), ('graphs', explorer.graphs), ('navigation', explorer.navigator.events),
            ('heading-decisions', controller.heading_host.rows), ('utility-events', controller.events),
            ('own-inputs', controller.inputs), ('return-navigation', controller.navigator.events),
            ('frontend-poses', explorer.poses), ('active-events', explorer.events)]:
            write(out / (name + '.json'), value)
        write(out / 'all-particle-maps.json', [sorted((x, y, v) for (x, y), v in m.cells.items()) for m in g.maps])
    return dict(frames=len(trend), available_frames=len(frames), start=start, end=frames[-1]['sim_time'],
                failure=None, trend=trend, input_selection=input_selection)


def worker(args):
    sys.path.insert(0, str(args.adapter))
    for name in ('sim', 'harness', 'scripts'):
        importlib.import_module(name).__path__ = [str(args.adapter / name)]
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    kind = args.kind
    inputs = verify_inputs(args.raw, ('r1', 'r2', 'r3') if kind == 's3' else ('r3',))
    # Import adapter before wrapping all references to shared pure functions.
    importlib.import_module('harness.zone_s3_motion_runtime' if kind == 's3' else 'scripts.run_goal_route_continuous')
    name = 'harness.controller_exact_speedups'
    spec = importlib.util.spec_from_file_location(name, ROOT / 'harness/controller_exact_speedups.py')
    speedups = importlib.util.module_from_spec(spec)
    sys.modules[name] = speedups
    spec.loader.exec_module(speedups)
    installed = speedups.install(args.speedups)
    timer = Timers()
    attach_timers(timer, kind)
    profiler = cProfile.Profile() if args.profile else None
    timer.profiler = profiler
    timer.profile_window = args.profile_window_frames
    load = os.getloadavg()
    started = time.perf_counter()
    if profiler:
        profiler.enable()
        timer.profile_active = True
    # Pair channel IDs are external setup randomness, not the PF stream.
    # Supply the archived IDs in their original record order in both arms.
    archived_ids = []
    if kind == 's3':
        for value in re.findall(r'pair-([0-9a-f]{32})', (args.raw / 'student_record.json').read_text()):
            if value not in archived_ids:
                archived_ids.append(value)
    ids = iter(archived_ids)
    try:
        with timer.span('setup_proof'), (patch('uuid.uuid4', side_effect=lambda: uuid.UUID(hex=next(ids))) if kind == 's3' else nullcontext()):
            result = (s3 if kind == 's3' else egomap)(args.raw, out, timer)
    except Exception as exc:
        source_frames = rows(args.raw / ('robots/r1/frames.jsonl' if kind == 's3' else 'robots/r3/frames.jsonl'))
        result = dict(frames=None, available_frames=len(source_frames),
                      start=source_frames[0]['sim_time'], end=source_frames[-1]['sim_time'],
                      failure=dict(type=type(exc).__name__, message=str(exc)), trend=[],
                      partial_outputs=True)
    wall = time.perf_counter() - started
    if profiler:
        profiler.disable()
        profiler.dump_stats(out / 'profile.pstats')
        with (out / 'profile.txt').open('w') as stream:
            pstats.Stats(profiler, stream=stream).sort_stats('cumulative').print_stats(80)
    write(out / 'trend.json', result.pop('trend'))
    write(out / 'result.json', dict(**result, kind=kind, profile=args.profile, wall_s=wall,
        wall_per_input_sim=wall / (result['end'] - result['start']), timers=timer.snapshot(),
        measured_online_wall_per_sim=False, physics_runs=0, render_calls=0,
        archived_setup_ids=archived_ids,
        speedups=installed.snapshot(),
        loadavg_start=load, loadavg_end=os.getloadavg(), input_sha256=inputs,
        source_adapter=str(args.adapter), implementation_sha=subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        cprofile_scope='initialization, first/last window and final serialization',
        cprofile_window_frames=args.profile_window_frames))
    installed.close()
    return result['failure'] is None and result['frames'] == result['available_frames']


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kind', choices=('s3', 'egomap'), required=True)
    p.add_argument('--raw', type=Path, required=True)
    p.add_argument('--adapter', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--profile', action='store_true')
    p.add_argument('--profile-window-frames', type=int, default=100)
    p.add_argument('--speedups', choices=('off', 'exact-v1'), default='off')
    p.add_argument('--lock-owner-pid', type=int)
    p.add_argument('--execute', action='store_true')
    a = p.parse_args()
    assert a.profile_window_frames > 0
    if not a.execute:
        print(json.dumps(dict(execution_started=False, physics_runs=0, raw=str(a.raw))))
        return
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == a.expected_source_sha
    assert int(subprocess.check_output(['ps', '-o', 'ni=', '-p', str(os.getpid())])) == 0
    from scripts import agent_lock
    held, owned = acquire_slot(a.expected_source_sha, 'speedctrl saved-input replay; physics0',
                               lock_owner_pid=a.lock_owner_pid)
    try:
        complete = worker(a)
    finally:
        released = agent_lock.release(agent_lock.DEFAULT_ROOT, owner='codex') if owned else None
        if a.output.exists():
            write(a.output / 'lock.json', dict(acquired=held, released=released, borrowed=not owned))
    if not complete:
        raise RuntimeError('INCOMPLETE_REPLAY: failure preserved in result.json')


if __name__ == '__main__':
    main()
