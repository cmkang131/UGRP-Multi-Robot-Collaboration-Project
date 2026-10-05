"""SUPERSEDED by route_sim2.py (v3, 2026-10-04): v1 kept for the record; its 50 mm named-checkpoint request rule is stale.
MODEL route simulation of the sigma re-fix rule (offline, not physics).
Start: recorded ac-672 own frames/commands replayed to the carry GO (89.1 s) through the v98 provider.
Carry: planned legs (align window 6 s held, 0.5 s pause, leg, stop hold) on the live PF, no wall observations at HIGH.
Decision at each eligible stop: harness.zone_pair_highpose_refix.predict on each robot's own PF; pair decision = OR.
Re-fix model: PF re-initialised around its current mean with the post-look spread of the synthetic look
(look_feas2.json, seed 0; static-map geometry, no occluders), then the loaded plant draw at the re-grasp.
A robot with no ranked look direction at a stop fails the real v3 path (ALIGN_RELOOK_NO_SAFE_VIEW): recorded as such."""
import sys, json, math
sys.path.insert(0, '../ckpt')
import numpy as np
import replay
from harness import zone_pair_highpose_refix as rf
GO = 89.09999999962103
looks = json.load(open('look_feas2.json'))

def build(rid):
    case = replay.load_case('ac-672', rid)
    src = replay.build(case, None, {})
    pf = src.loc._pf
    for kind, t, payload in replay.events(case):
        if t > GO + 1e-6: break
        if kind == 'report':
            if t >= pf.t - 1e-9: src.report(t)
        elif kind == 'profile': src.set_motion_profile(t, payload)
        elif kind == 'cmd': src.on_command(payload)
        elif kind == 'reloc': src.begin_relocalization(t, dict(src.servo))
        else:
            from PIL import Image
            src.on_frame(t, np.asarray(Image.open(case['root']/payload['path']).convert('RGB')))
    plan = json.load(open(case['root']/'student_record.json'))['pair'][0]['plan']
    return src, pf, plan

MODE = sys.argv[1] if len(sys.argv) > 1 else 'look'
import os
ALL = os.environ.get('ALL_STOPS') == '1'   # coordinator decision 2(a): stop 2 (in the door) allowed
if ALL:
    rf.eligible = lambda plan, j: 0 < j < len(plan['route'])-1
S = {rid: build(rid) for rid in ('r1', 'r2')}
import numpy as _np
GO_SPREAD = {}
for _rid, (_s, _pf, _) in S.items():
    _c = _np.asarray(_pf.estimate()['cov']); GO_SPREAD[_rid] = (math.sqrt(_c[0,0]), math.sqrt(_c[1,1]), math.sqrt(_c[2,2]))
plan = S['r1'][2]
mp = S['r1'][0].calibration['params']['motion_loaded']
door = rf.door_of(plan)
sig = lambda pf: (pf.estimate()['std_xy_m']*1e3, math.degrees(pf.estimate()['std_yaw_rad']))

def drive(pf, rid, k, t0, stop_hold):
    p = rf.leg_plan(plan, k, rid, mp)
    t = t0
    pf.command({'t': t, 'kind': 'hold'}); t += 6.5; pf.predict_to(t)
    u = np.asarray(p['u']); pf.pair_plan = {'t0': t, 't1': t+p['duration_s'], 'own': u.copy(), 'partner': -u.copy()}
    pf.command({'t': t, 'kind': 'mecanum', 'forward': p['u'][0], 'left': p['u'][1], 'turn': p['u'][2], 'duration_s': p['duration_s']})
    worst = 0.
    while t < t0 + 6.5 + p['duration_s'] - 1e-9:
        t = min(t0 + 6.5 + p['duration_s'], round(t + .05, 9)); pf.predict_to(t)
        worst = max(worst, pf.estimate()['std_xy_m'])
    pf.command({'t': t, 'kind': 'hold'})
    return t, p, worst

events, t, n_refix, refix_stops, status = [], GO, 0, [], 'completed'
issues = []
last = len(plan['route'])-1
for k in range(last):
    rows = {}
    for rid, (src, pf, _) in S.items():
        t1, p, worst = drive(pf, rid, k, t, None)
        rows[rid] = {'end_sigma': [round(v, 1) for v in sig(pf)], 'worst_xy_mm': round(worst*1e3, 1)}
    t = t1
    over_gate = {rid: r['worst_xy_mm'] > 70. for rid, r in rows.items()}
    events.append({'leg': k, 't_end': round(t-GO, 1), **rows})
    if any(over_gate.values()):
        msg = f'gate 70 mm crossed in leg {k} ({[r for r,v in over_gate.items() if v]})'
        issues.append(msg)
        events.append({'leg': k, 'gate_crossed': msg})
    j = k+1
    if j == last:
        break
    if not rf.eligible(plan, j):
        t += 1.2+.5; events.append({'stop': j, 'eligible': False}); continue
    legs = rf.horizon(plan, j)
    pred = {rid: rf.predict(pf, plan, rid, legs, mp, door=door) for rid, (src, pf, _) in S.items()}
    req = {rid: p['over'] for rid, p in pred.items()}
    named = [n for n, s in plan['checkpoint_segments'].items() if s == j]
    for rid, (src, pf, _) in S.items():
        if named and pf.estimate()['std_xy_m'] > .05: req[rid] = True
    ev = {'stop': j, 'horizon': legs, 'pred': {rid: {kk: p[kk] for kk in ('std_xy_m', 'std_yaw_rad', 'door_pl_m', 'reasons')} for rid, p in pred.items()},
          'request': req, 'refix': any(req.values())}
    events.append(ev)
    if not ev['refix']:
        t += 2.4+.5; continue
    t += 2*1.2 + 41.44
    n_refix += 1; refix_stops.append(j)
    blocked = []
    for rid, (src, pf, _) in S.items():
        L = looks[str(j)]['seeds']['0'][rid]
        if L.get('forced'):
            blocked.append(rid)
        d = L['dwell'][-1]
        est = pf.estimate()
        spread = (np.array([d['sx_mm']/1e3, d['sy_mm']/1e3, math.radians(d['std_yaw_deg'])]) if MODE == 'look'
                  else np.array(GO_SPREAD[rid]))
        pf.init_gaussian(np.array([est['x'], est['y'], est['yaw']]), spread)
        pf._draw_plant_state(True)
        pf.t = t; pf.vel = np.zeros(3)
    if blocked and MODE == 'look':
        issues.append(f'stop {j}: no ranked look direction for {blocked} -> ALIGN_RELOOK_NO_SAFE_VIEW in the v3 path')
        events.append({'stop': j, 'blocked': blocked})
        # continue the model as if the forced-pan look had been allowed (counterfactual, labelled)
    post = {rid: rf.predict(pf, plan, rid, rf.horizon(plan, j), mp, door=door) for rid, (src, pf, _) in S.items()}
    if any(p['over'] for p in post.values()):
        issues.append(f'stop {j}: post-re-fix horizon check over budget {[r for r,p in post.items() if p["over"]]} -> {rf.INFEASIBLE}')
    events.append({'stop': j, 'post_refix_sigma': {rid: [round(v, 1) for v in sig(pf)] for rid, (src, pf, _) in S.items()},
                   'post_check_over': {rid: p['over'] for rid, p in post.items()},
                   'post_pred_xy': {rid: p['std_xy_m'] for rid, p in post.items()}})
out = {'mode': MODE, 'issues_in_order': issues, 'note': 'model continues after each issue (counterfactual)', 'refixes': n_refix, 'refix_stops': refix_stops, 'carry_model_s_after_go': round(t-GO, 1),
       'events': events}
json.dump(out, open(f'route_sim_{MODE}{"_all" if ALL else ""}.json', 'w'), indent=1, default=str)
print(json.dumps({k: out[k] for k in ('issues_in_order', 'refixes', 'refix_stops', 'carry_model_s_after_go')}))
for e in events: print(e)
