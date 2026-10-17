"""Post-prediction GCP5 error curves, per-memory summaries and revisit-time scale."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import numpy as np


def dump(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2,allow_nan=False)


def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--stage',choices=['curves','fade'],default='curves');a=p.parse_args()
    if not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('GCP5_ORIGINAL_ONLY')
    a.output.mkdir(exist_ok=False,parents=True)
    if a.stage=='fade':
        predictions=json.loads((a.input/'predictions.json').read_text())
        gaps=[e['gap_s'] for r in predictions for e in r['events'] if e['reason']=='reobserved']
        dump(a.output/'fade-scale.json',dict(fade_tau_s=float(np.percentile(gaps,95)) if gaps else None,
             basis='P95 own-input reobserved event gaps; exploratory association timing, display-only decay',
             source_sha256=hashlib.sha256((a.input/'predictions.json').read_bytes()).hexdigest(),
             n=len(gaps),truth_files_opened=0,acceptance_cutoff=False))
        return
    errors=json.loads((a.input/'frame-errors.json').read_text());updates=json.loads((a.input/'reobservations.json').read_text())
    def stats(v):return dict(n=len(v),median=float(np.median(v)),p95=float(np.percentile(v,95)),max=float(max(v))) if v else dict(n=0,median=None,p95=None,max=None)
    ids=sorted(set(r['memory_id'] for r in errors),key=lambda k:int(k[1:]));rows=[]
    for key in ids:
        data=[r for r in errors if r['memory_id']==key]
        rows.append(dict(memory_id=key,kind=data[0]['kind'],evaluator_target=data[0]['target'],first_t=data[0]['t'],last_t=data[-1]['t'],
                         error_m=stats([r['error_m'] for r in data]),age_s=stats([r['age_s'] for r in data]),
                         since_seen_path_m=stats([r['since_seen_path_m'] for r in data])))
    dump(a.output/'per-memory.json',rows)
    bins=[]
    for kind in ('zone_boundary','zone_corner','door'):
        subset=[r for r in errors if r['kind']==kind]
        for key in ('since_seen_path_m','age_s'):
            if not subset:continue
            # Descriptive quintiles; no acceptance/calibration against GT.
            edges=np.unique(np.percentile([r[key] for r in subset],[0,20,40,60,80,100]))
            for i,(lo,hi) in enumerate(zip(edges[:-1],edges[1:])):
                data=[r['error_m'] for r in subset if lo<=r[key] and (r[key]<=hi if i==len(edges)-2 else r[key]<hi)]
                bins.append(dict(kind=kind,axis=key,low=float(lo),high=float(hi),error_m=stats(data)))
    dump(a.output/'distance-age-quintiles.json',bins)
    # Revisit timing comes from sealed OWN-INPUT predictions, not scored errors.
    predictions=json.loads((a.input/'predictions.json').read_text())
    gaps=[e['gap_s'] for r in predictions for e in r['events'] if e['reason']=='reobserved']
    dump(a.output/'fade-scale.json',dict(fade_tau_s=float(np.percentile(gaps,95)) if gaps else None,
         basis='P95 observed same-memory revisit gaps, own RGB/Mahalanobis associations; exploratory, may include incorrect association; display-only e^-age/tau, no physical acceptance cutoff',
         gap_distribution=stats(gaps),source_sha256=hashlib.sha256((a.input/'predictions.json').read_bytes()).hexdigest(),
         derivation='own-input reobserved event gap_s only; GT error values do not enter this statistic',
         runtime_recording1_applied=False))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    for kind in ('zone_boundary','zone_corner'):
        selected=[r for r in errors if r['kind']==kind]
        if not selected:continue
        fig,axes=plt.subplots(1,3,figsize=(14,4))
        for ax,key,label in zip(axes,['path_m','since_seen_path_m','age_s'],['Total travel (m)','Travel since last seen (m)','Last-seen age (SIM s)']):
            for ident in ids:
                data=[r for r in selected if r['memory_id']==ident]
                if not data:continue
                ax.plot([r[key] for r in data],[r['error_m'] for r in data],linewidth=.5,alpha=.5)
            ax.set(xlabel=label,ylabel='Line normal-distance error (m)' if kind=='zone_boundary' else 'Point relative-XY error (m)');ax.grid()
        fig.suptitle(f'{kind}: each trace is one memory; evaluation-label errors included')
        fig.tight_layout();fig.savefig(a.output/f'{kind}-curves.png',dpi=130);plt.close(fig)
    print(json.dumps(dict(memories=len(rows),fade_tau_s=float(np.percentile(gaps,95)) if gaps else None)),flush=True)


if __name__=='__main__':main()
