"""Check that the predict-only replay (registered loaded model) reproduces the recorded PF over each tag-blind carry leg.

For every leg of the chain raw (seed 911 and 912): start from the recorded posterior at the leg start, feed the recorded
commands, compare the replayed leg-end mean displacement and standard deviations with the recorded PF at the same PF clock.
"""
import sys, json
sys.path.insert(0, '.')
from xb_common import *
import xb_replay as R
from chain_counterfactual import pf_row, run_leg

RAW = 'door-relax-envelope-77fde5f6-chK1gP2'

def main(out_json):
    P = R.variant_params()
    rows = []
    for d, cid, meta in cases_of(OUT/RAW):
        c = load_case(d)
        row = json.loads(next(l for l in open(OUT/RAW/'cases.jsonl') if json.loads(l)['case_id'] == cid))
        for L in row['chain']['legs']:
            if not L['recorded']: continue
            for k in ROBOTS:
                b = base_cmds(c['cmds'], k)
                t0, m0, S0 = pf_row(c, k, L['start_sim_s'], 'le')
                t1, m1, S1 = pf_row(c, k, L['end_sim_s'], 'le')
                tr = run_leg(P, m0, S0, [x for x in b if t0-1e-9 <= x[0] <= t1+3.0], t0, t1, seed=1, n=4000)
                m, S = tr[-1][1], tr[-1][2]
                rows.append(dict(leg=L['leg'], robot=k, dx_rec_mm=1000*(m1[0]-m0[0]), dx_rep_mm=1000*(m[0]-m0[0]),
                                 sx_rec_mm=1000*math.sqrt(S1[0, 0]), sx_rep_mm=1000*math.sqrt(S[0, 0]),
                                 sy_rec_mm=1000*math.sqrt(S1[1, 1]), sy_rep_mm=1000*math.sqrt(S[1, 1]),
                                 syaw_rec_deg=math.degrees(math.sqrt(S1[2, 2])), syaw_rep_deg=math.degrees(math.sqrt(S[2, 2]))))
    out = {}
    for leg in (0, 1):
        rs = [r for r in rows if r['leg'] == leg]
        a = lambda f: np.array([r[f] for r in rs])
        out[f'L{leg}'] = dict(n=len(rs), dx_diff_mm_mean=float((a('dx_rep_mm')-a('dx_rec_mm')).mean()), dx_diff_mm_maxabs=float(np.abs(a('dx_rep_mm')-a('dx_rec_mm')).max()),
                              sx_ratio=float((a('sx_rep_mm')/a('sx_rec_mm')).mean()), sy_ratio=float((a('sy_rep_mm')/a('sy_rec_mm')).mean()),
                              syaw_ratio=float((a('syaw_rep_deg')/a('syaw_rec_deg')).mean()))
    json.dump(out, open(out_json, 'w'), indent=1)
    print(json.dumps(out, indent=1))

if __name__ == '__main__':
    main(sys.argv[1])
