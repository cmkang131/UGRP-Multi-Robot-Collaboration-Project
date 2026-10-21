"""pairact hybrid carry (I1-I11): pure tests, kinematic fake world, no simulator."""
import ast
import copy
import json
import math
from pathlib import Path

import pytest

from harness import hybrid_carry as h
from harness.grasp_act_contract import wheel_mix
from harness.pair_carry_teacher_warp import compose, relative

ROOT = Path(__file__).resolve().parents[1]
ROLES = {'r1': 'teal', 'r2': 'blue'}
PWM = {str(k): 1500 for k in (1, 3, 4, 5, 6)}
CAL = {'forward_m_per_pct_s': .004, 'lateral_m_per_pct_s': .004, 'yaw_deg_per_pct_s': .6}


def cfg(**over):
    c = {'mode': h.MODE, 'carry_mode': 'nav', 'navigator': 'teal', 'shadow_predict': False,
         'calibration': dict(CAL), 'formation': {'beam_half_m': .30, 'station_m': .203},
         'limits': {'carry_budget_s': 120., 'v_max': .08, 'w_max': .25, 'hold_settle_s': 1., 'settle_s': .5,
                    'message_ttl_s': .3, 'stretch_pause_m': .03, 'stretch_fail_m': .08, 'stretch_fail_s': 1.,
                    'sigma_xy_max_m': 5., 'sigma_yaw_max_deg': 90., 'sigma_xy_per_m': .02,
                    'sigma_yaw_per_rad': .02, 'acquire_budget_s': 40., 'reobserve_wait_s': 2.,
                    'heading_tol_deg': 8.},
         'nav': {'source': '/abs/nav', 'sha': h.NAV_SHA, 'profile': 'gpu_calib_v5_h112', 'hfov_deg': 120.,
                 'bearing_convention': 'positive_right', 'arm_ground_m': .9, 'advance_m': .4,
                 'confirm_ticks': 3, 'door_detector': None},
         'map': None}
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(c.get(k), dict):
            c[k] = {**c[k], **v}
        else:
            c[k] = v
    return c


def duty(drive):
    """sim.grasp_act_port.duty_wheels (same formula, no simulator import)."""
    desired = wheel_mix(drive); scale = max(.35, max(map(abs, desired)))
    wheels, durations = [], []
    for v in desired:
        dt = .1*abs(v)/scale
        if dt < .001:
            wheels.append(0.); durations.append(0.)
        else:
            wheels.append(math.copysign(.35, v)); durations.append(dt)
    return wheels, durations


class FakeWorld:
    """Robots move exactly by the calibrated own-command model (odometry is perfect here)."""

    def __init__(self, zone=(2.5, .2), fov_deg=120., visible=True):
        off = {r: h.role_offset(role, cfg()['formation']) for r, role in ROLES.items()}
        self.pose = {r: off[r] for r in ROLES}           # beam centre at the origin, yaw 0
        self.zone, self.fov, self.visible = zone, math.radians(fov_deg), visible

    def apply(self, r, cmd):
        o = h.OwnOdometry(CAL, sigma_xy_per_m=0, sigma_yaw_per_rad=0, pose=self.pose[r])
        self.pose[r] = o.step(cmd)

    def sensor(self, leader):
        def see(jpeg):
            if not self.visible:
                return None
            x, y, _ = relative(self.pose[leader], (self.zone[0], self.zone[1], 0.))
            if x <= .05 or abs(math.atan2(y, x)) > self.fov/2:
                return None
            return dict(point=(x, y), detection={'kind': 'zone_B'})
        return see

    def gap(self):
        a, b = self.pose['r1'], self.pose['r2']
        return math.hypot(a[0] - b[0], a[1] - b[1])


def command(t, wheels=(0.,)*4):
    return {'t': t, 'wheels': list(wheels), 'duration_s': [.1 if w else 0. for w in wheels], 'pwm': dict(PWM)}


def run_episode(world, c=None, *, ticks=2500, student_done_t=2.0):
    run = h.HybridRun(c or cfg(), ROLES, sensor=world.sensor('r1'), wheel_fn=duty)
    t, place_t = 0., None
    for _ in range(ticks):
        if run.student_controls():
            seg = 'release' if t >= student_done_t else 'grasp'
            applied = {r: command(t) for r in ROLES}
            if run.segment() == 'STUDENT_PLACE':
                place_t = t if place_t is None else place_t
                if t - place_t > 1.:
                    run.student_finished(t)
                    break
            issued = {r: {'segment': seg, 'done': True, 'stage': 'execute'} for r in ROLES}
            run.after_student_tick(t, issued, applied)
        else:
            if run.segment() == 'ABORT':
                break
            applied = run.code_tick(t, {r: b'jpeg' for r in ROLES})
            for r, cmd in applied.items():
                world.apply(r, cmd)
        t = round(t + .1, 6)
    return run


# ------------------------------------------------------------------ config / approval

def test_config_is_exact_and_fails_closed():
    assert h.validate_config(cfg())
    for bad in (dict(mode='x'), dict(carry_mode='gt'), dict(navigator='r1'), dict(shadow_predict=1),
                dict(calibration={'forward_m_per_pct_s': 0.}), dict(limits={'v_max': -1.}),
                dict(nav={'sha': 'deadbeef'}), dict(map={'approval': 'x'})):
        with pytest.raises(ValueError):
            h.validate_config(cfg(**bad))
    c = cfg(); del c['calibration']['yaw_deg_per_pct_s']
    with pytest.raises(ValueError, match='calibration'):
        h.validate_config(c)
    with pytest.raises(NotImplementedError, match='door detector'):
        h.validate_config(cfg(nav={'door_detector': 'x'}))


def test_map_mode_is_refused_until_owner_approval(tmp_path, monkeypatch):
    c = cfg(carry_mode='map', nav=None, map={'approval': str(tmp_path / 'approval.json')})
    assert h.MAP_MODE_APPROVAL_SHA256 is None
    with pytest.raises(h.MapModeNotApproved, match='창민'):
        h.validate_config(c)
    with pytest.raises(h.MapModeNotApproved):
        h.HybridRun(c, ROLES, static_map={}, start_poses={})
    record = tmp_path / 'approval.json'; record.write_text('{"approved_by": "test"}')
    import hashlib
    monkeypatch.setattr(h, 'MAP_MODE_APPROVAL_SHA256', hashlib.sha256(record.read_bytes()).hexdigest())
    assert h.validate_config(c)
    record.write_text('{"approved_by": "other"}')
    with pytest.raises(h.MapModeNotApproved, match='differs'):
        h.validate_config(c)


def test_default_carry_mode_is_nav():
    assert h.DEFAULT_CARRY_MODE == 'nav' and h.CARRY_MODES[0] == 'nav'


# ------------------------------------------------------------------ geometry / odometry

def test_wheel_body_inverts_wheel_mix():
    for drive in ((1., 0., 0.), (0., 1., 0.), (0., 0., 1.), (.3, -.2, .5)):
        w = wheel_mix(drive)
        f, l, t = h.wheel_body({'wheels': list(w), 'duration_s': [.01]*4})
        assert (round(f, 9), round(l, 9), round(t, 9)) == tuple(round(x*h.PCT*.01, 9) for x in drive)


def test_role_offsets_face_each_other():
    f = cfg()['formation']
    teal, blue = h.role_offset('teal', f), h.role_offset('blue', f)
    assert teal[0] < 0 < blue[0] and teal[2] == 0. and blue[2] == math.pi
    assert math.isclose(blue[0] - teal[0], 2*(.30 + .203))


def test_pose_trust_gate_fails_closed():
    o = h.OwnOdometry(CAL, sigma_xy_per_m=.5, sigma_yaw_per_rad=.5)
    gate = h.PoseTrustGate(cfg(limits={'sigma_xy_max_m': .1})['limits'])
    assert gate.check(o) is None
    for _ in range(100):
        o.step({'wheels': [.35]*4, 'duration_s': [.1]*4})
    assert gate.check(o) == 'SELF_POSE_UNCERTAIN'


# ------------------------------------------------------------------ I1 arbiter / I2 sync / I8

def test_arbiter_rejects_illegal_transitions():
    a = h.HybridSegmentArbiter('r1')
    with pytest.raises(ValueError, match='illegal'):
        a.to('CODE_CARRY', 0., 'skip sync')
    a.to('CARRY_SYNC', 0., 'own'); a.to('CODE_CARRY', 0., 'GO')
    assert not a.student_controls
    a.to('ABORT', 1., 'x'); a.to('ABORT', 2., 'again')
    assert a.segment == 'ABORT' and len(a.events) == 3


def test_full_nav_episode_hands_back_at_set_down_start():
    world = FakeWorld()
    run = run_episode(world)
    s = run.summary()
    assert s['segment'] == 'DONE' and s['outcome'] == 'handed_back', s['events']
    order = [e['to'] for e in s['switch_events'] if e['robot_id'] == 'r1']
    assert order == ['CARRY_SYNC', 'CODE_CARRY', 'PLACE_SYNC', 'STUDENT_PLACE', 'DONE']
    # the virtual beam ended near the zone point, the formation length stayed rigid
    V = run.planner.V
    assert math.hypot(V[0] - 2.5, V[1] - .2) < 1.0
    assert abs(world.gap() - 2*(.30 + .203)) < .03
    beam = compose(world.pose['r1'], (-h.role_offset('teal', cfg()['formation'])[0], 0., 0.))
    assert math.hypot(beam[0] - V[0], beam[1] - V[1]) < .05
    assert s['gt_inputs_to_code'] == 0 and s['teacher_steps'] == 0 and s['carry_mode'] == 'nav'
    assert 0 < s['student_commands_executed_ratio'] < 1 and s['code_segment_s'] > 0
    phases = [e['to'] for e in s['planner_events'] if e['event'] == 'phase']
    assert phases == ['acquire', 'approach', 'zone_settle']
    sync = s['sync_events']
    assert any(e['event'] == 'AUTHORIZED' for e in sync['carry']) and any(e['event'] == 'AUTHORIZED' for e in sync['place'])


def test_zone_never_seen_aborts_without_handing_back():
    run = run_episode(FakeWorld(visible=False), cfg(limits={'acquire_budget_s': 5.}))
    s = run.summary()
    assert s['segment'] == 'ABORT' and s['outcome'] == 'abort:zone_not_found'


def test_code_carry_timeout_aborts():
    run = run_episode(FakeWorld(zone=(30., 0.)), cfg(limits={'carry_budget_s': 8.}))
    assert run.summary()['outcome'] == 'abort:code_carry_timeout'


def test_student_controls_until_both_own_release_flags():
    run = h.HybridRun(cfg(), ROLES, sensor=lambda j: None, wheel_fn=duty)
    run.after_student_tick(0., {'r1': {'segment': 'release'}, 'r2': {'segment': 'grasp'}},
                           {r: command(0.) for r in ROLES})
    assert run.student_controls() and run.segment() == 'STUDENT_GRASP'
    run.after_student_tick(.1, {r: {'segment': 'release'} for r in ROLES}, {r: command(.1) for r in ROLES})
    assert not run.student_controls() and run.segment() == 'CARRY_SYNC'
    out = run.code_tick(.2, {r: b'j' for r in ROLES})
    assert run.segment() == 'CODE_CARRY' and all(not any(c['wheels']) for c in out.values())
    with pytest.raises(ValueError, match='own camera'):
        run.code_tick(.3, {'r1': b'j'})


def test_follower_holds_when_leader_message_is_stale():
    run = h.HybridRun(cfg(), ROLES, sensor=lambda j: None, wheel_fn=duty)
    run.after_student_tick(0., {r: {'segment': 'release'} for r in ROLES}, {r: command(0.) for r in ROLES})
    run.code_tick(.1, {r: b'j' for r in ROLES})
    run.bus.last = None
    run.planner.phase = 'acquire'; run.planner.phase_t = .1; run.planner.t0 = .1
    run._carry = lambda now, jpegs, hold: hold.update({r: False for r in ROLES})
    out = run.code_tick(.2, {r: b'j' for r in ROLES})
    assert not any(out['r2']['wheels'])


def test_shadow_request_carries_only_own_frame_and_applied_command():
    run = h.HybridRun(cfg(shadow_predict=True), ROLES, sensor=lambda j: None, wheel_fn=duty)
    req = run.shadow_request(1., {r: 'b64' for r in ROLES}, {r: command(1.) for r in ROLES})
    assert req['op'] == 'shadow' and req['predict'] is True
    assert all(set(v) == {'jpeg', 'applied'} for v in req['robots'].values())


# ------------------------------------------------------------------ I6 nav sensor

def test_nav_sensor_uses_component_bottom_centre_and_fails_closed():
    calls = []
    def det(jpeg):
        return [dict(kind='zone_B', bbox=(100, 50, 301, 200), bearing_deg=0.)]
    def project(u, v):
        calls.append((u, v)); return (1.2, -.1)
    s = h.NavZoneSensor(det, project)
    assert s(b'x')['point'] == (1.2, -.1) and calls == [(200., 199)]
    assert h.NavZoneSensor(lambda j: [], project)(b'x') is None
    assert h.NavZoneSensor(det, lambda u, v: None)(b'x') is None


def test_nav_module_pin_and_clean_tree_required(tmp_path):
    def git(sha, dirty=''):
        return lambda cmd, text=True: sha if 'rev-parse' in cmd else dirty
    with pytest.raises(ValueError, match='pinned'):
        h.load_nav_module(tmp_path, git=git('0' * 40))
    with pytest.raises(ValueError, match='clean'):
        h.load_nav_module(tmp_path, git=git(h.NAV_SHA, ' M x'))


# ------------------------------------------------------------------ I11 import audit

FORBIDDEN = ('mujoco', 'warp', 'sim.', 'harness.pair_carry_eval', 'harness.pairact_student_eval',
             'harness.grasp_act_visible_world', 'scripts.')


def test_hybrid_module_imports_no_simulator_truth_or_evaluator():
    tree = ast.parse((ROOT / 'harness/hybrid_carry.py').read_text())
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or '')
    assert names and not [n for n in names if n.startswith(FORBIDDEN) or n in ('mujoco', 'warp')]
    params = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            params |= {a.arg for a in node.args.args + node.args.kwonlyargs}
    assert not params & {'truth', 'gt', 'world', 'contacts', 'carry_eval', 'teacher', 'partner_pose'}
