"""Offline dead-reckoning replay (no simulation, no frames, no fixes).

Feeds a saved run's own issued commands to the real v98 PF (open loop) under three loaded-motion profiles and
compares the predicted displacement of each carry leg with the saved eval-only trajectory. GT only scores the
prediction after the fact; nothing here feeds a controller. Usage:
  .venv-sim-worker-mac/bin/python experiments/2026-10-05-solo-cyan-v106/dr_replay_motion_profiles.py <run output dir>
"""
import copy, json, math, sys, bisect
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[2]))
from harness import zone_solo_cyan_contract_v106 as contract
from harness import zone_solo_cyan_v106 as runtime

OUT = sys.argv[1] if len(sys.argv) > 1 else '/Users/changmin/projects/ugrp/outputs/solo-cyan-v106-ee40923c-s911-P1-2-place'
rec = json.load(open(OUT + '/student_record.json'))
truth = [json.loads(l) for l in open(OUT + '/eval_only/trajectory.jsonl')]
tt = [r['t'] for r in truth]
cal_path = contract.ROOT / contract.CALIBRATION
cal_json = json.load(open(cal_path))
static = contract.hp.resolve(contract.MAP_ID)[0]


def gt(t):
    i = bisect.bisect_left(tt, t)
    c = [j for j in (i - 1, i) if 0 <= j < len(truth)]
    return truth[min(c, key=lambda j: abs(tt[j] - t))]


def variant(name, src):
    pf = src.loc._pf
    P = pf.params
    unl, lod = P['motion'], cal_json['params']['motion_loaded']
    if name == 'V0_current_proxy':
        P['motion_loaded'] = copy.deepcopy(P['motion'])   # exactly what zone_solo_cyan_v106.build_provider does
    elif name == 'V1_pair_loaded_profile':
        P['motion_loaded'] = copy.deepcopy(lod)
    elif name == 'V2_unloaded_gain_plus_loaded_xy_deadband':
        m = copy.deepcopy(unl)
        m['deadband'] = copy.deepcopy(lod['deadband'])
        P['motion_loaded'] = m
    else:
        raise SystemExit(name)


def replay(name, sample_ts):
    src = runtime.partial.build_source_class()(static, cal_path, contract.CALIBRATION_SHA, 911)
    try:
        variant(name, src)
        rows = sorted(rec['commands'], key=lambda r: r['t'])
        g0 = gt(rows[0]['t'])['robot_xyz_m']
        src.init_prior((g0[0], g0[1], 0.), (0.001, 0.001, 0.001), source='offline replay start (scoring only)')
        events = [(r['t'], 0, r) for r in rows] + [(t, 1, None) for t in sample_ts]
        events.sort(key=lambda e: (e[0], e[1]))
        out = []
        for t, kind, r in events:
            if kind == 0:
                src.on_command(r)
            else:
                rep = src.report(t)
                a = gt(t)['robot_xyz_m']
                out.append((t, rep.x_m, rep.y_m, a[0], a[1], bool(src.loc._pf.load.loaded)))
        return out
    finally:
        src.close()


if __name__ == '__main__':
    ts = [82.7, 102.8, 161.8, 184.3, 243.2, 282.5, 341.7, 356]
    for name in ('V0_current_proxy', 'V1_pair_loaded_profile', 'V2_unloaded_gain_plus_loaded_xy_deadband'):
        res = {r[0]: r for r in replay(name, ts)}
        print('==', name)
        for a, b in ((82.7, 102.8), (161.8, 184.3), (243.2, 282.5)):
            ra, rb = res[a], res[b]
            ed = (rb[1]-ra[1], rb[2]-ra[2]); ad = (rb[3]-ra[3], rb[4]-ra[4])
            print(f'leg {a}-{b}: est_d=({ed[0]:+.3f},{ed[1]:+.3f}) act_d=({ad[0]:+.3f},{ad[1]:+.3f}) est-act=({ed[0]-ad[0]:+.3f},{ed[1]-ad[1]:+.3f}) x_ratio act/est={ad[0]/ed[0]:.3f}')
