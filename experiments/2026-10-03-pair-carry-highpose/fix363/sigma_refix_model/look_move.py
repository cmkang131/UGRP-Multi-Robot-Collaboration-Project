"""OFFLINE model of the bounded re-fix look move (coordinator decision 3, 2026-10-04; not physics).

At a set-down stop where the own v3 ranking finds no safe informative view (ALIGN_RELOOK_NO_SAFE_VIEW), the robot
backs off along the reverse of the last carry leg by the smallest 5 cm step d <= d_clear at which the ranking
finds a view, looks there (top MAX_DIRECTIONS dwells, synthetic observations), then drives back on the reversed
command. d_clear is derived from the guard's own clearance (chassis + arm at the current servo, sigma-aware margin
of the guard itself) along the whole path. Same synthetic observer as look_feas2 (static-map geometry only; the
partner robot and the beam on the floor are NOT modelled as occluders). Uses
harness.zone_pair_highpose_refix.look_move_plan when present, so the model and the controller share one rule.
"""
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
from harness import zone_pair_highpose_refix as rf
from scripts.study_owncam_pair_beam import ROLES
import cv2

PLAN = json.load(open('/Users/changmin/projects/ugrp/outputs/v98-dev-probe-align_to_carry-6727751b/before_door/student_record.json'))['pair'][0]['plan']
route = PLAN['route']; L = .4732
mpatch = MonkeyPatch(); tmp = Path(tempfile.mkdtemp(dir='.'))
cal = syn.admitted_copy(tmp, mpatch)
rgb = cv2.cvtColor(cv2.imdecode(np.frombuffer(syn.IMAGE.read_bytes(), np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
SIG0 = (.05, .05, math.radians(1.7))
LOOK = {1: 2000, **LOOK_P20}
HOVER = {1: 2000, 3: 807, 4: 1897, 5: 2187, 6: 1500}   # cp_open posture (zone_final_pair_loaded_schedule controller_hover, grip OPEN)
import os
SERVO0 = HOVER if os.environ.get('POSTURE', 'hover') == 'hover' else {**LOOK, 6: 1500}
SPIN = os.environ.get('SPIN') == '1'
STOPS = [int(a) for a in sys.argv[1].split(',')] if len(sys.argv) > 1 else list(range(1, len(route)-1))
SEEDS = (0, 1, 2)

def poses(b):
    return {'r1': (b[0]-L, b[1], 0.), 'r2': (b[0]+L, b[1], math.pi)}

def dwell(src, t, cands):
    rows = []
    for c in cands[:MAX_DIRECTIONS]:
        t += .05
        src.on_command({'t': t, 'kind': 'look', 'pan_pulse': c['pan']})
        for _ in range(28):
            t = round(t+.05, 6); src.on_frame(t, rgb)
        r = src.report(t)
        rows.append({'pan': c['pan'], 'std_xy_mm': round(r.std_xy_m*1e3, 1), 'last_fix_t': r.last_fix_t})
    return t, rows

def cov_mm(src):
    e = src.loc._pf.estimate(); c = np.asarray(e['cov'])
    return {'sx_mm': round(math.sqrt(c[0, 0])*1e3, 1), 'sy_mm': round(math.sqrt(c[1, 1])*1e3, 1),
            'std_xy_mm': round(e['std_xy_m']*1e3, 1), 'std_yaw_deg': round(math.degrees(e['std_yaw_rad']), 2),
            'x': e['x'], 'y': e['y']}

def drive(src, t, u, dur):
    src.on_command({'t': t, 'kind': 'mecanum', 'forward': u[0], 'left': u[1], 'turn': u[2], 'duration_s': dur})
    t1 = t+dur
    src.loc._pf.predict_to(t1)
    src.on_command({'t': t1, 'kind': 'hold'})
    return t1

out = {}
for j in STOPS:
    b = route[j]
    for rid in ('r1', 'r2'):
        row = {}
        for seed in SEEDS:
            true0 = poses(b)
            # 1) at the set-down pose: ranking as in the v3 path
            rt = syn.build(cal, seed=seed, true=true0)
            actor, src = rt.actors[rid], rt.providers[rid].provider
            guard = PairGeometry(actor.guard, PLAN['beam_geometry'], ROLES[rid])
            x, y, yaw = true0[rid]
            pose0 = OwnPose(x, y, yaw, math.hypot(*SIG0[:2]), SIG0[2])
            rep = SimpleNamespace(initialized=True, x_m=x, y_m=y, yaw_rad=yaw, std_xy_m=pose0.std_xy,
                                  std_yaw_rad=pose0.std_yaw, t_est=0., last_fix_t=None, fix_age_s=99.)
            servo = dict(SERVO0)
            src.on_command({'t': 0., 'kind': 'initial_servo_command', 'pulses': dict(servo)}); src.recovery_v6 = True
            cands0 = ranked_look_pans(actor.map, rep, servo, guard, src, recovery_v6=True)
            mp = src.get_motion_params()
            mv = rf.look_move_plan(PLAN, j, rid, pose0, servo, guard, mp,
                                   rank=lambda p: ranked_look_pans(actor.map, SimpleNamespace(
                                       initialized=True, x_m=p.x, y_m=p.y, yaw_rad=p.yaw, std_xy_m=p.std_xy,
                                       std_yaw_rad=p.std_yaw, t_est=0., last_fix_t=None, fix_age_s=99.),
                                       servo, guard, src, recovery_v6=True))
            if SPIN and seed == 0:
                spin = {}
                floor = min(0., min(guard.chassis_clearance(pose0)[0], guard.arm_clearance(servo, pose0, loaded=False)[0]))
                for deg in (-180, -120, -90, -60, -30, 30, 60, 90, 120):
                    ok = True
                    for f in np.linspace(0, 1, max(2, abs(deg)//2+1))[1:]:
                        p = OwnPose(x, y, yaw+math.radians(deg)*f, pose0.std_xy, pose0.std_yaw)
                        if min(guard.chassis_clearance(p)[0], guard.arm_clearance(servo, p, loaded=False)[0]) < floor:
                            ok = False; break
                    p = OwnPose(x, y, yaw+math.radians(deg), pose0.std_xy, pose0.std_yaw)
                    rk = ranked_look_pans(actor.map, SimpleNamespace(initialized=True, x_m=p.x, y_m=p.y, yaw_rad=p.yaw,
                         std_xy_m=p.std_xy, std_yaw_rad=p.std_yaw, t_est=0., last_fix_t=None, fix_age_s=99.),
                         servo, guard, src, recovery_v6=True)
                    spin[deg] = {'sweep_clear': ok, 'ranked': [(c['pan'], round(float(c['observability_score']), 3)) for c in rk[:3]]}
                print('  spin', j, rid, spin, flush=True)
            rt.close()
            res = {'ranked_at_stop': [c['pan'] for c in cands0[:3]], 'move': {k: v for k, v in mv.items() if k != 'ranked'}}
            if cands0 or not mv.get('ok'):
                row[seed] = res; continue
            # 2) synthetic: start at the stop with the DR prior, drive out, look there, drive back
            dx, dy = mv['direction_world']; d = mv['distance_m']
            true1 = dict(true0); true1[rid] = (x+dx*d, y+dy*d, yaw)
            rt = syn.build(cal, seed=seed, true=true1)
            src = rt.providers[rid].provider
            src.on_command({'t': 0., 'kind': 'initial_servo_command', 'pulses': dict(servo)}); src.recovery_v6 = True
            src.loc._pf.init_gaussian(np.array([x, y, yaw]), np.array(SIG0))
            t = drive(src, 0., mv['out_u'], mv['duration_s'])
            res['after_out'] = cov_mm(src)
            t, rows = dwell(src, t, mv['ranked'])
            res['dwell'] = rows; res['after_look'] = cov_mm(src)
            t = drive(src, t+.05, mv['back_u'], mv['duration_s'])
            res['after_back'] = cov_mm(src)
            res['after_back']['err_to_stop_mm'] = round(math.hypot(res['after_back']['x']-x, res['after_back']['y']-y)*1e3, 1)
            rt.close()
            row[seed] = res
        out[f'{j}:{rid}'] = row
        print(j, rid, {s: (r['ranked_at_stop'], r['move'].get('distance_m'), r['move'].get('d_clear_m'), r['move'].get('reason'),
                           r.get('after_back', {}).get('std_xy_mm'), r.get('after_back', {}).get('sx_mm'),
                           r.get('after_back', {}).get('sy_mm')) for s, r in row.items()}, flush=True)
json.dump(out, open('look_move.json', 'w'), indent=1, default=str)
