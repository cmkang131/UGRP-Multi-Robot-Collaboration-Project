"""Standalone E2E-min component smoke driver: CPU-only parts (no torch, no simulator)."""
import json
import sys
from pathlib import Path

import pytest

from harness import grasp_act_contract as C
from harness import e2e_min_handoff as H
from harness.e2e_min_act import ActServerTransport
from harness.e2e_min_release import OPEN_PWM

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import e2e_min_standalone_smoke as S  # noqa: E402
from e2e_min_act_server import C2C_EXECUTOR, ActServerCore  # noqa: E402

HOLD = {'1': 1499, '3': 738, '4': 1828, '5': 2216, '6': 1493}
ODO = dict(forward_m_per_pct_s=0.004024203361827748, yaw_deg_per_pct_s=1.7275488814064257)
ACT_ARGS = ['--act-python', '/x/py', '--act-source', '/x/src', '--expected-act-sha', 'a' * 40,
            '--checkpoint', '/x/ck', '--expected-model-sha256', 'b' * 64]


# -- CLI ------------------------------------------------------------------------------
def test_default_off_requires_enabled():
    with pytest.raises(SystemExit, match='DEFAULT_OFF'):
        S.parse_args(['act-server', '--out', '/tmp/x', '--expected-source-sha', 'c' * 40, *ACT_ARGS])


def test_act_server_args_and_defaults():
    a = S.parse_args(['act-server', '--enabled', '--out', '/tmp/x', '--expected-source-sha', 'c' * 40,
                      *ACT_ARGS])
    assert a.func is S.cmd_act_server and a.frames == 'render' and a.ticks == 30
    assert a.robots == ('r1', 'r2') and a.device == 'cuda'
    act = S.act_config(a)
    from harness.e2e_min_runner import ACT_KEYS, act_server_argv
    assert set(act) == ACT_KEYS
    argv = act_server_argv(act)
    assert argv[0] == '/x/py' and '--enabled' in argv and argv[argv.index('--device') + 1] == 'cuda'


def test_robot_parsing():
    assert S.parse_robots('r2') == ('r2',)
    for bad in ('r3', 'r1,r1', ''):
        with pytest.raises(Exception):
            S.parse_robots(bad)


def test_release_and_nav_arg_rules():
    with pytest.raises(SystemExit, match='expected-source-sha'):
        S.parse_args(['release-open', '--enabled', '--out', '/tmp/x', '--calibration', '/c.json'])
    a = S.parse_args(['release-open', '--enabled', '--out', '/tmp/x', '--calibration', '/c.json',
                      '--physics', 'none'])
    assert a.max_ticks == 120 and S.release_params(a) == {}
    a = S.parse_args(['release-open', '--enabled', '--out', '/tmp/x', '--calibration', '/c.json',
                      '--physics', 'none', '--backoff-m', '0.2'])
    assert S.release_params(a) == {'backoff_m': 0.2}
    nav = ['nav-render', '--enabled', '--out', '/tmp/x', '--expected-source-sha', 'c' * 40,
           '--components', '/m.json']
    assert S.parse_args(nav).ticks == 600
    with pytest.raises(SystemExit, match='exclusive'):
        S.parse_args(nav + ['--assume-verdict', 'act_lift_end', '--carry-pose-verdict', '/m.json'])
    with pytest.raises(SystemExit):
        S.parse_args(nav + ['--assume-verdict', 'carry_look_v1'])


# -- label / policy provenance ---------------------------------------------------------
def test_header_label_and_policy_kinds():
    assert S.LABEL == 'STANDALONE_SMOKE — 배관 확인, 판정 아님, 수집 데이터 아님'
    kinds = {sub: S.header(sub)['policy']['kind'] for sub in S.POLICY}
    assert kinds == {'act-server': 'learned', 'release-open': 'scripted', 'nav-render': 'scripted'}
    for sub in S.POLICY:
        h = S.header(sub)
        assert h['label'] == S.LABEL and h['verdict'] is None and h['n_over_N'] is None
        assert h['pooled'] is False and h['relay'] is False and h['llm_calls'] == 0
        assert h['policy']['teacher'] is False and h['policy']['llm'] is False
    assert 'R8' in S.POLICY['act-server']['component']
    assert 'not learned' in S.POLICY['release-open']['config']
    assert 'NOT an LLM decision' in S.POLICY['nav-render']['config']
    with pytest.raises(ValueError):
        S.header('teacher')


def test_header_is_json_serialisable():
    json.dumps(S.header('act-server', source_sha='c' * 40), ensure_ascii=False, allow_nan=False)


# -- ACT request / response schema (real client encoding, real server core) --------------
class FakeExecutor:
    def __init__(self, predict):
        self.predict, self.resets = predict, 0

    def reset(self):
        self.resets += 1

    def step(self, obs, jpegs):
        return self.predict(obs, jpegs)


class LoopbackTransport(ActServerTransport):
    """ActServerTransport.step/reset encoding, served in-process by ActServerCore."""

    def __init__(self, core):
        self.core, self.sent = core, []
        self.hello = dict(ready=True, act_source_sha='a' * 40, model_sha256='b' * 64,
                          executor=dict(C2C_EXECUTOR), done_head=False, loop_overlay=False)

    def request(self, payload):
        line = json.dumps(payload, allow_nan=False)
        self.sent.append(json.loads(line))
        reply, _ = self.core.handle(json.loads(line))
        return json.loads(json.dumps(reply))


def predict(obs, jpegs):
    assert len(jpegs) == C.RGB_HISTORY
    return dict(t=obs['t'], wheels=[0.35] * 4, duration_s=[0.1] * 4, pwm=dict(obs['issued'][-1]['pwm'])), False


def test_act_loop_roundtrip_schema():
    core = ActServerCore(predict, FakeExecutor, C)
    tr = LoopbackTransport(core)
    result = S.act_loop(tr, ('r1', 'r2'), {'r1': 'cyan', 'r2': 'red'}, 4,
                        lambda r, t: f'{r}-{t}'.encode(), initial_pwm=S.search_pwm())
    ops = [m['op'] for m in tr.sent]
    assert ops.count('reset') == 2 and ops.count('step') == 8
    step = next(m for m in tr.sent if m['op'] == 'step')
    assert set(step) == {'op', 'robot', 'observation', 'jpegs'}
    C.validate_observation(step['observation'])
    assert step['observation']['skill'] == 'grasp' and step['observation']['destination_zone'] == 'none'
    assert result['calls'] == {'r1': 4, 'r2': 4} and core.steps == {'r1': 4, 'r2': 4}
    record = dict(rows=result['rows'], receipt_problems=S.check_act_receipt(
        tr.hello, dict(expected_act_sha='a' * 40, expected_model_sha256='b' * 64)))
    assert S.act_plumbing(record, ('r1', 'r2'), 4) == dict(ok=True, problems=[])
    # commands are issued unchanged (t from the policy), as RobotHandoff._grasp does
    assert [r['command']['t'] for r in result['rows'] if r['robot'] == 'r1'] == [0.0, 0.1, 0.2, 0.3]


def test_act_loop_issue_and_step_hooks_called():
    core = ActServerCore(predict, FakeExecutor, C)
    issued, steps = [], []
    S.act_loop(LoopbackTransport(core), ('r1',), {'r1': 'cyan'}, 3, lambda r, t: b'x',
               issue=lambda r, c: issued.append((r, c['t'])), step=steps.append,
               initial_pwm=S.search_pwm())
    assert issued == [('r1', 0.0), ('r1', 0.1), ('r1', 0.2)] and steps == [0, 1, 2]


def test_act_receipt_and_plumbing_failures():
    act = dict(expected_act_sha='a' * 40, expected_model_sha256='b' * 64)
    bad = dict(ready=True, act_source_sha='z', model_sha256='b' * 64, executor=dict(C2C_EXECUTOR),
               done_head=True, loop_overlay=False)
    assert S.check_act_receipt(bad, act) == ['act_source_sha', 'C2c arms (done_head/loop_overlay)']
    rows = [dict(robot='r1', t=0.0, command=dict(t=0.0, wheels=[0.5] * 4, duration_s=[0.1] * 4, pwm=HOLD),
                 done=False)]
    out = S.act_plumbing(dict(rows=rows, receipt_problems=[]), ('r1', 'r2'), 1)
    assert not out['ok'] and any('r2: 0/1' in p for p in out['problems'])
    assert any('wheel range' in p for p in out['problems'])


# -- release_open_v1 (scripted) ----------------------------------------------------------
def odometry(_robot):
    from harness.e2ewarp_selfnav import OwnCommandOdometry
    return OwnCommandOdometry(**ODO)


def test_release_loop_dry_sequence():
    held = S.held_pose('act_lift_end')
    assert held == HOLD
    issued = []
    result = S.release_loop(('r1', 'r2'), odometry, held, {}, 120, issue=lambda r, c: issued.append((r, c)))
    assert all(t is not None for t in result['done_tick'].values())
    log = result['scripts']['r1']['log']
    stages = [row['stage'] for row in log]
    assert stages[:3] == ['stop'] * 3 and stages[-1] == 'done'
    order = [s for i, s in enumerate(stages) if i == 0 or stages[i - 1] != s]
    assert order == ['stop', 'open', 'backoff', 'done']
    assert [row['pwm1'] for row in log if row['stage'] == 'open'][4] == OPEN_PWM
    assert result['scripts']['r1']['backed_m'] >= 0.15
    assert all(row['wheel'] in (0.0, -0.35) for row in log)
    assert S.release_plumbing(result, {}) == dict(ok=True, problems=[])
    for _, c in issued:
        C.command(c)
        assert {k: v for k, v in c['pwm'].items() if k != '1'} == {k: v for k, v in HOLD.items() if k != '1'}


def test_release_plumbing_flags_short_run():
    result = S.release_loop(('r1',), odometry, HOLD, {}, 5)
    out = S.release_plumbing(result, {})
    assert not out['ok'] and 'r1: not done' in out['problems']


def test_release_params_pass_through():
    result = S.release_loop(('r1',), odometry, HOLD, {'stop_ticks': 1, 'backoff_m': 0.05}, 120)
    rec = result['scripts']['r1']
    assert rec['params']['stop_ticks'] == 1 and rec['params']['backoff_m'] == 0.05
    with pytest.raises(ValueError):
        S.release_loop(('r1',), odometry, HOLD, {'open_pwm': 1900}, 10)


# -- nav carry (H3 hold) -----------------------------------------------------------------
def test_carry_command_holds_all_pwm():
    nav = dict(t=9.9, wheels=[0.35, -0.35, 0.35, -0.35], duration_s=[0.075] * 4,
               pwm=S.search_pwm())
    out = S.carry_command(1.2, nav, HOLD)
    assert out == dict(t=1.2, wheels=nav['wheels'], duration_s=nav['duration_s'], pwm=HOLD)
    with pytest.raises(H.E2EMinError):
        S.carry_command(1.2, nav, {'1': 1500})


def test_held_pose_rejects_unknown():
    with pytest.raises(ValueError):
        S.held_pose('nope')


def test_nav_plumbing():
    ok = dict(robots={'r1': dict(proposals=10, pwm_not_held=0)})
    assert S.nav_plumbing(ok, ('r1',))['ok']
    bad = dict(robots={'r1': dict(proposals=0, pwm_not_held=2)})
    assert S.nav_plumbing(bad, ('r1',))['problems'] == ['r1: adapter never queried',
                                                         'r1: issued PWM differs from held PWM']


def test_assumed_verdict_is_recorded_as_unverified():
    a = S.parse_args(['nav-render', '--enabled', '--out', '/tmp/x', '--expected-source-sha', 'c' * 40,
                      '--components', '/m.json', '--assume-verdict', 'act_lift_end'])
    verdict, source = S.load_carry_verdict(a)
    assert verdict == {'adopted': 'act_lift_end'} and 'NOT render-verified' in source['source']
    a = S.parse_args(['nav-render', '--enabled', '--out', '/tmp/x', '--expected-source-sha', 'c' * 40,
                      '--components', '/m.json'])
    with pytest.raises(SystemExit, match='CARRY_POSE_VERDICT_REQUIRED'):
        S.load_carry_verdict(a)


def test_cube_spec_matches_runner_world():
    from harness.e2e_min_world import validate_cubes
    cubes = S.cube_spec(('r1', 'r2'))
    validate_cubes(cubes)
    assert cubes['r1']['item_id'] == 'cyan_1' and cubes['r2']['item_id'] == 'red_1'


# -- end to end on CPU: release-open --physics none ---------------------------------------
def calibration(tmp_path):
    payload = dict(schema='ugrp.e2ewarp.nav_calibration.v1', measured=True, measured_n=4,
                   source_sha='d' * 40, constants=dict(ODO),
                   per_robot={r: dict(ODO) for r in ('r1', 'r2')})
    path = tmp_path / 'nav-calibration.json'
    path.write_text(json.dumps(payload))
    return path


def test_release_open_cpu_main_writes_labelled_json(tmp_path):
    out = tmp_path / 'run'
    rc = S.main(['release-open', '--enabled', '--physics', 'none', '--out', str(out),
                 '--calibration', str(calibration(tmp_path))])
    record = json.loads((out / 'standalone-release-open.json').read_text())
    assert rc == 0 and record['status'] == 'PLUMBING_OK'
    assert record['label'] == S.LABEL and record['policy']['kind'] == 'scripted'
    assert record['held_pwm'] == HOLD and record['actuation'] == 'direct'
    assert record['calibration']['sha256'] and record['cube'].startswith('none')
    with pytest.raises(SystemExit, match='OUTPUT_EXISTS'):
        S.main(['release-open', '--enabled', '--physics', 'none', '--out', str(out),
                '--calibration', str(calibration(tmp_path))])


def test_synthetic_jpeg():
    pytest.importorskip('PIL')
    jpeg = S.synthetic_jpeg()
    assert jpeg[:2] == b'\xff\xd8'


# -- nav-render loop on CPU: real NavRobot/factory/adapter, fake world -------------------
class FakeWorld:
    def __init__(self, out, head, *, nav_cubes=None, nav_arm_pwm=None, nav_keep=('r1', 'r2')):
        self.arm, self.cubes = nav_arm_pwm, nav_cubes
        self.geometry = dict(destination=dict(zone='B'), robot_qpos_adr={'r1': 0, 'r2': 7})
        self.init_s, self.xml_sha256, self.issued, self.steps = 0.0, 'f' * 64, [], 0
        FakeWorld.last = self

    def capture(self, robot):
        return S.synthetic_jpeg(90)

    def issue(self, robot, command):
        self.issued.append((robot, command))

    def step(self, _tick=None):
        self.steps += 1

    def eval_xy(self, robot):
        return [0.0, 0.0]

    def close(self):
        pass


def test_nav_render_loop_with_fake_world(tmp_path, monkeypatch):
    pytest.importorskip('PIL')
    cal = calibration(tmp_path)
    manifest = tmp_path / 'components.json'
    from e2ewarp_nav_manifest import main as manifest_main
    manifest_main(['--out', str(manifest), '--calibration', str(cal), '--source-sha', 'c' * 40])
    for k, v in dict(E2EWARP_NAV_GATE_MODE='v230_r5', E2EWARP_NAV_ARRIVAL='odom_projection',
                     E2EWARP_NAV_CALIBRATION=str(cal), E2EWARP_NAV_L1LITE='on_v1').items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv('E2E_MIN_ACTUATION', raising=False)
    out = tmp_path / 'nav'

    def admit(_sha, o):
        Path(o).mkdir(parents=True)
        return 'c' * 40, Path(o)
    monkeypatch.setattr(S, 'admit_source', admit)
    monkeypatch.setattr(S, 'OneWorld', FakeWorld)
    rc = S.main(['nav-render', '--enabled', '--out', str(out), '--expected-source-sha', 'c' * 40,
                 '--components', str(manifest), '--assume-verdict', 'act_lift_end', '--ticks', '12'])
    record = json.loads((out / 'standalone-nav-render.json').read_text())
    assert record.get('error') is None, record.get('error')
    assert rc == 0 and record['status'] == 'PLUMBING_OK' and record['ticks'] == 12
    assert record['label'] == S.LABEL and record['policy']['kind'] == 'scripted'
    assert record['carry_pose_verdict']['source'].startswith('assumed')
    w = FakeWorld.last
    assert w.arm == {'r1': HOLD, 'r2': HOLD} and w.cubes is None
    assert w.issued and all(c['pwm'] == HOLD for _, c in w.issued)
    assert record['robots']['r1']['proposals'] == 12 and record['robots']['r1']['pwm_not_held'] == 0
    assert len(list((out / 'frames').glob('r1-*.jpg'))) == 3


def test_nav_render_rejects_untransitioned_verdict(tmp_path):
    m = tmp_path / 'measure.json'
    m.write_text(json.dumps(dict(verdict=dict(adopted='carry_look_v1'))))
    import hashlib
    with pytest.raises(SystemExit, match='carry_pose_transition'):
        S.main(['nav-render', '--enabled', '--out', str(tmp_path / 'o'), '--expected-source-sha', 'c' * 40,
                '--components', str(m), '--carry-pose-verdict', str(m),
                '--carry-pose-verdict-sha256', hashlib.sha256(m.read_bytes()).hexdigest()])


def _fake_admit(monkeypatch):
    def admit(_sha, o):
        Path(o).mkdir(parents=True)
        return 'c' * 40, Path(o)
    monkeypatch.setattr(S, 'admit_source', admit)
    monkeypatch.setattr(S, 'OneWorld', FakeWorld)


@pytest.mark.parametrize('frames', ['synthetic', 'render'])
def test_act_server_command_with_loopback(tmp_path, monkeypatch, frames):
    pytest.importorskip('PIL')
    import harness.e2e_min_act as act_mod
    _fake_admit(monkeypatch)
    FakeWorld.eval_cube = lambda self, robot: [0.0, 0.0, 0.02]
    seen = {}

    def factory(argv, *, stderr_path):
        seen['argv'] = argv
        tr = LoopbackTransport(ActServerCore(predict, FakeExecutor, C))
        tr.close = lambda: seen.setdefault('closed', True)
        return tr
    monkeypatch.setattr(act_mod, 'ActServerTransport', factory)
    out = tmp_path / 'act'
    rc = S.main(['act-server', '--enabled', '--out', str(out), '--expected-source-sha', 'c' * 40,
                 *ACT_ARGS, '--frames', frames, '--ticks', '3'])
    record = json.loads((out / 'standalone-act-server.json').read_text())
    assert record.get('error') is None, record.get('error')
    assert rc == 0 and record['status'] == 'PLUMBING_OK' and seen['closed']
    assert record['label'] == S.LABEL and record['policy']['kind'] == 'learned'
    assert record['receipt_problems'] == [] and len(record['rows']) == 6
    if frames == 'render':
        w = FakeWorld.last
        assert w.cubes == S.cube_spec(('r1', 'r2')) and w.arm is None
        assert len(w.issued) == 6 and w.steps == 3
        assert record['eval_only']['cube_end']['r1'] == [0.0, 0.0, 0.02]


def test_release_open_warp_path_with_fake_world(tmp_path, monkeypatch):
    _fake_admit(monkeypatch)
    out = tmp_path / 'rel'
    rc = S.main(['release-open', '--enabled', '--out', str(out), '--expected-source-sha', 'c' * 40,
                 '--calibration', str(calibration(tmp_path)), '--robots', 'r1'])
    record = json.loads((out / 'standalone-release-open.json').read_text())
    assert record.get('error') is None, record.get('error')
    assert rc == 0 and record['status'] == 'PLUMBING_OK' and record['physics'] == 'warp'
    w = FakeWorld.last
    assert w.arm == {'r1': HOLD, 'r2': HOLD} and w.cubes is None
    assert w.steps == record['ticks'] and record['eval_only']['base_displacement_m'] == {'r1': 0.0}
