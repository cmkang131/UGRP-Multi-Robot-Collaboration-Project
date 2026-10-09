"""Held-out pulse response evaluation, after all trajectory predictions seal."""
import argparse,importlib.util,json
from pathlib import Path
import numpy as np
from scripts.audit_s2_formal_stops import RUNS,read,sha
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('fit_forward',HERE/'fit_bias_tempering.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);root=p.parse_args().root
    for seed in RUNS:
        for c in ('scale','temper','combined'):assert not read(root/'replay'/f's{seed}-{c}.json')['partial']
    out=dict(gt_use='heldout response evaluation only; constants already sealed',runs=[])
    for seed in RUNS:
        table=read(root/'fit'/f's{seed}-calibration.json');assert seed not in table['fit_seeds'];data=m.samples(seed)
        for group,cal in table['groups'].items():
            qs=[q for q in data if q['group']==group and not q['exclude']]
            x=np.array([q['predicted'][0] for q in qs]);y=np.array([q['actual'][0] for q in qs]);a=x-y;b=x*cal['gain']-y
            out['runs'].append(dict(seed=seed,group=group,n=len(qs),gain=cal['gain'],bias_before_mm=float(a.mean()*1000),bias_after_mm=float(b.mean()*1000),rms_before_mm=float(np.sqrt(np.mean(a*a))*1000),rms_after_mm=float(np.sqrt(np.mean(b*b))*1000),calibration_sha256=sha(root/'fit'/f's{seed}-calibration.json')))
    with (root/'forward-heldout.json').open('x') as f:json.dump(out,f,indent=2);f.write('\n')
    print(json.dumps(out,indent=2))
if __name__=='__main__':main()
