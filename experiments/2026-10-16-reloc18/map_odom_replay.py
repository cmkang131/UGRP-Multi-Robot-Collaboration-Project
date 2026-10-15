"""GCP2 saved-stream global-frame diagnostic, not navigation execution."""
import hashlib,json,math,platform,subprocess,sys
from pathlib import Path
import numpy as np
from harness.natural_floor_slam import compose,wrap
from harness.selfmap4_geometry import inverse
try:from harness.reloc18_map_odom import MapOdomFilter
except ModuleNotFoundError:
    sys.path.insert(0,'/home/ugrp/ugrp-sim/analysis-tools')
    from reloc18_map_odom import MapOdomFilter
RUNS=Path('/home/ugrp/ugrp-sim/runs')
def load(p):return p.read_text() if p.exists() else subprocess.check_output(['zstd','-dc',str(p)+'.zst'],text=True)
def rows(p):return [json.loads(x) for x in load(p).splitlines()]
def stat(x):return dict(N=len(x),p50=float(np.median(x)),p95=float(np.percentile(x,95)),end=x[-1]) if x else dict(N=0)
def main():
    assert platform.node().startswith('ugrp-sim-gcp2')
    out=[]
    for seed in (93584,93583):
        raw=RUNS/f'reloc18-r2-selfmap-candidate-{seed}-46dd7ec3/raw';trace=rows(raw/'trace.jsonl');truth={round(x['t'],6):x for x in rows(raw/'eval_only/trajectory.jsonl')}
        f=MapOdomFilter();fixed=None;scored=[]
        for r in trace:
            reg=r['static_registration'];p=reg.get('reloc12',{});odom=p.get('replay',{}).get('own_odometry_pose')
            if odom is None or not reg.get('registered'):continue
            odom=np.asarray(odom);anchor,detail=f.step(t=r['t'],odom=odom,local_pose=odom,world_pose=reg['world_pose'],measurement_covariance=reg['raw_covariance'],fresh=reg['updated'],registered=reg['registered'])
            if anchor is None:continue
            if fixed is None:fixed=anchor.copy()
            gt=truth[round(r['t'],6)];actual=np.array([*gt['robot_xyz_m'][:2],gt['robot_yaw_rad']])
            def err(p):return [float(np.linalg.norm(p[:2]-actual[:2])),abs(math.degrees(wrap(p[2]-actual[2])))]
            scored.append(dict(t=r['t'],command=err(compose(fixed,odom)),candidate=err(f.x),R2=err(compose(p['map_from_execution'],r['pose'])),decision=detail['decision']))
        out.append(dict(seed=seed,raw=str(raw),scope='same saved commands and PF stream; fixed first RGB map registration for command-only comparator; no truth anchor or changed navigation',errors={k:dict(xy_m=stat([r[k][0] for r in scored]),yaw_deg=stat([r[k][1] for r in scored])) for k in ('command','candidate','R2')},accepted=sum(r['decision']['accepted'] for r in scored)))
    p=RUNS/'reloc18-round2/map-odom-replay.json';p.write_text(json.dumps(dict(runs=out),indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
