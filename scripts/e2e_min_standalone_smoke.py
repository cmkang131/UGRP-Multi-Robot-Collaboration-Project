#!/usr/bin/env python3
"""E2E-min standalone component smoke (no relay, no LLM, one world; default off).

Plumbing check only: each sub-command starts ONE E2E-min component by itself,
re-using the existing code paths, so that a failure of the full E2E smoke
(SMOKE.md, gcp6) can be localised.  Nothing here is a verdict, an n/N count or
collected data; every output JSON carries ``LABEL``.

Sub-commands
  act-server   ACT grasp server (learned R8 checkpoint, C2c config) started via
               the runner's own ``act_server_argv`` + ``ActServerTransport``;
               ``--frames synthetic``: open-loop requests on a grey JPEG (no
               physics, server/protocol/CUDA only); ``--frames render``: one
               nav-scene world with the E2E cubes, own camera frames, ACT
               commands issued to MJWarp for ``--ticks`` ticks (1 world grasp
               request round trip, NOT a grasp evaluation).
  release-open rule script ``release_open_v1`` (scripted, not learned) from a
               held arm pose; ``--physics none`` (CPU, command trace only) or
               ``--physics warp`` (commands issued to one MJWarp world, no cube).
  nav-render   ``NavCarryAdapter`` around the r5 nav task (rule-based self-nav)
               with the arm held at the carry pose (H3: all PWM = held), slot
               decision fixed to the spawn lane (no LLM), frames saved; no cube.

Default off: every sub-command needs ``--enabled``.  Nothing in the runner,
the handoff or the executors is changed by this file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from collections import namedtuple
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness import e2e_min_handoff as H  # noqa: E402

SCHEMA = 'ugrp.e2e_min.standalone_smoke.v1'
LABEL = 'STANDALONE_SMOKE — 배관 확인, 판정 아님, 수집 데이터 아님'
SEED = 601
ROBOTS = ('r1', 'r2')
CANDIDATES_PATH = ROOT / 'experiments/2026-10-21-e2e-min/carry_pose_candidates.json'
DEFAULT_HELD_POSE = 'act_lift_end'
FIXED_SLOTS = {'r1': 'left', 'r2': 'right'}   # == e2ewarp_l1lite.SPAWN_LANE_SLOT

#: Policy provenance per sub-command, written verbatim into every output.
POLICY = {
    'act-server': dict(
        kind='learned',
        component='ACT student grasp (act18_policy.Actor, R8 step-100000 checkpoint)',
        config='C2c: ChunkExecutor n_action_steps=1, temporal_ensemble_coeff=0.01, no done head, '
               'no loop overlay; client-side v7 deadband-2 pwm clock (harness/e2e_min_act.py)',
        teacher=False, llm=False),
    'release-open': dict(
        kind='scripted',
        component='release_open_v1 rule script (harness/e2e_min_release.py)',
        config='stop -> gripper ramp to OPEN_PWM 2000 -> reverse until own-command odometry '
               'backoff_m -> done; constants from teacher dataset statistics, not learned',
        teacher=False, llm=False),
    'nav-render': dict(
        kind='scripted',
        component='NavCarryAdapter(NavRobot) = rule-based self-nav (harness.e2ewarp_nav_gate:'
                  'navigation_factory, colour-band zone detector + own-command odometry)',
        config='arm held at carry pose (H3 last_hold_all_servos_v1: all 5 PWM = held); '
               'slot fixed to spawn lane r1=left r2=right (NOT an LLM decision)',
        teacher=False, llm=False),
}

Frame = namedtuple('Frame', 'robot_id jpeg issued')


# ---------------------------------------------------------------- pure helpers
def header(sub, **extra):
    if sub not in POLICY:
        raise ValueError('unknown sub-command: ' + str(sub))
    return dict(schema=SCHEMA, label=LABEL, subcommand=sub, policy=dict(POLICY[sub]),
                verdict=None, n_over_N=None, pooled=False, relay=False, llm_calls=0, **extra)


def parse_robots(text):
    robots = tuple(r for r in str(text).split(',') if r)
    if not robots or len(set(robots)) != len(robots) or set(robots) - set(ROBOTS):
        raise argparse.ArgumentTypeError('robots must be a subset of r1,r2')
    return robots


def held_pose(name, path=CANDIDATES_PATH):
    poses = json.loads(Path(path).read_text())['poses']
    if name not in poses:
        raise ValueError('unknown carry pose: ' + str(name))
    return H.held_pwm(poses[name])


def search_pwm():
    from harness.active_camera import SEARCH
    return {str(k): int(v) for k, v in SEARCH.items()}


def carry_command(now, command, held):
    """H3 (same as RobotHandoff._carry): nav wheels/pulses unchanged, all PWM held."""
    cmd = H.check_command(command)
    return H.check_command(dict(t=float(now), wheels=list(cmd['wheels']),
                                duration_s=list(cmd['duration_s']), pwm=H.held_pwm(held)))


def cube_spec(robots):
    from harness.e2e_min_world import PROPOSED_CUBE_XY
    return {r: dict(item_id=PROPOSED_CUBE_XY[r][0], xy=list(PROPOSED_CUBE_XY[r][1])) for r in robots}


def act_config(a):
    """Same dict shape as the runner config's ``act`` block (e2e_min_runner.ACT_KEYS)."""
    return dict(python=str(a.act_python), act_source=str(a.act_source), expected_act_sha=a.expected_act_sha,
                checkpoint=str(a.checkpoint), expected_model_sha256=a.expected_model_sha256,
                device=a.device)


def check_act_receipt(hello, act):
    problems = []
    if hello.get('ready') is not True:
        problems.append('not ready')
    if hello.get('act_source_sha') != act['expected_act_sha']:
        problems.append('act_source_sha')
    if hello.get('model_sha256') != act['expected_model_sha256']:
        problems.append('model_sha256')
    if hello.get('done_head') is not False or hello.get('loop_overlay') is not False:
        problems.append('C2c arms (done_head/loop_overlay)')
    if (hello.get('executor') or {}) != dict(n_action_steps=1, temporal_ensemble_coeff=.01):
        problems.append('executor')
    return problems


def act_plumbing(result, robots, ticks):
    """Plumbing criteria (not a grasp judgement): every request answered with a valid command."""
    from harness import grasp_act_contract as C
    problems = list(result.get('receipt_problems') or [])
    rows = result.get('rows') or []
    for robot in robots:
        mine = [r for r in rows if r['robot'] == robot]
        if len(mine) != ticks:
            problems.append(f'{robot}: {len(mine)}/{ticks} replies')
        for r in mine:
            try:
                C.command(r['command'])
            except ValueError as exc:
                problems.append(f'{robot}@{r["t"]}: {exc}')
            if type(r['done']) is not bool:
                problems.append(f'{robot}@{r["t"]}: done not bool')
    return dict(ok=not problems, problems=problems)


def act_loop(transport, robots, kinds, ticks, frame_for, *, issue=None, step=None, initial_pwm=None):
    """One world, ACT grasp per robot; same builder/client/observer order as route_tick."""
    from harness.e2e_min_act import ActObservationBuilder, ActSkillClient
    start = initial_pwm or search_pwm()
    builders, clients, issued = {}, {}, {}
    for robot in robots:
        first = H.hold_command(0.0, start)
        builders[robot] = ActObservationBuilder(robot, kinds[robot], 'west', first)
        clients[robot] = ActSkillClient(robot, 'grasp', builders[robot], transport)
        issued[robot] = [first]
    rows = []
    for tick in range(ticks):
        now = tick / 10
        for robot in robots:
            frame = Frame(robot, frame_for(robot, tick), tuple(issued[robot][-16:]))
            t0 = time.perf_counter()
            out = clients[robot].propose(frame, now)
            latency = time.perf_counter() - t0
            command = out['command']   # issued unchanged, as RobotHandoff._grasp does
            builders[robot].observe_tick(robot, frame, now, command)
            issued[robot].append(command)
            if issue is not None:
                issue(robot, command)
            rows.append(dict(robot=robot, tick=tick, t=now, command=command, done=out['done'],
                             latency_s=round(latency, 4)))
        if step is not None:
            step(tick)
    return dict(rows=rows, calls={r: clients[r].calls for r in robots},
                clock_resets={r: builders[r].v7.resets for r in robots})


def release_loop(robots, odometry_for, held, params, max_ticks, *, issue=None, step=None):
    """release_open_v1 per robot from the held PWM until done (or max_ticks)."""
    from harness.e2e_min_release import ReleaseOpenV1
    scripts = {r: ReleaseOpenV1(r, odometry_for(r), **params) for r in robots}
    issued = {r: [H.hold_command(0.0, held)] for r in robots}
    done = {r: None for r in robots}
    tick = 0
    while tick < max_ticks and any(d is None for d in done.values()):
        now = tick / 10
        for robot in robots:
            if done[robot] is not None:
                command = H.hold_command(now, issued[robot][-1]['pwm'])
            else:
                out = scripts[robot].propose(Frame(robot, b'', tuple(issued[robot][-16:])), now)
                command = H.check_command(out['command'])
                if out['done']:
                    done[robot] = tick
            issued[robot].append(command)
            if issue is not None:
                issue(robot, command)
        if step is not None:
            step(tick)
        tick += 1
    return dict(ticks=tick, done_tick=done, scripts={r: s.record() for r, s in scripts.items()})


def release_plumbing(result, params):
    from harness.e2e_min_release import DEFAULTS, OPEN_PWM
    p = {**DEFAULTS, **params}
    problems = []
    for robot, rec in result['scripts'].items():
        if result['done_tick'][robot] is None:
            problems.append(robot + ': not done')
        if not any(row['pwm1'] == OPEN_PWM for row in rec['log']):
            problems.append(robot + ': gripper never commanded to OPEN_PWM')
        if rec['backed_m'] < p['backoff_m'] - 1e-9:
            problems.append(robot + ': own-odometry backoff short')
    return dict(ok=not problems, problems=problems)


def nav_plumbing(result, robots):
    problems = []
    for robot in robots:
        r = result['robots'][robot]
        if r['proposals'] < 1:
            problems.append(robot + ': adapter never queried')
        if r['pwm_not_held']:
            problems.append(robot + ': issued PWM differs from held PWM')
    return dict(ok=not problems, problems=problems)


def synthetic_jpeg(shade=128, size=(640, 480)):
    from PIL import Image
    import io
    buf = io.BytesIO()
    Image.new('RGB', size, (shade, shade, shade)).save(buf, format='JPEG', quality=82)
    return buf.getvalue()


# ------------------------------------------------------------ source / output
def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def admit_source(expected_sha, out):
    """Same guards as carry_pose_render.py: clone root CWD, exact clean HEAD, new output dir."""
    if Path.cwd().resolve() != ROOT:
        raise SystemExit('CWD_MUST_BE_CLONE_ROOT')
    out = Path(out).resolve()
    if out.exists():
        raise SystemExit('OUTPUT_EXISTS:' + str(out))
    head = git('rev-parse', 'HEAD')
    if head != expected_sha:
        raise SystemExit('SOURCE_SHA_MISMATCH:' + head)
    if git('status', '--porcelain', '--untracked-files=normal'):
        raise SystemExit('SOURCE_DIRTY')
    out.mkdir(parents=True)
    return head, out


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=1, allow_nan=False) + '\n')


# ------------------------------------------------------------- one MJWarp world
class OneWorld:
    """One nav-scene world through the runner's own build_context/transport/issue."""

    def __init__(self, out, head, *, nav_cubes=None, nav_arm_pwm=None, nav_keep=ROBOTS):
        import numpy as np
        from scripts.e2e_warp_physics import build_context, issue, transport
        stack = json.loads((ROOT / 'configs/current_stack.json').read_text())
        self.values = {r['id']: r['current'] for r in stack['rules'] if 'e2e_llm' in r['flows']}
        folder = out / 'world-00'
        self.ctx = build_context(SEED, folder, self.values, nav_scene=True, nav_keep=nav_keep,
                                 nav_cubes=nav_cubes, nav_arm_pwm=nav_arm_pwm)
        self.geometry = json.loads((folder / 'eval-geometry.json').read_text())
        t0 = time.perf_counter()
        self.hooks = transport([self.ctx], out / 'transport', head, self.values)
        self.hooks.initialize([self.ctx])
        self.init_s = time.perf_counter() - t0
        self._issue, self._np = issue, np
        self.xml_sha256 = hashlib.sha256(self.ctx['world'].scene_xml.encode()).hexdigest()

    def capture(self, robot):
        return self.hooks.capture(0, self.ctx['world'], robot)

    def issue(self, robot, command):
        self._issue(self.ctx, robot, command)

    def step(self, _tick=None):
        self.hooks.step([self.ctx], self._np.ones(1, dtype=bool))

    def eval_xy(self, robot):
        """Eval-only base xy (never fed to a component)."""
        adr = self.geometry['robot_qpos_adr'][robot]
        q = self.ctx['world'].data.qpos
        return [round(float(q[adr]), 4), round(float(q[adr + 1]), 4)]

    def eval_cube(self, robot):
        adr = (self.geometry.get('cube_qpos_adr') or {}).get(robot)
        if adr is None:
            return None
        q = self.ctx['world'].data.qpos
        return [round(float(v), 4) for v in q[adr:adr + 3]]

    def close(self):
        close = getattr(self.hooks, 'close', None)
        if callable(close):
            close()


# ----------------------------------------------------------------- sub-commands
def cmd_act_server(a):
    from harness.e2e_min_act import ActServerTransport
    from harness.e2e_min_runner import act_server_argv
    head, out = admit_source(a.expected_source_sha, a.out)
    act = act_config(a)
    record = header('act-server', source_sha=head, frames=a.frames, ticks=a.ticks, robots=list(a.robots),
                    act={k: v for k, v in act.items()}, actuation=_actuation())
    world, transport = None, None
    t0 = time.perf_counter()
    try:
        transport = ActServerTransport(act_server_argv(act), stderr_path=out / 'act-server.stderr.log')
        record['server_start_s'] = round(time.perf_counter() - t0, 2)
        record['receipt'] = transport.hello
        record['receipt_problems'] = check_act_receipt(transport.hello, act)
        cubes = cube_spec(a.robots)
        kinds = {r: cubes[r]['item_id'].split('_')[0] for r in a.robots}
        if a.frames == 'synthetic':
            grey = synthetic_jpeg()
            result = act_loop(transport, a.robots, kinds, a.ticks, lambda r, t: grey)
            record['physics'] = 'none (open loop; commands not issued)'
        else:
            world = OneWorld(out, head, nav_cubes=cubes, nav_keep=ROBOTS)
            record.update(world_init_s=round(world.init_s, 2), xml_sha256=world.xml_sha256, cubes=cubes,
                          eval_only=dict(cube_start={r: world.eval_cube(r) for r in a.robots},
                                         base_start={r: world.eval_xy(r) for r in a.robots}))
            frames_dir = out / 'frames'
            frames_dir.mkdir()

            def frame_for(robot, tick):
                jpeg = world.capture(robot)
                if tick % 5 == 0:
                    (frames_dir / f'{robot}-{tick:04d}.jpg').write_bytes(jpeg)
                return jpeg
            t1 = time.perf_counter()
            result = act_loop(transport, a.robots, kinds, a.ticks, frame_for,
                              issue=world.issue, step=world.step)
            record['loop_s'] = round(time.perf_counter() - t1, 2)
            record['physics'] = 'MJWarp one world, ACT commands issued every tick'
            record['eval_only'].update(cube_end={r: world.eval_cube(r) for r in a.robots},
                                       base_end={r: world.eval_xy(r) for r in a.robots})
        record.update(result)
        record['plumbing'] = act_plumbing(record, a.robots, a.ticks)
        record['status'] = 'PLUMBING_OK' if record['plumbing']['ok'] else 'PLUMBING_FAIL'
    except Exception as exc:
        record['status'] = 'HOST_ERROR'
        record['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        if transport is not None:
            try:
                transport.close()
            except Exception as exc:  # recorded, not hidden
                record['close_error'] = f'{type(exc).__name__}: {exc}'
        if world is not None:
            world.close()
        record['wall_s'] = round(time.perf_counter() - t0, 2)
        write_json(out / 'standalone-act-server.json', record)
    print(json.dumps(dict(out=str(out), status=record['status'], label=LABEL), ensure_ascii=False))
    return 0 if record['status'] == 'PLUMBING_OK' else 1


def release_params(a):
    params = {}
    for key in ('stop_ticks', 'backoff_m'):
        value = getattr(a, key)
        if value is not None:
            params[key] = value
    return params


def cmd_release_open(a):
    from harness.e2ewarp_nav_gate import load_calibration
    from harness.e2ewarp_selfnav import OwnCommandOdometry
    if a.physics == 'warp':
        head, out = admit_source(a.expected_source_sha, a.out)
    else:
        out = Path(a.out).resolve()
        if out.exists():
            raise SystemExit('OUTPUT_EXISTS:' + str(out))
        out.mkdir(parents=True)
        head = git('rev-parse', 'HEAD')
    calibration = load_calibration(a.calibration)
    constants = calibration['constants']
    held = held_pose(a.held_pose)
    params = release_params(a)
    record = header('release-open', source_sha=head, physics=a.physics, robots=list(a.robots),
                    held_pose=a.held_pose, held_pwm=held, params=params, actuation=_actuation(),
                    calibration=dict(path=str(calibration.get('path')), sha256=calibration.get('sha256'),
                                     constants=dict(constants)),
                    cube='none (no grasp in standalone; gripper opens on empty fingers)')

    def odometry_for(_robot):
        return OwnCommandOdometry(forward_m_per_pct_s=constants['forward_m_per_pct_s'],
                                  yaw_deg_per_pct_s=constants['yaw_deg_per_pct_s'])
    world = None
    t0 = time.perf_counter()
    try:
        if a.physics == 'warp':
            world = OneWorld(out, head, nav_arm_pwm={r: held for r in ROBOTS})
            record.update(world_init_s=round(world.init_s, 2), xml_sha256=world.xml_sha256)
            start = {r: world.eval_xy(r) for r in a.robots}
            result = release_loop(a.robots, odometry_for, held, params, a.max_ticks,
                                  issue=world.issue, step=world.step)
            end = {r: world.eval_xy(r) for r in a.robots}
            record['eval_only'] = dict(base_start=start, base_end=end, base_displacement_m={
                r: round(((end[r][0] - start[r][0]) ** 2 + (end[r][1] - start[r][1]) ** 2) ** .5, 4)
                for r in a.robots}, note='GT displacement vs own-odometry backed_m; recorded, not judged')
        else:
            result = release_loop(a.robots, odometry_for, held, params, a.max_ticks)
        record.update(result)
        record['plumbing'] = release_plumbing(result, params)
        record['status'] = 'PLUMBING_OK' if record['plumbing']['ok'] else 'PLUMBING_FAIL'
    except Exception as exc:
        record['status'] = 'HOST_ERROR'
        record['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        if world is not None:
            world.close()
        record['wall_s'] = round(time.perf_counter() - t0, 2)
        write_json(out / 'standalone-release-open.json', record)
    print(json.dumps(dict(out=str(out), status=record['status'], label=LABEL), ensure_ascii=False))
    return 0 if record['status'] == 'PLUMBING_OK' else 1


def load_carry_verdict(a):
    if a.assume_verdict is not None:
        return dict(adopted=a.assume_verdict), dict(source='assumed (--assume-verdict; NOT render-verified)')
    if not a.carry_pose_verdict or not a.carry_pose_verdict_sha256:
        raise SystemExit('CARRY_POSE_VERDICT_REQUIRED (or --assume-verdict act_lift_end)')
    from harness.e2e_min_runner import load_verdict
    spec = dict(path=str(a.carry_pose_verdict), sha256=a.carry_pose_verdict_sha256)
    return load_verdict(spec), dict(source='measure.json', **spec)


def cmd_nav_render(a):
    import os
    from harness import e2ewarp_l1lite as l1lite
    from harness.e2e_warp_components import require_navigation
    from harness.e2e_warp_runtime import OwnFrame
    from harness.e2ewarp_nav_gate import (bind_slot_decisions, l1lite_enabled, load_calibration,
                                          validate_calibration_binding)
    from harness.e2ewarp_nav_mode import NavRobot, nav_static
    from harness.e2e_min_runtime import NavCarryAdapter
    verdict, verdict_source = load_carry_verdict(a)
    if verdict.get('adopted') != 'act_lift_end':
        # Same rule as NavCarryAdapter; checked before any GPU work.
        raise SystemExit('E2E_MIN_TODO:carry_pose_transition:' + str(verdict.get('adopted')))
    if not l1lite_enabled():
        raise SystemExit('E2EWARP_NAV_L1LITE=on_v1 required (same nav path as the E2E runner)')
    head, out = admit_source(a.expected_source_sha, a.out)
    held = held_pose('act_lift_end')
    env = {k: os.environ.get(k) for k in ('E2EWARP_NAV_GATE_MODE', 'E2EWARP_NAV_ARRIVAL',
                                          'E2EWARP_NAV_CALIBRATION', 'E2EWARP_NAV_L1LITE',
                                          'E2E_MIN_ACTUATION')}
    record = header('nav-render', source_sha=head, robots=list(a.robots), ticks_cap=a.ticks,
                    carry_pose_verdict=verdict_source, adopted=verdict.get('adopted'), held_pwm=held,
                    slots={r: FIXED_SLOTS[r] for r in a.robots}, env=env,
                    components=dict(path=str(a.components), sha256=sha256(a.components)),
                    cube='none (no grasp in standalone; cube occlusion is carry_pose_render scope)',
                    start='nav lane spawn (r5), not the post-grasp pose')
    world = None
    t0 = time.perf_counter()
    try:
        components = require_navigation(a.components, ROOT)
        # Same admission the runner does (validate_calibration_binding) for the
        # E2EWARP_NAV_CALIBRATION file; the factory reads only this record.
        calibration = load_calibration()
        validate_calibration_binding(dict(nav_calibration=dict(sha256=calibration['sha256'])))
        record['calibration'] = dict(path=calibration['path'], sha256=calibration['sha256'],
                                     constants=dict(calibration['constants']))
        bind_slot_decisions({r: FIXED_SLOTS[r] for r in ROBOTS}, robots=ROBOTS)
        world = OneWorld(out, head, nav_arm_pwm={r: held for r in ROBOTS})
        record.update(world_init_s=round(world.init_s, 2), xml_sha256=world.xml_sha256,
                      destination=world.geometry.get('destination'))
        adapters, issued, stats = {}, {}, {}
        for robot in a.robots:
            static = nav_static(dict(orders=l1lite.order_sheet()['orders'], condition='no_comm',
                                     robot_count=len(ROBOTS), destination_zone='B',
                                     slots={robot: FIXED_SLOTS[robot]}))
            task = NavRobot(robot, static, components)
            candidate = next((c for c in task.candidates()
                              if (c.get('order') or {}).get('slot') == FIXED_SLOTS[robot]), None)
            if candidate is None:
                raise ValueError('L1LITE_ORDER_CANDIDATE_MISSING:' + robot)
            task.select(candidate, 0.0, reason='standalone smoke: fixed spawn-lane slot (no LLM)')
            adapters[robot] = NavCarryAdapter(task, carry_pose_verdict=verdict)
            issued[robot] = [H.hold_command(0.0, held)]
            stats[robot] = dict(proposals=0, arrived_tick=None, no_claim_tick=None, pwm_not_held=0,
                                moving_ticks=0, base_start=world.eval_xy(robot))
        frames_dir = out / 'frames'
        frames_dir.mkdir()
        tick = 0
        for tick in range(a.ticks):
            now = tick / 10
            for robot in a.robots:
                jpeg = world.capture(robot)
                if tick % a.save_every == 0:
                    (frames_dir / f'{robot}-{tick:04d}.jpg').write_bytes(jpeg)
                s = stats[robot]
                if s['arrived_tick'] is not None or s['no_claim_tick'] is not None:
                    command = H.hold_command(now, held)          # handoff: release / FAIL hold
                else:
                    frame = OwnFrame(robot, 0, tick, now, jpeg, tuple(issued[robot][-16:]))
                    proposal = adapters[robot].propose(frame, now)
                    s['proposals'] += 1
                    if proposal['no_claim'] is True:
                        s['no_claim_tick'] = tick                # handoff: E2E_NAV_NO_CLAIM
                        command = H.hold_command(now, held)
                    elif proposal['arrived'] is True:
                        s['arrived_tick'] = tick                 # handoff: hold, release next tick
                        command = H.hold_command(now, held)
                    else:
                        command = carry_command(now, proposal['command'], held)
                    adapters[robot].record_issued(command)
                if command['pwm'] != held:
                    s['pwm_not_held'] += 1
                if any(w != 0.0 for w in command['wheels']):
                    s['moving_ticks'] += 1
                issued[robot].append(command)
                world.issue(robot, command)
            if all(stats[r]['arrived_tick'] is not None or stats[r]['no_claim_tick'] is not None
                   for r in a.robots):
                break
            world.step(tick)
        for robot in a.robots:
            stats[robot]['base_end'] = world.eval_xy(robot)
        record.update(ticks=tick + 1, robots=stats)
        record['plumbing'] = nav_plumbing(record, a.robots)
        record['eval_only_note'] = 'base xy and destination are eval-only; arrival flag is own claim, unverified'
        record['status'] = 'PLUMBING_OK' if record['plumbing']['ok'] else 'PLUMBING_FAIL'
    except Exception as exc:
        record['status'] = 'HOST_ERROR'
        record['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        if world is not None:
            world.close()
        record['wall_s'] = round(time.perf_counter() - t0, 2)
        write_json(out / 'standalone-nav-render.json', record)
    print(json.dumps(dict(out=str(out), status=record['status'], label=LABEL), ensure_ascii=False))
    return 0 if record['status'] == 'PLUMBING_OK' else 1


def _actuation():
    from harness import e2e_min_actuation as A
    return A.mode()


# ----------------------------------------------------------------------- CLI
def build_parser():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)

    def common(p, *, source_required=True):
        p.add_argument('--enabled', action='store_true', help='required (default off)')
        p.add_argument('--out', type=Path, required=True, help='new directory')
        p.add_argument('--expected-source-sha', required=source_required)
        p.add_argument('--robots', type=parse_robots, default=ROBOTS)

    p = sub.add_parser('act-server', help='ACT grasp server alone (+ one world request round trip)')
    common(p)
    p.add_argument('--act-python', type=Path, required=True)
    p.add_argument('--act-source', type=Path, required=True)
    p.add_argument('--expected-act-sha', required=True)
    p.add_argument('--checkpoint', type=Path, required=True)
    p.add_argument('--expected-model-sha256', required=True)
    p.add_argument('--device', default='cuda')
    p.add_argument('--frames', choices=('synthetic', 'render'), default='render')
    p.add_argument('--ticks', type=int, default=30)
    p.set_defaults(func=cmd_act_server)

    p = sub.add_parser('release-open', help='release_open_v1 alone')
    common(p, source_required=False)
    p.add_argument('--physics', choices=('none', 'warp'), default='warp')
    p.add_argument('--calibration', type=Path, required=True, help='nav-calibration.json (r5)')
    p.add_argument('--held-pose', default=DEFAULT_HELD_POSE)
    p.add_argument('--stop-ticks', type=int, default=None)
    p.add_argument('--backoff-m', type=float, default=None)
    p.add_argument('--max-ticks', type=int, default=120)
    p.set_defaults(func=cmd_release_open)

    p = sub.add_parser('nav-render', help='NavCarryAdapter with the held carry pose alone')
    common(p)
    p.add_argument('--components', type=Path, required=True, help='e2ewarp_nav_manifest output')
    p.add_argument('--carry-pose-verdict', type=Path, default=None, help='carry_pose_render measure.json')
    p.add_argument('--carry-pose-verdict-sha256', default=None)
    p.add_argument('--assume-verdict', choices=('act_lift_end',), default=None,
                   help='use before the render verdict exists; recorded as NOT render-verified')
    p.add_argument('--ticks', type=int, default=600, help='cap (60 SIM s = nav carry budget)')
    p.add_argument('--save-every', type=int, default=5)
    p.set_defaults(func=cmd_nav_render)
    return ap


def parse_args(argv=None):
    a = build_parser().parse_args(argv)
    if not a.enabled:
        raise SystemExit('STANDALONE_SMOKE_DEFAULT_OFF: pass --enabled')
    if a.cmd == 'release-open' and a.physics == 'warp' and not a.expected_source_sha:
        raise SystemExit('--expected-source-sha required with --physics warp')
    if getattr(a, 'ticks', 1) < 1 or getattr(a, 'max_ticks', 1) < 1 or getattr(a, 'save_every', 1) < 1:
        raise SystemExit('tick counts must be >= 1')
    if a.cmd == 'nav-render' and a.assume_verdict and a.carry_pose_verdict:
        raise SystemExit('--assume-verdict and --carry-pose-verdict are exclusive')
    return a


def main(argv=None):
    a = parse_args(argv)
    return a.func(a)


if __name__ == '__main__':
    raise SystemExit(main())
