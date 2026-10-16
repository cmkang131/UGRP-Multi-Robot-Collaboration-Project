"""Run the offline counterfactual for every recorded case and write per-sample records (JSON lines in results/).

usage: run_counterfactual.py <out_dir> [--workers N]
"""
import sys, json, math, time, multiprocessing as mp
sys.path.insert(0, '.')
from chain_counterfactual import *

K1 = 0.9483        # fit_forward_model.py: M1 kappa (fit set only)
K2, TAU2 = 0.9607, 1.0

def variants():
    v = {'V0': R.variant_params(),
         'V1': R.variant_params(fwd_gain_mult=K1),
         'V2': R.variant_params(fwd_gain_mult=K2, tau=TAU2)}
    for f in (0.0, 0.25, 0.5, 0.75, 1.5, 2.0):
        v[f'V1_s{f}'] = R.variant_params(fwd_gain_mult=K1, white_x_mult=f, scale_x_mult=f)
    for f in (1.5, 2.0, 3.0, 4.0):
        v[f'V0_s{f}'] = R.variant_params(white_x_mult=f, scale_x_mult=f)
    for a in (0.03, 0.05, 0.08):
        v[f'V0_w{a}'] = R.variant_params(extra_white_x=a)
        v[f'V1_w{a}'] = R.variant_params(fwd_gain_mult=K1, extra_white_x=a)
    return v

CHAIN = {  # label -> (raw, seed filter)
    'chain911': ('door-relax-envelope-77fde5f6-chK1gP2', {911}),
    'chain912': ('door-relax-envelope-77fde5f6-chK1gP2', {912}),
    'chainP1': ('door-relax-envelope-fdd35cee-chK1gP1', None),
    'chainK1g': ('door-relax-envelope-fdd35cee-chK1g', None),
    'chainK0g': ('door-relax-envelope-fdd35cee-chK0g', None),
    'chainBase': ('door-relax-envelope-fdd35cee-chBase', None),
}
LEGS = {   # label -> (raw, leg filter)
    'hR2_L1': ('pair-stage-probes-3f6ca985-ghR2', {1}),
    'hR2_L2': ('pair-stage-probes-3f6ca985-ghR2', {2}),
    'hR2_L6': ('pair-stage-probes-3f6ca985-ghR2', {6}),
    'hR2_L7': ('pair-stage-probes-3f6ca985-ghR2L7', None),
    'hR2_L0': ('pair-stage-probes-3f6ca985-ghR2', {0}),      # in the fit set (kappa), shown for reference
    'hR_L0': ('pair-stage-probes-495c1173-ghR', {0}),
    'hR_L1': ('pair-stage-probes-495c1173-ghR', {1}),
    'hR_L2': ('pair-stage-probes-495c1173-ghR', {2}),
    'hR_L6': ('pair-stage-probes-495c1173-ghR', {6}),
    'hB': ('pair-stage-probes-f0716773-ghB', {0, 1, 2, 6}),
    'hC': ('pair-stage-probes-f0716773-ghC', {0, 1, 2, 6}),
    'hD': ('pair-stage-probes-f0716773-ghD', {0, 1, 2, 6}),
    'env_L0': ('door-relax-envelope-fdd35cee-envK1gL0', None),
    'env_L1': ('door-relax-envelope-fdd35cee-envK1gL1', None),
    'cal_fcal': ('pair-stage-probes-ece01311-fcal', {0, 1, 2, 6}),
    'cal_fcal2': ('pair-stage-probes-7cecaf9b-fcal2', {0, 1, 2, 6}),
}

def compact(st):
    return dict(e=[float(x) for x in st['e']], sd=[float(x) for x in st['sd']], nees=st['nees'], sxy=st['sxy'])

def job_chain(a):
    label, raw, d, cid, fix_mode = a
    pv = variants()
    out = analyse_case(d, cid, pv, fix_mode=fix_mode)
    recs = []
    for v in pv:
        for k in ROBOTS:
            r = out[v][k]
            recs.append(dict(kind='chain', label=label, fix_mode=fix_mode, case=cid, variant=v, robot=k, fix_time=r['fix_time'],
                             L0=compact(r['L0'][0]), L1start=compact(r['L1start'][0]), L1=compact(r['L1'][0]),
                             max_sxy_L0=max(x[1] for x in r['tr0'][0]), max_sxy_L1=max(x[1] for x in r['tr1'][0]),
                             max_syaw_L0=max(x[2] for x in r['tr0'][0]), max_syaw_L1=max(x[2] for x in r['tr1'][0])))
    return recs

def job_leg(a):
    label, raw, d, cid, leg = a
    pv = variants()
    out = analyse_leg(d, cid, pv)
    recs = []
    for v in pv:
        for k, r in out[v].items():
            recs.append(dict(kind='leg', label=label, case=cid, leg=leg, variant=v, robot=k, end=compact(r['end']),
                             max_sxy=max(x[1] for x in r['tr']), max_syaw=max(x[2] for x in r['tr'])))
    return recs

def main(out_dir, workers=3, chain_only=False):
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    jobs_c, jobs_l = [], []
    for label, (rawn, seeds) in CHAIN.items():
        for d, cid, meta in cases_of(OUT/rawn):
            cj = json.load(open(str(d)+'.case.json'))
            if seeds is not None and cj['seed'] not in seeds: continue
            row = json.loads(next(l for l in open(OUT/rawn/'cases.jsonl') if json.loads(l)['case_id'] == cid))
            legs = [l for l in row['chain']['legs'] if l['recorded']]
            if len(legs) < 2: continue        # the chain has to have reached the door leg
            for fm in (('fuse', 'replace') if label in ('chain911', 'chain912') else ('fuse',)):
                jobs_c.append((label, rawn, d, cid, fm))
    for label, (rawn, legs) in LEGS.items():
        for d, cid, meta in cases_of(OUT/rawn):
            cj = json.load(open(str(d)+'.case.json'))
            if legs is not None and cj.get('leg') not in legs: continue
            jobs_l.append((label, rawn, d, cid, cj.get('leg')))
    print(len(jobs_c), 'chain jobs', len(jobs_l), 'leg jobs', flush=True)
    t = time.time()
    with mp.Pool(workers) as pool, open(out_dir/'records.jsonl', 'w') as f:
        for i, recs in enumerate(pool.imap_unordered(job_chain, jobs_c)):
            for r in recs: f.write(json.dumps(r) + '\n')
            if i % 10 == 0: print('chain', i, time.time()-t, flush=True)
        for i, recs in enumerate(pool.imap_unordered(job_leg, [] if chain_only else jobs_l, chunksize=4)):
            for r in recs: f.write(json.dumps(r) + '\n')
            if i % 50 == 0: print('leg', i, time.time()-t, flush=True)

if __name__ == '__main__':
    main(sys.argv[1], 3, chain_only='--chain-only' in sys.argv)
