"""How much does the one regrasp tag fix tell each robot about x?  Recorded PF just before / after the fix (chain raw, both seeds)."""
import sys, json
sys.path.insert(0, '.')
from xb_common import *
from chain_counterfactual import pf_row, fix_rows, fix_time
RAW = 'door-relax-envelope-77fde5f6-chK1gP2'
rows = {k: [] for k in ROBOTS}
for d, cid, meta in cases_of(OUT/RAW):
    c = load_case(d)
    row = json.loads(next(l for l in open(OUT/RAW/'cases.jsonl') if json.loads(l)['case_id'] == cid))
    L = [l for l in row['chain']['legs'] if l['recorded']]
    if len(L) < 2: continue
    for k in ROBOTS:
        fr = fix_rows(c, k, fix_time(d, k, L[0]['end_sim_s'], L[1]['start_sim_s']))
        if fr is None: continue
        _, m0, S0, tp, m1, S1 = fr
        A = S1 @ np.linalg.inv(S0)
        rows[k].append(dict(sx_pre=math.sqrt(S0[0, 0]), sx_post=math.sqrt(S1[0, 0]), sy_pre=math.sqrt(S0[1, 1]), sy_post=math.sqrt(S1[1, 1]),
                            jump_x_mm=1000*(m1[0]-m0[0]), jump_y_mm=1000*(m1[1]-m0[1]), jump_yaw_mrad=1000*wrap(m1[2]-m0[2]), A_xx=float(A[0, 0])))
out = {}
for k in ROBOTS:
    r = rows[k]
    out[k] = {key: float(np.mean([x[key] for x in r])) for key in r[0]}
    out[k]['n'] = len(r)
json.dump(out, open('../results/fix_information.json', 'w'), indent=1)
print(json.dumps(out, indent=1))
