"""S3 control composition: real providers/planner, fake motion, no physics/model."""
import base64
import copy
import hashlib
import sys
from types import SimpleNamespace

import pytest

from harness import zone_s3_host as host
from harness import zone_s3_contract as c
from harness import zone_final_pair_skill as old_skill
from harness.zone_robot_model_runtime import require_v3_consumers


@pytest.fixture(autouse=True)
def no_physics(monkeypatch):
    monkeypatch.setitem(sys.modules, 'mujoco', None)
    monkeypatch.setitem(sys.modules, 'sim.multi_masterpi_production', None)


def frames(t):
    return {r: ({'robot_id': r, 'camera': 'robot_cam', 'sim_time': t, 'frame_id': 1,
                 'image': base64.b64encode(r.encode()).decode(),
                 'sha256': hashlib.sha256(r.encode()).hexdigest()}, r) for r in host.ROBOTS}


class FakePair:
    def __init__(self, static, cal, sha, *, seed, order):
        self.task = host.pair_task(static, order)
        self.actors = {r: SimpleNamespace(job=None, jobs_done=[], events=[], belief_projection=lambda: {})
                       for r in ('r1', 'r2')}
        self.team = SimpleNamespace(start=self.submit, records=lambda: [], sessions=[])
        self.look_recovery = SimpleNamespace(failures=lambda: {})
        self.commands, self.observations, self.submissions = [], [], []
        self.closed = False

    def submit(self, rid, item, target, partner, *, now):
        self.submissions.append((rid, item, target, partner, now))
        self.actors[rid].job = SimpleNamespace(kind='pair_carry')
        return {'accepted': True, 'local_state': 'command_issued', 'rejected_reason': None}

    def initial_commands(self, now, commands):
        assert set(commands) == {'r1', 'r2'}
        self.initial = copy.deepcopy(commands)

    def on_frames(self, now, own_frames):
        assert set(own_frames) == {'r1', 'r2'}
        self.observations.append(own_frames)

    def step(self, now):
        if not self.submissions:
            for r, p in (('r1', 'r2'), ('r2', 'r1')):
                self.team.start(r, 'cargoX', 'B', p, now=now)
        return [(r, {'kind': 'mecanum', 'forward': .01, 'left': 0., 'turn': 0., 'duration_s': .1})
                for r in ('r1', 'r2')]

    def arm_step(self, now):
        return []

    def on_command(self, rid, now, cmd):
        assert rid in ('r1', 'r2')
        self.commands.append((rid, now, copy.deepcopy(cmd)))

    def record(self):
        return {'commands': self.commands}

    def close(self):
        self.closed = True


class FakeSolo:
    def __init__(self, static, cal, sha, **task):
        assert task['robot_id'] == 'r3' and task['destination'] == 'A'
        self.task, self.terminal, self.failure = task, False, None
        self.commands, self.observations = [], []
        self.last_report, self.closed = None, False

    def initial_commands(self, now, commands):
        assert set(commands) == {'r3'}
        self.initial = copy.deepcopy(commands)

    def on_frames(self, now, own_frames):
        assert set(own_frames) == {'r3'}
        self.observations.append(own_frames)

    def step(self, now):
        return [('r3', {'kind': 'arm', 'servo_id': 1, 'pulse': 1500})]

    def on_command(self, rid, now, cmd):
        assert rid == 'r3'
        self.commands.append((rid, now, copy.deepcopy(cmd)))

    def record(self):
        return {'commands': self.commands}

    def close(self):
        self.closed = True


def runtime():
    scenario, mb, sheet = c.inputs()
    rt = host.Runtime(c.hp.resolve(c.solo.MAP_ID)[0], sheet['orders'], None, None,
                      seed=601, pair_factory=FakePair, solo_factory=FakeSolo)
    rt.trial = host.IntegratedTrial(scenario, seed=601, links=rt.links, map_bundle=mb,
        horizon_s=1800., code_sha='a'*40, pair_records=rt.pair.team.records)
    return rt


def test_real_pair_public_prior_plan_provider_and_original_defaults():
    static = c.hp.resolve(c.solo.MAP_ID)[0]
    orders = c.inputs()[2]['orders']
    original_task = old_skill.task(static)
    original_plan = old_skill.make_plan(static, original_task['sheet'], 'B')
    require_v3_consumers({'skill_module': 'harness.zone_s3_host'}, host.build_pair_provider)
    rt = host.PairRuntime(static, c.ROOT/c.solo.CALIBRATION, c.solo.CALIBRATION_SHA,
                          seed=601, order=host.public_tasks(orders)['long_beam'])
    try:
        assert rt.task['sheet']['beam_xyyaw'] == [1.3, 0., 0.]
        assert 'not measured' in rt.task['sheet']['source']
        assert rt.team.sheets['cargoX'] == rt.task['sheet']
        assert set(rt.actors) == {'r1', 'r2'}
        for r in rt.actors:
            assert rt.providers[r].provider.loc._pf.partial_fix['record']['id'] == host.solo.partial.ID
            assert 'row assignment unknown' in rt.providers[r].provider.prior['source']
        # Same production planner and Execution constructor retained inside the bound team.
        assert old_skill.task(static) == original_task
        assert old_skill.make_plan(static, original_task['sheet'], 'B') == original_plan
    finally:
        rt.close()


def test_private_placement_does_not_change_public_task_or_pair_prior():
    from harness.zone_environment_registry import bundle_for
    from harness.zone_study_inputs import OrderSheetSource
    scenario, _, original = c.inputs()
    moved = copy.deepcopy(scenario)
    moved['eval']['setup']['placements'][1]['pose_m'][1] += .1
    sheet = OrderSheetSource(moved, bundle_for(moved)).sheet()
    static = c.hp.resolve(c.solo.MAP_ID)[0]
    assert sheet == original
    assert host.pair_task(static, host.public_tasks(sheet['orders'])['long_beam']) == host.pair_task(
        static, host.public_tasks(original['orders'])['long_beam'])


def test_scripted_claims_real_integrated_trial_no_wire_and_own_inputs_only():
    rt = runtime()
    from harness.zone_study_integration import IntegratedTrial
    assert isinstance(rt.trial, IntegratedTrial)
    try:
        rt.initial_commands(0., {r: {'owner': r} for r in host.ROBOTS})
        rt.trial.begin(0.)
        rt.on_frames(0., frames(0.))
        commands = rt.step(0.)
        assert {r for r, _ in commands} == set(host.ROBOTS)
        for r, cmd in commands:
            rt.on_command(r, 0., cmd)
        assert [(d['actor'], d['api'], d['action']['order_id']) for d in rt.trial.dispatch_log] == [
            ('r3', 'deliver', 'order-1'), ('r1', 'pair_carry', 'order-5'), ('r2', 'pair_carry', 'order-5')]
        assert rt.pair.submissions == [('r1', 'cargoX', 'B', 'r2', 0.), ('r2', 'cargoX', 'B', 'r1', 0.)]
        assert rt.solo.task['seed'] == 603
        assert rt.links['r1'].frame_at(0).jpeg == b'r1'
        report = rt.trial.finish(1.)
        assert report['model_calls'] == report['http_attempts'] == report['tokens'] == 0
        assert not rt.trial.calls and not rt.trial.scheduler.calls and not rt.trial.requests
        with pytest.raises(RuntimeError, match='forbids'):
            rt.trial.transport.submit(None)
    finally:
        rt.close()


@pytest.mark.parametrize('change', ['robot', 'camera', 'hash', 'clock'])
def test_foreign_corrupt_frame_rejected_before_any_provider(change):
    rt = runtime()
    rows = frames(0.)
    obs = rows['r3'][0]
    key, val = {'robot': ('robot_id', 'r1'), 'camera': ('camera', 'top'),
                'hash': ('sha256', 'bad'), 'clock': ('sim_time', 5.)}[change]
    obs[key] = val
    try:
        with pytest.raises(ValueError, match='own frame'):
            rt.on_frames(0., rows)
        assert not rt.pair.observations and not rt.solo.observations
    finally:
        rt.close()


def test_fixed_roles_wrong_destination_and_r3_pair_refused():
    rt = runtime()
    try:
        for rid, api, args in [('r3', 'pair_carry', ('order-5', 'B', 'r1', 'end_pos')),
                               ('r1', 'pair_carry', ('order-5', 'A', 'r2', 'end_neg')),
                               ('r2', 'pair_carry', ('order-5', 'B', 'r3', 'end_pos'))]:
            with pytest.raises(ValueError, match='fixed'):
                rt.links[rid].call(api, *args)
    finally:
        rt.close()


def test_same_tick_later_failure_vetoes_all_robot_motion():
    rt = runtime()
    try:
        rt.trial.begin(0.)
        def fail(now):
            rt.solo.failure = 'LOADED_COMMAND_STATE_LOST'
            return [('r3', {'kind': 'arm', 'servo_id': 1, 'pulse': 1500})]
        rt.solo.step = fail
        assert rt.step(0.) == [(r, {'kind': 'hold'}) for r in host.ROBOTS]
    finally:
        rt.close()


def test_pair_finishes_solo_keeps_own_job_and_no_peer_wake():
    rt = runtime()
    try:
        rt.trial.begin(0.)
        for own in rt.pair.actors.values():
            own.jobs_done.append({'kind': 'pair_carry', 'confirmation': 'unconfirmed'})
        rt.on_frames(0., frames(0.))
        assert not rt.terminal
        assert not rt.pair.observations and len(rt.solo.observations) == 1
        assert rt.step(0.)[:2] == [('r1', {'kind': 'hold'}), ('r2', {'kind': 'hold'})]
        assert not rt.trial.scheduler.calls
    finally:
        rt.close()


def test_constructor_failure_closes_existing_provider_owner():
    made = []
    def pair_factory(*args, **kw):
        obj = FakePair(*args, **kw)
        made.append(obj)
        return obj
    def broken(*args, **kw):
        raise RuntimeError('solo construction failed')
    with pytest.raises(RuntimeError, match='solo construction failed'):
        host.Runtime(c.hp.resolve(c.solo.MAP_ID)[0], c.inputs()[2]['orders'], None, None,
                     seed=601, pair_factory=pair_factory, solo_factory=broken)
    assert made[0].closed
