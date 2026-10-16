"""Freeze a finite sweep step budget from OWN R1 motion, never GT/wall time."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import platform


def main(a):
    if not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('GCP5_ONLY')
    import numpy as np
    def read(p):return json.loads(p.read_text())
    rows=read(a.input/'online-trajectory.json');frames=read(a.input/'own.json')['frames'];events=read(a.input/'events.json')
    begin=next(e['t'] for e in events if e['event']=='body_sweep_start');end=next(e['t'] for e in events if e['event']=='body_sweep_end')
    selected=[r for r,f in zip(rows,frames) if begin<r['t']<=end and f['command_delta'][2]!=0 and r['lk']['status']=='measured']
    values=np.array([r['motion_delta'][2] for r in selected]);positive=values[values>0]
    if not len(positive):raise ValueError('NO_POSITIVE_MEASURED_TURN_RESPONSE')
    q=np.percentile(positive,[5,50,95]);files=[a.input/n for n in ('online-trajectory.json','own.json','events.json')]
    source={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    out=dict(schema='ugrp.mapbuild8.own_sweep.v1',interval_s=.1,positive_yaw_p05_rad=float(q[0]),positive_yaw_p50_p95_rad=q[1:].tolist(),
        measured_n=len(values),positive_n=len(positive),nonpositive_n=int(np.sum(values<=0)),step_budget=math.ceil(2*math.pi/q[0]),
        basis='finite nodes=ceil(2pi/own measured positive 0.1s yaw P05); 5th percentile lower-response convention matches frozen requirements P5; not a guarantee of final pose or physical revolution',
        raw=str(a.input),truth_inputs=0,source_files=source,source_sha256=hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest())
    if a.output.exists():raise ValueError('NO_MODEL_OVERWRITE')
    a.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);main(p.parse_args())
