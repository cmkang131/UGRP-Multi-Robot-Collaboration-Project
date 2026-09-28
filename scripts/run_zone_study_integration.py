"""Physical no-LLM plumbing run of the integrated zone study (issue #223).

One MuJoCo world (sync SIM), three robots, one own-camera executor each (#206),
driven by the study core (#194) through ``harness.zone_study_integration``:

    fixture actor reply -> SIM-costed release -> executor job API -> physics
    -> own executor events -> own wake triggers -> next call (own RGB inputs)

The physics owner advances in ``QUANTUM_S`` chunks; every scheduler event lands
on a chunk boundary. Robot inputs: own robot_cam frames, own issued commands,
static tagged map, order sheet from the scenario config, and (by condition) the
messages actually delivered. Simulator truth goes to ``eval_only/`` only. Weld
OFF, contact profile ``cargo_noslip_v1`` (user approval 2026-09-26).

Pose provider: chosen by ``--prereg``'s ``pose_provider`` from
``configs/zone_study_integration/pose_providers.json``; ``tags_temporary`` is the
own-camera wall-tag PF, a TEMPORARY provider: "임시, 표식 사용, 연구 결과 아님".

CLI defaults to plumbing with fixture decisions. ``--llm`` drives real model
calls per robot per turn through the same scheduler and own-camera inputs
(B7, ``harness.zone_study_llm_driver``): the prereg selects a registered driver
profile and speech-cap profile, and every POST is recorded in the NEW main-study
ledger (``harness.zone_main_budget``, never the #222 pilot DB) with raw
request/response bytes, tokens, latency and failure class. The only retry is
in place, once, for a HOST_ERROR before the first model request. Tests exercise
the driver over a fake wire, without a model call or physical run.

    python scripts/run_zone_study_integration.py --prereg experiments/2026-09-26-zone-study-integration/prereg.json \
        --episode smoke-i700 --condition no_comm --output /Users/changmin/projects/ugrp/outputs/zone-study-integration
    python scripts/run_zone_study_integration.py --prereg ... --episode smoke-i700 --bundle   # print the run bundle only
    python scripts/run_zone_study_integration.py --prereg <main prereg> --episode ... --condition peer_ko \
        --output ... --llm --proxy-pid <running proxy PID>        # real model calls (prereg llm_driver block)
"""
from __future__ import annotations

import argparse
import base64
import collections
import copy
import json
import math
import os
import platform
import subprocess
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness import zone_study_integration as zi  # noqa: E402
from harness import zone_study_offline as zo  # noqa: E402
from harness import zone_study_llm_driver as llm  # noqa: E402
from harness import zone_study_referee as zr  # noqa: E402  (eval only: physics owner side, never the study layer)
from harness.zone_own_executor import OwnCamTeamHost, ROBOTS  # noqa: E402
from harness.zone_study_contract import MAIN_CONDITIONS, digest  # noqa: E402
from sim import zone_eval_top  # noqa: E402
from sim import zone_hidden_events as zhe  # noqa: E402  (eval only: experimenter-injected physics)

SCHEMA = 'ugrp.zone_study_integration_run.v1'
ON_FLOOR_MAX_Z_M = zr.ON_FLOOR_MAX_Z_M
SLOT_HALF_M = .06
TAP_FRAMES = 64
PROGRESS_EVERY_S = 60.
# Module names selected by config (importlib) are roots too. External adapter
# injection uses the supported transport entry point, even in fixture bundles.
RUNTIME_ENTRY_POINTS = ('scripts/run_zone_study_integration.py',
                        'harness/zone_study_llm_transport.py')
RUNTIME_ASSETS = ('configs/zone_study_integration/pose_providers.json',
                  'configs/zone_study_integration/llm_driver.json')


def runtime_files(prereg, provider):
    from harness.python_source_closure import source_closure
    return source_closure(ROOT, (*RUNTIME_ENTRY_POINTS, *RUNTIME_ASSETS, *provider['source_files']),
                          modules=(prereg['student']['skill_module'], provider['factory'].partition(':')[0]))



def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(r, ensure_ascii=False, default=str) + '\n' for r in rows))


# ---------------------------------------------------------------------------
# One robot seen by the study layer

class HostRobotLink:
    """``zi.RobotLink`` over ONE host robot slot: own frames, own executor, own job API."""

    def __init__(self, host, rid):
        self.robot_id, self._host, self._slot = rid, host, host.robots[rid]
        self._frames = collections.deque(maxlen=TAP_FRAMES)
        self.aborts = []
        capture = self._slot.port.capture

        def tapped(camera='robot_cam'):
            if camera != 'robot_cam':
                raise zi.ContractViolation(f'{rid}: study inputs require own robot_cam, got {camera!r}')
            obs = capture(camera)
            jpeg = base64.b64decode(obs['image'])
            if (zi.hashlib.sha256(jpeg).hexdigest() != obs['sha256'] or obs['robot_id'] != rid
                    or obs['camera'] != 'robot_cam'):
                raise RuntimeError(f'{rid}: frame tap got a foreign or corrupted frame')
            self._frames.append(zi.OwnFrame(len(self._slot.frames), round(float(obs['sim_time']), 4), jpeg,
                                            obs['sha256']))
            return obs
        self._slot.port.capture = tapped

    def clock(self):
        return float(self._host.world.data.time)

    def frame_at(self, t):
        return next((f for f in reversed(self._frames) if f.t <= t + 1e-9), None)

    def belief(self):
        return self._slot.executor.belief_projection()

    def job(self):
        job = self._slot.executor.job
        return None if job is None else {'kind': job.kind, 'order_id': job.args.get('order_id'),
                                         'job_id': job.job_id}

    def call(self, api, *args):
        """The executor job API of THIS robot. An accepted abort also drops the host's
        scheduled macro commands of this robot and holds at once (#221 P1 at the host layer)."""
        before = len(self._slot.cancellations)
        ack = self._host.call(self.robot_id, api, *args)
        if api == 'abort' and ack['accepted']:
            self.aborts.extend(copy.deepcopy(self._slot.cancellations[before:]))
        return ack



class StudyTeamHost(OwnCamTeamHost):
    """#206's 3-robot host, stepped in chunks by the study clock, pose provider from config."""

    def __init__(self, spec, student, *, root, provider_spec, frames_dir=None, hidden=None):
        self.provider_sources = {}
        self.hidden = hidden or zr.HiddenEventSchedule({'eval': {'hidden_events': []}})
        providers = []

        def pose_factory(rid, static, params, seed):
            provider = zi.build_pose_provider(provider_spec, static, params, seed)
            providers.append(provider)
            if callable(getattr(getattr(provider, 'provider', provider), 'init_prior', None)):
                prior = spec.get('pose_priors', {}).get(rid)
                if prior is None:
                    raise zi.ContractViolation(f'{rid}: provider requires a preregistered own dock prior')
                provider.init_prior(**prior)
            self.provider_sources[rid] = provider.source
            return provider

        scene = None
        if spec.get('pair_order_sheets') and provider_spec['uses_landmark_tags']:
            # Reuse #235's standard Scene setup (drops its colour placeholder
            # before XML generation, never based on runtime state).
            from scripts.zone_pair_dev_runtime import make_scene
            scene = make_scene(spec)
        if self.hidden.obstacles():
            # Parked obstacles through the host's scene= argument (the host and
            # the frozen scene sources stay unchanged); none -> the same scene.
            scene = zhe.hidden_event_scene(spec, spec['contact_profile'], self.hidden.obstacles(), scene)
        try:
            super().__init__(spec, student, root=root, study_layer=self._no_layer, frames_dir=frames_dir,
                             scene=scene, pose_factory=pose_factory)
        except Exception:
            for provider in providers:
                if callable(getattr(provider, 'close', None)):
                    provider.close()
            if hasattr(self, 'world'):
                self.world.close()
            raise
        # scene.setup has finished. Overlay only the evaluation cameras in the
        # world; keep self.static and every executor's own static map untouched.
        profile = evaluation_top_config(self.static)['profile']['id']
        self.eval_static = zone_eval_top.eval_static_map(self.static, profile)
        self.eval_only['top_camera'] = zone_eval_top.apply_to_world(self.world, self.static, profile)
        self.links = {rid: HostRobotLink(self, rid) for rid in ROBOTS}
        # Hidden events act on physics only (sim.zone_hidden_events): never a robot
        # input, command row or wake. No events -> nothing is built or wrapped.
        self.hidden_physics = (zhe.HiddenEventPhysics(self.world, self.hidden, objects=self.objects,
                                                      item_geoms=self._box_geom, finger_geoms=self._fingers)
                               if self.hidden.events else None)

    @property
    def hidden_log(self):
        return self.hidden_physics.log if self.hidden_physics is not None else []

    def hidden_tick(self, now):
        """Fire the due hidden events (before physics advances past ``now``)."""
        if self.hidden_physics is not None:
            self.hidden_physics.tick(now)

    # -- referee truth (eval only) -----------------------------------------------
    def referee_truth(self):
        """Per item: pose, height, finger contact and speed from simulator truth. Evaluation only."""
        import mujoco
        import numpy as np
        m, d = self.world.model, self.world.data
        held = set()
        fingers = {r: self._fingers[r][0] | self._fingers[r][1] for r in ROBOTS}
        every = set().union(*fingers.values())
        for i in range(d.ncon):
            pair = {int(d.contact[i].geom1), int(d.contact[i].geom2)}
            if pair & every:
                held.update(b for b, gs in self._box_geom.items() if pair & gs)
        out, vel = {}, np.zeros(6)
        for item, o in self.objects.items():
            if 'body_name' not in o:
                continue
            b = d.body(o['body_name'])
            mujoco.mj_objectVelocity(m, d, mujoco.mjtObj.mjOBJ_BODY, int(b.id), vel, 0)
            out[item] = {'kind': o['kind'], 'x': float(b.xpos[0]), 'y': float(b.xpos[1]),
                         'yaw': zr.item_yaw(b.xquat), 'z': float(b.xpos[2]), 'held': item in held,
                         'speed': float(np.linalg.norm(vel[3:6]))}
        return out

    @staticmethod
    def _no_layer(*_args):
        raise AssertionError('StudyTeamHost is stepped by advance_to(), never by run()')

    def settle(self, t0):
        """Settle to the first quantum boundary >= ``t0`` and the post-setup SIM time; one own frame each."""
        q = zi.QUANTUM_S
        start = round(q * math.ceil(max(float(t0), float(self.world.data.time)) / q - 1e-9), 6)
        self._physics_until(start)
        now = float(self.world.data.time)
        for rid, slot in self.robots.items():
            self._capture(rid, now)
            slot.next_decide = now
        return start

    def advance_to(self, t_end):
        """Advance own jobs even while the scheduler charges thinking/talking (#223).

        Idle executors wait; busy executors keep their current job/macros.
        Scheduler holding is a pending decision, not a physical pause command.
        """
        data, events = self.world.data, []
        while True:
            now = float(data.time)
            for rid in ROBOTS:
                slot = self.robots[rid]
                if slot.dead:
                    continue
                deadline = slot.executor.deadline()
                if deadline is not None and now > deadline:
                    self._expire(rid, now)
                if slot.timeline or slot.capture_after:
                    self._run_timeline(rid, now)
                if not slot.timeline and not slot.capture_after and now + 1e-9 >= slot.next_decide:
                    self._decide(rid, now)
            for rid in ROBOTS:
                events.extend(self.robots[rid].executor.drain_events())
            if now >= t_end - 1e-9:
                self.event_log.extend(events)
                return events
            # Visit the host's physics ticks: independent pair heartbeat/arm
            # clocks and macro deadlines must not depend on a peer's wakeups.
            self._physics_until(min(now + float(self.world.model.opt.timestep), t_end))

    def close(self):
        errors = []
        for slot in self.robots.values():
            close = getattr(slot.executor.pose, 'close', None)
            if close is not None:
                try:
                    close()
                except Exception as exc:
                    errors.append(exc)
        try:
            super().close()
        finally:
            if errors:
                raise errors[0]



# ---------------------------------------------------------------------------
# Bundle, scenario, plan

def evaluation_top_config(static):
    """Pinned evaluation/video overlay; never part of the robots' map/input bundle."""
    base_id, _ = zone_eval_top.base_map_of(static)
    profile = 'zone_eval_top_v2' if base_id == 'zone_wide_corridor' else 'zone_eval_top_v1'
    cameras = zone_eval_top.eval_top_cameras(static, profile)
    return {'profile': zone_eval_top.profile_record(profile), 'cameras': cameras,
            'cameras_sha256': zone_eval_top.digest(cameras),
            'note': 'evaluation/video only; never a robot input; apply after scene.setup on replay'}


def load_prereg(path):
    prereg = json.loads(Path(path).read_text())
    if prereg.get('schema') != 'ugrp.zone_study_integration_prereg.v1':
        raise SystemExit(f'{path}: not an integration prereg')
    return prereg


class _StubLink:
    def __init__(self, rid):
        self.robot_id = rid

    def __getattr__(self, name):
        raise AssertionError(f'bundle construction must not touch a robot ({name})')


def host_spec(scenario, episode, map_bundle):
    """Only setup/static declarations; no runtime truth enters a pair order."""
    from harness.zone_study_inputs import OrderSheetSource
    from harness.zone_pair_executor import make_plan
    setup = scenario['eval']['setup']
    if (setup['contact_profile'] != 'cargo_noslip_v1' or episode['contact_profile'] != 'cargo_noslip_v1'
            or setup['weld'] != 'off'):
        raise zi.ContractViolation('study requires cargo_noslip_v1 and weld OFF in scenario and episode')
    spec = {k: copy.deepcopy(episode[k]) for k in
            ('map', 'goal', 'extra_boxes', 'contact_profile', 'job_sim_limit_s')}
    spec['seed'] = episode['layout_seed']
    spec['order_sheet'] = OrderSheetSource(scenario, map_bundle).sheet()
    team_orders = [o for o in spec['order_sheet']['orders'] if o['required_robots'] > 1]
    sheets = copy.deepcopy(episode.get('pair_order_sheets', {}))
    cargo = copy.deepcopy(episode.get('team_cargo', []))
    if team_orders:
        if (len(spec['order_sheet']['orders']) != 1 or len(team_orders) != 1 or team_orders[0]['kind'] != 'long_beam'
                or team_orders[0]['required_robots'] != 2 or team_orders[0]['count'] != 1
                or set(sheets) != {team_orders[0]['order_id']}
                or len(cargo) != 1 or cargo[0]['item_id'] != team_orders[0]['order_id']
                or cargo[0]['kind'] != 'long_beam'):
            raise zi.ContractViolation('M2 dev supports a pair-only order with explicit static sheet and matching order/item id')
        static = json.loads((ROOT / map_bundle['map_file']).read_text())
        make_plan(static, sheets[team_orders[0]['order_id']], team_orders[0]['destination_zone'])
    elif sheets or cargo:
        raise zi.ContractViolation('pair setup without a team order')
    spec.update(pair_order_sheets=sheets, team_cargo=cargo,
                pose_priors=copy.deepcopy(episode.get('pose_priors', {})))
    return spec


def run_bundle(prereg, episode, *, model_adapter=None, driver=None):
    """Everything that identifies this execution, hashed (docs/execution_versioning.md)."""
    from harness.zone_study_scenarios import bundle_for, validate
    from sim.zone_own_scene_provider import scene_static_map
    provider = zi.pose_provider_spec(prereg['pose_provider'], map_id=episode['map'])
    scenario = json.loads((ROOT / episode['scenario']).read_text())
    if not provider['uses_landmark_tags'] and scenario.get('landmark_detail') != 'none':
        raise SystemExit('geometry provider requires explicit landmark_detail=none')
    report = validate(scenario)
    if not report.ok:
        raise SystemExit(f'scenario {episode["scenario"]} fails validation: {report.checks}')
    map_bundle = bundle_for(scenario)
    static = json.loads(Path(map_bundle['map_file']).read_text())
    if static != scene_static_map(episode['map']):
        raise SystemExit('the map file the robots read differs from the static map the scene builds')
    spec = host_spec(scenario, episode, map_bundle)
    from scripts.zone_pair_dev_contract import profile_contract
    # Record the calibration actually passed to the executor/provider, including
    # the M2 loop-v2 calibration. Never label it with the registry's M1 default.
    provider['calibration'] = prereg['student']['calibration']
    stub = {r: _StubLink(r) for r in ROBOTS}
    limits, caps = llm.speech_caps_for(prereg)
    trial = zi.IntegratedTrial(scenario, condition=MAIN_CONDITIONS[0], seed=episode['trial_seed'], links=stub,
                               horizon_s=prereg['horizon_s'], map_bundle=map_bundle,
                               policy=zo.CallPolicy(**prereg.get('call_policy', {})),
                               decision_limits=limits,
                               pose_label=zi.provider_record(provider)['label'])
    invariant = zi.condition_invariant_config(trial.study_config())
    if driver is not None:
        model_adapter = zi.ModelAdapter(driver.client_factory, None)
    if model_adapter is not None:
        invariant.update(zi.model_config('gemini_proxy', model_adapter.client_factory))
    from harness.owncam_memory_time import TIME_CONTRACT
    bundle = {'execution_bundle_id': zi.EXECUTION_BUNDLE_ID, 'schema': SCHEMA,
              'memory_time_contract': TIME_CONTRACT,
              'runtime_files_sha256': {f: zi.file_sha256(ROOT / f) for f in runtime_files(prereg, provider)},
              'scenario': episode['scenario'], 'scenario_sha256': zi.file_sha256(ROOT / episode['scenario']),
              'map_id': episode['map'], 'map_file_sha256': map_bundle['map_file_sha256'],
              'public_map_sha256': map_bundle['public_map_sha256'], 'scene_static_map_sha256': digest(scene_static_map(episode['map'])),
              'physical': {k: episode[k] for k in ('base_map', 'layout_seed', 'goal', 'extra_boxes',
                                                    'contact_profile', 'job_sim_limit_s')},
              'actor': 'gemini_proxy' if model_adapter else zi.FIXTURE_ACTOR,
              'model_settings_sha256': digest(model_adapter.client_factory.settings) if model_adapter else None,
              'host_spec': spec, 'contact_profile_expected': profile_contract(),
              'perception_delay_s': zi.PERCEPTION_DELAY_S,
              'weld': 'off', 'sync_sim': True, 'frame_period_s': OwnCamTeamHost.FRAME_S,
              'executor_tick_s': zi.QUANTUM_S, 'student': dict(prereg['student']),
              'student_calibration_sha256': zi.file_sha256(ROOT / prereg['student']['calibration']),
              'pose_provider': zi.provider_record(provider),
              'eval_top_camera': evaluation_top_config(static),
              'referee': zr.profile(), 'hidden_events': zr.HiddenEventSchedule(scenario).config(),
              'study_invariant': invariant,
              'conditions': list(MAIN_CONDITIONS), 'horizon_s': prereg['horizon_s'],
              'speech_caps': caps, 'llm_driver': driver.bundle_record() if driver is not None else None}
    return bundle, scenario, map_bundle, provider


def placements_match(scenario, host):
    """The scenario's declared setup placements are the physical episode's."""
    want = {p['item_id']: [round(v, 4) for v in p['pose_m'][:2]] for p in scenario['eval']['setup']['placements']}
    got = {oid: [round(v, 4) for v in o['position_m'][:2]] for oid, o in host.objects.items()
           if 'position_m' in o}
    got.update({c['item_id']: [round(v, 4) for v in c['pose'][:2]] for c in host.spec.get('team_cargo', [])})
    if want != got:
        raise SystemExit(f'scenario placements {want} != physical episode {got}')


# ---------------------------------------------------------------------------
# Evaluation only (after the run, from simulator truth)

def robot_eval(host, rid, boxes_final):
    """Eval-only per-robot audit (#206 E3/E6 style) against simulator truth."""
    slot = host.robots[rid]
    ex = slot.executor
    summ = ex.summary()
    confirmed = []
    for job in summ['jobs']:
        if job['kind'] == 'deliver' and job['confirmation'] == 'own_camera_confirmed' and job.get('slot_id'):
            s = next(s for zs in host.static['zone_slots'].values() for s in zs if s['slot_id'] == job['slot_id'])
            in_slot = [b for b, (x, y, z) in boxes_final.items() if abs(x - s['center_m'][0]) <= SLOT_HALF_M
                       and abs(y - s['center_m'][1]) <= SLOT_HALF_M and z < ON_FLOOR_MAX_Z_M]
            confirmed.append({'job_id': job['job_id'], 'slot_id': job['slot_id'], 'cyan_in_slot': in_slot,
                              'false_confirmation': not in_slot})
    ev = host.eval_only
    return {'jobs': summ['jobs'], 'events': [e['event'] for e in ex.events], 'pose_sources_seen': summ['pose_sources_seen'],
            'cameras_seen': summ['cameras_seen'], 'counts_as_m1_inputs': summ['counts_as_m1_inputs'],
            'foreign_frames_fed': sum(1 for f in slot.frames if f['robot_id'] != rid or f['camera'] != 'robot_cam'),
            'rejected_foreign_frames': summ['rejected_foreign_frames'], 'frames': len(slot.frames),
            'commands': len(slot.commands), 'exception': slot.exception, 'dead': slot.dead,
            'aborts': host.links[rid].aborts, 'confirmed_deliveries': confirmed,
            'false_confirmations': sum(c['false_confirmation'] for c in confirmed),
            'evaluation_only': {'contact_steps': ev['kind_steps'][rid], 'retention': ev['retention'][rid]}}


# ---------------------------------------------------------------------------
# One trial

def check_run_source(prereg, bundle_sha, *, dev=False, expected_source_sha=None):
    """Fail before imports, output creation or host setup on a provenance mismatch.

    Resolve abbreviated commit IDs through Git (not a string-prefix comparison).
    --dev-horizon-s retains its unregistered plumbing escape only when no source
    pin is supplied; any explicit source pin is always binding.
    """
    code = {'sha': git('rev-parse', '--verify', 'HEAD^{commit}'),
            'dirty': bool(git('status', '--porcelain', '--', 'harness', 'sim', 'scripts', 'configs', 'maps'))}
    pins = [pin for pin in (prereg.get('source_sha'), expected_source_sha) if pin is not None]
    if not dev and not pins:
        raise SystemExit('pre-registered source_sha (or --expected-source-sha) is required')
    for pin in pins:
        if not isinstance(pin, str) or not 7 <= len(pin) <= 40 or any(c not in '0123456789abcdefABCDEF' for c in pin):
            raise SystemExit(f'invalid expected source SHA: {pin!r}')
        resolved = git('rev-parse', '--verify', pin + '^{commit}')
        if not resolved or resolved != code['sha']:
            raise SystemExit(f'run source SHA {code["sha"]} differs from expected source SHA {pin}')
    if not dev and code['dirty']:
        raise SystemExit('execution source is dirty; commit and preregister the final source before running')
    if not dev and prereg.get('bundle_sha256') != bundle_sha:
        raise SystemExit(f'run bundle {bundle_sha[:12]} differs from the pre-registered '
                         f'{str(prereg.get("bundle_sha256"))[:12]}; commit, then refresh the prereg')
    return code


def run_loop(host, trial, referee, t, horizon_s, *, progress=None, health=None):
    """The chunked episode loop. Returns (stop, t).

    Per chunk: due hidden events act on physics only -> physics + own executor
    events -> study scheduler -> (``health``: the B7 runner boundary, which
    raises on a fatal ledger/budget state before another physics step) ->
    eval-only referee sample. The referee's result reaches nothing but this
    loop's stop decision: robots see the episode end, exactly as at the
    horizon, and never why.
    """
    stop, next_report = 'horizon', t + PROGRESS_EVERY_S
    host.hidden_tick(t)
    while t < horizon_s - 1e-9:
        t = round(t + zi.QUANTUM_S, 6)
        if progress is not None and t >= next_report:
            next_report += PROGRESS_EVERY_S
            progress(t)
        for event in host.advance_to(t):
            trial.on_executor_event(event, at_s=t)
        trial.step_to(t)
        if health is not None:
            health(trial)
        host.hidden_tick(t)
        referee.observe(t, host.referee_truth())
        if referee.orders_complete():
            stop = zr.ev.SUCCESS_END_REASON
            break
        if all(s.dead for s in host.robots.values()):
            stop = 'all_robots_stopped'
            break
        if trial.quiescent():
            stop = 'quiescent_budget_spent'
            break
    return stop, t


def run_trial(prereg, episode, condition, out, *, horizon_s, dev=False, model_adapter=None,
              expected_source_sha=None, driver=None, run_key=None, attempt=1, raise_on_failure=True):
    """One trial attempt. With ``driver`` (``llm.LiveDriver``) the model adapter is built per attempt.

    ``raise_on_failure=False`` returns ``(record, exception)`` so the caller can
    apply the single pre-request retry (``llm.run_attempts``).
    """
    if driver is not None and (model_adapter is not None or run_key is None):
        raise zi.ContractViolation('a driver run builds its own adapter and needs the ledger run_key')
    bundle, scenario, map_bundle, provider = run_bundle(prereg, episode, model_adapter=model_adapter,
                                                        driver=driver)
    bundle_sha = digest(bundle)
    code = check_run_source(prereg, bundle_sha, dev=dev, expected_source_sha=expected_source_sha)
    import cv2
    import mujoco
    import numpy as np
    run_id = f'{condition}-{episode["episode_id"]}' + ('' if attempt == 1 else f'-attempt{attempt}')
    out = Path(out) / run_id
    out.mkdir(parents=True, exist_ok=False)                   # never overwrite a result
    started, load0 = time.time(), os.getloadavg()
    label = dict(bundle['pose_provider']['label'])
    (out / 'attempt_started.json').write_text(json.dumps(
        {'run_id': run_id, 'condition': condition, 'episode': episode['episode_id'], 'code': code, 'dev': dev,
         'bundle_sha256': bundle_sha, 'horizon_s': horizon_s, 'pose_provider': label,
         'attempt': attempt, 'ledger_run_key': run_key,
         'started_unix': round(started, 3), 'load_average_start': load0}, indent=2, ensure_ascii=False) + '\n')
    spec = host_spec(scenario, episode, map_bundle)
    host = trial = result = referee = error = None
    failure, t = None, 0.0
    try:
        if driver is not None:
            model_adapter = driver.adapter(run_key=run_key, store_dir=out / 'study' / 'wire')
        host = StudyTeamHost(spec, prereg['student'], root=ROOT, provider_spec=provider,
                             frames_dir=out / 'own_frames', hidden=zr.HiddenEventSchedule(scenario))
        expected = bundle['contact_profile_expected']
        if any(host.contact_record[k] != expected[k] for k in ('profile', 'base_profile', 'noslip_iterations', 'timestep_s')):
            raise zi.ContractViolation('applied contact profile differs from the pinned bundle')
        placements_match(scenario, host)
        host.assigned_box = {}
        trial = zi.IntegratedTrial(scenario, condition=condition, seed=episode['trial_seed'], links=host.links,
                                   horizon_s=horizon_s, code_sha=code['sha'], map_bundle=map_bundle,
                                   pose_label=label, actor='gemini_proxy' if model_adapter else zi.FIXTURE_ACTOR,
                                   model_adapter=model_adapter,
                                   policy=zo.CallPolicy(**prereg.get('call_policy', {})),
                                   decision_limits=llm.speech_caps_for(prereg)[0],
                                   pair_records=lambda: host.pairs.records() if host.pairs else [])
        referee = zr.Referee(spec['order_sheet']['orders'], host.static)
        t = host.settle(float(prereg['t0_s']))
        trial.begin(t)
        llm.check_trial_health(trial)
        stop, t = run_loop(host, trial, referee, t, horizon_s, progress=lambda t: print(json.dumps(
            {'run_id': run_id, 'sim_s': t, 'wall_s': round(time.time() - started, 1),
             'calls': len(trial.scheduler.calls), 'load': [round(v, 1) for v in os.getloadavg()]}),
            file=sys.stderr, flush=True), health=llm.check_trial_health)
        llm.check_trial_health(trial, final=True)
        for rid in ROBOTS:
            host._hold(rid, float(host.world.data.time))
        result = trial.finish(t)
    except Exception as exc:                                 # noqa: BLE001 - recorded, then re-raised below
        error = exc
        failure = {'type': type(exc).__name__, 'message': str(exc)[:2000], 'traceback': traceback.format_exc()[-8000:],
                   'sim_s': None if host is None else round(float(host.world.data.time), 3),
                   'failure_class': llm.classify_exception(exc)}
        stop = 'exception'
    finally:
        record = write_outputs(out, prereg, episode, condition, bundle, bundle_sha, host, trial, result, stop,
                               failure, code, started, load0, dev, referee=referee)
        if host is not None:
            host.close()
    env = {'mujoco': mujoco.__version__, 'opencv': cv2.__version__, 'numpy': np.__version__}
    manifest = json.loads((out / 'manifest.json').read_text())
    manifest['env'].update(env)
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str) + '\n')
    if not raise_on_failure:
        return record, error
    if failure is not None:
        raise SystemExit(f'{run_id}: {failure["type"]}: {failure["message"]}')
    return record


def write_outputs(out, prereg, episode, condition, bundle, bundle_sha, host, trial, result, stop, failure, code,
                  started, load0, dev, *, referee=None):
    """Everything that exists, also after an exception; returns the result summary."""
    ledger = getattr(trial, 'send_ledger', None) if trial is not None else None
    summary = {'schema': SCHEMA, 'run_id': out.name, 'condition': condition, 'episode': episode['episode_id'],
               'dev': dev, 'stop': stop, 'failure': failure, 'bundle_sha256': bundle_sha,
               'failure_class': (failure or {}).get('failure_class') or (
                   llm.trial_failure_class(None, ledger, transport=trial.transport)
                   if isinstance(ledger, llm.MainStudySendLedger) else None),
               'pose_provider': bundle['pose_provider']['label'],
               'actor': trial.actor if trial else prereg.get('actor', zi.FIXTURE_ACTOR),
               'plumbing_only': trial is None or trial.actor == zi.FIXTURE_ACTOR,
               'note_ko': '통합 dev 경로. 통신 효과·연구 결과가 아니다. ' + zi.TEMPORARY_NOTE_KO}
    if host is not None:
        summary['sim_s'] = round(float(host.world.data.time), 3)
        ev = host.eval_only
        boxes = {b: [float(v) for v in host.world.data.body(o['body_name']).xpos] for b, o in host.objects.items()
                 if o['kind'] in ('cyan', 'long_beam')}
        ref_row = referee.record() if referee is not None else None
        summary['robots'] = {rid: robot_eval(host, rid, boxes) for rid in ROBOTS}
        hidden = list(getattr(host, 'hidden_log', []))    # the full rows go to eval_only/hidden_events.jsonl only
        summary['eval_only'] = {'referee': ref_row, 'hidden_events': {'file': 'eval_only/hidden_events.jsonl',
                                                                       'rows': len(hidden)},
                                'box_final_xyz': {b: [round(v, 4) for v in p] for b, p in boxes.items()},
                                'weld_max_eq_active': ev['max_eq_active'], 'contact_profile': host.contact_record}
        for rid, slot in host.robots.items():
            base = out / 'robots' / rid
            jsonl(base / 'inputs' / 'commands.jsonl', slot.commands)
            jsonl(base / 'inputs' / 'pose_timing.jsonl', getattr(slot.executor.pose, 'timing', []))
            jsonl(base / 'inputs' / 'frames.jsonl', slot.frames)
            jsonl(base / 'executor' / 'events.jsonl', slot.executor.events)
            jsonl(base / 'executor' / 'api.jsonl', slot.executor.api_log)
            jsonl(base / 'executor' / 'judgments.jsonl', slot.executor.judgment_log)
            jsonl(base / 'executor' / 'macros.jsonl', slot.decisions)
            (base / 'executor' / 'job_summaries.json').write_text(
                json.dumps(slot.executor._summaries, indent=1, default=str) + '\n')
        jsonl(out / 'eval_only' / 'gt.jsonl', ev['gt'])
        jsonl(out / 'eval_only' / 'frames_eval.jsonl', ev['frames_eval'])
        jsonl(out / 'eval_only' / 'contacts.jsonl', ev['contacts'])
        (out / 'eval_only' / 'referee.json').write_text(json.dumps(ref_row, indent=1) + '\n')
        jsonl(out / 'eval_only' / 'hidden_events.jsonl', hidden)
        (out / 'eval_only' / 'top_camera.json').write_text(json.dumps(ev['top_camera'], indent=1) + '\n')
        (out / 'eval_only' / 'static_map.json').write_text(json.dumps(host.eval_static, indent=1) + '\n')
        (out / 'scene.xml').write_text(host.world.scene_xml)
        summary['provider_sources'] = dict(host.provider_sources)
    if trial is not None:
        write_study(out, trial, result, summary, referee)
    manifest = {'schema': SCHEMA, 'run_id': out.name, 'bundle': bundle, 'bundle_sha256': bundle_sha, 'code': code,
                'applied_contact_profile': copy.deepcopy(host.contact_record) if host else None,
                'perception_delay_s': zi.PERCEPTION_DELAY_S,
                'actor': summary['actor'],
                'prereg_sha256': zi.file_sha256(ROOT / prereg['_path']) if prereg.get('_path') else None,
                'env': {'python': platform.python_version(), 'platform': platform.platform(),
                        'threads': {k: os.environ.get(k) for k in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
                                                                   'VECLIB_MAXIMUM_THREADS', 'MKL_NUM_THREADS')}},
                'load_average': {'start': [round(v, 2) for v in load0], 'end': [round(v, 2) for v in os.getloadavg()]},
                'wall_s': round(time.time() - started, 1), 'pose_provider': bundle['pose_provider']['label']}
    (out / 'result.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str) + '\n')
    manifest['files'] = {str(q.relative_to(out)): zi.file_sha256(q) for q in sorted(out.rglob('*'))
                         if q.is_file() and q.name not in ('manifest.json',)}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str) + '\n')
    return summary


def write_study(out, trial, result, summary, referee=None):
    """Study-side logs: requests (text + image bytes), calls, messages, actions, dispatch, checks."""
    study = out / 'study'
    images = study / 'request_images'
    images.mkdir(parents=True, exist_ok=True)
    for sha, jpeg in trial.request_images.items():
        (images / f'{sha}.jpg').write_bytes(jpeg)
    if isinstance(trial.send_ledger, llm.MainStudySendLedger):
        # Raw request/response bytes are already in study/wire/ (written before/after each POST).
        rows = llm.call_rows(trial.send_ledger)
        jsonl(study / 'model_calls.jsonl', rows)
        summary['model_usage'] = llm.usage_summary(rows)
        summary['model_ledger'] = {'run_key': trial.send_ledger.run_key, 'live': trial.send_ledger.live,
                                   'host_errors': list(trial.send_ledger.host_errors),
                                   'proxy_identity': getattr(trial.send_ledger, 'proxy_identity', None)}
    jsonl(study / 'dispatch.jsonl', trial.dispatch_log)
    jsonl(study / 'inputs.jsonl', trial.input_log)
    jsonl(study / 'executor_events.jsonl', trial.executor_events)
    jsonl(study / 'scheduler_events.jsonl', trial.scheduler.events)
    jsonl(study / 'decision_events.jsonl', trial.scheduler.decision_events)
    (study / 'pair_status.json').write_text(json.dumps(trial.pair_status.record(), indent=1) + '\n')
    (study / 'study_config.json').write_text(json.dumps(trial.study_config(), indent=1, ensure_ascii=False) + '\n')
    (study / 'send_ledger.json').write_text(json.dumps(trial.send_ledger.to_dict(), indent=1) + '\n')
    if result is None:
        return
    # Always write the trial record (PR #257 review P1-G b). Without a referee
    # (the run failed before it existed) the block says not_evaluated and the
    # record is never a success.
    record = (zr.apply_to_record(trial.trial_record(result), referee) if referee is not None
              else zr.not_evaluated(trial.trial_record(result)))
    if isinstance(trial.send_ledger, llm.MainStudySendLedger):
        record['failure_class'] = summary.get('failure_class')
        record['model_usage'] = summary['model_usage']
        if record['failure_class'] == llm.API_ERROR:
            record['end_reason'] = 'api_failure'
    record['pose_provider'] = dict(summary['pose_provider'])   # A's provenance keys are closed: top level
    record['plumbing_only'] = trial.actor == zi.FIXTURE_ACTOR
    (study / 'trial_record.json').write_text(json.dumps(record, indent=1, ensure_ascii=False) + '\n')
    evaluation = (zr.evaluation_block(record, referee) if referee is not None
                  else {'schema': 'ugrp.zone_study_referee_evaluation.v2', 'status': 'not_evaluated',
                        'success': False, 'note': 'no referee: the run failed before the referee existed'})
    summary.setdefault('eval_only', {})['evaluation'] = evaluation
    (out / 'eval_only').mkdir(parents=True, exist_ok=True)
    (out / 'eval_only' / 'evaluation.json').write_text(json.dumps(evaluation, indent=1, ensure_ascii=False) + '\n')
    summary['study'] = {'calls': len(result.calls), 'messages': len(result.messages), 'actions': len(result.actions),
                        'end_reason': record['end_reason'], 'end_sim_s': record['end_sim_s'],
                        'end_state': record['end_state'],
                        'channel': zo.channel_checks(trial, result), 'cost': zo.cost_checks(trial, result),
                        'requests': zo.request_checks(result),
                        'reopen': zo.reopen_trial_record(study / 'trial_record.json'),
                        'clock_drift_s': trial.clock_drift_s, 'wakeups': {r: trial.wakeups(r) for r in ROBOTS},
                        'dispatch': collections.Counter(f'{d["api"]}:{(d["ack"] or {}).get("accepted")}'
                                                        for d in trial.dispatch_log),
                        'pair_status_sha256': trial.pair_status.config_sha256(),
                        'study_config_sha256': digest(trial.study_config())}


def llm_driver(prereg, args, *, wire=None):
    """The prereg's registered driver + main-study ledger cohort (never the #222 pilot DB)."""
    path = ROOT / prereg['_path'] if prereg.get('_path') else None
    return llm.LiveDriver.from_prereg(
        prereg, prereg_sha256=zi.file_sha256(path) if path else None,
        source={'code_sha': git('rev-parse', 'HEAD'), 'execution_bundle_id': zi.EXECUTION_BUNDLE_ID},
        proxy_pid=args.proxy_pid, create_budget=args.create_budget, wire=wire)


def run_llm_trial(prereg, episode, condition, out, *, horizon_s, dev, expected_source_sha, driver):
    """All attempts of one (episode, condition); only a pre-request HOST_ERROR is retried, once."""
    run_id = f'{condition}-{episode["episode_id"]}'
    paths = [Path(out) / run_id, Path(out) / f'{run_id}-attempt2', Path(out) / f'{run_id}.attempts.json']
    if any(path.exists() or path.is_symlink() for path in paths):
        raise SystemExit(f'{run_id}: existing result/attempt path; refusing overwrite or rerun')
    driver.budget.check_available(driver.cohort_id)
    bundle_sha = digest(run_bundle(prereg, episode, driver=driver)[0])

    def start(attempt, run_key):
        driver.start_run(run_key, bundle_id=zi.EXECUTION_BUNDLE_ID, bundle_sha256=bundle_sha,
                         record={'run_id': run_id, 'attempt': attempt, 'condition': condition,
                                 'episode': episode['episode_id'], 'dev': dev})

    def attempt_fn(attempt, run_key):
        return run_trial(prereg, episode, condition, out, horizon_s=horizon_s, dev=dev,
                         expected_source_sha=expected_source_sha, driver=driver, run_key=run_key,
                         attempt=attempt, raise_on_failure=False)

    record, exc, attempts = llm.run_attempts(attempt_fn, budget=driver.budget, run_id=run_id, start=start)
    path = Path(out) / f'{run_id}.attempts.json'
    with path.open('x') as handle:
        handle.write(json.dumps({'run_id': run_id, 'bundle_sha256': bundle_sha, 'attempts': attempts,
                                'ledger': driver.ledger_record(),
                                'cohort_usage': driver.budget.usage(driver.cohort_id)},
                               indent=1, ensure_ascii=False) + '\n')
    if exc is not None:
        raise SystemExit(f'{run_id}: {type(exc).__name__}: {exc} (attempts: {path})')
    return record


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--prereg', required=True)
    p.add_argument('--episode', required=True)
    p.add_argument('--condition', choices=MAIN_CONDITIONS)
    p.add_argument('--output')
    p.add_argument('--expected-source-sha', help='expected execution commit; checked alongside prereg.source_sha')
    p.add_argument('--bundle', action='store_true', help='print the run bundle and its sha256, run nothing')
    p.add_argument('--dev-horizon-s', type=float, help='dev plumbing only: shorter horizon, bundle not enforced')
    p.add_argument('--llm', action='store_true', help='real model calls via the prereg llm_driver block (B7)')
    p.add_argument('--proxy-pid', type=int, help='PID of the already running local subscription proxy (read-only check)')
    p.add_argument('--create-budget', action='store_true',
                   help='explicitly create the NEW main-study ledger file named by llm_driver.budget_db')
    args = p.parse_args(argv)
    prereg = load_prereg(args.prereg)
    prereg['_path'] = str(Path(args.prereg).resolve().relative_to(ROOT)) if Path(args.prereg).resolve().is_relative_to(ROOT) else None
    episode = next((e for e in prereg['episodes'] if e['episode_id'] == args.episode), None)
    if episode is None:
        raise SystemExit(f'unknown episode {args.episode!r}')
    driver = llm_driver(prereg, args) if args.llm else None
    if args.bundle:
        bundle = run_bundle(prereg, episode, driver=driver)[0]
        print(json.dumps({'bundle_sha256': digest(bundle), 'bundle': bundle}, indent=1, ensure_ascii=False))
        return 0
    if not args.condition or not args.output:
        raise SystemExit('--condition and --output are required to run')
    dev = args.dev_horizon_s is not None
    horizon = float(args.dev_horizon_s if dev else prereg['horizon_s'])
    if driver is not None:
        rec = run_llm_trial(prereg, episode, args.condition, args.output, horizon_s=horizon, dev=dev,
                            expected_source_sha=args.expected_source_sha, driver=driver)
    else:
        rec = run_trial(prereg, episode, args.condition, args.output, horizon_s=horizon, dev=dev,
                        expected_source_sha=args.expected_source_sha)
    study = rec.get('study', {})
    print(json.dumps({'run_id': rec['run_id'], 'stop': rec['stop'], 'sim_s': rec.get('sim_s'),
                      'end_reason': study.get('end_reason'), 'end_state': study.get('end_state'),
                      'calls': study.get('calls'),
                      'messages': study.get('messages'), 'dispatch': study.get('dispatch'),
                      'deliveries': len((rec.get('eval_only', {}).get('referee') or {}).get('deliveries', [])),
                      'par_makespan_sim_s': rec.get('eval_only', {}).get('evaluation', {}).get('par_makespan_sim_s'),
                      'delivery_rate': rec.get('eval_only', {}).get('evaluation', {}).get('delivery_rate'),
                      'pose_provider': rec['pose_provider']}, ensure_ascii=False, default=str), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
