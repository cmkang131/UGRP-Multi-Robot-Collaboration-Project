"""Replay only the saved CPU index generator; no model/optimizer execution."""
from pathlib import Path
from collections import Counter
import argparse
import json
import numpy as np
import torch
from harness.grasp_act_data import read_json,write_json
from analyze_actdiag import existing


def main():
    from scripts.beamact1_runtime import require_gcp2
    require_gcp2(training=False)
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(exist_ok=False,parents=True)
    base=Path('/home/ugrp/ugrp-sim/ops-reviews/beamact1/data-v1')
    manifest=read_json(base/'split-v1/manifest.json')
    phases={r['sample_id']:r['phase'] for r in read_json(existing(base/'stages.json'))}
    rowphase=[]
    for ep in manifest['episodes']:
        if ep['split']=='train':rowphase.extend(phases[r['sample_id']] for r in read_json(base/'split-v1'/ep['path']/'samples.json'))
    rowphase=np.asarray(rowphase);n=len(rowphase);counts=np.zeros(n,np.int64)
    gen=torch.Generator().manual_seed(20261015)
    for _ in range(10000):
        ix=torch.randint(n,(8,),generator=gen).numpy();np.add.at(counts,ix,1)
    result=dict(scope=__doc__,seed=20261015,steps=10000,batch8=8,rows=n,draws=int(counts.sum()),
        equivalent_input_row_passes=80000/n,unique_input_rows_seen=int((counts>0).sum()),
        unseen_input_rows=int((counts==0).sum()),unseen_input_fraction=float((counts==0).mean()),
        count_histogram={str(k):int(v) for k,v in Counter(counts).items()},
        per_phase={ph:dict(rows=int((rowphase==ph).sum()),unseen_input_rows=int(((rowphase==ph)&(counts==0)).sum()),
            draws=int(counts[rowphase==ph].sum())) for ph in sorted(set(rowphase))},
        caveat='Counts direct observation draws, not future-action target coverage. No optimizer RNG state loaded; reconstructs code seed and contiguous smoke300/main9700 sampler sequence.')
    write_json(a.output/'sampler.json',result);print(json.dumps(result,indent=2))


if __name__=='__main__':main()
