"""Stage-scoped probes for the own-camera pair-carry controller (issue #221, PR #259 follow-up).

A probe STARTS from a staged physical state, runs ONLY one controller stage and
stops with a pass/fail plus stage metrics. It is a stage probe, not an E2E
success, and its output is labelled so.

Boundary (AGENTS.md "로봇 입력과 학습 경계", teacher exception):

* Staging (robot/beam placement, an optional teacher-held beam) may use ground
  truth. It happens before the controller under test exists or acts.
* The controller under test receives only its allowed inputs: own RGB, the
  static map/calibration/order sheet, its own issued commands and STATUS enums.
  Ultrasonic is not connected in any bundle and stays off here.
* Its localizer starts from a STATED prior (mean + std, AMCL ``initial_pose`` /
  ``initial_cov`` style). A prior is not a fix: it sets no fix time.
* The stage boundary is detected from the controller's own state only. Ground
  truth is read by the eval-only observer and never reaches control.

This module imports no simulator; the physical runner is
``scripts/run_pair_stage_probes.py``.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 'ugrp.pair_stage_probe.v1'
PROBE_VERSION = '0.4.0'  # 0.2.0: pair_policy axis, align-tolerance boundary set, state checkpoints; 0.3.0: b-v6c;
#                          0.4.0: carry legs along the route + setdown at the destination, end/cross-track metrics,
#                                 cause codes, loaded-yaw diagnostic patches
LABELS = ['stage_probe', 'not_e2e_success', 'dev', '연구 결과 아님']
PARTICIPANTS = ('r1', 'r2')
POLICIES = ('v5h', 'b-only', 'a+b', 'b-v6c')   # harness.zone_pair_v6_policy.POLICIES (no A-only policy exists)
ROLE = {'r1': 'end_neg', 'r2': 'end_pos'}

# Stage registry. ``entry`` is the controller state injected at stage start;
# ``exit_hook`` is the controller transition that ends the stage (the robot is
# then held in ``exit_state`` and publishes ``exit_status`` until its partner
# also exits or fails). Budgets are SIM seconds after the stage entry.
STAGES = {
    'bootstrap': {
        'order': 1, 'implemented': False,
        'owner': 'claude/zone-pair-v6-boot (separate agent; not duplicated here)',
        'interface': ('harness.owncam_bootstrap_v6b.enable_bootstrap(provider, now) + '
                      'bootstrap_fix(report); a probe would start at the dock with a stated dock '
                      'prior and pass on an informative settled fix before the first arm motion'),
    },
    'align': {
        'order': 2, 'implemented': True, 'entry': 'align_start', 'exit_hook': '_queue_grasp',
        'exit_state': 'probe_exit_align', 'exit_status': 'aligning', 'budget_s': 110.,
        'plan_pose': 'prestation',
        'description': 'own-RGB beam alignment from the approach-end (pre-station) pose',
    },
    'grasp_lift': {
        'order': 3, 'implemented': True, 'entry': 'pregrasp_standoff', 'exit_hook': '_wait_carry',
        'exit_state': 'probe_exit_lift', 'exit_status': 'lift', 'budget_s': 60.,
        'plan_pose': 'station',
        'description': 'open descent, close rendezvous, grasp confirmation and joint lift from the standoff',
    },
    'carry': {
        'order': 4, 'implemented': True, 'entry': 'wait_carry', 'exit_hook': '_wait_lower',
        'exit_state': 'probe_exit_carry', 'exit_status': 'carry', 'budget_s': 90.,
        'plan_pose': 'station', 'teacher_held': True,
        'description': 'first carry leg with a teacher-lifted beam (door-axis trim + axial leg)',
    },
    'setdown': {
        'order': 5, 'implemented': True, 'entry': 'wait_lower', 'exit_hook': None,
        'exit_state': None, 'exit_status': None, 'budget_s': 60., 'final_states': ('done',),
        'plan_pose': 'station', 'teacher_held': True,
        'description': 'lower, open and back off with a teacher-lifted beam (final segment)',
    },
}

# GT criteria (eval only). Development hypotheses, recorded with every result
# so a different threshold can be re-applied to the raw metrics later.
CRITERIA = {
    'align': {'grip_x_err_m': .017, 'grip_y_err_m': .012, 'yaw_err_rad': .052,
              'note': '1.5x the controller align tolerance (12 mm/8 mm/0.035 rad), x bounded by the '
                      '14.5-18.0 cm grip IK envelope around the 0.162 m target'},
    'grasp_lift': {'min_lift_m': .03, 'max_tilt_deg': 10., 'both_jaws_contact': True,
                   'note': 'both jaws of both robots touch the beam, beam centre >= 3 cm above rest'},
    'carry': {'min_lift_m': .03, 'max_tilt_deg': 10., 'both_jaws_contact': True, 'max_leg_error_m': .10,
              'max_end_error_m': .10,
              'note': 'held throughout (min height), tilt bounded, beam travel within 10 cm of the leg, '
                      'beam end point within 10 cm of the planned route point (0.4.0; includes cross-track)'},
    'setdown': {'max_rest_height_m': .005, 'max_tilt_deg': 3., 'no_jaw_contact': True, 'max_shift_m': .05,
                'note': 'beam back on the floor, level, released, and not dragged'},
}

MAP_ID = 'zone_wide_door_tags_v2_dock_v3'   # the dev map every probe runs on (scripts/run_pair_stage_probes.py MAP_ID)
GRASP_RADIUS_M = .162        # harness.owncam_pair_beam.GRASP_RADIUS_M (controller align target)
PRIOR_STD_XY_M = .06         # stated grid prior (report convention: sqrt(var_x + var_y))
PRIOR_STD_YAW_RAD = .05
STAGING_S = 1.5              # stationary own-frame window before the pair submission
SUBMIT_AFTER_S = .5          # OwnCamTeamHost.run settles physics to 0.5 s first


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


# ------------------------------------------------------------------ geometry (static catalogue)
def stations(beam_xyyaw):
    """Grasp stations and pre-stations for a beam pose (catalogue geometry, no world).

    With the TRUE beam pose this is the teacher's placement; with the coarse
    order-sheet pose it is the controller's static plan.
    """
    from scripts import run_m2_pair as m2
    from sim.zone_cargo import instances, world_grasps

    pose = [float(v) for v in beam_xyyaw]
    item = instances([{'item_id': 'probe_beam', 'kind': 'long_beam', 'pose': pose}])[0]
    grasps = world_grasps(item, pose=pose)
    st = {r: [float(v) for v in grasps[ROLE[r]]['base_xyyaw']] for r in PARTICIPANTS}
    pre = {r: [float(v) for v in m2.pa.prestation(st[r], m2.study.PRESTATION_BACK_M)] for r in PARTICIPANTS}
    grip = {r: [float(v) for v in grasps[ROLE[r]]['grip_xyz']] for r in PARTICIPANTS}
    return {'station': st, 'prestation': pre, 'grip_xyz': grip}


def offset_pose(pose, along, lateral, dyaw):
    """Apply (along heading, left of heading, yaw) offsets in the pose's own frame."""
    x, y, yaw = pose
    c, s = math.cos(yaw), math.sin(yaw)
    return [x + c * along - s * lateral, y + s * along + c * lateral, wrap(yaw + dyaw)]


def grip_errors(robot_xyyaw, grip_xy, station_yaw):
    """Controller-convention align errors from GT: grip in the robot base frame.

    (gx - 0.162, gy, heading error vs the station heading). Eval only.
    """
    x, y, yaw = robot_xyyaw
    dx, dy = grip_xy[0] - x, grip_xy[1] - y
    c, s = math.cos(yaw), math.sin(yaw)
    gx, gy = c * dx + s * dy, -s * dx + c * dy
    return {'grip_x_err_m': gx - GRASP_RADIUS_M, 'grip_y_err_m': gy, 'yaw_err_rad': wrap(yaw - station_yaw),
            'grip_base_m': [gx, gy]}


# ------------------------------------------------------------------ prior
def gaussian_prior(mean_xyyaw, std_xy_m, std_yaw_rad, source):
    mean = [float(v) for v in mean_xyyaw]
    if len(mean) != 3 or not all(math.isfinite(v) for v in mean):
        raise ValueError('prior mean must be finite (x, y, yaw)')
    if not (0 < std_xy_m < 5 and 0 < std_yaw_rad < math.pi):
        raise ValueError('prior std out of range')
    return {'kind': 'gaussian', 'mean_xyyaw': mean, 'std_xy_m': float(std_xy_m),
            'std_yaw_rad': float(std_yaw_rad), 'source': source,
            'convention': 'std_xy_m = sqrt(var_x + var_y) as in PoseReport; per-axis std = std_xy_m / sqrt(2)',
            'is_fix': False}


def seed_gaussian_prior(loc, t, prior):
    """Initialise an ``OwnCamLocalizer`` from a stated prior (ROS amcl ``initial_pose``/``initial_cov``).

    The localizer's own RNG draws the particles. No fix time is set: the first
    accepted own-camera observation is still required for any fix receipt.
    """
    import numpy as np

    if prior.get('kind') != 'gaussian' or prior.get('is_fix') is not False:
        raise ValueError('only a stated gaussian prior (not a fix) is supported')
    loc.predict_to(t)
    n = loc.n
    mean = np.asarray(prior['mean_xyyaw'], float)
    axis = prior['std_xy_m'] / math.sqrt(2.)
    px = np.empty((n, 3))
    px[:, 0] = mean[0] + loc.rng.normal(size=n) * axis
    px[:, 1] = mean[1] + loc.rng.normal(size=n) * axis
    px[:, 2] = (mean[2] + loc.rng.normal(size=n) * prior['std_yaw_rad'] + math.pi) % (2 * math.pi) - math.pi
    loc.px = px
    loc.scale = 1. + loc.rng.normal(size=(n, 3)) * loc.params['motion']['scale_std']
    loc.logw = loc._map_logprior(px)
    loc.initialized = True
    return loc.estimate()


# ------------------------------------------------------------------ cases
BASE_SETUP = {
    # v6-s911 setup: true beam 5 cm off the coarse sheet (dev05-14/v6 geometry).
    'beam_xyyaw': [1.0, .05, 0.],
    'coarse_order_sheet': {'beam_xyyaw': [1.0, 0.0, 0.0], 'grid': {'xy_m': .1, 'yaw_rad': .174533},
                           'source': 'coarse order sheet (setup pose rounded to the sheet grid; static, fixed before the run)'},
}


def _grid_offsets(stage):
    """(name, r1 offset, r2 offset); offsets are (along, lateral, yaw) in the staged pose frame."""
    if stage == 'align':
        d, lat, yaw = .04, .04, math.radians(3.)
        singles = [('along+', (d, 0, 0)), ('along-', (-d, 0, 0)), ('lat+', (0, lat, 0)), ('lat-', (0, -lat, 0)),
                   ('yaw+', (0, 0, yaw)), ('yaw-', (0, 0, -yaw))]
        corners = [('corner++', (d, lat, yaw)), ('corner--', (-d, -lat, -yaw))]
    elif stage in ('grasp_lift', 'carry', 'setdown'):
        # v7 DESIGN axis D: align-tolerance boundary (12 mm standoff, 8 mm width, 0.035 rad).
        d, lat, yaw = .012, .008, .035
        singles = [('along+', (d, 0, 0)), ('along-', (-d, 0, 0)), ('lat+', (0, lat, 0)), ('lat-', (0, -lat, 0)),
                   ('yaw+', (0, 0, yaw)), ('yaw-', (0, 0, -yaw))]
        corners = [('corner++', (d, lat, yaw)), ('corner--', (-d, -lat, -yaw))]
    else:
        raise ValueError(f'no grid for stage {stage!r}')
    rows = [('nominal', (0, 0, 0), (0, 0, 0))]
    for name, off in singles + corners:
        rows.append((name + '/same', off, off))
        rows.append((name + '/opp', off, tuple(-v for v in off)))
    return rows


def _pid(policy):
    if policy not in POLICIES:
        raise ValueError(f'unknown pair policy {policy!r}')
    return '' if policy == 'v5h' else '@' + policy


E2E_MATCHED_PRIOR = {'std_xy_m': .03, 'std_yaw_rad': .012,
                     'why': ('std of the robots\' own PoseReports at align entry in the v5h E2E runs '
                             '(v6-s911-v5h, v6-s912-v5h: 0.026-0.033 m, 0.009-0.012 rad, fix age 0 s)')}


def _prior_std(prior_std):
    """(std_xy, std_yaw, case-id tag, source note). Default = the grid1 prior."""
    if prior_std in (None, 'grid'):
        return PRIOR_STD_XY_M, PRIOR_STD_YAW_RAD, '', ''
    if prior_std == 'e2e':
        return E2E_MATCHED_PRIOR['std_xy_m'], E2E_MATCHED_PRIOR['std_yaw_rad'], ':pE2E', '; std ' + E2E_MATCHED_PRIOR['why']
    raise ValueError(f'unknown prior std {prior_std!r}')


def plan_route(sheet, *, map_id=MAP_ID, target='B'):
    """The controller's own static route for a coarse order sheet (harness.zone_pair_executor.make_plan).

    Pure static geometry: the map JSON and the sheet, no world. 9 points / 8 legs for the dev map:
    legs 0-2 axial (leg 1 crosses the 0.5 m door at x=2.2), legs 3-5 lateral, legs 6-7 axial into the zone.
    """
    from harness.zone_pair_executor import make_plan
    static = json.loads((ROOT / 'maps' / 'zones' / f'{map_id}.json').read_text())
    return [[float(v) for v in p] for p in make_plan(static, sheet, target)['route']]


def leg_index(stage, leg, n_points):
    """Route-point index a carry/setdown case starts at. carry: leg k starts at route[k] (default 0);
    setdown: None = legacy (staged at the pickup), 'end'/last index = the final segment at the destination."""
    if stage == 'carry':
        k = 0 if leg is None else int(leg)
        if not 0 <= k <= n_points - 2:
            raise ValueError(f'carry leg {k} outside 0..{n_points - 2}')
        return k
    if stage == 'setdown':
        if leg is None:
            return None
        k = n_points - 1 if leg == 'end' else int(leg)
        if k != n_points - 1:
            raise ValueError('setdown is defined for the final segment (leg end) only')
        return k
    if leg is not None:
        raise ValueError(f'stage {stage!r} has no route legs')
    return None


def shifted_pose(pose, route, k):
    """A pose translated by the route displacement route[0] -> route[k] (yaw unchanged)."""
    return [float(pose[0]) + route[k][0] - route[0][0], float(pose[1]) + route[k][1] - route[0][1], float(pose[2])]


def teacher_cases(stage, *, seeds=(911,), nominal_seeds=(911, 912, 913), setup=None, subset=None, policy='v5h',
                  prior_std=None, leg=None):
    """Teacher-placed cases with a perturbation grid (placement = GT, prior = static plan).

    ``leg`` (carry/setdown only, 0.4.0): carry leg k starts with the beam lifted at route point k and the
    controller segment set to k; setdown 'end' starts at the last route point with the final segment. The
    true beam and the static-sheet prior are both translated by route[0] -> route[k], so leg 0 is exactly
    the 0.3.0 case and the 5 cm true-beam-vs-sheet offset of BASE_SETUP is kept on every leg.
    """
    spec = STAGES[stage]
    if not spec['implemented']:
        raise ValueError(f'stage {stage!r} is not implemented here: {spec["owner"]}')
    setup = copy.deepcopy(setup or BASE_SETUP)
    route, k = None, None
    if stage in ('carry', 'setdown'):
        route = plan_route(setup['coarse_order_sheet'])
        k = leg_index(stage, leg, len(route))
    else:
        leg_index(stage, leg, 0)
    true_beam, plan_beam = list(setup['beam_xyyaw']), list(setup['coarse_order_sheet']['beam_xyyaw'])
    if k:
        true_beam, plan_beam = shifted_pose(true_beam, route, k), shifted_pose(plan_beam, route, k)
    true_geo = stations(true_beam)
    plan_geo = stations(plan_beam)
    key = spec['plan_pose']
    sxy, syaw, ptag, pnote = _prior_std(prior_std)
    # align starts where the approach ended: the planned pre-station (static
    # sheet). Later stages start at the station aligned to the TRUE beam.
    base = plan_geo[key] if stage == 'align' else true_geo[key]
    ltag = '' if not k else (':Lend' if stage == 'setdown' else f':L{k}')
    out = []
    for name, off1, off2 in _grid_offsets(stage):
        if subset is not None and name not in subset:
            continue
        for seed in (nominal_seeds if name == 'nominal' else seeds):
            placement = {'r1': offset_pose(base['r1'], *off1), 'r2': offset_pose(base['r2'], *off2)}
            priors = {r: gaussian_prior(plan_geo[key][r], sxy, syaw,
                                        f'static plan {key} from the coarse order sheet (not GT){pnote}')
                      for r in PARTICIPANTS}
            case = {'case_id': f'{stage}{_pid(policy)}:teacher:{name}:s{seed}{ptag}{ltag}', 'stage': stage,
                    'source': 'teacher_grid', 'pair_policy': policy, 'prior_std': prior_std or 'grid',
                    'cell': name, 'seed': seed, 'beam_xyyaw': list(true_beam),
                    'coarse_order_sheet': copy.deepcopy(setup['coarse_order_sheet']),
                    'placement_xyyaw': placement, 'r3_xyyaw': None, 'offsets': {'r1': list(off1), 'r2': list(off2)},
                    'prior': priors, 'teacher_held': bool(spec.get('teacher_held')),
                    'staging': 'teacher placement from GT beam geometry (setup only)'}
            if route is not None and stage == 'setdown' and k is not None:
                # Staging only: the destination view can fail the submit-time image admission (dark floor), and a
                # real setdown never re-submits there. The real verdict is recorded; the endpoint's own per-step
                # image check (INVALID_OWN_IMAGE) stays active and is judged.
                case.update(staging_bypass=['admission_image_valid'],
                            staging_bypass_note='submit-time admission image_valid forced true for the stage-entry '
                                                'submit only; real verdict recorded in result.admission_image_valid_real')
            if route is not None:
                case.update(leg=k, route=[list(p) for p in route],
                            route_note='controller static route (make_plan) for the coarse sheet; staged at route point '
                                       + ('0 (legacy setdown at the pickup)' if k is None else str(k)))
            out.append(case)
    return out


ALIGN_TOL = {'x_m': .012, 'y_m': .008, 'yaw_rad': .035}   # harness.owncam_pair_beam ALIGN_TOL_X_M / ALIGN_TOL_M / ALIGN_TOL_RAD


def boundary_offsets():
    """(name, (ex, ey, eyaw)) in the controller's own align-error convention (grip x - 0.162, grip y, axis heading)."""
    tx, ty, ta = ALIGN_TOL['x_m'], ALIGN_TOL['y_m'], ALIGN_TOL['yaw_rad']
    rows = [('ex%+.0fmm' % (v * 1000), (v, 0., 0.)) for v in (-tx, -2 * tx / 3, -tx / 3, 0., tx / 3, 2 * tx / 3, tx)]
    rows += [('ey%+.0fmm' % (v * 1000), (0., v, 0.)) for v in (-ty, -ty / 2, ty / 2, ty)]
    rows += [('eyaw%+.4frad' % v, (0., 0., v)) for v in (-ta, -ta / 2, ta / 2, ta)]
    rows += [('corner%s%s%s' % ('+' if sx > 0 else '-', '+' if sy > 0 else '-', '+' if sa > 0 else '-'),
              (sx * tx, sy * ty, sa * ta)) for sx in (-1, 1) for sy in (-1, 1) for sa in (-1, 1)]
    return rows


def pose_for_align_error(grip_xy, station_yaw, ex, ey, eyaw):
    """GT base pose whose TRUE grip lies at (0.162+ex, ey) in its base frame and whose beam axis
    heading error is eyaw (controller convention: axis heading = station yaw - robot yaw)."""
    yaw = wrap(station_yaw - eyaw)
    gx, gy = GRASP_RADIUS_M + ex, ey
    c, s = math.cos(yaw), math.sin(yaw)
    return [grip_xy[0] - (c * gx - s * gy), grip_xy[1] - (s * gx + c * gy), yaw]


def boundary_cases(stage='grasp_lift', *, policy='v5h', seed=911, setup=None, subset=None, prior_std=None):
    """Stage 3 entries exactly at the controller's align-done tolerance boundary (both robots same
    offset in their own frames). Placement = GT/teacher (setup only); prior = static sheet station."""
    if stage != 'grasp_lift':
        raise ValueError('boundary set is defined for grasp_lift')
    setup = copy.deepcopy(setup or BASE_SETUP)
    true_geo = stations(setup['beam_xyyaw'])
    plan_geo = stations(setup['coarse_order_sheet']['beam_xyyaw'])
    out = []
    for name, (ex, ey, ea) in boundary_offsets():
        if subset is not None and name not in subset:
            continue
        placement = {r: pose_for_align_error(true_geo['grip_xyz'][r][:2], true_geo['station'][r][2], ex, ey, ea)
                     for r in PARTICIPANTS}
        sxy, syaw, ptag, pnote = _prior_std(prior_std)
        priors = {r: gaussian_prior(plan_geo['station'][r], sxy, syaw,
                                    f'static plan station from the coarse order sheet (not GT){pnote}') for r in PARTICIPANTS}
        out.append({'case_id': f'{stage}{_pid(policy)}:boundary:{name}:s{seed}{ptag}', 'stage': stage,
                    'source': 'tolerance_boundary', 'pair_policy': policy, 'cell': name, 'seed': seed,
                    'prior_std': prior_std or 'grid',
                    'beam_xyyaw': list(setup['beam_xyyaw']), 'coarse_order_sheet': copy.deepcopy(setup['coarse_order_sheet']),
                    'placement_xyyaw': placement, 'r3_xyyaw': None,
                    'offsets': {r: [ex, ey, ea] for r in PARTICIPANTS}, 'offset_frame': 'controller align error (ex, ey, eyaw)',
                    'prior': priors, 'teacher_held': False,
                    'staging': 'GT placement at the controller align-done tolerance boundary (setup only)'})
    return out


# Probe-only DIAGNOSTIC patches of the controller under test. A case that uses one is NOT the
# registered v6 controller; its result answers "what does the next failure look like once this
# defect is removed", never "does v6 work". The controller source on main is not changed.
LOADED_YAW_GATE_DIAG_DEG = (12., 10.)   # (high, low) for loaded_yaw_gate_wide; the registered loaded gate is (3.0, 2.5)
DIAG_PATCHES = {
    'fix_age_round': ('harness.owncam_recovery_v6.RecoveryLocalizer.estimate reports fix_age_s = self.t - t '
                      'unrounded; predict_to stops within 1e-9 s of t, so a fix made at this frame has '
                      'fix_age_s ~ -1e-13 and owncam_time.accepted_fix_checks rejects it (fix_age_valid). '
                      'Patch: round(self.t - t, 3), exactly as harness.owncam_localizer.OwnCamLocalizer.estimate '
                      'computes since_tag_s for v5h.'),
    'loaded_yaw_gate_wide': ('0.4.0. harness.zone_own_guards.GATE_LOADED (and every module that imported the name) '
                             'uses high_yaw/low_yaw = 12/10 deg instead of 3.0/2.5 deg. Everything else, including '
                             'the xy gate and the dwell times, is unchanged. Answers "what fails next once the '
                             'loaded yaw gate is not the first blocker", never "does v6c carry".'),
    'pf_rest_no_abs_noise': ('0.4.0. harness.owncam_localizer.OwnCamLocalizer._motion_params returns noise_abs = 0 '
                             'while the robot is at rest (no live command and |vel| < 1 mm/s or rad/s). The registered '
                             'model adds noise_abs = [0.0149, 0.0038, 0.0976] (yaw in rad/s) on EVERY 0.05 s step, so a '
                             'stationary robot without a fix diffuses (yaw sigma ~ 0.0218 rad/sqrt(s)). Motion-time '
                             'noise is unchanged. Confirms the rest-diffusion cause; not a proposed model.'),
    'rest_noise_off_and_gate_wide': '0.4.0. both patches above (pf_rest_no_abs_noise + loaded_yaw_gate_wide).',
}
DIAG_COMPONENTS = {'rest_noise_off_and_gate_wide': ('pf_rest_no_abs_noise', 'loaded_yaw_gate_wide')}


def apply_diag_patch(cases, name):
    if name is None:
        return cases
    if name not in DIAG_PATCHES:
        raise ValueError(f'unknown diagnostic patch {name!r}')
    return [{**c, 'case_id': c['case_id'] + ':diag-' + name, 'diag_patch': name,
             'diag_patch_note': DIAG_PATCHES[name]} for c in cases]


GLOBAL_ANCHOR_MAX_AGE_S = 30.   # harness.zone_pair_global.GlobalEnvelope.pose: anchor usable for 30 s


def staged_global_anchor(case):
    """Staged v6 global-safety anchor (a+b only; b-only/v5h do not use the global envelope).

    In an E2E run the approach supplies it: the last informative absolute fix
    (v5h E2E align entries: fix age 0.0 s, std 0.026-0.033 m / 0.009-0.012 rad).
    A staged stage entry has no approach, so the anchor is STATED like the PF
    prior: teacher/boundary cases use the stated prior (mean, std) as a fix of
    age 0; E2E checkpoints use the robot's own recorded report and fix age.
    Never GT. None when the recorded fix is older than the anchor lifetime.
    """
    ages = (case.get('e2e_source') or {}).get('own_fix_age_s') or {}
    out = {}
    for rid in PARTICIPANTS:
        p = case['prior'][rid]
        age = ages.get(rid, 0.) if case['source'] == 'e2e_checkpoint' else 0.
        if age is None or age > GLOBAL_ANCHOR_MAX_AGE_S:
            out[rid] = None
            continue
        out[rid] = {'xyyaw': list(p['mean_xyyaw']), 'std_xy_m': p['std_xy_m'], 'std_yaw_rad': p['std_yaw_rad'],
                    'age_s': float(age), 'source': 'stated anchor = ' + p['source'] + ' (not GT)'}
    return out


def _read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line]


def e2e_checkpoint(run_dir, stage, *, seeds=None, policy='v5h'):
    """Stage entry reconstructed from a real E2E run at the moment the stage began.

    Physical placement uses the run's eval-only GT trace (setup only). The
    prior is the robot's OWN recorded pose report at that moment (mean + std),
    never the GT pose. Returns None when both robots never entered the stage.
    """
    run_dir = Path(run_dir)
    spec = STAGES[stage]
    events = _read_jsonl(run_dir / 'events.jsonl')
    entered = {}
    for e in events:
        if e['event'] == 'pair_progress' and e['detail'].get('phase') == spec['entry'] and e['robot_id'] in PARTICIPANTS:
            entered.setdefault(e['robot_id'], e['sim_s'])
    if set(entered) != set(PARTICIPANTS):
        return {'unavailable': True, 'run': run_dir.name, 'stage': stage,
                'reason': f'not both robots entered {spec["entry"]}: {sorted(entered)}'}
    t0 = max(entered.values())
    row = None
    for r in _read_jsonl(run_dir / 'eval_only/trace.jsonl'):
        if r['t'] <= t0 + 1e-6:
            row = r
        else:
            break
    corners = row['beam_corners']
    beam_yaw = math.atan2(corners[4][1] - corners[0][1], corners[4][0] - corners[0][0])
    frames = json.loads((run_dir / 'robots.json').read_text())
    prereg = json.loads((run_dir / 'prereg.json').read_text())
    manifest = json.loads((run_dir / 'manifest.json').read_text())
    run = next(r for r in prereg['runs'] if r['id'] == manifest['run_id'])
    priors, servo, fix_age = {}, {}, {}
    for rid in PARTICIPANTS:
        f = [x for x in frames[rid]['frames'] if x['t'] <= t0 + 1e-6][-1]
        rep = f['report']
        priors[rid] = gaussian_prior(rep['xyyaw'], rep['std_xy_m'], rep['std_yaw_rad'],
                                     f'own recorded PoseReport at t={f["t"]} frame {f["frame_id"]} (not GT)')
        servo[rid] = f['commanded_servo']
        lf = rep.get('last_fix_t')
        fix_age[rid] = None if lf is None else max(0., float(f['t']) - float(lf))
    out = []
    for seed in (seeds or (manifest['seed'],)):
        out.append({'case_id': f'{stage}{_pid(policy)}:e2e:{run_dir.name}:s{seed}', 'stage': stage, 'source': 'e2e_checkpoint',
                    'pair_policy': policy,
                    'cell': run_dir.name, 'seed': seed,
                    'beam_xyyaw': [row['beam_xyz'][0], row['beam_xyz'][1], beam_yaw],
                    'coarse_order_sheet': run['coarse_order_sheet'],
                    'placement_xyyaw': {r: list(row['robots'][r]) for r in PARTICIPANTS},
                    'r3_xyyaw': list(row['robots']['r3']), 'offsets': None, 'prior': priors,
                    'teacher_held': False, 'e2e_commanded_servo': servo,
                    'e2e_source': {'run_dir': str(run_dir), 'entry_state': spec['entry'], 'entry_sim_s': t0,
                                   'trace_row_t': row['t'], 'states_at_entry': row['states'],
                                   'own_fix_age_s': fix_age,
                                   'manifest_sha256': sha_file(run_dir / 'manifest.json'),
                                   'trace_sha256': sha_file(run_dir / 'eval_only/trace.jsonl'),
                                   'robots_sha256': sha_file(run_dir / 'robots.json'),
                                   'events_sha256': sha_file(run_dir / 'events.jsonl')},
                    'staging': 'placement from the E2E eval-only GT trace at stage entry (setup only)'})
    return out


# ------------------------------------------------------------------ evaluation
def evaluate(stage, record):
    """Pass/fail from the controller exits (own states) AND eval-only GT metrics."""
    crit = CRITERIA[stage]
    exits = record.get('exits', {})
    failure = record.get('first_failure')
    both = all(r in exits for r in PARTICIPANTS)
    checks = {'controller_exit_both': both}
    metrics = {}
    if stage == 'align':
        for rid in PARTICIPANTS:
            gt = exits.get(rid, {}).get('gt')
            if gt is None:
                continue
            e = gt['grip_errors']
            metrics[rid] = e
            checks[f'{rid}_grip_x'] = abs(e['grip_x_err_m']) <= crit['grip_x_err_m']
            checks[f'{rid}_grip_y'] = abs(e['grip_y_err_m']) <= crit['grip_y_err_m']
            checks[f'{rid}_yaw'] = abs(e['yaw_err_rad']) <= crit['yaw_err_rad']
    elif stage in ('grasp_lift', 'carry'):
        gt = record.get('gt_at_exit')
        if gt is not None:
            metrics = {'lift_m': gt['lift_m'], 'tilt_deg': gt['tilt_deg'], 'jaws': gt['jaws'],
                       'max_tilt_deg_stage': record.get('max_tilt_deg'), 'min_lift_m_after_lift': record.get('min_lift_after_first_lift_m')}
            checks['lift'] = gt['lift_m'] >= crit['min_lift_m']
            checks['tilt'] = gt['tilt_deg'] <= crit['max_tilt_deg']
            checks['both_jaws_both_robots'] = all(all(gt['jaws'][r]) for r in PARTICIPANTS)
            if stage == 'carry':
                travel = record.get('beam_travel_m')
                planned = record.get('planned_leg_m')
                metrics.update(beam_travel_m=travel, planned_leg_m=planned)
                checks['held_throughout'] = (record.get('min_lift_after_first_lift_m') or 0) >= crit['min_lift_m']
                checks['leg_error'] = (travel is not None and planned is not None
                                       and abs(travel - planned) <= crit['max_leg_error_m'])
                if record.get('end_error_m') is not None:   # 0.4.0: distance to the planned route point
                    metrics.update(end_error_m=record['end_error_m'], cross_track_m=record.get('cross_track_m'),
                                   yaw_drift_deg=record.get('yaw_drift_deg'))
                    checks['end_error'] = record['end_error_m'] <= crit['max_end_error_m']
    elif stage == 'setdown':
        gt = record.get('gt_at_exit')
        if gt is not None:
            metrics = {'lift_m': gt['lift_m'], 'tilt_deg': gt['tilt_deg'], 'jaws': gt['jaws'],
                       'shift_m': record.get('beam_shift_m')}
            checks['rest'] = gt['lift_m'] <= crit['max_rest_height_m']
            checks['tilt'] = gt['tilt_deg'] <= crit['max_tilt_deg']
            checks['released'] = not any(any(gt['jaws'][r]) for r in PARTICIPANTS)
            checks['shift'] = (record.get('beam_shift_m') or 0.) <= crit['max_shift_m']
    passed = bool(both and all(checks.values()) and failure is None)
    if record.get('entry_error'):
        category = 'ENTRY:' + record['entry_error']
    elif failure is not None:
        category = failure['reason']
    elif not both:
        category = 'STAGE_BUDGET_EXHAUSTED'
    elif not passed:
        category = 'GT_CRITERIA:' + ','.join(sorted(k for k, v in checks.items() if not v))
    else:
        category = 'PASS'
    return {'passed': passed, 'category': category, 'checks': checks, 'metrics': metrics,
            'criteria': crit, 'labels': LABELS}


# ------------------------------------------------------------------ failure cause codes (0.4.0)
GATE_LOADED_HIGH = {'std_xy_m': .07, 'std_yaw_rad': math.radians(3.)}   # harness.zone_own_guards.GATE_LOADED (registered)
CAUSES = {
    'PASS': 'stage passed',
    'SELF_POSE_UNCERTAIN': 'own pose std above the loaded gate (or no usable estimate) -> controller abort; see sub',
    'ENVELOPE_BLOCKED': 'global/sweep envelope certificate not clear for the (uncertain) own pose',
    'MOTION_STALL': 'PAIR_blocked: no progress toward the route point although the pose is trusted',
    'COLLISION_GUARD': 'command guard refused an arm/base command (swept volume vs map/partner keepout)',
    'BEAM_PARTNER_RECOGNITION': 'own-RGB beam/partner check failed (grip not seen, beam inconsistent, unsafe pregrasp)',
    'PARTNER_ABORT': 'the partner aborted first (a consequence; the partner\'s own reason is the root cause)',
    'LOAD_DROP': 'the beam was lost from the jaws or lift below the criterion without a controller failure',
    'MOTION_ERROR': 'controller finished but the beam ended off the planned route point (dead-reckoning error)',
    'TILT': 'beam tilt above the criterion',
    'NOT_LOWERED': 'setdown: beam not back on the floor', 'NOT_RELEASED': 'setdown: jaws still touch the beam',
    'DRAGGED': 'setdown: beam moved more than the criterion while set down',
    'STAGE_TIMEOUT_NO_EXIT': 'no controller failure and no stage exit within the stage budget',
    'OWN_IMAGE_INVALID': 'the endpoint\'s per-step own-image check failed (dark-pixel share >= 25 % / low contrast)',
    'ENTRY_ERROR': 'staged entry rejected (admission / entry check)', 'HOST_ERROR': 'simulator/host exception',
    'UNCLASSIFIED': 'reason not in the map (see category)'}
FAILURE_TO_CAUSE = {
    'POSE_UNCERTAIN': 'SELF_POSE_UNCERTAIN', 'POSE_UNCERTAIN_PROGRESS': 'SELF_POSE_UNCERTAIN',
    'DOOR_POSE_NOT_LOCALIZED': 'SELF_POSE_UNCERTAIN',
    'GLOBAL_ENVELOPE_BLOCKED': 'ENVELOPE_BLOCKED', 'PAIR_blocked': 'MOTION_STALL',
    'PAIR_COLLISION_GUARD': 'COLLISION_GUARD', 'INVALID_OWN_IMAGE': 'OWN_IMAGE_INVALID',
    'GRIP_NOT_SEEN': 'BEAM_PARTNER_RECOGNITION', 'APPROACH_INCONSISTENT_WITH_BEAM': 'BEAM_PARTNER_RECOGNITION',
    'PREGRASP_BEAM_UNSAFE': 'BEAM_PARTNER_RECOGNITION', 'PAIR_RELOOK_WHILE_GRIPPED': 'BEAM_PARTNER_RECOGNITION',
    'LOAD_NOT_HELD_AFTER_LIFT': 'LOAD_DROP', 'PARTNER_ABORT': 'PARTNER_ABORT',
    'PARTNER_ABORT_AFTER_OWN_EXIT': 'PARTNER_ABORT'}
CHECK_TO_CAUSE = {'lift': 'LOAD_DROP', 'held_throughout': 'LOAD_DROP', 'both_jaws_both_robots': 'LOAD_DROP',
                  'tilt': 'TILT', 'leg_error': 'MOTION_ERROR', 'end_error': 'MOTION_ERROR',
                  'rest': 'NOT_LOWERED', 'released': 'NOT_RELEASED', 'shift': 'DRAGGED'}
CONTACT_KINDS = ('wall', 'cargo_wall', 'peer_robot')   # eval-only host contact kinds that count as a collision


def pose_uncertainty_sub(own):
    """Which quantity crossed the loaded gate, from the failing robot's OWN report (a PoseReport dict)."""
    if not own:
        return 'no_report'
    std_xy, std_yaw = own.get('std_xy_m'), own.get('std_yaw_rad')
    parts = []
    if std_yaw is not None and std_yaw > GATE_LOADED_HIGH['std_yaw_rad']:
        parts.append('yaw')
    if std_xy is not None and std_xy > GATE_LOADED_HIGH['std_xy_m']:
        parts.append('xy')
    if not parts:
        return 'gate_not_ok_dwell_or_hysteresis'
    return '+'.join(parts)


def classify_cause(stage, ev, record, diag=None):
    """One cause code per row. ``ev`` = evaluate(); ``record`` = its input; ``diag`` (optional) = the
    runner's own-report / eval-only contact summary. Pure and deterministic; labelled, not a proof of cause."""
    diag = diag or {}
    contacts = {k: v for k, v in (diag.get('contacts') or {}).items() if k in CONTACT_KINDS and v}
    out = {'code': None, 'sub': None, 'contacts_in_stage': contacts, 'reason': record.get('first_failure')}
    if ev['passed']:
        out['code'] = 'PASS'
        return out
    cat = ev['category']
    failure = record.get('first_failure')
    if cat.startswith('HOST_ERROR'):
        out['code'] = 'HOST_ERROR'
    elif cat.startswith('ENTRY:'):
        out['code'] = 'ENTRY_ERROR'
        out['sub'] = cat[len('ENTRY:'):]
    elif failure is not None:
        reason = failure['reason']
        out['code'] = FAILURE_TO_CAUSE.get(reason) or ('PARTNER_ABORT' if str(reason).startswith('PARTNER') else 'UNCLASSIFIED')
        if out['code'] == 'SELF_POSE_UNCERTAIN':
            rid = failure.get('robot_id')
            out['sub'] = pose_uncertainty_sub((diag.get('own_at_failure') or {}).get(rid))
    elif not ev['checks'].get('controller_exit_both', True):
        out['code'] = 'STAGE_TIMEOUT_NO_EXIT'
    else:
        bad = [k for k, v in ev['checks'].items() if not v]
        order = ['lift', 'held_throughout', 'both_jaws_both_robots', 'rest', 'released', 'end_error', 'leg_error', 'shift', 'tilt']
        bad.sort(key=lambda k: order.index(k) if k in order else len(order))
        out['code'] = CHECK_TO_CAUSE.get(bad[0], 'UNCLASSIFIED') if bad else 'UNCLASSIFIED'
        out['sub'] = ','.join(bad)
    return out


def summarize(rows):
    """Per-stage and per-source pass rates plus the failure histogram."""
    out = {'schema': SCHEMA, 'labels': LABELS, 'stages': {}}
    for stage in sorted({r['stage'] for r in rows}, key=lambda s: STAGES[s]['order']):
        rs = [r for r in rows if r['stage'] == stage]
        by_source = {}
        for src in sorted({r['source'] for r in rs}):
            sub = [r for r in rs if r['source'] == src]
            by_source[src] = {'cases': len(sub), 'passed': sum(r['passed'] for r in sub)}
        walls = sorted(r['wall_s'] for r in rs if r.get('wall_s') is not None)
        sims = sorted(r['stage_sim_s'] for r in rs if r.get('stage_sim_s') is not None)
        out['stages'][stage] = {
            'cases': len(rs), 'passed': sum(r['passed'] for r in rs),
            'pass_rate': round(sum(r['passed'] for r in rs) / len(rs), 4) if rs else None,
            'by_source': by_source,
            'failures': dict(Counter(r['category'] for r in rs if not r['passed']).most_common()),
            'causes': dict(Counter(r['cause'] for r in rs if not r['passed'] and r.get('cause')).most_common()),
            'by_leg': {str(leg): {'cases': len(q), 'passed': sum(r['passed'] for r in q)}
                       for leg in sorted({r.get('leg') for r in rs if r.get('leg') is not None})
                       for q in [[r for r in rs if r.get('leg') == leg]]},
            'wall_s_median': walls[len(walls) // 2] if walls else None,
            'wall_s_max': walls[-1] if walls else None,
            'stage_sim_s_median': sims[len(sims) // 2] if sims else None,
        }
        by_policy = {}
        for pol in sorted({r.get('pair_policy', 'v5h') for r in rs}):
            sub = [r for r in rs if r.get('pair_policy', 'v5h') == pol]
            by_policy[pol] = {
                'cases': len(sub), 'passed': sum(r['passed'] for r in sub),
                'by_source': {src: {'cases': len(q), 'passed': sum(r['passed'] for r in q)}
                              for src in sorted({r['source'] for r in sub})
                              for q in [[r for r in sub if r['source'] == src]]},
                'failures': dict(Counter(r['category'] for r in sub if not r['passed']).most_common())}
        out['stages'][stage]['by_policy'] = by_policy
    return out
