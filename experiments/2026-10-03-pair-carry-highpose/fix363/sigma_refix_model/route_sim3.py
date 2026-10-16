"""v4 (2026-10-05, coordinator decisions v4-1'..v4-4) = route_sim2 (kept for the v3 record) with:
  * post-look window P = rf.POST_LOOK_WINDOW_S (10 s, every condition) after the re-fix look, then one fix-refresh
    look (assumed ONE dock pan: the prior is a fix 10 s old; .3 + .8+.6 + .6+.3 = 2.6 s; the PF is re-initialised with
    the same post-look spread -- an assumption, labelled);
  * 10 SIM s decision window at every stop: a stop without a re-fix costs D + 1.2 + .5 = rf.STOP_HOLD_S; a re-fix stop
    decides at t_end + D (+ one control tick to see the echo); the rule's prediction starts with the rest of the
    current stop (rf.lead_hold_s at t_end);
  * re-fix look = the dock look's directions (look_feas3.json, seed 0): the spread after the FIRST fix-quality pan and
    a look time from the pan count (stop .3 + .8+.6 + (n-1)*(.4+.6) + return .6+.3); no ranked 'no safe view';
    a robot without a fix-quality pan in seven is recorded as ALIGN_RELOOK_NO_FIX (model continues, labelled);
  * NOLOOK=1: counterfactual of decision v4-3 (NOT implemented in the controller): a robot whose own bit was False
    (OR-forced) keeps its PF through the partner's look instead of looking; reported: its sigma at the re-grasp
    against the 50 mm / 3 deg pre-close gate and the 67.4 mm budget, and at the post-lift horizon check.
v2 (2026-10-04, coordinator stop-2 sigma_y question): per-axis sigma, door overlap sigma_y/PL per robot, re-fix
phases predicted (lower loaded 13.6 s, open+hover unloaded 1.5 s, look reset, align+pregrasp unloaded 5.2 s, grasp
unloaded 3.04 s, then loaded plant draw, low lift + raise loaded 18.7 s); remaining re-fix time = look dwells.
MODEL route simulation of the sigma re-fix rule (offline, not physics).
Start: recorded ac-672 own frames/commands replayed to the carry GO (89.1 s) through the v98 provider.
Carry: planned legs (align window 6 s held, 0.5 s pause, leg, stop hold) on the live PF, no wall observations at HIGH.
Decision at each eligible stop: harness.zone_pair_highpose_refix.predict on each robot's own PF; pair decision = OR.
Re-fix model: PF re-initialised around its current mean with the post-look spread of the synthetic look
(look_feas2.json, seed 0; static-map geometry, no occluders), then the loaded plant draw at the re-grasp.
A robot with no ranked look direction at a stop fails the real v3 path (ALIGN_RELOOK_NO_SAFE_VIEW): recorded as such.
v3 (2026-10-04, coordinator): parametric motion-noise model from the carry GO on (NOISE env):
  current  = the calibrated PF unchanged (noise_rel*|v| + noise_abs, rest noise per profile);
  odom_rel = HYPOTHESIS pending recalibration: classic odometry model (Thrun et al. 2005 ch. 5.4, alpha1-4): rate
             noise only proportional to the own motion (noise_rel*|v| from the same calibration), noise_abs = 0,
             no noise at rest (rest_noise False). The motion-gated terms (drift per distance, yaw bias, scale walk)
             are kept. The same PF drives the prediction, so the rule forecasts the sigma the PF would declare.
  rest_off = intermediate: only rest_noise False (noise_abs kept while moving) -- the variant behind the DR
             decomposition's "rest noise off" sigma_y 11.7 mm (outputs/dr-error-decomposition-20261004)."""
import sys, json, math
sys.path.insert(0, '../ckpt')
import numpy as np
import replay
from harness import zone_pair_highpose_refix as rf
GO = 89.09999999962103
looks = json.load(open('look_feas3.json'))['stops']

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
NOISE = os.environ.get('NOISE', 'current')
NOLOOK = os.environ.get('NOLOOK') == '1'
D = rf.DECIDE_WINDOW_S
NOLOOK_ROWS = []
from harness import zone_pair_highpose_dr_checkpoint as _dc
assert NOISE in ('current', 'odom_rel', 'rest_off'), NOISE
def _motion_dicts(params):
    for key in ('motion', 'motion_loaded'):
        if isinstance(params.get(key), dict):
            yield params[key]
    for v in (params.get('motion_profiles') or {}).values():
        yield v
if NOISE in ('odom_rel', 'rest_off'):
    for _rid, (_s, _pf, _) in S.items():
        for _p in {id(x): x for x in list(_motion_dicts(_pf.params)) + list(_motion_dicts(_s.calibration['params']))}.values():
            if NOISE == 'odom_rel':
                _p['noise_abs'] = [0., 0., 0.]
            _p['rest_noise'] = False
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
        e = pf.estimate(); worst = max(worst, e['std_xy_m']); door_track(rid, t, pf, e, f'leg{k}')
    pf.command({'t': t, 'kind': 'hold'})
    return t, p, worst

DOOR = {}
def axes(pf):
    c = np.asarray(pf.estimate()['cov']); return math.sqrt(c[0, 0]), math.sqrt(c[1, 1]), math.sqrt(c[2, 2])
def door_track(rid, t, pf, e, phase):
    sx, sy, syaw = axes(pf)
    if rf.overlaps_door(e['x'], e['yaw'], sx, door['x_range_m']):
        pl = rf.DOOR_K*math.hypot(sy, rf.DOOR_LEVER_M*syaw)
        d = DOOR.setdefault(rid, {'entry': None, 'max_sy_mm': 0., 'max_pl_mm': 0., 'exit': None, 'phases': set()})
        row = {'t_after_go': round(t-GO, 2), 'sy_mm': round(sy*1e3, 1), 'pl_mm': round(pl*1e3, 1), 'phase': phase}
        if d['entry'] is None: d['entry'] = row
        d['exit'] = row; d['phases'].add(phase)
        d['max_sy_mm'] = max(d['max_sy_mm'], row['sy_mm']); d['max_pl_mm'] = max(d['max_pl_mm'], row['pl_mm'])
def hold_phase(rid, pf, t0, dur, phase, loaded):
    pf.load.loaded = loaded
    pf.command({'t': t0, 'kind': 'hold'})
    t, mx = t0, 0.
    while t < t0+dur-1e-9:
        t = min(t0+dur, round(t+.05, 9)); pf.predict_to(t); e = pf.estimate()
        mx = max(mx, axes(pf)[1]); door_track(rid, t, pf, e, phase)
    sx, sy, syaw = axes(pf)
    return {'phase': phase, 'end_sx_mm': round(sx*1e3, 1), 'end_sy_mm': round(sy*1e3, 1), 'max_sy_mm': round(mx*1e3, 1),
            'end_std_xy_mm': round(pf.estimate()['std_xy_m']*1e3, 1)}

events, t, n_refix, refix_stops, status = [], GO, 0, [], 'completed'
issues = []
last = len(plan['route'])-1
for k in range(last):
    rows = {}
    for rid, (src, pf, _) in S.items():
        t1, p, worst = drive(pf, rid, k, t, None)
        sx, sy, _ = axes(pf)
        rows[rid] = {'end_sigma': [round(v, 1) for v in sig(pf)], 'worst_xy_mm': round(worst*1e3, 1),
                     'end_sx_sy_mm': [round(sx*1e3, 1), round(sy*1e3, 1)]}
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
    lead = rf.lead_hold_s(t, t)                       # entered at the leg end: the whole 8 s window + stop tail
    pred = {rid: rf.predict(pf, plan, rid, legs, mp, door=door, lead_hold_s=lead) for rid, (src, pf, _) in S.items()}
    req = {rid: p['over'] for rid, p in pred.items()}
    # = SigmaRefix._own_request: an own report over the derived DR receipt budget (67.4 mm / 2.89 deg) at ANY stop
    # requests the re-fix (v3 fix: the v1 model still had the old 50 mm named-checkpoint rule here)
    from harness import zone_pair_highpose_dr_checkpoint as _dc
    for rid, (src, pf, _) in S.items():
        _e = pf.estimate()
        if _e['std_xy_m'] > _dc.BUDGET_XY_M or _e['std_yaw_rad'] > _dc.BUDGET_YAW_RAD: req[rid] = True
    ev = {'stop': j, 'horizon': legs, 'pred': {rid: {kk: p[kk] for kk in ('std_xy_m', 'std_yaw_rad', 'door_pl_m', 'reasons')} for rid, p in pred.items()},
          'request': req, 'refix': any(req.values())}
    events.append(ev)
    if not ev['refix']:
        t += rf.STOP_HOLD_S; continue
    t += D+.1
    n_refix += 1; refix_stops.append(j)
    blocked = []
    PH = [('lower_loaded', 13.6, True), ('open_hover_unloaded', 1.5, False)]
    PH2 = [('align_pregrasp_unloaded', 2.3+.4+2.5, False), ('grasp_unloaded', 3.04, False)]
    LK = {rid: looks[str(j)]['seeds']['0'][rid] for rid in S}
    def look_time(L):
        f = L['first_fix']
        return f['look_s'] if f is not None else .3+.8+.6+6*(.4+.6)+.6+.3
    look_s = max(look_time(L) for L in LK.values())     # the pair re-grasps together (close barrier)
    P, REFRESH_S = rf.POST_LOOK_WINDOW_S, .3+.8+.6+.6+.3
    phases, nolook = {}, {}
    for rid, (src, pf, _) in S.items():
        sx0, sy0, _ = axes(pf)
        ph = [{'phase': 'stop_before_set_down', 'end_sx_mm': round(sx0*1e3, 1), 'end_sy_mm': round(sy0*1e3, 1)}]
        tt = t
        for name, dur, loaded in PH:
            ph.append(hold_phase(rid, pf, tt, dur, name, loaded)); tt += dur
        L = LK[rid]
        skip = NOLOOK and not req[rid]
        if L['first_fix'] is None and not skip:
            blocked.append(rid)
        if skip:
            hold = look_s+P+REFRESH_S
            ph.append(hold_phase(rid, pf, tt, hold, 'partner_look_window_refresh_hold_unloaded', False)); tt += hold
            nolook[rid] = {'own_request': False, 'std_xy_mm_at_regrasp': round(pf.estimate()['std_xy_m']*1e3, 1),
                           'std_yaw_deg_at_regrasp': round(math.degrees(pf.estimate()['std_yaw_rad']), 2)}
        else:
            d = L['first_fix'] if L['first_fix'] is not None else L['dwell'][-1]
            est = pf.estimate()
            spread = (np.array([d['sx_mm']/1e3, d['sy_mm']/1e3, math.radians(d['std_yaw_deg'])]) if MODE == 'look'
                      else np.array(GO_SPREAD[rid]))
            tt += look_s
            pf.t = tt; pf.vel = np.zeros(3)
            pf.init_gaussian(np.array([est['x'], est['y'], est['yaw']]), spread)
            sx, sy, _ = axes(pf)
            ph.append({'phase': 'after_look', 'end_sx_mm': round(sx*1e3, 1), 'end_sy_mm': round(sy*1e3, 1),
                       'look_s': round(look_s, 2), 'pans': None if L['first_fix'] is None else L['first_fix']['n_pans']})
            door_track(rid, tt, pf, pf.estimate(), 'after_look')
            ph.append(hold_phase(rid, pf, tt, P, 'post_look_window_unloaded', False)); tt += P
            est = pf.estimate(); tt += REFRESH_S
            pf.t = tt; pf.vel = np.zeros(3)
            pf.init_gaussian(np.array([est['x'], est['y'], est['yaw']]), spread)      # refresh look (assumed 1 pan)
        for name, dur, loaded in PH2:
            ph.append(hold_phase(rid, pf, tt, dur, name, loaded)); tt += dur
        if skip:
            e = pf.estimate()
            nolook[rid].update(std_xy_mm_at_close=round(e['std_xy_m']*1e3, 1),
                               std_yaw_deg_at_close=round(math.degrees(e['std_yaw_rad']), 2),
                               preclose_gate_50mm_3deg=bool(e['std_xy_m'] <= .05 and e['std_yaw_rad'] <= math.radians(3.)),
                               within_budget=bool(e['std_xy_m'] <= _dc.BUDGET_XY_M and e['std_yaw_rad'] <= _dc.BUDGET_YAW_RAD))
        pf.load.loaded = True
        pf._draw_plant_state(True)
        ph.append(hold_phase(rid, pf, tt, 18.7, 'lift_raise_loaded', True)); tt += 18.7
        if skip:
            e = pf.estimate()
            nolook[rid].update(std_xy_mm_after_lift=round(e['std_xy_m']*1e3, 1),
                               within_budget_after_lift=bool(e['std_xy_m'] <= _dc.BUDGET_XY_M and e['std_yaw_rad'] <= _dc.BUDGET_YAW_RAD))
        phases[rid] = ph
    t = tt
    events.append({'stop': j, 'refix_phases': phases, 'look_s': round(look_s, 2),
                   'cycle_s': round(13.6+1.5+look_s+P+REFRESH_S+5.2+3.04+18.7, 2), 'nolook': nolook})
    if nolook:
        NOLOOK_ROWS.append({'stop': j, **nolook})
    if blocked and MODE == 'look':
        issues.append(f'stop {j}: no fix-quality view in the seven dock directions for {blocked} -> ALIGN_RELOOK_NO_FIX')
        events.append({'stop': j, 'blocked': blocked})
        # continue the model with the last dwell's spread (counterfactual, labelled)
    post = {rid: rf.predict(pf, plan, rid, rf.horizon(plan, j), mp, door=door) for rid, (src, pf, _) in S.items()}
    if any(p['over'] for p in post.values()):
        issues.append(f'stop {j}: post-re-fix horizon check over budget {[r for r,p in post.items() if p["over"]]} -> {rf.INFEASIBLE}')
    events.append({'stop': j, 'post_refix_sigma': {rid: [round(v, 1) for v in sig(pf)] for rid, (src, pf, _) in S.items()},
                   'post_check_over': {rid: p['over'] for rid, p in post.items()},
                   'post_pred_xy': {rid: p['std_xy_m'] for rid, p in post.items()}})
for d in DOOR.values(): d['phases'] = sorted(d['phases'])
stop2 = {}
for rid, (src, pf, _) in S.items():
    x, y, yaw = (plan['route'][2][0] + (-.4732 if rid == 'r1' else .4732), plan['route'][2][1], 0. if rid == 'r1' else math.pi)
    stop2[rid] = {'chassis_overlaps_door_at_stop2_with_sx_40mm': rf.overlaps_door(x, yaw, .04, door['x_range_m']),
                  'chassis_overlaps_door_at_stop2_with_sx_80mm': rf.overlaps_door(x, yaw, .08, door['x_range_m'])}
out = {'version': 'v4', 'decide_window_s': D, 'nolook_counterfactual': NOLOOK, 'nolook_rows': NOLOOK_ROWS,
       'noise_model': NOISE, 'door': DOOR, 'stop2_chassis_overlap': stop2, 'door_alert_limit_mm': round(door['alert_limit_m']*1e3, 1), 'mode': MODE, 'issues_in_order': issues, 'note': 'model continues after each issue (counterfactual)', 'refixes': n_refix, 'refix_stops': refix_stops, 'carry_model_s_after_go': round(t-GO, 1),
       'events': events}
json.dump(out, open(f'route_sim3_{MODE}{"_all" if ALL else ""}{"" if NOISE == "current" else "_" + NOISE}{"_nolook" if NOLOOK else ""}.json', 'w'), indent=1, default=str)
print(json.dumps({k: out[k] for k in ('issues_in_order', 'refixes', 'refix_stops', 'carry_model_s_after_go', 'nolook_rows')}))
for e in events: print(e)
