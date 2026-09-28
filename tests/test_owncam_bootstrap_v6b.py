"""v6b start bootstrap: dock prior, stationary look, belief-checked pan scan. No physics or models."""
import copy
import json
import math
from pathlib import Path

import numpy as np
import pytest

from harness import zone_own_guards as guards
from harness.owncam_bootstrap_v6b import (AMCL_INITIAL_STD_XY_M, AMCL_INITIAL_STD_YAW_RAD, FAIL_REASON,
                                          BootstrapLocalizer, PAN_RISK_BOUND, StationaryBootstrap,
                                          belief_cells, belief_pan_clear, belief_particles, pan_risk_upper,
                                          bootstrap_complete, bootstrap_state, dock_prior, enable_bootstrap,
                                          prior_logdensity, sigma_points)
from harness.owncam_drive import WIDE_LOOK_PANS
from harness.owncam_pose_source import OwnCamPoseSource, PoseReport
from harness.owncam_recovery_v6 import enable_provider

ROOT = Path(__file__).resolve().parents[1]
DOCK_MAP = json.loads((ROOT/'maps/zones/zone_wide_door_tags_v2_dock_v3.json').read_text())
PARAMS = json.loads((ROOT/'experiments/2026-09-26-zone-owncam-loop-v2/calibration_loop_v2.json').read_text())['params']
FOLDED = {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}     # dev initial_servo_command


def provider(seed=911, particles=None, static=DOCK_MAP):
    params = copy.deepcopy(PARAMS)
    if particles:
        params['particles'] = particles
    p = OwnCamPoseSource(static, params, seed=seed)
    p.on_command({'t': 0., 'kind': 'initial_servo_command', 'pulses': {str(k): v for k, v in FOLDED.items()}})
    return p


def detections(static, pose_xyyaw, servo, rng, noise_px=.3, max_range=4.):
    """Synthetic own detections (same camera model as tests/test_owncam_localizer.py)."""
    import cv2
    from harness.wall_tags import TagDetector, camera_in_base, tag_world_frame
    det = TagDetector()
    o_bc, r_bc = camera_in_base(servo)
    x, y, yaw = pose_xyyaw
    c, s = math.cos(yaw), math.sin(yaw)
    r_wb = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    o_wc, r_wc = np.array([x, y, 0.]) + r_wb @ o_bc, r_wb @ r_bc
    out = []
    for tag in static['landmarks']['tags']:
        cw, rot = tag_world_frame(tag)
        h = tag['size_m']/2
        pc = (cw + np.array([[-h, h, 0], [h, h, 0], [h, -h, 0], [-h, -h, 0]]) @ rot.T - o_wc) @ r_wc
        if np.any(pc[:, 2] < .1) or np.dot(r_wc.T @ rot[:, 2], pc.mean(0)) >= 0:
            continue
        px = cv2.fisheye.distortPoints((pc[:, :2]/pc[:, 2:]).reshape(-1, 1, 2), det.K, det.D).reshape(-1, 2)
        if np.any(px < 0) or np.any(px[:, 0] > 639) or np.any(px[:, 1] > 479) or np.linalg.norm(pc.mean(0)) > max_range:
            continue
        px = px + rng.normal(size=px.shape)*noise_px
        if float(np.mean(np.linalg.norm(px - np.roll(px, 1, axis=0), axis=1))) < 8:
            continue
        sols = det.solve_pnp(det.undistort(px), tag['size_m'])
        if sols:
            out.append({'id': tag['id'], 'solutions': sols})
    return out


def test_dock_prior_uses_only_the_sealed_static_rows():
    prior = dock_prior(DOCK_MAP)
    dock = DOCK_MAP['start_dock']
    assert prior['components'] == [[dock['spawn_x_m'], y, dock['spawn_yaw_rad']] for y in dock['spawn_rows_y_m']]
    assert prior['weights'] == pytest.approx([1/3]*3)
    assert (prior['std_xy_m'], prior['std_yaw_rad']) == (AMCL_INITIAL_STD_XY_M, AMCL_INITIAL_STD_YAW_RAD) == (.5, math.pi/12)
    assert dock_prior({k: v for k, v in DOCK_MAP.items() if k != 'start_dock'}) is None
    bad = copy.deepcopy(DOCK_MAP); bad['start_dock']['spawn_rows_y_m'][0] += .1
    with pytest.raises(ValueError, match='seal'):
        dock_prior(bad)
    rows = np.array(prior['components'])
    dens = prior_logdensity(rows, prior)
    assert np.ptp(dens) < .05                              # only the neighbours' tails differ
    assert prior_logdensity(rows + [0, .7, 0], prior).max() < dens.min() - .2   # between rows
    assert prior_logdensity(np.array([[1.5, -.85, 0.], [-.65, -.85, math.pi/2]]), prior).max() < dens.min() - 5


def test_prior_is_not_a_fix_and_needs_the_v6_provider():
    p = provider()
    with pytest.raises(ValueError, match='recovery'):
        enable_bootstrap(p, 0.)
    enable_provider(p)
    state = enable_bootstrap(p, 0.)
    assert state['prior_applied'] and state['prior']['dock_sha256'] == DOCK_MAP['start_dock']['sha256']
    assert isinstance(p.loc, BootstrapLocalizer) and p.source.endswith(':recovery_v6:boot_v6b')
    rep = p.report(0.)
    assert rep.initialized and rep.last_fix_t is None and rep.fix_age_s is None
    assert not bootstrap_complete(rep)
    rows = {round(y, 2) for y in DOCK_MAP['start_dock']['spawn_rows_y_m']}
    near = [min(rows, key=lambda r: abs(r - y)) for y in p.loc.px[:, 1]]
    assert {r: near.count(r) for r in rows} == pytest.approx({r: p.loc.n/3 for r in rows}, rel=.15)
    assert enable_bootstrap(p, 5.) is state            # idempotent


def test_prior_only_at_session_start():
    p = provider(); enable_provider(p)
    p.on_command({'t': .5, 'kind': 'mecanum', 'forward': .1, 'left': 0., 'turn': 0., 'duration_s': .3})
    state = enable_bootstrap(p, .6)
    assert not state['prior_applied'] and state['prior_skip_reason'] == 'wheel_motion_seen'
    assert not p.loc.initialized
    q = provider(static={k: v for k, v in DOCK_MAP.items() if k != 'start_dock'}); enable_provider(q)
    assert enable_bootstrap(q, 0.)['prior_skip_reason'] == 'no_static_dock_prior'


def test_markerless_provider_contract_without_tag_fallback():
    class NoPrior:
        def report(self, now): return None
    with pytest.raises(ValueError, match='static-prior'):
        enable_bootstrap(NoPrior(), 0.)

    class Markerless:
        static_map = DOCK_MAP
        def __init__(self): self.got = None
        def report(self, now): return None
        def initialize_from_prior(self, now, prior):
            self.got = prior
            return True
    m = Markerless()
    state = enable_bootstrap(m, 0.)
    assert state['prior_applied'] and m.got['source'] == 'static_map.start_dock'
    assert bootstrap_state(m) is state


def test_moving_frames_are_never_used_by_the_bootstrap():
    p = provider(particles=600); enable_provider(p); enable_bootstrap(p, 0.)
    truth = (-.65, .55, 0.)
    dets = detections(DOCK_MAP, truth, FOLDED, np.random.default_rng(1))
    assert len(dets) >= 3
    p.on_command({'t': 1.3, 'kind': 'arm', 'servo_id': 3, 'pulse': 800})
    before = p.loc.px.copy()
    p.loc.update(1.30025, dets, dict(p.servo))
    assert p.loc.boot_obs == [] and 'moves' not in p.loc.stats
    assert p.loc.last_informative_t is None
    assert np.abs(p.loc.px - before).max() < .05        # only stationary diffusion


@pytest.mark.parametrize('truth', [(-.65, .55, 0.), (-.65, -.85, 0.), (-.65, -2.25, 0.), (-.6, .6, .05),
                                   (-.7, -.8, -.08)])
def test_prior_and_pan_scan_alone_reach_completion_without_dual_samples(truth):
    """Review #261 finding 3: dual injection removed; prior + stationary pan views suffice (synthetic)."""
    from harness.owncam_drive import LOOK_P20
    assert not hasattr(BootstrapLocalizer, '_inject_dual') and not hasattr(BootstrapLocalizer, 'DUAL_FRACTION')
    guard = guards.SweepGuard(DOCK_MAP)
    first = {**LOOK_P20, 1: 2000, 6: 1500}
    rng = np.random.default_rng(3)
    p = provider(particles=2000); enable_provider(p); enable_bootstrap(p, 0.)
    t, sigmas, done = 1.3, [], False
    for pan in (1500, 1230, 970, 1770, 2030):
        servo = {**FOLDED, 6: pan}
        if pan != 1500:
            p.on_command({'t': t, 'kind': 'look', 'pan_pulse': pan})
            t += .6
        p.loc.update(t, detections(DOCK_MAP, truth, servo, rng), servo)
        rep = p.report(t)
        sigmas.append(rep.std_xy_m)
        if bootstrap_complete(rep, guard=guard, servo=FOLDED, first_motion=first):
            done = True
            break
        t += .2
    assert done and rep.std_xy_m <= guards.SIGMA_CAP_XY_M and rep.std_yaw_rad <= guards.SIGMA_CAP_YAW_RAD
    assert math.hypot(rep.x_m - truth[0], rep.y_m - truth[1]) < .15
    assert sigmas[-1] < sigmas[0] and rep.last_fix_t is not None and p.loc.stats['moves'] >= 1
    assert 'dual_samples' not in p.loc.stats


def test_rejected_observation_leaves_particles_and_weights_untouched():
    """Review #261 finding 5: a saturated/incompatible view must not mutate the PF."""
    p = provider(particles=800); enable_provider(p); enable_bootstrap(p, 0.)
    far = detections(DOCK_MAP, (3.5, -2.0, math.pi), {**FOLDED, 6: 1500}, np.random.default_rng(2))
    assert far
    p.loc.predict_to(1.5)
    px, logw, scale = p.loc.px.copy(), p.loc.logw.copy(), p.loc.scale.copy()
    p.loc.update(1.5, far, dict(p.servo))
    q = p.loc.quality
    assert not q.get('informative') and (q.get('saturated') or q.get('inlier_fraction', 0) < .66)
    assert np.array_equal(p.loc.px, px) and np.array_equal(p.loc.logw, logw) and np.array_equal(p.loc.scale, scale)
    assert p.loc.boot_obs == [] and 'moves' not in p.loc.stats


def test_wheel_motion_ends_the_stationary_belief():
    p = provider(particles=300); enable_provider(p); enable_bootstrap(p, 0.)
    assert p.loc.bootstrap_active()
    p.on_command({'t': 1., 'kind': 'mecanum', 'forward': .1, 'left': 0., 'turn': 0., 'duration_s': .3})
    assert not p.loc.bootstrap_active() and p.loc.boot_ended == 'wheel_motion'


def report(x=-.65, y=.55, yaw=0., cov=((1e-4, 0, 0), (0, 1e-4, 0), (0, 0, 1e-4)), fix=None, t=2.):
    sxy = math.sqrt(cov[0][0] + cov[1][1]); syaw = math.sqrt(cov[2][2])
    q = None if fix is None else {'accepted': True, 'informative': True, 'settled': True, 'ambiguous': False,
                                  'last_fix_quality': {'accepted': True, 'informative': True, 'settled': True,
                                                       'ambiguous': False, 't': fix}}
    return PoseReport(t, True, x_m=x, y_m=y, yaw_rad=yaw, cov=cov, std_xy_m=sxy, std_yaw_rad=syaw,
                      last_fix_t=fix, fix_age_s=None if fix is None else t - fix, observation_quality=q)


def test_belief_pan_check_uses_the_covariance_not_an_isotropic_cap():
    guard = guards.SweepGuard(DOCK_MAP)
    ridge = report(cov=((.004, 0, 0), (0, .12, .01), (0, .01, .01)))      # y-yaw ridge (first view)
    assert ridge.std_xy_m > guards.SIGMA_CAP_XY_M
    iso = guards.OwnPose(ridge.x_m, ridge.y_m, ridge.yaw_rad, ridge.std_xy_m, ridge.std_yaw_rad)
    assert not guard.transition_clear(FOLDED, {6: 1230}, iso, loaded=False)
    assert belief_pan_clear(guard, FOLDED, 1230, ridge)
    toward_wall = report(cov=((.09, 0, 0), (0, .001, 0), (0, 0, .001)))   # 0.6 m 2-sigma toward x=-1.05
    assert not belief_pan_clear(guard, FOLDED, 1230, toward_wall)
    assert len(sigma_points(ridge, 2.)) == 7


def test_particle_pan_check_handles_a_multimodal_row_belief():
    """Three-row posterior after one view: sigma points land outside the arena; particles do not."""
    guard = guards.SweepGuard(DOCK_MAP)
    rows = np.array([[-.65, y, 0.] for y in (-2.25, -.85, .55) for _ in range(20)])
    mean = rows.mean(axis=0)
    cov = np.cov(rows.T) + np.eye(3) * 1e-6
    rep = report(x=mean[0], y=mean[1], yaw=mean[2], cov=tuple(map(tuple, cov)))
    assert not belief_pan_clear(guard, FOLDED, 1230, rep)                       # Gaussian fallback refuses
    even = np.full(len(rows), 1 / len(rows))
    assert belief_pan_clear(guard, FOLDED, 1230, rep, particles=(rows, even))
    bad = np.vstack([rows, [[-1.0, -.85, 0.]]])                                 # 1/61 of the mass at the west wall
    assert not belief_pan_clear(guard, FOLDED, 1230, rep, particles=(bad, np.full(len(bad), 1 / len(bad))))
    p = provider(particles=300); enable_provider(p); enable_bootstrap(p, 0.)
    pts, w = belief_particles(p)
    assert pts.shape == (300, 3) and np.isclose(w.sum(), 1.) and np.array_equal(pts, p.loc.px)


def _wall_mixture(n=800, n_wall=80, order='interleaved'):
    safe = np.array([[-.65, y, 0.] for y in (-2.25, -.85, .55)])
    pts = np.array([safe[i % 3] for i in range(n - n_wall)] + [[-1.0, .55, 0.]] * n_wall)
    if order == 'interleaved':                  # collision particles spread between systematic sample indices
        idx = np.argsort(np.r_[np.arange(n - n_wall), (np.arange(n_wall) + .5) * (n - n_wall) / n_wall])
        pts = pts[idx]
    elif order == 'shuffled':
        pts = pts[np.random.default_rng(5).permutation(n)]
    return pts, np.full(n, 1 / n)


@pytest.mark.parametrize('order', ['interleaved', 'shuffled', 'blocked'])
def test_pan_risk_counts_all_particle_mass_regardless_of_order(order):
    """Re-review #261 P1: a 10 % collision mass must be refused whatever the particle order."""
    guard = guards.SweepGuard(DOCK_MAP)
    pts, w = _wall_mixture(order=order)
    wall = guards.OwnPose(-1.0, .55, 0., 0., 0.)
    assert not guard.transition_clear(FOLDED, {6: 1440}, wall, loaded=False)
    rep = report(x=-.65, y=-.85, cov=((.01, 0, 0), (0, .8, 0), (0, 0, .001)))
    clear, risk, _ = pan_risk_upper(guard, FOLDED, {6: 1440}, (pts, w))
    assert not clear and risk > PAN_RISK_BOUND and risk >= .1 - 1e-9
    assert not belief_pan_clear(guard, FOLDED, 1440, rep, particles=(pts, w))
    small_pts, small_w = _wall_mixture(n=1000, n_wall=5, order=order)          # 0.5 % mass: within the bound
    assert belief_pan_clear(guard, FOLDED, 1440, rep, particles=(small_pts, small_w))


def test_cell_bound_is_conservative_for_every_particle_in_a_clear_cell():
    guard = guards.SweepGuard(DOCK_MAP)
    rng = np.random.default_rng(11)
    pts = np.c_[rng.uniform(-1.0, -.4, 3000), rng.uniform(.3, .8, 3000), rng.normal(0, .15, 3000)]
    centres, mass = belief_cells((pts, np.full(len(pts), 1 / len(pts))))
    assert np.isclose(mass.sum(), 1.)
    half_xy = math.hypot(.04, .04) / 2
    for c in centres[:60]:
        inflated = guards.OwnPose(*map(float, c), half_xy / guards.K_SIGMA, .02 / guards.K_SIGMA)
        if not guard.transition_clear(FOLDED, {6: 1440}, inflated, loaded=False):
            continue
        members = pts[np.all(np.floor(pts[:, :2] / .04) == np.floor(c[:2] / .04), axis=1)
                      & (np.floor(((pts[:, 2] + math.pi) % (2 * math.pi) - math.pi) / .04) == math.floor(c[2] / .04))]
        for q in members:
            assert guard.transition_clear(FOLDED, {6: 1440}, guards.OwnPose(*map(float, q), 0., 0.), loaded=False)


@pytest.mark.parametrize('field,value', [('std_xy_m', float('nan')), ('std_yaw_rad', float('inf')),
                                         ('x_m', float('nan')), ('std_xy_m', -.01)])
def test_non_finite_or_negative_report_never_completes_or_pans(field, value):
    """Re-review #261 P1: NaN sigma must not pass as 'within cap' nor as the guard's uninitialized pose."""
    import dataclasses
    guard = guards.SweepGuard(DOCK_MAP)
    first = {**LOOK_P20_FOR_TEST, 1: 2000, 6: 1500}
    good = report(cov=((.004, 0, 0), (0, .004, 0), (0, 0, .004)), fix=1.5)
    assert bootstrap_complete(good, guard=guard, servo=FOLDED, first_motion=first)
    bad = dataclasses.replace(good, **{field: value})
    assert not bootstrap_complete(bad, guard=guard, servo=FOLDED, first_motion=first)
    assert not belief_pan_clear(guard, FOLDED, 1230, bad)
    low = dataclasses.replace(report(fix=1.5), **{field: value})               # gate-LOW path too
    assert not bootstrap_complete(low, guard=guard, servo=FOLDED, first_motion=first)


from harness.owncam_drive import LOOK_P20 as LOOK_P20_FOR_TEST  # noqa: E402


class FakeProvider:
    def __init__(self, reports):
        self.reports, self.i = reports, 0

    def report(self, now):
        return self.reports(now)


def run_scan(reports, until=12.):
    guard = guards.SweepGuard(DOCK_MAP)
    servo = dict(FOLDED)
    scan = StationaryBootstrap(guard, WIDE_LOOK_PANS, servo, 1.3)
    t, issued = 1.3, []
    while t < until:
        out = scan.step(t, FakeProvider(reports), servo)
        if out is None:
            return scan, issued, t
        for c in out:
            issued.append((round(t, 2), c))
            if c['kind'] == 'look':
                servo[6] = c['pan_pulse']
        if scan.outcome == 'blocked':
            return scan, issued, t
        t = round(t + .1, 6)
    return scan, issued, t


def test_scan_holds_pans_only_and_restores_before_completion():
    fix_at = 4.
    def reports(now):
        if now < fix_at:
            return report(cov=((.004, 0, 0), (0, .12, .01), (0, .01, .01)), t=now)
        return report(fix=fix_at, t=now)
    scan, issued, t = run_scan(reports)
    kinds = {c['kind'] for _, c in issued}
    assert kinds <= {'hold', 'look'} and scan.outcome == 'fix'
    looks = [c['pan_pulse'] for _, c in issued if c['kind'] == 'look']
    assert looks and all(abs(b - a) <= 60 for a, b in zip([1500] + looks, looks))
    assert looks[-1] == 1500
    first_look = next(tt for tt, c in issued if c['kind'] == 'look')
    assert first_look >= 1.3 + .6 - 1e-9                    # observe the settled first view before panning


def test_scan_fails_closed_on_budget_without_arm_or_wheel_commands():
    scan, issued, t = run_scan(lambda now: report(cov=((.004, 0, 0), (0, .12, .01), (0, .01, .01)), t=now),
                               until=30.)
    assert scan.outcome == 'blocked' and 10. - 1e-6 <= scan.wait.waited_s <= 10.2
    assert {c['kind'] for _, c in issued} <= {'hold', 'look'}


def test_refused_pans_stay_queued_and_are_rechecked_when_the_belief_improves():
    """Re-review #261 P2: a pan refused under a wide early belief is not consumed."""
    wide = ((.09, 0, 0), (0, .2, 0), (0, 0, .04))
    def reports(now):
        if now < 1.95:
            return report(cov=wide, t=now)                                     # every pan refused
        if now < 4.:
            return report(cov=((.004, 0, 0), (0, .12, .01), (0, .01, .01)), t=now)
        return report(fix=4., t=now)
    guard = guards.SweepGuard(DOCK_MAP)
    assert not any(belief_pan_clear(guard, FOLDED, p, report(cov=wide)) for p in (1230, 970, 1770, 2030))
    scan, issued, t = run_scan(reports)
    refused = [e for e in scan.log if e['event'] == 'pan_refused']
    assert refused and all(e['t'] < 1.95 for e in refused)
    assert any(c['kind'] == 'look' and c['pan_pulse'] != 1500 for _, c in issued)
    assert scan.outcome == 'fix' and scan.visited


def test_restore_rechecks_after_settle_and_reobserves_when_the_fix_is_lost():
    """Review #261 finding 4: homing alone is not completion."""
    state = {'lost_after_restore': True, 'restore_t': None, 'servo': None}
    def reports(now):
        if now < 4.:
            return report(cov=((.004, 0, 0), (0, .12, .01), (0, .01, .01)), t=now)
        homed = state['restore_t'] is not None and state['servo'][6] == 1500
        if homed and state['lost_after_restore']:
            return report(cov=((.004, 0, 0), (0, .12, .01), (0, .01, .01)), t=now)   # fix lost once home
        return report(fix=4., t=now)
    guard = guards.SweepGuard(DOCK_MAP)
    servo = dict(FOLDED)
    state['servo'] = servo
    scan = StationaryBootstrap(guard, WIDE_LOOK_PANS, servo, 1.3)
    t, last_home_step = 1.3, None
    while t < 30. and scan.outcome is None:
        out = scan.step(t, FakeProvider(reports), servo)
        if out is None:
            break
        if scan.stage == 'restore' and state['restore_t'] is None:
            state['restore_t'] = t
        for c in out:
            if c['kind'] == 'look':
                servo[6] = c['pan_pulse']
                if servo[6] == 1500:
                    last_home_step = t
        t = round(t + .1, 6)
    assert state['restore_t'] is not None and servo[6] == 1500
    assert scan.outcome == 'blocked'                                   # never 'fix' without a current fix
    assert any(e['event'] == 'verify_failed' for e in scan.log)
    # With the fix kept, completion happens only after the settle time at home.
    state.update(lost_after_restore=False, restore_t=None)
    servo = dict(FOLDED)
    state['servo'] = servo
    scan = StationaryBootstrap(guard, WIDE_LOOK_PANS, servo, 1.3)
    t, last_home_step = 1.3, None
    while t < 30.:
        out = scan.step(t, FakeProvider(reports), servo)
        if out is None:
            break
        for c in out:
            if c['kind'] == 'look':
                servo[6] = c['pan_pulse']
                last_home_step = t if servo[6] == 1500 else last_home_step
        t = round(t + .1, 6)
    assert scan.outcome == 'fix' and last_home_step is not None and t - last_home_step >= .6 - 1e-9


def test_informative_fix_alone_does_not_complete_a_wide_posterior():
    from harness.owncam_drive import LOOK_P20
    guard = guards.SweepGuard(DOCK_MAP)
    first = {**LOOK_P20, 1: 2000, 6: 1500}
    wide = report(cov=((.004, 0, 0), (0, .09, 0), (0, 0, .004)), fix=1.9)
    assert not bootstrap_complete(wide) and not bootstrap_complete(wide, guard=guard, servo=FOLDED, first_motion=first)
    assert bootstrap_complete(report(fix=1.9))
    mid = report(cov=((.002, 0, 0), (0, .006, 0), (0, 0, .002)), fix=1.9)      # sigma_xy 0.089 m > LOW
    assert not bootstrap_complete(mid)
    assert bootstrap_complete(mid, guard=guard, servo=FOLDED, first_motion=first)
    assert not bootstrap_complete(report(cov=mid.cov), guard=guard, servo=FOLDED, first_motion=first)  # no fix


def test_completion_rejects_clearance_that_exists_only_by_sigma_clamping():
    """Review #261 finding 2 (reviewer's case): sigma above the guard cap never completes."""
    from harness.owncam_drive import LOOK_P20
    guard = guards.SweepGuard(DOCK_MAP)
    first = {**LOOK_P20, 1: 2000, 6: 1500}
    wide = report(x=-.50, y=.55, cov=((.04, 0, 0), (0, .09, 0), (0, 0, .09)), fix=1.9)
    assert wide.std_xy_m > guards.SIGMA_CAP_XY_M and wide.std_yaw_rad > guards.SIGMA_CAP_YAW_RAD
    clamped = guards.OwnPose.from_report(wide)
    assert guard.transition_clear(FOLDED, first, clamped, loaded=False)      # the old guard (unchanged) clears it
    assert not bootstrap_complete(wide, guard=guard, servo=FOLDED, first_motion=first)
    just_over = report(x=-.50, y=.55, cov=((.0115, 0, 0), (0, .0115, 0), (0, 0, .001)), fix=1.9)
    assert just_over.std_xy_m > guards.SIGMA_CAP_XY_M
    assert not bootstrap_complete(just_over, guard=guard, servo=FOLDED, first_motion=first)


def test_executor_is_inert_without_state_and_fails_closed_with_it():
    from harness.zone_own_executor import ZoneOwnExecutor
    from tests.test_zone_own_executor_host import FakeHost
    from tests.test_zone_pair_executor import ORDER, CALIB
    from tests.test_zone_own_executor import ROWS_Y

    def run(boot):
        ex = ZoneOwnExecutor('r1', DOCK_MAP, CALIB['params'], ORDER, skill_factory=lambda *a, **kw: None,
                             pose_estimate_cls=tuple, search_rows_y=ROWS_Y, judgments=False, job_sim_limit_s=60)
        others = {r: ZoneOwnExecutor(r, DOCK_MAP, CALIB['params'], ORDER, skill_factory=lambda *a, **kw: None,
                                     pose_estimate_cls=tuple, search_rows_y=ROWS_Y, judgments=False)
                  for r in ('r2', 'r3')}
        host = FakeHost({'r1': ex, **others}, lambda *a: None)
        if boot:
            enable_provider(ex.pose); enable_bootstrap(ex.pose, 0.)
        host.call('r1', 'look_around')
        host.run(14.)
        return ex, [c for c in host.robots['r1'].commands if c['kind'] not in ('hold', 'initial_servo_command')]
    ex, cmds = run(False)
    assert any(c['kind'] == 'arm' for c in cmds)            # unchanged: uninitialised pose -> bootstrap look
    assert 'stationary_bootstrap' not in ex.summary()
    ex, cmds = run(True)
    assert not any(c['kind'] in ('arm', 'mecanum', 'drive') for c in cmds)
    assert ex.jobs_done[-1]['outcome'] == FAIL_REASON
    assert ex.summary()['stationary_bootstrap']['exhausted_at'] is not None


def test_exhausted_bootstrap_keeps_refusing_motion_for_later_jobs():
    """Review #261 finding 1 (reviewer's repro): no dock prior, no fix, then a second look_around."""
    from harness.zone_own_executor import ZoneOwnExecutor
    from tests.test_zone_own_executor_host import FakeHost
    from tests.test_zone_pair_executor import ORDER, CALIB
    from tests.test_zone_own_executor import ROWS_Y
    nodock = {k: v for k, v in DOCK_MAP.items() if k != 'start_dock'}
    exs = {r: ZoneOwnExecutor(r, nodock, CALIB['params'], ORDER, skill_factory=lambda *a, **kw: None,
                              pose_estimate_cls=tuple, search_rows_y=ROWS_Y, judgments=False, job_sim_limit_s=60)
           for r in ('r1', 'r2', 'r3')}
    seen = {}
    def again(h):
        seen['first'] = [j['outcome'] for j in h.robots['r1'].executor.jobs_done]
        h.call('r1', 'look_around')
    host = FakeHost(exs, lambda *a: None, hooks=[(14., again)])
    ex = exs['r1']
    enable_provider(ex.pose)
    assert enable_bootstrap(ex.pose, 0.)['prior_skip_reason'] == 'no_static_dock_prior'
    host.call('r1', 'look_around')
    host.run(28.)
    assert seen['first'] == [FAIL_REASON]
    motion = [c for c in host.robots['r1'].commands if c['kind'] in ('arm', 'mecanum', 'drive')]
    assert motion == [] and not ex.pose.loc.initialized
    assert [j['outcome'] for j in ex.jobs_done] == [FAIL_REASON, FAIL_REASON]
    assert ex.summary()['stationary_bootstrap']['attempts'] == 2


def test_policies_bundle_and_pair_team_opt_in():
    from harness.zone_pair_v6_policy import EXECUTION_BUNDLE_ID, POLICIES, REVISION_POLICIES, pair_policy
    # v75 (v6b) is retired with the historical v6b DRAFT; v77 (PR #256), v78 (PR #257) and v79 (PR #249) keep these policies unchanged.
    # v76 (PR #263) adds only the opt-in v6c flags, which are False for every policy below.
    from harness.zone_study_integration import RETIRED_BUNDLE_IDS
    assert EXECUTION_BUNDLE_ID == 'zone-pair-v76-fixclock-grasp-entry'
    assert {'zone-study-integration-v78-referee-hidden-events',
            'zone-study-integration-v79-masterpi-v3'} <= set(RETIRED_BUNDLE_IDS)
    assert 'zone-pair-v75-dock-prior-bootstrap' in RETIRED_BUNDLE_IDS
    v6c_off = {'exact_fix_clock': False, 'grasp_range_entry': False}
    assert [vars(POLICIES[k]) for k in ('v5h', 'b-only', 'a+b', 'b-boot', 'a+b-boot')] == [
        {'name': 'v5h', 'posterior_relook': False, 'beam_relative': False, 'stationary_bootstrap': False, **v6c_off},
        {'name': 'b-only', 'posterior_relook': True, 'beam_relative': False, 'stationary_bootstrap': False, **v6c_off},
        {'name': 'a+b', 'posterior_relook': True, 'beam_relative': True, 'stationary_bootstrap': False, **v6c_off},
        {'name': 'b-boot', 'posterior_relook': True, 'beam_relative': False, 'stationary_bootstrap': True, **v6c_off},
        {'name': 'a+b-boot', 'posterior_relook': True, 'beam_relative': True, 'stationary_bootstrap': True, **v6c_off}]
    assert pair_policy('b-boot').stationary_bootstrap and pair_policy('a+b-boot').beam_relative
    assert REVISION_POLICIES['v6b'] == ('v5h', 'b-boot', 'a+b-boot')
    from harness.zone_own_executor import ZoneOwnExecutor
    from tests.test_zone_pair_executor import CALIB, ORDER, SHEETS, PairFakeHost
    from tests.test_zone_own_executor import ROWS_Y

    def team(policy):
        exs = {r: ZoneOwnExecutor(r, DOCK_MAP, CALIB['params'], ORDER, skill_factory=lambda *a, **kw: None,
                                  pose_estimate_cls=tuple, search_rows_y=ROWS_Y, judgments=False)
               for r in ('r1', 'r2', 'r3')}
        host = PairFakeHost(exs, lambda *a: None)
        host.contact_record = {'profile': 'cargo_noslip_v1'}
        host.enable_pair_carry(SHEETS, CALIB['params'], policy=policy)
        return exs
    for policy in ('v5h', 'b-only', 'a+b'):
        assert all(bootstrap_state(ex.pose) is None for ex in team(policy).values())
    for policy in ('b-boot', 'a+b-boot'):
        exs = team(policy)
        assert all(bootstrap_state(ex.pose)['prior_applied'] for ex in exs.values())
        assert all(ex.pose.loc.initialized and ex.pose.report(0.).last_fix_t is None for ex in exs.values())


def test_bootstrap_probe_grid_is_setup_only_and_bounded():
    from types import SimpleNamespace
    from scripts import probe_zone_pair_bootstrap as probe
    args = probe.parser().parse_args(['--output', '/tmp/x', '--seeds', '911', '912', '--docks', 'seeded', 'rot1',
                                      '--perturb', '0,0,0', '0.05,-0.05,0.1'])
    grid = list(probe.cases(args))
    assert len(grid) == 8 and grid[-1]['perturb'] == [.05, -.05, .1] and grid[0]['policy'] == 'b-boot'
    with pytest.raises(ValueError):
        probe.parse_perturb('0.3,0,0')
    scene = SimpleNamespace(config={'setup_only': {'spawns': {'r1': [-.65, .55, 0., 0.], 'r2': [-.65, -.85, 0., 0.],
                                                              'r3': [-.65, -2.25, 0., 0.]}}})
    spawns = probe.spawn_setup(scene, 'rot1', [.05, -.05, .1])
    assert [round(spawns[r][1], 3) for r in ('r1', 'r2', 'r3')] == [-.9, -2.3, .55]
    assert spawns['r1'][0] == pytest.approx(-.6) and spawns['r3'][3] == 0. and spawns['r2'][3] == pytest.approx(.1)
    with pytest.raises(SystemExit):
        probe.main(['--output', 'relative/dir'])
