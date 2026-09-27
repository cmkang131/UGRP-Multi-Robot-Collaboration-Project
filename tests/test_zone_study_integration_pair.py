"""#223 integration: real host/PairTeam/Gemini adapter, fake physics and wire only."""
from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import socket
from pathlib import Path
from types import MethodType, SimpleNamespace

import numpy as np
import pytest

from harness import zone_study_integration as zi
from harness import zone_study_scenarios as scenarios
from harness.owncam_pose_source import PoseReport
from harness.zone_own_executor import ZoneOwnExecutor
from harness.zone_pair_status import FIELDS
from harness.zone_send_ledger import SendLedger, completion_body
from harness.zone_study_llm_transport import gemini_client_factory
from harness.zone_study_pose_delay import DelayedPoseSource
from scripts import run_zone_study_integration as runner
from tests.test_zone_pair_executor import PairFakeHost, FakeM2, pair_obs
from tests.test_zone_own_executor import SEARCH_POSE, ROWS_Y, rgb_of
from tests.test_zone_study_integration import FRAMES

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / 'configs/zone_study_integration/pair_dev_DRAFT.json'


@pytest.fixture(autouse=True)
def no_network_or_physics(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, 'mujoco', None)
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('network forbidden'))
    monkeypatch.setattr(socket.socket, 'connect_ex', lambda *a: pytest.fail('network forbidden'))


def setup():
    pre = runner.load_prereg(PREREG)
    bundle, scenario, map_bundle, provider = runner.run_bundle(pre, pre['episodes'][0])
    spec = bundle['host_spec']
    static = json.loads((ROOT / map_bundle['map_file']).read_text())
    params = json.loads((ROOT / pre['student']['calibration']).read_text())['params']
    executors = {r: ZoneOwnExecutor(r, static, params, spec['order_sheet'],
                                  skill_factory=lambda *a, **k: None, pose_estimate_cls=tuple,
                                  search_rows_y=ROWS_Y, judgments=False) for r in zi.ROBOTS}
    host = PairFakeHost(executors, lambda *a: None)
    host.contact_record = bundle['contact_profile_expected']
    host.enable_pair_carry(spec['pair_order_sheets'], params, controller_factory=FakeM2)
    for index, (rid, slot) in enumerate(host.robots.items()):
        def capture(camera='robot_cam', rid=rid, slot=slot, index=index):
            slot.port.fid += 1
            now = host.world.data.time
            obs = pair_obs(rid, slot.port.fid, now, slot.port.servo)
            jpeg = FRAMES[(index + int(now // 10)) % len(FRAMES)]
            return {**obs, 'image': base64.b64encode(jpeg).decode(),
                    'sha256': hashlib.sha256(jpeg).hexdigest()}
        slot.port.capture = capture
        slot.executor.pose.on_frame = lambda t, rgb, ex=slot.executor: PoseReport(
            t, True, x_m=0., y_m=0., yaw_rad=0., std_xy_m=.01, std_yaw_rad=.01,
            since_tag_s=0., source=ex.pose.source)
    host.links = {r: runner.HostRobotLink(host, r) for r in zi.ROBOTS}

    def capture_raw(host, rid, now):
        slot = host.robots[rid]
        obs = slot.port.capture()  # real HostRobotLink tap, one separate own stream
        slot.executor.on_frame(now, obs, rgb_of(obs))
        slot.frames.append({'robot_id': rid, 'camera': obs['camera'], 'sha256': obs['sha256'], 't': now})
        slot.next_frame = now + host.FRAME_S
    host._capture_raw = MethodType(capture_raw, host)
    for r in zi.ROBOTS:
        host._capture(r, 0.)
    return host, scenario, map_bundle, bundle


@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS)
def test_pair_and_multiple_real_adapter_calls_use_each_own_camera(condition, tmp_path):
    host, scenario, map_bundle, bundle = setup()
    raw_requests, outputs = [], []
    actors = {r: zi.zo.FixtureActor(r, condition, 700) for r in zi.ROBOTS}

    def wire(request, *, timeout=None):
        body = json.loads(request.data)
        parts = body['messages'][-1]['content']
        user = next(p['text'] for p in parts if p['type'] == 'text')
        payload = json.loads(user)
        raw_requests.append((payload, parts))
        reply = actors[payload['robot_id']].respond({'messages': [body['messages'][0],
                                                                 {'role': 'user', 'content': user}]})
        outputs.append(reply)
        return io.BytesIO(completion_body(reply, usage={'prompt_tokens': 500, 'completion_tokens': 100,
                                                       'total_tokens': 600}))
    adapter = zi.ModelAdapter(gemini_client_factory(model='offline-adapter-test', url='http://offline.invalid',
                                                   max_tokens=768, temperature=.2, study_json=True),
                              SendLedger(wire, store_dir=tmp_path / 'wire'))
    trial = zi.IntegratedTrial(scenario, condition=condition, seed=700, links=host.links, horizon_s=85.,
                               map_bundle=map_bundle, actor='gemini_proxy', model_adapter=adapter,
                               pair_records=host.pairs.records)
    trial.begin(0.)
    for i in range(1, 851):
        t = round(i * zi.QUANTUM_S, 6)
        for event in runner.StudyTeamHost.advance_to(host, t):
            trial.on_executor_event(event, at_s=t)
        trial.step_to(t)
    result = trial.finish(85.)
    accepted = [d for d in trial.dispatch_log if d['api'] == 'pair_carry' and d['ack']['accepted']]
    assert {d['actor'] for d in accepted} == {'r1', 'r2'}
    assert not [d for d in trial.dispatch_log if d['api'] == 'deliver']
    records = trial.pair_status.record()
    assert records['messages'] > 0 and records['sessions'] == host.pairs.records()
    assert records['config']['profile'] == 'zone_pair_status_v4'
    assert all(set(m) == set(FIELDS) for s in records['sessions'] for m in s['status_messages'])
    assert any(m['state'] == 'start_ready' for s in records['sessions'] for m in s['status_messages'])
    assert any(m['state'] == 'lift_go_0' for s in records['sessions'] for m in s['status_messages'])
    assert all(any(kind == 'mecanum' for _, kind, _ in host.robots[r].port.log) for r in ('r1', 'r2'))
    assert trial.send_ledger is trial.scheduler.send_ledger is adapter.send_ledger
    assert trial.send_ledger.sends() == len(raw_requests) > 3
    first_hashes = {}
    for payload, parts in raw_requests:
        rid = payload['robot_id']
        data = next(p['image_url']['url'] for p in parts if p['type'] == 'image_url')
        jpeg = base64.b64decode(data.split(',', 1)[1])
        ref = payload['own_rgb_refs'][0]
        sha = hashlib.sha256(jpeg).hexdigest()
        assert sha == ref['sha256']
        first_hashes.setdefault(rid, sha)
        own = [f for f in host.robots[rid].frames if f['t'] <= payload['sim_time_s'] + 1e-9]
        assert sha == own[-1]['sha256']
        assert 'pair_status' not in payload and not zi.zo.contract_condition(condition).input_allowlist - set(payload)
    assert len(set(first_hashes.values())) == 3  # rejects the common fixture photo regression
    for rid in zi.ROBOTS:
        assert sum(p['robot_id'] == rid for p, _ in raw_requests) > 1
    if condition == 'no_comm':
        assert not result.messages and all('inbox' not in p for p, _ in raw_requests)
        assert all(trigger != 'report' for r in zi.ROBOTS for _, trigger in trial.wakeups(r))
    else:
        assert result.messages
        for rid in zi.ROBOTS:
            calls = [p for p, _ in raw_requests if p['robot_id'] == rid]
            assert any(p.get('inbox') for p in calls[1:])
            assert any(trigger == 'report' for _, trigger in trial.wakeups(rid))
    assert trial.sim_output_tokens(outputs[0], 0) == zi.pk.count_tokens(outputs[0])
    runner.write_study(tmp_path, trial, result, {'pose_provider': bundle['pose_provider']['label']})
    for sha, jpeg in trial.request_images.items():
        assert (tmp_path / 'study/request_images' / f'{sha}.jpg').read_bytes() == jpeg


def test_pair_release_cancels_own_job_and_never_auto_submits_a_peer():
    host, scenario, _, _ = setup()
    host._physics_until(.6)
    plan = zi.executor_plan({'kind': 'claim', 'order_id': 'cargoX', 'destination_zone': 'B', 'role': 'end_neg'},
                            None, actor='r1', orders=scenario['orders'])
    assert host.links['r1'].call(plan.api, *plan.args)['accepted']
    assert host.links['r2'].job() is None
    release = zi.executor_plan({'kind': 'release', 'order_id': 'cargoX'}, host.links['r1'].job())
    assert host.links['r1'].call(release.api, *release.args)['accepted']
    assert host.links['r1'].job() is None
    assert host.pairs.records()[0]['status_messages'][-1]['state'] == 'abort'


def test_research_scenarios_and_bundle_use_study_wide_profile():
    for s in scenarios.load_all().values():
        assert s['eval']['setup']['contact_profile'] == 'cargo_noslip_v1'
    pre = runner.load_prereg(PREREG)
    bundle = runner.run_bundle(pre, pre['episodes'][0])[0]
    assert bundle['contact_profile_expected']['noslip_iterations'] == 10
    assert bundle['contact_profile_expected']['timestep_s'] == .00025
    assert bundle['perception_delay_s'] == .16
    assert bundle['pose_provider']['label']['research_result'] is False
    assert bundle['pose_provider']['spec']['calibration'] == pre['student']['calibration']
    from scripts.zone_pair_dev_runtime import make_scene
    scene = make_scene(bundle['host_spec'])
    assert scene.config['setup_only']['objects'] == {} and scene.inventory == []
    assert scene.config['cargo_set']['items'] == bundle['host_spec']['team_cargo']
    bad = copy.deepcopy(pre['episodes'][0]); bad['contact_profile'] = 'local_contact_fine'
    with pytest.raises(zi.ContractViolation, match='cargo_noslip'):
        runner.run_bundle(pre, bad)


def test_pose_is_unavailable_until_point16_in_both_report_and_loc():
    class Provider:
        source = 'owncam_pf_v2:stub'
        def __init__(self):
            self.loc = self
            self.events, self.initialized, self.t, self.closed = [], False, 0., False
        def on_command(self, row): self.events.append(('command', row['t']))
        def set_motion_profile(self, t, name): self.events.append(('profile', t))
        def on_frame(self, t, rgb):
            self.events.append(('frame', t)); self.initialized = True
        def report(self, t):
            self.t = t
            return PoseReport(t, self.initialized, source=self.source)
        def estimate(self): return {'t': self.t, 'initialized': self.initialized}
        def close(self): self.closed = True
    raw = Provider(); provider = DelayedPoseSource(raw)
    provider.on_command({'t': 0., 'kind': 'hold'})
    assert not provider.on_frame(1., np.zeros((1, 1, 3))).initialized
    provider.set_motion_profile(1.05, 'carry')
    provider.loc.predict_to(1.159)
    assert not provider.loc.estimate()['initialized']
    assert not provider.report(1.159).initialized
    assert provider.report(1.16).initialized
    assert provider.loc.estimate()['t'] == pytest.approx(1.)
    assert raw.events == [('command', 0.), ('frame', 1.)]
    provider.report(1.21)
    assert raw.events[-1] == ('profile', 1.05)
    assert provider.timing[0]['available_sim_s'] == 1.16
    assert provider.timing[0]['inference_wall_s'] >= 0
    provider.close(); assert raw.closed


def test_m2_relocalization_cannot_replace_or_bypass_the_delayed_interface():
    from harness.owncam_pose_source import OwnCamPoseSource
    from tests.test_zone_own_executor import MAP, CALIB
    provider = DelayedPoseSource(OwnCamPoseSource(MAP, CALIB['params'], seed=700))
    facade = provider.loc
    provider.on_frame(1., np.zeros((480, 640, 3), np.uint8))
    replacement = OwnCamPoseSource(MAP, CALIB['params'], seed=701).loc
    provider.loc = replacement  # the M2 reset path
    assert provider.loc is facade and provider.provider.loc is replacement and not provider.pending
    with pytest.raises(AttributeError, match='does not expose update'):
        provider.loc.update(1., [], {})
    provider.loc.command({'t': 1., 'kind': 'initial_servo_command', 'pulses': SEARCH_POSE})
    provider.report(1.159)
    assert provider.provider.servo == {}
    provider.report(1.16)
    assert provider.provider.servo == SEARCH_POSE


def test_output_manifest_preserves_actual_profile_separately_from_expected(tmp_path, monkeypatch):
    import time
    host, _, map_bundle, bundle = setup()
    pre = runner.load_prereg(PREREG)
    host.objects = {}
    host.static = host.eval_static = json.loads((ROOT / map_bundle['map_file']).read_text())
    host.provider_sources = {}
    host.world.scene_xml = '<mujoco/>'  # serialization fixture, no model is compiled
    host.eval_only.update(gt=[], contacts=[], max_eq_active=0, top_camera={})
    monkeypatch.setattr(runner, 'robot_eval', lambda *a: {})
    host.contact_record = {**host.contact_record, 'noslip_iterations': 9}
    runner.write_outputs(tmp_path, pre, pre['episodes'][0], 'no_comm', bundle, zi.digest(bundle),
                         host, None, None, 'exception', {'type': 'profile_mismatch'}, {'sha': 'uncommitted'},
                         time.time(), [0, 0, 0], True)
    manifest = json.loads((tmp_path / 'manifest.json').read_text())
    assert manifest['bundle']['contact_profile_expected']['noslip_iterations'] == 10
    assert manifest['applied_contact_profile']['noslip_iterations'] == 9
    assert manifest['perception_delay_s'] == .16


def test_provider_prior_and_close_hooks_use_only_preregistered_own_docks(monkeypatch):
    fake, _, _, _ = setup()
    host = runner.StudyTeamHost.__new__(runner.StudyTeamHost)
    host.robots, host.world = fake.robots, fake.world
    created, closed, priors = [], [], []
    class FutureProvider:
        source = 'owncam_pf_v2:stub'
        def on_command(self, row): pass
        def init_prior(self, **prior): priors.append(prior)
        def close(self): closed.append(self)
    def build(*args):
        provider = FutureProvider(); created.append(provider)
        return provider
    monkeypatch.setattr(zi, 'build_pose_provider', build)
    dock = {'mean': [0., 0., 0.], 'std': [.15, .15, .17], 'source': 'scenario_own_dock'}
    runner.StudyTeamHost._install_providers(host, {'pose_priors': {r: dock for r in zi.ROBOTS}}, {})
    assert priors == [dock] * 3
    runner.StudyTeamHost.close(host)
    assert closed == created
    fake, _, _, _ = setup()
    host = runner.StudyTeamHost.__new__(runner.StudyTeamHost)
    host.robots, host.world = fake.robots, fake.world
    with pytest.raises(zi.ContractViolation, match='preregistered own dock'):
        runner.StudyTeamHost._install_providers(host, {}, {})
    runner.StudyTeamHost.close(host)
    assert created[-1] in closed
