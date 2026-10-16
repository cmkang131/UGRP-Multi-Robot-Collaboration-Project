"""OFFLINE look feasibility at each route stop after a set-down (not physics).
Guard: the real v98 actor guard wrapped in the pair PairGeometry (what align_look_choices uses), LOOK_P20 pans
from PREGRASP_PANS_V2, ranked by ranked_look_pans(recovery_v6=True). Observations: synthetic_observe (expected
rows at an ASSUMED true pose + residual model C=.3/S=.7 px) -- pure static-map geometry; the partner robot and the
beam lying on the floor are NOT modelled as occluders. PF: v98 HighPoseSource (unloaded, LOOK_P20)."""
import sys, json, math, tempfile
from pathlib import Path
from types import SimpleNamespace
WT = Path('/Users/changmin/projects/ugrp-wt/carry-ckpt'); sys.path.insert(0, str(WT))
import numpy as np
from _pytest.monkeypatch import MonkeyPatch
from tests import highpose_relook_synthetic as syn
from harness.zone_final_pair_guards import PairGeometry
from harness.zone_pair_align import ranked_look_pans, MAX_DIRECTIONS
from harness.zone_own_guards import OwnPose
from harness.owncam_drive import LOOK_P20
from scripts.study_owncam_pair_beam import ROLES
import cv2

PLAN = json.load(open('/Users/changmin/projects/ugrp/outputs/v98-dev-probe-align_to_carry-6727751b/before_door/student_record.json'))['pair'][0]['plan']
route = PLAN['route']; L = .4732
mp = MonkeyPatch(); tmp = Path(tempfile.mkdtemp(dir='.'))
cal = syn.admitted_copy(tmp, mp)
jpeg = syn.IMAGE.read_bytes()
rgb = cv2.cvtColor(cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
SIG0 = (.05, .05, math.radians(1.7))       # DR spread entering the look (dr_route: 42-66 mm, 1.4-1.9 deg)
LOOK = {1: 2000, **LOOK_P20}

def poses(b):
    return {'r1': (b[0]-L, b[1], 0.), 'r2': (b[0]+L, b[1], math.pi)}

FORCED = [{'pan': p, 'observability_score': 0.} for p in (1500, 1230, 1770)]

def one(true, seed):
    rt = syn.build(cal, seed=seed, true=true)
    out = {}
    for rid in ('r1', 'r2'):
        actor = rt.actors[rid]
        src = rt.providers[rid].provider          # HighPoseSource (inside DelayedPoseSource)
        guard = PairGeometry(actor.guard, PLAN['beam_geometry'], ROLES[rid])
        x, y, yaw = true[rid]
        rep = SimpleNamespace(initialized=True, x_m=x, y_m=y, yaw_rad=yaw, std_xy_m=math.hypot(*SIG0[:2]),
                              std_yaw_rad=SIG0[2], t_est=0., last_fix_t=None, fix_age_s=99.)
        servo = {**LOOK, 6: 1500}
        # provider at the stop: unloaded, DR prior around the true pose
        src.on_command({'t': 0., 'kind': 'initial_servo_command', 'pulses': dict(servo)})
        pf = src.loc._pf
        pf.init_gaussian(np.array([x, y, yaw]), np.array(SIG0))   # offline DR prior (assumed), PF clock 0
        src.recovery_v6 = True
        cands = ranked_look_pans(actor.map, rep, servo, guard, src, recovery_v6=True)
        allp = []
        from scripts.run_m2_pair import PREGRASP_PANS_V2
        for pan in dict.fromkeys(PREGRASP_PANS_V2):
            target = {**LOOK, 6: pan}
            plan = guard.plan(servo, target, [pan], OwnPose.from_report(rep), loaded=False, allow_backoff=False)
            allp.append({'pan': pan, 'reason': plan['reason'], 'transition_clear': bool(plan.get('transition_clear'))})
        # dwell on the top MAX_DIRECTIONS pans, 1.4 s each at the 0.05 s tick (arm settle .6 + look)
        t, rows = 0., []
        for c in (cands[:MAX_DIRECTIONS] or FORCED):
            t += .05
            src.on_command({'t': t, 'kind': 'look', 'pan_pulse': c['pan']})
            for k in range(28):
                t = round(t + .05, 6)
                src.on_frame(t, rgb)
            r = src.report(t)
            cov = np.asarray(src.loc._pf.estimate()['cov'])
            rows.append({'sx_mm': round(math.sqrt(cov[0,0])*1e3,1), 'sy_mm': round(math.sqrt(cov[1,1])*1e3,1), 'pan': c['pan'], 't': t, 'std_xy_mm': round(r.std_xy_m*1e3, 1),
                         'std_yaw_deg': round(math.degrees(r.std_yaw_rad), 2),
                         'err_mm': round(math.hypot(r.x_m-x, r.y_m-y)*1e3, 1), 'last_fix_t': r.last_fix_t})
        out[rid] = {'guard': allp, 'ranked': [{'pan': c['pan'], 'score': round(float(c['observability_score']), 3)} for c in cands],
                    'dwell': rows, 'forced': not cands}
    rt.close()
    return out

res = {}
for j in range(1, len(route)-1):
    b = route[j]
    res[j] = {'beam': b, 'seeds': {s: one(poses(b), s) for s in (0, 1, 2)}}
    for s, o in res[j]['seeds'].items():
        print(j, b, 'seed', s, {rid: ([r['pan'] for r in v['ranked'][:3]], v['dwell'][-1] if v['dwell'] else None) for rid, v in o.items()})
json.dump(res, open('look_feas2.json', 'w'), default=str)
