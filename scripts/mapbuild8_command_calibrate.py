"""gcp5 own-input calibration: fixed FOLDED repeated turn, no evaluation reads."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import platform
import sys


def main(a):
    if not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('GCP5_ONLY')
    sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(a.teacher/'scripts')]
    import numpy as np
    from zone_teacher import FOLDED
    def read(p):return json.loads(p.read_text())
    def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    frames=read(a.input/'own.json')['frames'];rows=read(a.input/'online-trajectory.json');commands=read(a.input/'commands.json')
    groups=defaultdict(list)
    for k in range(1,len(rows)):
        f=frames[k];r=rows[k];servo={int(k):v for k,v in f['servo'].items()};before={int(k):v for k,v in frames[k-1]['servo'].items()}
        if servo!=FOLDED or before!=FOLDED or r['lk']['status']!='measured' or f['command_delta'][2]==0:continue
        cmd=commands[k-1];sig=(tuple(cmd['wheels']),tuple(cmd['duration_s']))
        groups[sig].append(dict(t=f['t'],delta=r['lk']['delta'],vo_covariance=r['lk']['covariance']))
    if not groups:raise ValueError('NO_FIXED_POSE_MEASURED_TURN')
    sig,selected=max(groups.items(),key=lambda item:len(item[1]));values=np.asarray([x['delta'] for x in selected]);mean=values.mean(0)
    centered=values-mean;P=centered.T@centered/len(values)
    if np.linalg.eigvalsh(P).min()<=0:raise ValueError('EMPIRICAL_DISTRIBUTION_DOES_NOT_SPAN_SE2')
    source={str(a.input/n):sha(a.input/n) for n in ('own.json','online-trajectory.json','commands.json')}
    out=dict(schema='ugrp.mapbuild8.own_command_motion.v1',interval_s=.1,qualified_servo={str(k):v for k,v in FOLDED.items()},
        wheels=list(sig[0]),duration_s=list(sig[1]),n=len(selected),mean_delta=mean.tolist(),predictive_covariance=P.tolist(),
        source_sha256=hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest(),source_files=source,
        input_scope='own issued command/PWM and qualified raw LK measurements only; no eval/GT file opened',
        qualification='exact signature + fixed open FOLDED only; no extrapolation to other wheel patterns/servo/load',
        covariance_scope='MLE per-interval observed spread; contains VO error and correlated within-run response; NOT divided by n, NOT independent-trial CI',
        delta_p05_p50_p95=np.percentile(values,[5,50,95],axis=0).tolist(),sample_times=[r['t'] for r in selected],reproduction=sys.argv)
    if a.output.exists():raise ValueError('NO_CALIBRATION_OVERWRITE')
    a.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in ('sample_times','source_files')}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('input','teacher','output'):p.add_argument('--'+k,type=Path,required=True)
    main(p.parse_args())
