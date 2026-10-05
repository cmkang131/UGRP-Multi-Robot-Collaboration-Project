"""v4 (2026-10-05, coordinator decision v4-4): OFFLINE re-fix look with the dock look's eight directions (not physics).

Differences from look_feas2 (v3 ranked top-3, kept for the record):
* candidates = zone_pair_highpose_refix.REFIX_LOOK_PANS (dock order 1500, 1230, 970, 700, 1770, 2030, 2300) filtered
  by the real v98 actor guard wrapped in PairGeometry (plan clear + transition clear, from the pan the camera is on)
  and expected observability > 0 -- what SigmaRefix.align_look_choices does; the recovery_v6 clearance weight is
  NOT applied. The v3 ranking (recovery_v6=True) is also recorded per stop to show the artifact.
* dwell timing of the v3 align re-look: first pan .8 + .6 s, later pans .4 + .6 s (frames every 0.05 s).
* the look stops at the first pan whose report passes the fix-quality part of ``_align_fix_checks``: an accepted fix
  after the look start, std_xy <= 50 mm and < 55 mm (sigma_reserve), std_yaw <= 3 deg and < 2.5 deg.
  All seven pans are still dwelt to show the sigma path (``dwell``); ``first_fix`` is what the controller would use.
Observations: synthetic_observe (expected rows at an ASSUMED true pose + residual model C=.3/S=.7 px) -- pure
static-map geometry; the partner robot and the beam on the floor are NOT occluders. PF: v98 HighPoseSource
(unloaded, LOOK_P20), prior spread SIG0 around the true pose (the sigma the look starts from is an assumption; the
ranking artifact depends on it, the dock list does not)."""
import sys, json, math, tempfile
from pathlib import Path
from types import SimpleNamespace
WT = Path('/Users/changmin/projects/ugrp-wt/carry-ckpt'); sys.path.insert(0, str(WT))
import numpy as np
from _pytest.monkeypatch import MonkeyPatch
from tests import highpose_relook_synthetic as syn
from harness.zone_final_pair_guards import PairGeometry
from harness.zone_pair_align import ranked_look_pans, RELOOK_XY_M, RELOOK_YAW_RAD
from harness.zone_pair_grasp import FIX_STD_XY_M, FIX_STD_YAW_RAD
from harness.zone_pair_highpose_refix import REFIX_LOOK_PANS, REFIX_MAX_LOOK_S
from harness.zone_own_guards import OwnPose
from harness.owncam_drive import LOOK_P20
from scripts.study_owncam_pair_beam import ROLES

PLAN = json.load(open('/Users/changmin/projects/ugrp/outputs/v98-dev-probe-align_to_carry-6727751b/before_door/student_record.json'))['pair'][0]['plan']
route = PLAN['route']; L = .4732
SIG0 = (.05, .05, math.radians(1.7))       # DR spread entering the look (dr_route: 42-66 mm, 1.4-1.9 deg); std_xy 70.7 mm
LOOK = {1: 2000, **LOOK_P20}
STOP_S, FIRST_S, NEXT_S, RETURN_S = .3, .8+.6, .4+.6, .6+.3
mp = MonkeyPatch(); tmp = Path(tempfile.mkdtemp(dir='.'))
cal = syn.admitted_copy(tmp, mp)


def poses(b):
    return {'r1': (b[0]-L, b[1], 0.), 'r2': (b[0]+L, b[1], math.pi)}


def fix_ok(r):
    return (r.last_fix_t is not None and 0 <= r.std_xy_m <= FIX_STD_XY_M and r.std_xy_m < RELOOK_XY_M
            and 0 <= r.std_yaw_rad <= FIX_STD_YAW_RAD and r.std_yaw_rad < RELOOK_YAW_RAD)


def one(true, seed):
    rt = syn.build(cal, seed=seed, true=true)
    out = {}
    for rid in ('r1', 'r2'):
        actor = rt.actors[rid]
        src = rt.providers[rid].provider
        guard = PairGeometry(actor.guard, PLAN['beam_geometry'], ROLES[rid])
        x, y, yaw = true[rid]
        rep = SimpleNamespace(initialized=True, x_m=x, y_m=y, yaw_rad=yaw, std_xy_m=math.hypot(*SIG0[:2]),
                              std_yaw_rad=SIG0[2], t_est=0., last_fix_t=None, fix_age_s=99.)
        servo = {**LOOK, 6: 1500}
        src.on_command({'t': 0., 'kind': 'initial_servo_command', 'pulses': dict(servo)})
        pf = src.loc._pf
        pf.init_gaussian(np.array([x, y, yaw]), np.array(SIG0))
        src.recovery_v6 = True
        v3 = ranked_look_pans(actor.map, rep, servo, guard, src, recovery_v6=True)
        dock = ranked_look_pans(actor.map, rep, servo, guard, src, recovery_v6=False)
        by = {c['pan']: c for c in dock}
        cands = [p for p in REFIX_LOOK_PANS if p in by]
        t, rows, first, cur = 0., [], None, 1500
        for i, pan in enumerate(cands):
            pose = OwnPose.from_report(rep)
            step = guard.plan({**LOOK, 6: cur}, {**LOOK, 6: pan}, [pan], pose, loaded=False, allow_backoff=False)
            dwell = FIRST_S if i == 0 else NEXT_S
            t += .05
            src.on_command({'t': t, 'kind': 'look', 'pan_pulse': pan})
            for k in range(int(round(dwell/.05))):
                t = round(t+.05, 6)
                src.on_frame(t, rgb)
            r = src.report(t)
            cov = np.asarray(src.loc._pf.estimate()['cov'])
            row = {'pan': pan, 'guard_from_prev': step['reason'], 'transition_clear': bool(step.get('transition_clear')),
                   'sx_mm': round(math.sqrt(cov[0, 0])*1e3, 1), 'sy_mm': round(math.sqrt(cov[1, 1])*1e3, 1),
                   't': t, 'std_xy_mm': round(r.std_xy_m*1e3, 1), 'std_yaw_deg': round(math.degrees(r.std_yaw_rad), 2),
                   'err_mm': round(math.hypot(r.x_m-x, r.y_m-y)*1e3, 1), 'last_fix_t': r.last_fix_t,
                   'fix_quality': fix_ok(r)}
            rows.append(row)
            if first is None and row['fix_quality']:
                first = {**row, 'n_pans': i+1, 'look_s': round(STOP_S+FIRST_S+i*NEXT_S+RETURN_S, 2)}
            cur = pan
        out[rid] = {'v3_ranked': [{'pan': c['pan'], 'score': round(float(c['observability_score']), 3)} for c in v3],
                    'v3_no_safe_view': not v3,
                    'dock_candidates': [{'pan': p, 'observability': round(float(by[p]['observability_score']), 1)}
                                        for p in cands],
                    'dwell': rows, 'first_fix': first,
                    'within_look_bound': first is not None and first['look_s'] <= REFIX_MAX_LOOK_S}
    rt.close()
    return out


import cv2
jpeg = syn.IMAGE.read_bytes()
rgb = cv2.cvtColor(cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
res = {'sig0': [SIG0[0], SIG0[1], SIG0[2]], 'pans': list(REFIX_LOOK_PANS), 'max_look_s': REFIX_MAX_LOOK_S, 'stops': {}}
for j in range(1, len(route)-1):
    b = route[j]
    res['stops'][j] = {'beam': b, 'seeds': {s: one(poses(b), s) for s in (0, 1, 2)}}
    for s, o in res['stops'][j]['seeds'].items():
        print(j, b, 'seed', s, {rid: ('v3-empty' if v['v3_no_safe_view'] else 'v3-ok',
                                      None if v['first_fix'] is None else (v['first_fix']['pan'], v['first_fix']['n_pans'],
                                                                           v['first_fix']['std_xy_mm'], v['first_fix']['look_s'])) for rid, v in o.items()})
json.dump(res, open('look_feas3.json', 'w'), default=str, indent=1)
