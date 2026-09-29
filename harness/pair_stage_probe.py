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

SCHEMA = 'ugrp.pair_stage_probe.v1'
PROBE_VERSION = '0.5.0'  # 0.2.0: pair_policy axis, align-tolerance boundary set, state checkpoints; 0.3.0: b-v6c; 0.5.0: b-v6d (0.4.x is PR #266: carry legs + setdown)
LABELS = ['stage_probe', 'not_e2e_success', 'dev', '연구 결과 아님']
PARTICIPANTS = ('r1', 'r2')
POLICIES = ('v5h', 'b-only', 'a+b', 'b-v6c', 'b-v6d')   # harness.zone_pair_v6_policy.POLICIES (no A-only policy exists)
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
              'note': 'held throughout (min height), tilt bounded, beam travel within 10 cm of the leg'},
    'setdown': {'max_rest_height_m': .005, 'max_tilt_deg': 3., 'no_jaw_contact': True, 'max_shift_m': .05,
                'note': 'beam back on the floor, level, released, and not dragged'},
}

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


def teacher_cases(stage, *, seeds=(911,), nominal_seeds=(911, 912, 913), setup=None, subset=None, policy='v5h',
                  prior_std=None):
    """Teacher-placed cases with a perturbation grid (placement = GT, prior = static plan)."""
    spec = STAGES[stage]
    if not spec['implemented']:
        raise ValueError(f'stage {stage!r} is not implemented here: {spec["owner"]}')
    setup = copy.deepcopy(setup or BASE_SETUP)
    true_geo = stations(setup['beam_xyyaw'])
    plan_geo = stations(setup['coarse_order_sheet']['beam_xyyaw'])
    key = spec['plan_pose']
    sxy, syaw, ptag, pnote = _prior_std(prior_std)
    # align starts where the approach ended: the planned pre-station (static
    # sheet). Later stages start at the station aligned to the TRUE beam.
    base = plan_geo[key] if stage == 'align' else true_geo[key]
    out = []
    for name, off1, off2 in _grid_offsets(stage):
        if subset is not None and name not in subset:
            continue
        for seed in (nominal_seeds if name == 'nominal' else seeds):
            placement = {'r1': offset_pose(base['r1'], *off1), 'r2': offset_pose(base['r2'], *off2)}
            priors = {r: gaussian_prior(plan_geo[key][r], sxy, syaw,
                                        f'static plan {key} from the coarse order sheet (not GT){pnote}')
                      for r in PARTICIPANTS}
            out.append({'case_id': f'{stage}{_pid(policy)}:teacher:{name}:s{seed}{ptag}', 'stage': stage,
                        'source': 'teacher_grid', 'pair_policy': policy, 'prior_std': prior_std or 'grid',
                        'cell': name, 'seed': seed, 'beam_xyyaw': list(setup['beam_xyyaw']),
                        'coarse_order_sheet': copy.deepcopy(setup['coarse_order_sheet']),
                        'placement_xyyaw': placement, 'r3_xyyaw': None, 'offsets': {'r1': list(off1), 'r2': list(off2)},
                        'prior': priors, 'teacher_held': bool(spec.get('teacher_held')),
                        'staging': 'teacher placement from GT beam geometry (setup only)'})
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
DIAG_PATCHES = {
    'fix_age_round': ('harness.owncam_recovery_v6.RecoveryLocalizer.estimate reports fix_age_s = self.t - t '
                      'unrounded; predict_to stops within 1e-9 s of t, so a fix made at this frame has '
                      'fix_age_s ~ -1e-13 and owncam_time.accepted_fix_checks rejects it (fix_age_valid). '
                      'Patch: round(self.t - t, 3), exactly as harness.owncam_localizer.OwnCamLocalizer.estimate '
                      'computes since_tag_s for v5h.'),
}


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
