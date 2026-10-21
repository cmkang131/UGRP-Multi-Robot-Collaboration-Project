"""Hybrid code-carry smoke (teacher near field + code carry + teacher place; not learned): pure tests."""
import importlib.util
import inspect
import json
import math
from pathlib import Path

import pytest

from harness import hybrid_carry as h
from harness import hybrid_smoke_eval as se
from harness import pair_carry_eval as ce
from harness import pair_carry_teacher_warp as ct

_spec = importlib.util.spec_from_file_location('_hybrid_carry_tests', Path(__file__).with_name('test_hybrid_carry.py'))
_hct = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_hct)
CAL, FakeWorld, ROLES, cfg, duty = _hct.CAL, _hct.FakeWorld, _hct.ROLES, _hct.cfg, _hct.duty

ROOT = Path(__file__).resolve().parents[1]
MAP = json.loads((ROOT/'maps/zones_final_v3/zone_wide_two_doors_final_v3.json').read_text())


def smoke_episode(world, c=None, ticks=2500):
    run = h.HybridRun(c or cfg(), ROLES, sensor=world.sensor('r1'), wheel_fn=duty, purpose='teacher_smoke')
    prev = {r: {'pwm': {str(k): 1500 for k in (1, 3, 4, 5, 6)}} for r in ROLES}
    t, rows, logged = 0., [], []
    run.teacher_handover(t, prev)
    for _ in range(ticks):
        rows.append({'t': t, 'robots': {r: {'pose': list(world.pose[r])} for r in ROLES}})
        if run.student_controls() or run.segment() == 'ABORT':
            break
        applied = run.code_tick(t, {r: b'jpeg' for r in ROLES})
        logged.append(se.tick_row(t, run, applied, {'beam': {'pose': [0., 0., 0.]},
                                                    'robots': {r: {'pose': list(world.pose[r])} for r in ROLES}}))
        for r, cmd in applied.items():
            world.apply(r, cmd)
        t = round(t + .1, 6)
    rows.append({'t': t, 'robots': {r: {'pose': list(world.pose[r])} for r in ROLES}})
    return run, rows, logged


def test_teacher_smoke_hands_back_at_set_down_start_without_a_student():
    run, rows, logged = smoke_episode(FakeWorld())
    assert run.segment() == 'STUDENT_PLACE' and run.outcome is None
    s = run.summary()
    assert s['purpose'] == 'teacher_smoke' and s['near_field'] == 'teacher' and s['ticks']['student'] == 0
    assert s['gt_inputs_to_code'] == 0 and s['outcome'] == 'handed_back'
    assert any(e['event'] == 'teacher_handover' for e in s['events'])
    # code log in the GT teacher's drive-log format -> the same eval-only drive_response works
    resp = ce.drive_response([{**r, 'beam': {}, 'contacts': {}} for r in rows], run.log, list(ROLES))
    assert resp['phases']['all']['r1']['ticks'] > 10
    assert {e['segment'] for e in logged} >= {'CODE_CARRY', 'PLACE_SYNC'}   # segment after the tick = command source
    assert any(e['zone_seen'] for e in logged)


def test_teacher_handover_only_in_teacher_smoke_and_only_once():
    run = h.HybridRun(cfg(), ROLES, sensor=FakeWorld().sensor('r1'), wheel_fn=duty)
    prev = {r: {'pwm': {'1': 1500}} for r in ROLES}
    with pytest.raises(ValueError, match='teacher near-field smoke'):
        run.teacher_handover(0., prev)
    run = h.HybridRun(cfg(), ROLES, sensor=FakeWorld().sensor('r1'), wheel_fn=duty, purpose='teacher_smoke')
    run.teacher_handover(0., prev)
    with pytest.raises(ValueError, match='once'):
        run.teacher_handover(.1, prev)


class JitterWorld(FakeWorld):
    """Calibrated motion plus a small deterministic lateral jitter (so the drift estimate is not exactly 0)."""

    k = 0

    def apply(self, r, cmd):
        super().apply(r, cmd)
        JitterWorld.k += 1
        x, y, yaw = self.pose[r]
        j = .0004*math.sin(1.7*JitterWorld.k)
        self.pose[r] = (x - math.sin(yaw)*j, y + math.cos(yaw)*j, yaw)


def test_smoke_code_log_feeds_the_loaded_odometry_fit(tmp_path):
    run, rows, logged = smoke_episode(JitterWorld())
    raw = tmp_path/'run'/'world-000'/'raw'; raw.mkdir(parents=True)
    (raw/'hybrid-drive.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in logged))
    (raw/'eval-only.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    (tmp_path/'run'/'summary.json').write_text(json.dumps({'worlds': [{'world': 0, 'seed': 8420001}]}))
    spec = importlib.util.spec_from_file_location('fit_loaded_odom', ROOT/'scripts/fit_loaded_odom.py')
    fit = importlib.util.module_from_spec(spec); spec.loader.exec_module(fit)
    rep = fit.run_fit([tmp_path/'run'])
    assert rep['worlds'][0]['source'] == 'hybrid_code_log'
    assert rep['calibration']['latency_ticks'] == 0
    assert rep['calibration']['forward_m_per_pct_s'] == pytest.approx(CAL['forward_m_per_pct_s'], rel=.01)
    assert rep['calibration']['yaw_deg_per_pct_s'] == pytest.approx(CAL['yaw_deg_per_pct_s'], rel=.01)


def test_place_only_teacher_starts_at_lower_without_route():
    beam = (4.6, -2.1, math.pi/2)
    robots = {'r1': ct.compose(beam, (-.5, 0., 0.)), 'r2': ct.compose(beam, (.5, 0., math.pi))}
    arm = {r: {'place': {1: 1500, 3: 1400, 4: 1600, 5: 1500, 6: 1500},
               'hover': {1: 2000, 3: 1300, 4: 1700, 5: 1500, 6: 1500}} for r in ROLES}
    pwm = {r: {1: 1500, 3: 1200, 4: 1800, 5: 1500, 6: 1500} for r in ROLES}
    row = {'t': 50., 'beam': {'pose': list(beam), 'min_z': .03, 'tilt_deg': 1.},
           'robots': {r: {'pose': list(p)} for r, p in robots.items()}, 'contacts': {r: [2., 2.] for r in ROLES}}
    t = ct.PairCarryTeacherWarp(ROLES, row, 50., MAP, arm, pwm, wheel_fn=duty, place_only=True)
    assert t.phase == 'lower' and t.route == [] and t.route_info == {'place_only': True}
    assert t.route_plans == 0 and t.outcome is None
    now = 50.
    while not t.done and now < 70.:
        now = round(now + .1, 6)
        t.step({**row, 't': now}, now)
    assert t.outcome == 'command_sequence_complete'
    assert [e['to'] for e in t.events if e.get('event') == 'phase'] == ['lower', 'open', 'raise', 'retreat', 'done']
    with pytest.raises(TypeError):
        ct.start_place_from_runner({'roles': ROLES}, row, 50., None, {}, {}, 110., route_mode='detour_v1')


def test_runner_smoke_flag_is_default_off_and_fails_closed(tmp_path):
    from scripts import run_grasp_act_teacher as runner
    assert inspect.signature(runner.run).parameters['hybrid_smoke'].default is None
    plan = {'roles': ROLES}
    ok = cfg(shadow_predict=False)
    with pytest.raises(ValueError, match='shadow_predict'):
        runner.run(plan, tmp_path, pair_carry='pair_carry_gt_v1', teacher_profile='visible_only',
                   hybrid_smoke=cfg(shadow_predict=True))
    with pytest.raises(ValueError, match='student'):      # hybrid_carry needs a student; the smoke has none
        runner.run(plan, tmp_path, pair_carry='pair_carry_gt_v1', teacher_profile='visible_only', hybrid_smoke=ok,
                   hybrid_carry=cfg())
    with pytest.raises(ValueError, match='pair joint hold'):
        runner.run(plan, tmp_path, pair_carry='off', teacher_profile='visible_only', hybrid_smoke=ok)
    with pytest.raises(ValueError, match='records'):
        runner.run(plan, tmp_path, pair_carry='pair_carry_gt_v1', teacher_profile='visible_only', hybrid_smoke=ok,
                   noise=True)
    bad = cfg(shadow_predict=False); bad['calibration']['forward_m_per_pct_s'] = .005
    with pytest.raises(ValueError, match='values_sha256'):
        runner.run(plan, tmp_path, pair_carry='pair_carry_gt_v1', teacher_profile='visible_only', hybrid_smoke=bad)


# ------------------------------------------------------------------ eval-only geometry

def look(yaw, pitch_down_deg):
    """MuJoCo camera rotation (row-major) looking along heading yaw, pitched down."""
    p = math.radians(pitch_down_deg)
    fwd = (math.cos(yaw)*math.cos(p), math.sin(yaw)*math.cos(p), -math.sin(p))
    right = (math.sin(yaw), -math.cos(yaw), 0.)
    up = (right[1]*fwd[2] - right[2]*fwd[1], right[2]*fwd[0] - right[0]*fwd[2], right[0]*fwd[1] - right[1]*fwd[0])
    back = tuple(-v for v in fwd)
    return [right[0], up[0], back[0], right[1], up[1], back[1], right[2], up[2], back[2]]


def test_camera_mount_reads_height_pitch_and_offsets():
    m = se.camera_mount((1.1, 2.0, .35), look(math.pi/2, 25.), (1.0, 2.0, math.pi/2))
    assert m['height_m'] == pytest.approx(.35) and m['pitch_down_deg'] == pytest.approx(25.)
    assert m['x_offset_m'] == pytest.approx(0., abs=1e-9) and m['y_offset_m'] == pytest.approx(-.1)
    assert m['yaw_rel_deg'] == pytest.approx(0., abs=1e-9)


def flat_projection(u, v, proj):
    """Toy pinhole floor projection with the same keys as nav GATE_GROUND_PROJECTION (no fisheye)."""
    a = math.radians(proj['pitch_down_deg']) + math.atan((v - proj['cy_px'])/proj['fy_px'])
    if a <= 0:
        return None
    x = proj['camera_height_m']/math.tan(a) + proj['camera_x_offset_m']
    return (x, -x*(u - proj['cx_px'])/proj['fx_px'])


GATE = dict(width=640, height=480, fx_px=620., fy_px=620., cx_px=320., cy_px=240., fisheye_d=(0, 0, 0, 0),
            camera_height_m=.29983, pitch_down_deg=18.9934, camera_x_offset_m=.0255)


def test_projection_check_is_zero_at_the_gate_mount_and_grows_when_the_arm_lifts_the_camera():
    same = {'height_m': GATE['camera_height_m'], 'pitch_down_deg': GATE['pitch_down_deg'],
            'x_offset_m': GATE['camera_x_offset_m'], 'y_offset_m': 0., 'yaw_rel_deg': 0.}
    r = se.projection_check((300, 200, 341, 400), same, flat_projection, GATE)
    assert r['error_m'] == pytest.approx(0., abs=1e-12)
    lifted = dict(same, height_m=.36, pitch_down_deg=12.)
    r = se.projection_check((300, 200, 341, 400), lifted, flat_projection, GATE)
    assert r['error_m'] > .05 and r['height_delta_m'] == pytest.approx(.36 - .29983)


def test_zone_occlusion_counts_fov_beam_and_partner():
    zone = {'cx': 4.6, 'cy': -2.1, 'hx': .3, 'hy': .6}
    cam = (3.0, -2.1, .3)
    xmat = look(0., 10.)
    clear = se.zone_occlusion(cam, xmat, zone, ((3.0, 5., .1), (3.0, 5.6, .1)), None)
    assert clear['in_fov'] == clear['grid_points'] == 25 and clear['visible'] == 25
    # beam lying across the line of sight just in front of the camera
    blocked = se.zone_occlusion(cam, xmat, zone, ((3.3, -3.5, .27), (3.3, -.7, .27)), None, beam_radius=.05)
    assert blocked['blocked_by_beam'] == 25 and blocked['visible'] == 0
    partner = se.zone_occlusion(cam, xmat, zone, ((3.0, 5., .1), (3.0, 5.6, .1)), (3.8, -2.1))
    assert 0 < partner['blocked_by_partner'] < 25
    behind = se.zone_occlusion(cam, look(math.pi, 10.), zone, ((3.0, 5., .1), (3.0, 5.6, .1)), None)
    assert behind['in_fov'] == 0 and behind['visible_frac_of_fov'] is None


def test_smoke_eval_module_is_not_imported_by_the_code_path():
    import ast
    tree = ast.parse((ROOT/'harness/hybrid_carry.py').read_text())
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {
        a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not {m for m in mods if m and ('hybrid_smoke_eval' in m or 'pair_carry_eval' in m)}
