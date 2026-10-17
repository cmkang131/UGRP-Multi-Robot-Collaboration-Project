"""Post-seal source-VM integrity, diagnostic summaries and lossless archival."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys


def main(a):
    if not platform.node().startswith('ugrp-act-l4-'+a.host):raise ValueError('SOURCE_VM_ONLY')
    sys.path.insert(0,str(a.source))
    import numpy as np
    from harness.mapbuild_amcl import StaticField
    from harness.mapbuild_amcl_vendor import algorithms as nav2
    def raw(p):return p.read_bytes() if p.exists() else subprocess.check_output(['zstd','-qdc',str(p)+'.zst'])
    def read(p):return json.loads(raw(p))
    def sha(p):return hashlib.sha256(raw(p)).hexdigest()
    def dump(p,v):
        with p.open('x') as f:json.dump(v,f,indent=2,allow_nan=False);f.write('\n')
    b=a.work;seal=read(b/'prediction-seal.json');g=read(b/'prior-generation-eval-only.json');own=read(b/'own-seal.json');bad=[]
    for p,h in seal['input_sha256'].items():
        if sha(Path(p))!=h:bad.append(p)
    for p,h in seal['prediction_sha256'].items():
        if sha(b/'predictions'/p)!=h:bad.append(p)
    for p,h in {**own['sources'],**g['truth_sources']}.items():
        if sha(Path(p))!=h:bad.append(p)
    if sha(b/'priors.json')!=g['priors_sha256']:bad.append('prior_generation_link')
    if bad:raise ValueError(str(bad))
    e=read(b/'evaluation.json');summary=read(b/'summary.json');phases=[]
    if not (b/'phase-summary.json').exists():
        for aggregate in e['aggregates']:
            rs=[r for r in e['results'] if r['stream']==aggregate['stream'] and r['mode']==aggregate['mode']]
            bins=sorted({v['start_sim_s'] for r in rs for v in r['segments']})
            phases.append(dict(stream=aggregate['stream'],mode=aggregate['mode'],phases=[dict(start_sim_s=t,
                xy_rmse_median_p90=np.percentile([v['xy_rmse_m'] for r in rs for v in r['segments'] if v['start_sim_s']==t],[50,90]).tolist(),
                off_xy_rmse_m=next(v['off_xy_rmse_m'] for r in rs for v in r['segments'] if v['start_sim_s']==t)) for t in bins]))
        dump(b/'phase-summary.json',phases)
    fractions=np.array([[v['relative_x'],v['relative_y'],v['relative_yaw']] for v in g['relative_positions']])
    compact=dict(host=a.host,trials=e['trials'],cases=len(e['results']),scope=e['scope'],modes=[])
    for mode in ('coarse','global'):
        rs=[r for r in e['results'] if r['mode']==mode]
        compact['modes'].append(dict(mode=mode,cases=len(rs),converged_cases=sum(r['ready_updates']>0 for r in rs),
            wrong_converged_cases=sum(r['wrong_ready_updates']>0 for r in rs),offline_pass_cases=sum(r['offline_pass'] for r in rs),
            endpoint_requirement_pass_cases=sum(r['final_handoff_pass'] for r in rs),
            note='endpoint scores include unresolved proposals; no physical/runtime admission'))
    dump(b/'compact-summary.json',compact)
    if a.host=='gcp5':
        own_data=read(b/'own-streams.json');s=next(s for s in own_data['streams'] if s['id']=='r3')
        gt=read(Path(s['evaluation_source']))['frames'];field=StaticField(s['static']);diagnostics=[];end_bias=[]
        for trial in range(20):
            pred=read(b/f'predictions/r3-coarse-{trial:03d}.json')['rows']
            end_bias.append((np.array(pred[-1]['candidate'][:2])-gt[-1]['pose'][:2]).tolist())
            for f,r,t in zip(s['frames'],pred,gt):
                if not r['attempted']:continue
                scan=f['scan'];camera=np.asarray(scan['camera']);points=np.array([
                    camera+v['range_m']*np.array([np.cos(v['bearing_rad']),np.sin(v['bearing_rad'])]) if v['status']=='hit' else [np.nan,np.nan] for v in scan['columns']])
                values=nav2.likelihood(field,np.array([t['pose'],r['candidate']]),points,.2)
                xy=float(np.linalg.norm(np.array(r['candidate'][:2])-t['pose'][:2]))
                diagnostics.append(dict(trial=trial,t=f['t'],ready=r['ready'],xy_error_m=xy,
                    exact_evaluation_pose_likelihood=float(values[0]),candidate_likelihood=float(values[1]),candidate_scores_higher=bool(values[1]>values[0])))
        dump(b/'r3-likelihood-diagnostic.json',dict(scope='post-seal evaluation only; never changes predictions/thresholds',rows=diagnostics,
            final_xy_bias_mean_m=np.mean(end_bias,axis=0).tolist(),final_xy_bias_std_m=np.std(end_bias,axis=0).tolist(),
            candidate_scores_higher_updates=sum(d['candidate_scores_higher'] for d in diagnostics),updates=len(diagnostics),
            warning='A score comparison is not a proof of a global optimum or a complete causal explanation.'))
    compressed=[]
    for p in sorted(b.rglob('*.json')):
        if p.stat().st_size<=65536:continue
        before=sha(p);dest=Path(str(p)+'.zst')
        subprocess.run(['zstd','-q','-T1',str(p),'-o',str(dest)],check=True)
        if hashlib.sha256(subprocess.check_output(['zstd','-qdc',str(dest)])).hexdigest()!=before:raise ValueError('COMPRESSION_CHANGED')
        compressed.append(dict(original=str(p),sha256=before,compressed=str(dest),compressed_sha256=hashlib.sha256(dest.read_bytes()).hexdigest()))
        p.unlink()
    receipt=dict(source_sha='9fa2aad39',verified_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        input_files=len(seal['input_sha256']),prediction_files=len(seal['prediction_sha256']),source_files=len(own['sources']),truth_source_files=len(g['truth_sources']),
        rgb_sha_checked=own['rgb_sha_checked'],mismatch=bad,prior_generation_link_verified=True,
        synthetic_prior_n=len(fractions),relative_position_min_max=[fractions.min(0).tolist(),fractions.max(0).tolist()],
        centered_xy_n=int(np.sum(np.all(np.isclose(fractions[:,:2],.5),axis=1))),compressed=compressed,
        retrieval_sha256={p.name:sha(p) for p in b.iterdir() if p.is_file() and p.suffix=='.json' and p.stat().st_size<=65536})
    dump(b/'final-integrity.json',receipt)
    print(json.dumps(compact),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',choices=['gcp5','gcp3'],required=True)
    for name in ('work','source'):p.add_argument('--'+name,type=Path,required=True)
    main(p.parse_args())
