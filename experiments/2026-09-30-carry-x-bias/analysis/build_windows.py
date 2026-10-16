"""Collect every recorded carry-leg window (GT body-frame travel + issued commands) from the PF-tracked stage raws.

Output: a pickle in the scratchpad (large) and a compact per-window table ``results/windows_summary.json`` (in repo).
Set labels: F = fit set (chain seed 911 of the door-relax chain raw + single-leg L0 of the hR2 sweep);
every other set is hold-out.
"""
import sys, json, pickle, hashlib
sys.path.insert(0, '.')
from xb_common import *

RAWS = {
    # name: (set label, seed filter or None, leg filter or None)
    'door-relax-envelope-77fde5f6-chK1gP2': ('F_chain911', {911}, None),
    'pair-stage-probes-3f6ca985-ghR2': ('F_L0_hR2', None, {0}),
    # ---- hold-out
    'door-relax-envelope-77fde5f6-chK1gP2#912': ('H_chain912', {912}, None),
    'door-relax-envelope-fdd35cee-chK1g': ('H_chain_k1g', None, None),
    'door-relax-envelope-fdd35cee-chBase': ('H_chain_base', None, None),
    'pair-stage-probes-3f6ca985-ghR2#L1+': ('H_hR2_legs', None, {1, 2, 3, 4, 5, 6}),
    'pair-stage-probes-3f6ca985-ghR2L7': ('H_hR2_legs', None, None),
    'pair-stage-probes-495c1173-ghR': ('H_hR', None, None),
    'pair-stage-probes-495c1173-ghRL7': ('H_hR', None, None),
    'pair-stage-probes-f0716773-ghB': ('H_hB', None, None),
    'pair-stage-probes-f0716773-ghC': ('H_hC', None, None),
    'pair-stage-probes-f0716773-ghD': ('H_hD', None, None),
    'pair-stage-probes-f0716773-ghBL7': ('H_hB', None, None),
    'pair-stage-probes-f0716773-ghCL7': ('H_hC', None, None),
    'pair-stage-probes-f0716773-ghDL7': ('H_hD', None, None),
    'pair-stage-probes-ece01311-fcal': ('H_cal', None, None),
    'pair-stage-probes-7cecaf9b-fcal2': ('H_cal', None, None),
    'pair-stage-probes-d08818ef-cal2': ('H_cal', None, None),
    'pair-stage-probes-4fac772d-yawcal': ('H_cal', None, None),
    'door-relax-envelope-fdd35cee-envK1gL1': ('H_env', None, None),
    'door-relax-envelope-fdd35cee-envK1gL0': ('H_env', None, None),
    'door-relax-envelope-fdd35cee-envBaseL1': ('H_env', None, None),
    'door-relax-envelope-fdd35cee-envBaseL0': ('H_env', None, None),
    'pair-stage-probes-1b776a34-dK1': ('H_door_guard', None, None),
    'pair-stage-probes-d93909e5-dK1g': ('H_door_guard', None, None),
}

def main(out_pkl):
    windows = []
    seen = set()
    for key, (label, seeds, legs) in RAWS.items():
        name = key.split('#')[0]
        raw = OUT/name
        if not raw.exists():
            print('missing', name); continue
        n0 = len(windows)
        for d, cid, meta in cases_of(raw):
            cj = json.load(open(str(d)+'.case.json'))
            if seeds is not None and cj.get('seed') not in seeds: continue
            case_leg = cj.get('leg')
            if legs is not None and case_leg not in legs: continue
            uid = (name, cid)
            if uid in seen: continue
            seen.add(uid)
            try:
                c = load_case(d)
            except Exception as e:
                print('skip', cid, e); continue
            for k in ROBOTS:
                b = base_cmds(c['cmds'], k)
                for s in segments(c, k):
                    a = s['t_carry']; z = min(s['t_end'] + 2.0, c['t'][-1])
                    if z - a < 3: continue
                    ts = np.arange(a, z + 1e-9, STEP)
                    g = interp_gt(c, k, ts)
                    yaw = g[0, 2]; cs, sn = math.cos(yaw), math.sin(yaw)
                    dx, dy = g[:, 0]-g[0, 0], g[:, 1]-g[0, 1]
                    fwd = cs*dx + sn*dy; left = -sn*dx + cs*dy
                    _, u = cmd_series(b, a, z)
                    windows.append(dict(set=label, raw=name, case=cid, cell=cj.get('cell'), seed=cj.get('seed'),
                                        leg=case_leg if case_leg is not None else s['leg'], robot=k,
                                        t_carry=a, t_drive=s['t_drive'], t_end=s['t_end'], z=z,
                                        gt_fwd=fwd, gt_left=left, gt_yaw=g[:, 2]-g[0, 2], u=u))
        print(key, label, len(windows)-n0, 'windows')
    pickle.dump(windows, open(out_pkl, 'wb'))
    return windows

if __name__ == '__main__':
    main(sys.argv[1])
