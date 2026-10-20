"""E2E-min runner session: everything run_e2e_warp needs behind one object.

Default OFF: ``enabled()`` is true only for ``E2E_MIN_HANDOFF=on_v1``; the
session config comes from the JSON file named by ``E2E_MIN_CONFIG``.  The
runner patch (experiments/2026-10-21-e2e-min/patches/run_e2e_warp.patch) only
calls the functions here, so the DeepSeek-owned runner stays thin.

Config (frozen into queue['e2e_config'] at prepare; sha256 bound)::

    {"level": "E2E-1p",
     "cubes": {"r1": {"item_id": "cyan_1", "xy": [x, y]}, "r2": {...}},
     "carry_pose_verdict": {"path": ".../measure.json", "sha256": "..."},
     "act": {"python": ".../ugrp-rl1b-act-env/bin/python",
             "act_source": ".../src/act18-c2c-257dcacc", "expected_act_sha": "257dcacc...",
             "checkpoint": ".../R8/step-100000", "expected_model_sha256": "e1ec6592...",
             "device": "cuda"},
     "release": {"stop_ticks": 3, "backoff_m": 0.15},
     "timeouts": {"release": 45.0},
     "sim_budget_s": 200.0}

``sim_budget_s`` replaces the nav gate's <=120 s budget for the E2E loop
only (grasp 90 + settle 3.1 + carry 60 + release must fit); the nav queue
fields stay untouched.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

from harness import e2e_min_handoff as H
from harness.e2e_min_world import validate_cubes

CONFIG_ENV = 'E2E_MIN_CONFIG'
CONFIG_SCHEMA = 'ugrp.e2e_min.config.v1'
ROOT = Path(__file__).resolve().parents[1]
CONFIG_KEYS = {'level', 'cubes', 'carry_pose_verdict', 'act', 'release', 'timeouts', 'sim_budget_s'}
ACT_KEYS = {'python', 'act_source', 'expected_act_sha', 'checkpoint', 'expected_model_sha256', 'device'}


def enabled(environ=None):
    return H.enabled(environ)


def load_config(environ=None):
    env = os.environ if environ is None else environ
    path = env.get(CONFIG_ENV)
    if not path or not Path(path).is_file():
        raise ValueError('E2E_CONFIG_MISSING:' + str(path))
    raw = Path(path).read_bytes()
    config = json.loads(raw)
    check_config(config)
    return dict(schema=CONFIG_SCHEMA, path=str(path), sha256=hashlib.sha256(raw).hexdigest(),
                value=config)


def check_config(config):
    if not isinstance(config, dict) or set(config) - CONFIG_KEYS or not {'level', 'cubes', 'act'} <= set(config):
        raise ValueError('E2E_CONFIG_FIELDS')
    if config['level'] not in H.LEVELS:
        raise ValueError('E2E_CONFIG_LEVEL')
    validate_cubes(config['cubes'])
    if set(config['act']) != ACT_KEYS:
        raise ValueError('E2E_CONFIG_ACT_FIELDS')
    if H.LEVELS[config['level']]['release'] == 'rule_script':
        from harness.e2e_min_release import DEFAULTS
        if set(config.get('release') or {}) - set(DEFAULTS):
            raise ValueError('E2E_CONFIG_RELEASE_FIELDS')
    budget = config.get('sim_budget_s')
    if budget is not None and not (isinstance(budget, (int, float)) and 0 < float(budget) <= 300):
        raise ValueError('E2E_CONFIG_SIM_BUDGET')
    verdict = config.get('carry_pose_verdict')
    if not isinstance(verdict, dict) or set(verdict) != {'path', 'sha256'}:
        raise ValueError('E2E_CONFIG_CARRY_POSE_VERDICT_REQUIRED')
    return config


def queue_fields(record):
    value = record['value']
    fields = H.queue_fields(value['level'])
    fields['e2e_config'] = dict(path=record['path'], sha256=record['sha256'], value=value)
    return fields


def validate_queue(queue, environ=None):
    H.validate_queue(queue)
    record = load_config(environ)
    bound = queue.get('e2e_config') or {}
    if bound.get('sha256') != record['sha256'] or bound.get('value') != record['value']:
        raise ValueError('E2E_CONFIG_CHANGED_SINCE_PREPARE')
    return record


def sim_budget_s(queue):
    value = queue['e2e_config']['value']
    if value.get('sim_budget_s') is not None:
        return float(value['sim_budget_s'])
    t = {**H.DEFAULT_TIMEOUTS, **(value.get('timeouts') or {})}
    return float(t['grasp'] + t['settle'] + t['carry'] + t['release'] + 1.0)


def nav_cubes(queue):
    return copy.deepcopy(queue['e2e_config']['value']['cubes'])


def load_verdict(spec):
    path = Path(spec['path'])
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != spec['sha256']:
        raise ValueError('E2E_CARRY_POSE_VERDICT_HASH')
    return json.loads(raw)['verdict']


def act_server_argv(act):
    return [act['python'], '-u', str(ROOT / 'scripts/e2e_min_act_server.py'), '--enabled',
            '--act-source', act['act_source'], '--expected-act-sha', act['expected_act_sha'],
            '--checkpoint', act['checkpoint'], '--expected-model-sha256', act['expected_model_sha256'],
            '--device', act['device']]


class E2ESession:
    """Owns the handoff episode, executors and observers for one world (w=0)."""

    def __init__(self, queue, output, tasks, allocation, calibration, *, transport=None,
                 initial_pwm=None):
        from harness.e2e_min_act import ActObservationBuilder, ActServerTransport, ActSkillClient
        from harness.e2e_min_runtime import NavCarryAdapter
        from harness.e2ewarp_selfnav import OwnCommandOdometry
        value = queue['e2e_config']['value']
        self.output, self.value = Path(output), value
        level = value['level']
        self.episode = H.E2EMinEpisode(level, timeouts=value.get('timeouts'),
                                       initial_pwm=initial_pwm)
        verdict = load_verdict(value['carry_pose_verdict'])
        self.transport = transport or ActServerTransport(
            act_server_argv(value['act']), stderr_path=self.output / 'act-server.stderr.log')
        constants = calibration['constants']
        self.builders, self.executors, self.releases = {}, {}, {}
        for robot in H.ROBOTS:
            item = value['cubes'][robot]['item_id']
            kind = item.split('_')[0]
            start = H.hold_command(0.0, (initial_pwm or {}).get(robot) or _search())
            builder = ActObservationBuilder(robot, kind, 'west', start)
            self.builders[robot] = builder
            ex = dict(grasp=ActSkillClient(robot, 'grasp', builder, self.transport),
                      nav=NavCarryAdapter(tasks[robot], carry_pose_verdict=verdict))
            if H.LEVELS[level]['release'] == 'act':
                ex['release'] = ActSkillClient(robot, 'release', builder, self.transport)
            else:
                from harness.e2e_min_release import ReleaseOpenV1
                odo = OwnCommandOdometry(forward_m_per_pct_s=constants['forward_m_per_pct_s'],
                                         yaw_deg_per_pct_s=constants['yaw_deg_per_pct_s'])
                ex['release'] = ReleaseOpenV1(robot, odo, **(value.get('release') or {}))
                self.releases[robot] = ex['release']
            self.executors[robot] = ex
        self.episode.allocate(0.0, allocation)
        self.receipt = getattr(self.transport, 'hello', None)

    def step(self, now, frames):
        from harness.e2e_min_runtime import route_tick
        commands = route_tick(self.episode, now, frames, self.executors,
                              observers={r: [self.builders[r]] for r in H.ROBOTS})
        return {r: (c if c is not None else H.hold_command(now, _search()))
                for r, c in commands.items()}

    @property
    def finished(self):
        return self.episode.finished

    def export(self):
        out = self.episode.export()
        out['act_server'] = self.receipt
        out['release_scripts'] = {r: rel.record() for r, rel in self.releases.items()}
        out['config_sha256'] = None
        return out

    def close(self, queue):
        record = self.export()
        record['config_sha256'] = queue['e2e_config']['sha256']
        (self.output / 'e2e-handoff.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
        close = getattr(self.transport, 'close', None)
        if callable(close):
            close()
        return record


def _search():
    from harness.active_camera import SEARCH
    return {str(k): int(v) for k, v in SEARCH.items()}
