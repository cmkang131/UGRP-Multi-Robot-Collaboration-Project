"""ACT skill client/server core and release_open_v1 (CPU only; no torch, no simulator)."""
import base64
import io
import json
import sys
from pathlib import Path

import pytest

from harness import grasp_act_contract as C
from harness import e2e_min_handoff as H
from harness import e2e_min_runtime as R
from harness.e2e_min_act import ActObservationBuilder, ActSkillClient, DeadbandClock
from harness.e2e_min_release import OPEN_PWM, ReleaseOpenV1
from harness.e2e_warp_runtime import OwnFrame
from harness.e2ewarp_selfnav import OwnCommandOdometry

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from e2e_min_act_server import ActServerCore, serve  # noqa: E402

SEARCH = {'1': 2000, '3': 740, '4': 2320, '5': 1320, '6': 1500}
HOLD = {'1': 1499, '3': 738, '4': 1828, '5': 2216, '6': 1493}
ODO = dict(forward_m_per_pct_s=0.004024203361827748, yaw_deg_per_pct_s=1.7275488814064257)


def cmd(t, pwm=SEARCH, wheel=0.0):
    return dict(t=t, wheels=[wheel] * 4, duration_s=[0.1 if wheel else 0.0] * 4, pwm=dict(pwm))


def frame(robot, t, issued=()):
    return OwnFrame(robot, 0, int(round(t * 10)), t, f'{robot}-{t:.1f}'.encode(), tuple(issued))


# -- clock / observation builder ------------------------------------------------------
def test_deadband_clock_ignores_small_moves():
    clock = DeadbandClock()
    inst = ('grasp', 'cyan', 'west', 'none')
    assert clock.observe(inst, 0.0, SEARCH)['pwm_elapsed_s'] == 0.0
    assert clock.observe(inst, 0.1, dict(SEARCH, **{'3': 742}))['pwm_elapsed_s'] == pytest.approx(0.1)
    assert clock.observe(inst, 0.2, dict(SEARCH, **{'3': 745}))['pwm_elapsed_s'] == 0.0   # |d|=3
    with pytest.raises(ValueError):
        DeadbandClock(deadband=0)


def test_builder_matches_owner_history_semantics():
    b = ActObservationBuilder('r2', 'red', 'west', cmd(0.0))
    obs, jpegs = b.observe(0.0, b'f0', 'grasp')
    assert len(obs['issued']) == C.HISTORY and obs['robot_id'] == 'r2'
    assert obs['destination_zone'] == 'none' and len(jpegs) == C.RGB_HISTORY
    for k in range(1, 61):
        t = k / 10
        b.observe_tick('r2', frame('r2', t), t, cmd(t, dict(SEARCH, **{'3': 740 + (k % 2)})))
    obs, jpegs = b.observe(6.1, b'f61', 'release')
    assert obs['destination_zone'] == 'pickup_site'
    assert obs['issued'][-1]['t'] == pytest.approx(6.0)
    # +-1 PWM jitter does not reset the v7 pwm clock; the skill clock restarts on release
    assert obs['skill_elapsed_s'] == 0.0
    assert obs['pwm_elapsed_s'] == pytest.approx(6.1)
    # image lags 5.2/1.5/0.5/0 s picked by time only; the ring keeps <= MEMORY_S + 0.1 s
    assert [r['t'] for r in obs['rgb']] == pytest.approx([0.9, 4.6, 5.6, 6.1])
    assert jpegs[-1] == b'f61'
    with pytest.raises(ValueError):
        ActObservationBuilder('r1', 'can', 'any', cmd(0.0))


class FakeTransport:
    def __init__(self, done_at):
        self.done_at, self.resets, self.steps = done_at, [], []

    def reset(self, robot):
        self.resets.append(robot)

    def step(self, robot, obs, jpegs):
        self.steps.append((robot, obs['skill'], obs['t']))
        return cmd(obs['t'], HOLD), obs['t'] >= self.done_at - 1e-9


def test_act_client_resets_once_and_validates():
    tr = FakeTransport(done_at=0.3)
    b = ActObservationBuilder('r1', 'cyan', 'west', cmd(0.0))
    client = ActSkillClient('r1', 'grasp', b, tr)
    out = [client.propose(frame('r1', t), t) for t in (0.1, 0.2, 0.3)]
    assert tr.resets == ['r1'] and [o['done'] for o in out] == [False, False, True]
    with pytest.raises(ValueError):
        client.propose(frame('r2', 0.4), 0.4)


# -- server core ----------------------------------------------------------------------
class FakeExecutor:
    def __init__(self, predict):
        self.predict, self.resets = predict, 0

    def reset(self):
        self.resets += 1

    def step(self, obs, jpegs):
        return self.predict(obs, jpegs)


def test_server_core_protocol_and_whitelist():
    core = ActServerCore(lambda obs, jpegs: (cmd(obs['t'], HOLD), True), FakeExecutor, C)
    b = ActObservationBuilder('r1', 'cyan', 'west', cmd(0.0))
    obs, jpegs = b.observe(0.0, b'img', 'grasp')
    req = dict(op='step', robot='r1', observation=obs, jpegs=[base64.b64encode(j).decode() for j in jpegs])
    lines = [json.dumps(dict(op='reset', robot='r1')), json.dumps(req), json.dumps(dict(op='close'))]
    out = io.StringIO()
    serve(core, io.StringIO('\n'.join(lines) + '\n'), out)
    replies = [json.loads(x) for x in out.getvalue().splitlines()]
    assert replies[0] == {'ok': True} and replies[1]['done'] is True and replies[2] == {'ok': True}
    assert core.executors['r1'].resets == 1 and core.steps == {'r1': 1, 'r2': 0}
    with pytest.raises(ValueError):
        core.handle(dict(req, robot='r2'))                  # observation robot mismatch
    with pytest.raises(ValueError):
        core.handle(dict(op='step', robot='r1'))            # whitelist
    with pytest.raises(ValueError):
        core.handle(dict(req, jpegs=req['jpegs'][:2]))      # four lags required


# -- release_open_v1 --------------------------------------------------------------------
def test_release_open_v1_sequence_and_backoff_distance():
    rel = ReleaseOpenV1('r1', OwnCommandOdometry(**ODO), backoff_m=0.05)
    issued = (cmd(9.9, HOLD),)
    out = []
    for k in range(1, 40):
        t = 10.0 + k / 10
        o = rel.propose(frame('r1', t, issued), t)
        C.command(o['command'])
        out.append(o)
        if o['done']:
            break
    stages = [row['stage'] for row in rel.log]
    assert stages[:3] == ['stop'] * 3 and stages[3:11] == ['open'] * 8
    pwm1 = [o['command']['pwm']['1'] for o in out[3:11]]
    assert pwm1[4] == OPEN_PWM and pwm1 == sorted(pwm1)
    assert all(o['command']['wheels'] == [0.0] * 4 for o in out[:11])
    back = [o for o, s in zip(out, stages) if s == 'backoff']
    assert back and all(o['command']['wheels'] == [-0.35] * 4 for o in back)
    assert len(back) == 4                    # 0.0141 m per reverse tick at the gate calibration
    assert out[-1]['done'] is True and rel.backed_m >= 0.05
    assert all(o['command']['pwm']['3'] == HOLD['3'] for o in out)
    with pytest.raises(ValueError):
        ReleaseOpenV1('r1', OwnCommandOdometry(**ODO), surprise=1)


def test_release_needs_issued_history():
    rel = ReleaseOpenV1('r1', OwnCommandOdometry(**ODO))
    with pytest.raises(ValueError):
        rel.propose(frame('r1', 1.0, ()), 1.0)


def test_e2e1p_route_with_act_grasp_and_script_release():
    ep = H.E2EMinEpisode('E2E-1p', timeouts=dict(settle=0.2))
    alloc = dict(decisions={'r1': 'left', 'r2': 'right'}, success_eligible=True, fatal=False)
    ep.allocate(0.0, alloc)
    tr = FakeTransport(done_at=0.5)
    builders = {r: ActObservationBuilder(r, k, 'west', cmd(0.0)) for r, k in (('r1', 'cyan'), ('r2', 'red'))}

    class Nav:
        def __init__(self):
            self.n = 0

        def propose(self, f, now):
            self.n += 1
            return dict(command=cmd(now, SEARCH, 0.35), arrived=self.n >= 3, no_claim=False)
    issued = {r: [cmd(0.0)] for r in H.ROBOTS}
    execs = {r: dict(grasp=ActSkillClient(r, 'grasp', builders[r], tr), nav=Nav(),
                     release=ReleaseOpenV1(r, OwnCommandOdometry(**ODO), backoff_m=0.03))
             for r in H.ROBOTS}
    for k in range(1, 60):
        t = k / 10
        frames = {r: frame(r, t, issued[r][-16:]) for r in H.ROBOTS}
        out = R.route_tick(ep, t, frames, execs, observers={r: [builders[r]] for r in H.ROBOTS})
        for r in H.ROBOTS:
            issued[r].append(out[r])
        if ep.finished:
            break
    assert all(h.phase == H.DONE for h in ep.robots.values())
    exp = ep.export()
    assert exp['e2e_substitutions'] == [{'stage': 'release', 'by': 'rule_script:release_open_v1'}]
    assert exp['display'] == "E2E-1'"
    # the release script started from the held PWM the handoff issued
    assert execs['r1']['release'].held == HOLD
    # ACT builder saw every tick's issued command (history ends at the last tick)
    assert builders['r1'].issued[-1]['t'] == pytest.approx(t)


# -- runner session (patch helper) ----------------------------------------------------
def _config(tmp_path, level='E2E-1p', adopted='act_lift_end'):
    from harness import e2e_min_runner as M
    measure = tmp_path / 'measure.json'
    measure.write_text(json.dumps(dict(verdict=dict(adopted=adopted))))
    import hashlib
    cfg = dict(level=level,
               cubes={'r1': dict(item_id='cyan_1', xy=[-0.05, -2.375]),
                      'r2': dict(item_id='red_1', xy=[-0.05, -2.875])},
               carry_pose_verdict=dict(path=str(measure),
                                       sha256=hashlib.sha256(measure.read_bytes()).hexdigest()),
               act=dict(python='py', act_source='src', expected_act_sha='a' * 40, checkpoint='ck',
                        expected_model_sha256='b' * 64, device='cuda'),
               release=dict(backoff_m=0.03), timeouts=dict(settle=0.2), sim_budget_s=30.0)
    path = tmp_path / 'e2e-config.json'
    path.write_text(json.dumps(cfg))
    return M, {M.CONFIG_ENV: str(path), H.ENV: H.MODE}


def test_runner_config_queue_binding(tmp_path):
    M, env = _config(tmp_path)
    record = M.load_config(env)
    queue = M.queue_fields(record)
    assert M.validate_queue(queue, env)['sha256'] == record['sha256']
    assert M.sim_budget_s(queue) == 30.0 and M.nav_cubes(queue)['r2']['item_id'] == 'red_1'
    Path(env[M.CONFIG_ENV]).write_text(json.dumps(dict(record['value'], level='E2E-2')))
    with pytest.raises(ValueError, match='E2E_CONFIG_CHANGED'):
        M.validate_queue(queue, env)
    bad = dict(record['value']); bad.pop('carry_pose_verdict')
    with pytest.raises(ValueError):
        M.check_config(bad)
    argv = M.act_server_argv(record['value']['act'])
    assert argv[0] == 'py' and '--enabled' in argv and argv[argv.index('--device') + 1] == 'cuda'


class FakeNavRobot:
    def __init__(self):
        class Comp:
            phase = 'NAVIGATE'
        self.component, self.command_history, self.n = Comp(), [], 0

    def observe(self, f):
        self.n += 1
        if self.n >= 3:
            self.component.phase = 'ARRIVED'
        return dict(own_navigation={})

    def command(self, now):
        row = cmd(now, SEARCH, 0.35)
        self.command_history.append(row)
        return row


def test_runner_session_end_to_end_with_fakes(tmp_path):
    M, env = _config(tmp_path)
    queue = M.queue_fields(M.load_config(env))
    alloc = dict(decisions={'r1': 'left', 'r2': 'right'}, success_eligible=True, fatal=False)
    session = M.E2ESession(queue, tmp_path, {r: FakeNavRobot() for r in H.ROBOTS}, alloc,
                           dict(constants=ODO), transport=FakeTransport(done_at=0.5))
    issued = {r: [cmd(0.0)] for r in H.ROBOTS}
    for k in range(0, 80):
        t = k / 10
        out = session.step(t, {r: frame(r, t, issued[r][-16:]) for r in H.ROBOTS})
        for r in H.ROBOTS:
            C.command(out[r])
            issued[r].append(out[r])
        if session.finished:
            break
    assert session.finished
    record = session.close(queue)
    saved = json.loads((tmp_path / 'e2e-handoff.json').read_text())
    assert saved['config_sha256'] == queue['e2e_config']['sha256']
    assert all(row['phase'] == H.DONE for row in saved['robots'].values())
    assert saved['release_scripts']['r1']['name'] == 'release_open_v1'
    assert record['e2e_substitutions'][0]['by'] == 'rule_script:release_open_v1'


def test_runner_session_refuses_unadmitted_carry_pose(tmp_path):
    M, env = _config(tmp_path, adopted='carry_look_v1')
    queue = M.queue_fields(M.load_config(env))
    with pytest.raises(NotImplementedError, match='carry_pose_transition'):
        M.E2ESession(queue, tmp_path, {r: FakeNavRobot() for r in H.ROBOTS}, {}, dict(constants=ODO),
                     transport=FakeTransport(done_at=0.5))
