"""Where does the along-track (world x) PF error of the chained L0 -> L1 accumulate?  (recorded PF vs eval-only GT)

Per phase, per robot, over the 20 chain cases (seed 911 and 912 of the k1g+p2 raw; the physics of the two seeds is
the same, only the PF random numbers differ, so n counts case-robots, not independent trials):
  steer   carry entry -> first cruise command       (tiny closed-loop corrections, door alignment)
  drive   cruise command window until the controller stops
  coast   1 s after the stop
  rest    L0 stop -> L1 carry entry (lower / open / re-grasp look / lift): no base command; the PF sees one tag fix
Each row: PF and GT world-x displacement, their difference (= change of the estimate error e_x = PF - GT) in mm,
and the commanded distance sum(u_fwd*dt) for the drive.
"""
import sys, json, collections
sys.path.insert(0, '.')
from xb_common import *

RAW = 'door-relax-envelope-77fde5f6-chK1gP2'

def main(out_json, out_txt):
    rows = []
    for d, cid, meta in cases_of(OUT/RAW):
        c = load_case(d)
        row = json.loads(next(l for l in open(OUT/RAW/'cases.jsonl') if json.loads(l)['case_id'] == cid))
        seed = row['seed']
        for k in ROBOTS:
            segs = segments(c, k)
            if len(segs) < 2: continue
            b = base_cmds(c['cmds'], k)
            pts = [('start', segs[0]['t_carry']), ('L0 drive start', segs[0]['t_drive']), ('L0 stop', segs[0]['t_end']),
                   ('L0 stop+1s', segs[0]['t_end']+1.0), ('L1 carry entry', segs[1]['t_carry']),
                   ('L1 drive start', segs[1]['t_drive']), ('L1 stop', segs[1]['t_end']), ('L1 stop+1s', min(segs[1]['t_end']+1.0, c['t'][-1]))]
            phases = [('L0 steer', 0, 1), ('L0 drive', 1, 2), ('L0 coast', 2, 3), ('rest (lower..lift, 1 fix)', 3, 4), ('L1 steer', 4, 5), ('L1 drive', 5, 6), ('L1 coast', 6, 7)]
            tt = [t for _, t in pts]
            G = interp_gt(c, k, tt); P = interp_pf(c, k, tt)
            for name, i, j in phases:
                a, z = tt[i], tt[j]
                ts, u = cmd_series(b, a, z)
                rows.append(dict(seed=seed, case=cid, robot=k, phase=name, t0=a, t1=z, gt_dx=float(G[j, 0]-G[i, 0]), pf_dx=float(P[j, 0]-P[i, 0]),
                                 u_fwd=float(u[:-1, 0].sum()*STEP), e_start=float(P[i, 0]-G[i, 0]), e_end=float(P[j, 0]-G[j, 0])))
    agg = collections.OrderedDict()
    for r in rows:
        agg.setdefault((r['robot'], r['phase']), []).append(r)
    lines = ['robot | phase | n | GT dx mm | PF dx mm | change of e_x = PF-GT (mm, mean ± sd) | e_x after (mm)']
    out = []
    for robot in ROBOTS:
        for name in ['L0 steer', 'L0 drive', 'L0 coast', 'rest (lower..lift, 1 fix)', 'L1 steer', 'L1 drive', 'L1 coast']:
            rs = agg[(robot, name)]
            d = np.array([r['pf_dx']-r['gt_dx'] for r in rs])*1000
            m = lambda f: 1000*np.mean([r[f] for r in rs])
            lines.append(f"{robot} | {name} | {len(rs)} | {m('gt_dx'):+.1f} | {m('pf_dx'):+.1f} | {d.mean():+.1f} ± {d.std():.1f} | {m('e_end'):+.1f}")
            out.append(dict(robot=robot, phase=name, n=len(rs), gt_dx_mm=m('gt_dx'), pf_dx_mm=m('pf_dx'), d_err_mm=float(d.mean()), d_err_sd_mm=float(d.std()), e_after_mm=m('e_end')))
    # cumulative check: error at L0 start and each boundary
    open(out_txt, 'w').write('\n'.join(lines) + '\n')
    json.dump({'rows': out}, open(out_json, 'w'), indent=1)
    print('\n'.join(lines))

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
