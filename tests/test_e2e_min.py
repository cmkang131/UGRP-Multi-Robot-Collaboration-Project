"""Minimal E2E handoff state machine, substitutions and evaluator (CPU only)."""
import json

import numpy as np
import pytest

from harness import e2e_min_eval as E
from harness import e2e_min_handoff as H

HOLD = {'1': 1500, '3': 800, '4': 2100, '5': 1400, '6': 1500}
OPEN = {'1': 2000, '3': 740, '4': 2320, '5': 1320, '6': 1500}
ALLOC = dict(decisions={'r1': 'left', 'r2': 'right'}, success_eligible=True, fatal=False,
             errors=[], constraint_ok={'r1': True, 'r2': True})


def cmd(t, pwm=OPEN, wheel=0.0):
    w = [wheel] * 4
    return dict(t=t, wheels=w, duration_s=[0.1 if wheel else 0.0] * 4, pwm=dict(pwm))


def drive(h, t0, t1, make):
    """Tick a RobotHandoff from t0 to t1 (inclusive, 10 Hz) using make(t, source)."""
    out = []
    for k in range(int(round(t0 * 10)), int(round(t1 * 10)) + 1):
        t = k / 10
        src = h.source(t)
        out.append((t, src, h.tick(t, make(t, src) if src else None)))
    return out


# -- flags / queue ---------------------------------------------------------
def test_default_off_and_exact_opt_in():
    assert H.enabled({}) is False
    assert H.enabled({H.ENV: H.MODE}) is True
    with pytest.raises(ValueError):
        H.enabled({H.ENV: 'on'})


@pytest.mark.parametrize('level,subs', [('E2E-1p', [{'stage': 'release', 'by': 'rule_script:release_open_v1'}]), ('E2E-2', [])])
def test_substitutions_and_queue(level, subs):
    assert H.substitutions(level) == subs
    q = H.queue_fields(level)
    assert q['e2e_substitutions'] == subs and q['e2e_overlay_text'] is False
    assert H.validate_queue(dict(q, other=1)) == q
    with pytest.raises(ValueError):
        H.validate_queue(dict(q, e2e_substitutions=[]) if subs else dict(q, e2e_substitutions=['x']))
    with pytest.raises(ValueError):
        H.validate_queue(dict(q, e2e_overlay_text=True))


def test_unknown_level_and_hold_rule_rejected():
    with pytest.raises(ValueError):
        H.queue_fields('E2E-3')
    with pytest.raises(ValueError):
        H.RobotHandoff('r1', 'E2E-1p', hold_rule='free')


# -- happy path ------------------------------------------------------------
def test_full_transition_sequence_and_hold_rules():
    h = H.RobotHandoff('r1', 'E2E-1p', initial_pwm=OPEN)
    assert h.tick(0.0) == H.hold_command(0.0, OPEN)          # ALLOCATE holds
    h.allocated(0.0, 'left')
    assert h.phase == H.ACT_GRASP
    # grasp: executor command passes through; done at 2.0 with the hold PWM
    rows = drive(h, 0.1, 2.0, lambda t, s: dict(command=cmd(t, HOLD if t >= 1.0 else OPEN,
                                                             0.35 if t < 1.0 else 0.0),
                                                done=t >= 2.0))
    assert rows[0][2]['wheels'] == [0.35] * 4
    assert h.phase == H.NAV_CARRY and h.hold_pwm == HOLD
    assert rows[-1][2] == H.hold_command(2.0, HOLD)           # H1 on the transition tick
    # settle 3.1 s: nav is not queried, wheels 0, PWM held (H2)
    settle = drive(h, 2.1, 5.0, lambda t, s: pytest.fail('nav queried during settle'))
    assert all(src is None and c['wheels'] == [0.0] * 4 and c['pwm'] == HOLD for _, src, c in settle)
    # carry: nav wheels pass, PWM forced to hold (H3) even though nav sends SEARCH
    carry = drive(h, 5.1, 7.0, lambda t, s: dict(command=cmd(t, OPEN, 0.35), arrived=t >= 7.0))
    assert carry[0][1] == 'nav' and carry[0][2]['wheels'] == [0.35] * 4
    assert all(c['pwm'] == HOLD for _, _, c in carry)
    assert h.phase == H.SCRIPT_RELEASE
    assert carry[-1][2] == H.hold_command(7.0, HOLD)
    # release: executor drives from next tick; done -> DONE and hold last PWM (H5)
    rel = drive(h, 7.1, 8.0, lambda t, s: dict(command=cmd(t, OPEN), done=t >= 8.0))
    assert rel[0][1] == 'release' and h.phase == H.DONE
    assert h.tick(8.1) == H.hold_command(8.1, OPEN)
    phases = [r['to'] for r in h.transitions]
    assert phases == [H.ACT_GRASP, H.NAV_CARRY, H.SCRIPT_RELEASE, H.DONE]
    assert set(h.reach) == {H.ALLOCATE, H.ACT_GRASP, H.NAV_CARRY, H.SCRIPT_RELEASE, H.DONE}


def test_level_selects_executors():
    for level, grasp, release in (('E2E-1p', H.ACT_GRASP, H.SCRIPT_RELEASE),
                                  ('E2E-2', H.ACT_GRASP, H.ACT_RELEASE)):
        h = H.RobotHandoff('r2', level, timeouts=dict(settle=0.0))
        h.allocated(0.0, 'right')
        assert h.phase == grasp
        h.tick(0.1, dict(command=cmd(0.1, HOLD), done=True))
        h.tick(0.2, dict(command=cmd(0.2, OPEN, 0.35), arrived=True))
        assert h.phase == release


# -- fail-closed -------------------------------------------------------------
def test_grasp_timeout_and_invalid_proposal():
    h = H.RobotHandoff('r1', 'E2E-1p', timeouts=dict(grasp=1.0), initial_pwm=OPEN)
    h.allocated(0.0, 'left')
    drive(h, 0.1, 1.1, lambda t, s: dict(command=cmd(t), done=False))
    assert h.phase == H.FAIL and h.fail_code == 'E2E_GRASP_TIMEOUT'
    h2 = H.RobotHandoff('r1', 'E2E-1p', initial_pwm=OPEN)
    h2.allocated(0.0, 'left')
    out = h2.tick(0.1, dict(command=dict(cmd(0.1), wheels=[0.9] * 4)))
    assert h2.fail_code == 'E2E_GRASP_EXECUTOR_ERROR'
    assert out == H.hold_command(0.1, OPEN)      # gripper not opened by failure
    h3 = H.RobotHandoff('r1', 'E2E-1p')
    h3.allocated(0.0, 'left')
    h3.tick(0.1, None)
    assert h3.fail_code == 'E2E_GRASP_EXECUTOR_ERROR'


def test_hold_missing_and_hold_rule_alternative_not_implemented():
    with pytest.raises(H.E2EMinError) as exc:
        H.held_pwm({'1': 1500})
    assert exc.value.code == 'E2E_HOLD_MISSING'
    with pytest.raises(NotImplementedError, match='E2E_MIN_TODO'):
        H.held_pwm(HOLD, 'gripper_hold_arm_search_v1')


def test_nav_no_claim_timeout_and_release_timeout():
    def to_carry(**timeouts):
        h = H.RobotHandoff('r1', 'E2E-2', timeouts=dict(settle=0.0, **timeouts))
        h.allocated(0.0, 'left')
        h.tick(0.1, dict(command=cmd(0.1, HOLD), done=True))
        return h
    h = to_carry()
    h.tick(0.2, dict(command=cmd(0.2, OPEN, 0.35), no_claim=True))
    assert h.fail_code == 'E2E_NAV_NO_CLAIM'
    h = to_carry(carry=0.5)
    drive(h, 0.2, 0.8, lambda t, s: dict(command=cmd(t, OPEN, 0.35)))
    assert h.fail_code == 'E2E_NAV_TIMEOUT'
    h = to_carry(release=0.3)
    h.tick(0.2, dict(command=cmd(0.2, OPEN, 0.35), arrived=True))
    drive(h, 0.3, 0.6, lambda t, s: dict(command=cmd(t, HOLD), done=False))
    assert h.fail_code == 'E2E_RELEASE_TIMEOUT'


def test_time_going_backwards_fails():
    h = H.RobotHandoff('r1', 'E2E-1p', initial_pwm=OPEN)
    h.allocated(0.0, 'left')
    h.tick(0.5, dict(command=cmd(0.5)))
    h.tick(0.4, dict(command=cmd(0.4)))
    assert h.fail_code == 'E2E_EVENT_OUT_OF_ORDER'
    with pytest.raises(H.E2EMinError):
        h.allocated(0.6, 'left')


def test_episode_allocation_fail_closed():
    ep = H.E2EMinEpisode('E2E-1p')
    assert ep.allocate(0.0, dict(ALLOC, success_eligible=False, errors=['L1LITE_X'])) is False
    assert {h.fail_code for h in ep.robots.values()} == {'E2E_ALLOC_FAILED'}
    ep = H.E2EMinEpisode('E2E-1p')
    assert ep.allocate(0.0, dict(ALLOC, decisions={'r1': 'left', 'r2': 'left'})) is False
    assert {h.fail_code for h in ep.robots.values()} == {'E2E_ALLOC_SLOTS_INVALID'}
    ep = H.E2EMinEpisode('E2E-1p')
    assert ep.allocate(0.0, None) is False and ep.finished
    ep = H.E2EMinEpisode('E2E-1p')
    assert ep.allocate(0.0, ALLOC) is True
    assert ep.sources(0.1) == {'r1': 'grasp', 'r2': 'grasp'}
    exp = ep.export()
    assert exp['e2e_substitutions'] == [{'stage': 'release', 'by': 'rule_script:release_open_v1'}] and exp['overlay_text'] is False
    assert exp['slots'] == {'r1': 'left', 'r2': 'right'}
    assert 'teacher_skill' in exp['integration_points_open']
    assert 'world_builder' not in exp['integration_points_open']


def test_integration_points_raise_not_implemented():
    for name in ('teacher_skill', 'runner_wiring'):
        with pytest.raises(NotImplementedError, match='E2E_MIN_TODO'):
            getattr(H, name)()


# -- evaluator ---------------------------------------------------------------
def good_inputs(**over):
    base = dict(level='E2E-1p', allocation=ALLOC, slots={'r1': 'left', 'r2': 'right'},
                cube_final_xy={'r1': [4.6, -1.8], 'r2': [4.6, -2.4]},
                drops={'r1': False, 'r2': False}, claims={'r1': True, 'r2': True},
                contacts_available=True, robot_robot_contacts=0)
    base.update(over)
    return base


def test_evaluate_success_and_each_component():
    rep = E.evaluate(**good_inputs())
    assert rep['success'] is True and rep['e2e_substitutions'] == [{'stage': 'release', 'by': 'rule_script:release_open_v1'}]
    assert rep['research_result'] is False
    bad = [dict(cube_final_xy={'r1': [4.6, -2.4], 'r2': [4.6, -1.8]}),   # swapped slots
           dict(cube_final_xy={'r1': [4.6, -1.8]}),                     # GT missing
           dict(drops={'r1': True, 'r2': False}),
           dict(drops={'r1': False}),                                   # drop unmeasured
           dict(contacts_available=False),
           dict(robot_robot_contacts=1),
           dict(claims={'r1': True, 'r2': False}),
           dict(allocation=dict(ALLOC, success_eligible=False)),
           dict(slots={'r1': 'right', 'r2': 'left'})]                   # != allocation
    for over in bad:
        assert E.evaluate(**good_inputs(**over))['success'] is False, over


def test_evaluate_flags_substitution_mismatch():
    rep = E.evaluate(**good_inputs(substitutions=[]))
    assert rep['substitutions_match_level'] is False


def test_carry_drop_rules():
    n = 20
    xy = [[1.0 + 0.01 * i, -2.0] for i in range(n)]
    base = [[0.8 + 0.01 * i, -2.0] for i in range(n)]
    held = E.carry_drop([0.05] * n, xy, base, cube_half_m=0.02)
    assert held['dropped'] is False
    z = [0.05] * 10 + [0.021] * 10
    floor = E.carry_drop(z, xy, base, cube_half_m=0.02)
    assert floor['dropped'] is True and floor['reason'] == 'floor' and floor['first_index'] == 10
    blip = E.carry_drop([0.05] * 10 + [0.021] * 3 + [0.05] * 7, xy, base, cube_half_m=0.02)
    assert blip['dropped'] is False                       # < min_ticks
    far = [[0.0, -2.0]] * n
    assert E.carry_drop([0.05] * n, xy, far, cube_half_m=0.02)['reason'] == 'detach'
    grip = E.carry_drop([0.05] * n, xy, base, cube_half_m=0.02, finger_max_n=[0.0] * n)
    assert grip['reason'] == 'no_grip'
    assert E.carry_drop([], [], [], cube_half_m=0.02)['dropped'] is None


def _episode_export():
    ep = H.E2EMinEpisode('E2E-1p', timeouts=dict(settle=0.0))
    ep.allocate(0.0, ALLOC)
    ep.tick(1.0, {r: dict(command=cmd(1.0, HOLD), done=True) for r in H.ROBOTS})
    ep.tick(3.0, {r: dict(command=cmd(3.0, OPEN, 0.35), arrived=True) for r in H.ROBOTS})
    ep.tick(4.0, {r: dict(command=cmd(4.0, OPEN), done=True) for r in H.ROBOTS})
    return ep.export()


def test_stage_reach_from_export():
    reach = E.stage_reach(_episode_export())
    for r in H.ROBOTS:
        assert all(reach[r]['reached'].values())
        assert reach[r]['sim_s']['carry'] == 1.0 and reach[r]['final_phase'] == H.DONE


def _write_run(tmp_path, *, drop_r2=False):
    ticks = 51
    nq = 30
    qpos = np.zeros((ticks, 1, nq))
    robot_adr, cube_adr = {'r1': 0, 'r2': 7}, {'r1': 14, 'r2': 21}
    for k in range(ticks):
        for r, y in (('r1', -1.8), ('r2', -2.4)):
            x = 4.0 + 0.004 * k
            qpos[k, 0, robot_adr[r]:robot_adr[r] + 2] = [x, y]
            qpos[k, 0, cube_adr[r]:cube_adr[r] + 3] = [x + 0.2, y, 0.05]
        if drop_r2 and 15 <= k <= 30:
            qpos[k, 0, cube_adr['r2'] + 2] = 0.02
    qpos[-1, 0, cube_adr['r1']:cube_adr['r1'] + 3] = [4.6, -1.8, 0.02]   # released in slot
    qpos[-1, 0, cube_adr['r2']:cube_adr['r2'] + 3] = [4.6, -2.4, 0.02]
    np.savez(tmp_path / 'evaluation-state.npz', qpos=qpos)
    (tmp_path / 'world-00').mkdir()
    (tmp_path / 'world-00' / 'eval-geometry.json').write_text(json.dumps(dict(
        robot_qpos_adr=robot_adr, cube_qpos_adr=cube_adr, cube_half_m=0.02,
        destination=dict(center_m=[4.6, -2.1], half_extents_m=[0.3, 0.7]))))
    (tmp_path / 'queue.json').write_text(json.dumps(H.queue_fields('E2E-1p')))
    (tmp_path / 'slot-decisions.json').write_text(json.dumps(ALLOC))
    (tmp_path / 'e2e-handoff.json').write_text(json.dumps(_episode_export()))
    (tmp_path / 'nav-events.json').write_text(json.dumps(
        {f'0:{r}': [dict(sim_s=3.0, after='ARRIVED')] for r in H.ROBOTS}))
    (tmp_path / 'contact-ledger.json').write_text(json.dumps(
        dict(contacts_available=True, contact_pairs_total=0)))
    (tmp_path / 'llm_ledger.json').write_text(json.dumps(
        [dict(usage=dict(prompt_tokens=1000, completion_tokens=20))] * 2))
    return tmp_path


def test_recount_run_success(tmp_path):
    rep = E.recount_run(_write_run(tmp_path))
    assert rep['success'] is True, rep['success_components']
    assert rep['drop_detail']['r1']['dropped'] is False
    assert rep['aux']['llm']['calls'] == 2 and rep['aux']['llm']['cost_usd'] > 0


def test_recount_run_detects_carry_drop(tmp_path):
    rep = E.recount_run(_write_run(tmp_path, drop_r2=True))
    assert rep['success'] is False
    assert rep['drop_detail']['r2']['dropped'] is True and rep['drop_detail']['r2']['reason'] == 'floor'


def test_recount_without_cube_geometry_is_not_success(tmp_path):
    run = _write_run(tmp_path)
    (run / 'world-00' / 'eval-geometry.json').write_text(json.dumps(dict(robot_qpos_adr={'r1': 0, 'r2': 7})))
    rep = E.recount_run(run)
    assert rep['success'] is False and rep['success_components']['gt_measured'] is False


def test_aggregate_never_pools_levels():
    ok = E.evaluate(**good_inputs())
    bad = E.evaluate(**good_inputs(level='E2E-2', drops={'r1': True, 'r2': False}))
    agg = E.aggregate([ok, ok, bad])
    assert agg['E2E-1p'] == dict(n=2, N=2, fail_codes={})
    assert agg['E2E-2']['n'] == 0 and agg['E2E-2']['N'] == 1


# -- runtime glue ----------------------------------------------------------------
from harness import e2e_min_runtime as R  # noqa: E402


class FakeComponent:
    def __init__(self):
        self.phase = 'NAVIGATE'


class FakeNavTask:
    """NavRobot stand-in: arrives after `arrive_after` observed frames."""

    def __init__(self, arrive_after=3, no_claim=False):
        self.component = FakeComponent()
        self.command_history, self.observed = [], []
        self.arrive_after, self.no_claim = arrive_after, no_claim

    def observe(self, frame):
        self.observed.append(frame)
        if len(self.observed) >= self.arrive_after:
            self.component.phase = 'ARRIVED'
        return dict(own_navigation=dict(arrival_no_claim=self.no_claim))

    def command(self, now):
        row = cmd(now, OPEN, 0.35)
        self.command_history.append(row)
        return row


class Script:
    def __init__(self, done_at, pwm=HOLD, fail=False):
        self.done_at, self.pwm, self.fail, self.calls = done_at, pwm, fail, 0

    def propose(self, frame, now):
        self.calls += 1
        if self.fail:
            raise RuntimeError('boom')
        return dict(command=cmd(now, self.pwm), done=now >= self.done_at - 1e-9)


VERDICT = dict(adopted='act_lift_end')


def test_nav_carry_adapter_requires_admitted_verdict():
    with pytest.raises(NotImplementedError, match='carry_pose_transition'):
        R.NavCarryAdapter(FakeNavTask(), carry_pose_verdict=dict(adopted='carry_look_v1'))
    with pytest.raises(NotImplementedError):
        R.NavCarryAdapter(FakeNavTask(), carry_pose_verdict=None)
    task = FakeNavTask()
    task.component.phase = 'TASK'
    adapter = R.NavCarryAdapter(task, carry_pose_verdict=VERDICT)
    with pytest.raises(ValueError):
        adapter.propose('f', 1.0)


def test_route_tick_full_episode_with_fakes():
    ep = H.E2EMinEpisode('E2E-1p', timeouts=dict(settle=0.3))
    ep.allocate(0.0, ALLOC)
    navs = {r: FakeNavTask(arrive_after=3) for r in H.ROBOTS}
    grasp = {r: Script(done_at=0.5) for r in H.ROBOTS}
    release = {r: Script(done_at=2.0, pwm=OPEN) for r in H.ROBOTS}
    execs = {r: dict(grasp=grasp[r], nav=R.NavCarryAdapter(navs[r], carry_pose_verdict=VERDICT),
                     release=release[r]) for r in H.ROBOTS}
    issued = []
    for k in range(1, 31):
        t = k / 10
        issued.append((t, R.route_tick(ep, t, {r: f'{r}@{t}' for r in H.ROBOTS}, execs)))
        if ep.finished:
            break
    assert ep.finished and all(h.phase == H.DONE for h in ep.robots.values())
    nav = navs['r1']
    # nav saw frames only after settle (0.5 + 0.3) and never during grasp
    assert nav.observed[0] == 'r1@0.8'
    # every nav command the runner keeps has the held PWM, not SEARCH/open
    assert all(c['pwm'] == HOLD for c in nav.command_history)
    assert ep.export()['e2e_substitutions'] == [{'stage': 'release', 'by': 'rule_script:release_open_v1'}]


def test_route_tick_executor_exception_fails_closed():
    ep = H.E2EMinEpisode('E2E-1p', initial_pwm={r: OPEN for r in H.ROBOTS})
    ep.allocate(0.0, ALLOC)
    execs = {'r1': dict(grasp=Script(1.0, fail=True)), 'r2': {}}
    out = R.route_tick(ep, 0.1, {'r1': 'f', 'r2': 'f'}, execs)
    assert ep.robots['r1'].fail_code == 'E2E_GRASP_EXECUTOR_ERROR'
    assert 'boom' in ep.robots['r1'].fail_detail
    assert ep.robots['r2'].fail_code == 'E2E_GRASP_EXECUTOR_ERROR'   # missing executor
    assert out['r1'] == H.hold_command(0.1, OPEN)


def test_route_tick_nav_no_claim_fails():
    ep = H.E2EMinEpisode('E2E-2', timeouts=dict(settle=0.0))
    ep.allocate(0.0, ALLOC)
    execs = {r: dict(grasp=Script(0.1),
                     nav=R.NavCarryAdapter(FakeNavTask(arrive_after=99, no_claim=True),
                                           carry_pose_verdict=VERDICT)) for r in H.ROBOTS}
    for t in (0.1, 0.2):
        R.route_tick(ep, t, {r: 'f' for r in H.ROBOTS}, execs)
    assert {h.fail_code for h in ep.robots.values()} == {'E2E_NAV_NO_CLAIM'}
