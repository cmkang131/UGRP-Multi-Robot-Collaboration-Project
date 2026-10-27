"""Replay previously extracted own RGB features; estimator never reads evaluation."""
import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path
from harness.e2e_static_rgb_localizer import create


def lines(path):
    if not path.exists():path=Path(str(path)+'.zst')
    raw=subprocess.check_output(['zstd','-qdc',str(path)]) if path.suffix=='.zst' else path.read_bytes()
    return [json.loads(x) for x in raw.splitlines() if x]


def main():
    p=argparse.ArgumentParser();p.add_argument('--features',type=Path,required=True);p.add_argument('--static-map',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--option',choices=['static_walls_v1','static_landmarks_v1'],required=True);p.add_argument('--motion',choices=['command_delta','fused_delta'],required=True);p.add_argument('--seed',type=int,default=64001)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);static=json.loads(a.static_map.read_text());source=json.loads((a.features/'summary.json').read_text());assert hashlib.sha256(a.static_map.read_bytes()).hexdigest()==source['static_map_sha256']
    started=time.monotonic();counts={}
    for rid in ('r1','r2'):
        pf=create(static,option=a.option,seed=a.seed);rows=lines(a.features/f'{rid}.jsonl');count=0
        with (a.output/f'{rid}.jsonl').open('w') as f:
            for i,x in enumerate(rows):
                belief=pf.step(t=x['t'],points=x['points'],delta=x[a.motion] if i else [0.,0.,0.],servo={int(k):v for k,v in x['servo'].items()},features=x['features'])
                f.write(json.dumps(dict(**belief,physical_t=x['physical_t'],frame_id=x['frame_id'],sha256=x['sha256']),separators=(',',':'))+'\n');count+=1
                if count%100==0:f.flush();print(json.dumps(dict(robot=rid,frames=count,wall_s=time.monotonic()-started,clusters=belief['cluster']['clusters'],resolved=belief['resolved'])),flush=True)
        counts[rid]=count
    summary=dict(option=a.option,motion=a.motion,seed=a.seed,features=str(a.features),source_raw=source['source_raw'],static_map_sha256=source['static_map_sha256'],counts=counts,wall_s=time.monotonic()-started,scope='fixed own RGB features and original issued commands; no evaluation or physics input',files={x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in a.output.glob('*.jsonl')})
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)

if __name__=='__main__':main()
