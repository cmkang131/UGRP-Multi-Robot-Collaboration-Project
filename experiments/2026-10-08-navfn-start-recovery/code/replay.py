"""Previously byte-verified egomap46 A snapshot; no physics or GT reads."""
from pathlib import Path
import json,hashlib,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
EXP=Path(__file__).resolve().parents[1]
from harness.active_wall_recovery import ExplorationRecoveryNavigator
from harness.active_navfn_start import StartRecoveryNavigator
from harness.public_navigation_unknown import UnknownCostmap
from scripts.run_active_wall_rotleft import dump

def main():
    src=Path('/Users/changmin/projects/ugrp/outputs/frontier-duration-v1/exhaustion-audit-v2')
    seal=json.loads((src/'seal.json').read_text())
    for name in ('costmap.npz','state.json','replay.json'):
        assert hashlib.sha256((src/name).read_bytes()).hexdigest()==seal[name]
    d=np.load(src/'costmap.npz');c=UnknownCostmap(d['raw'],d['origin'],float(d['resolution']));pose=d['pose']
    before=(c.raw.tobytes(),c.costs.tobytes());old,new=ExplorationRecoveryNavigator(),StartRecoveryNavigator()
    candidates=old.core.frontiers(c.raw,c.origin,c.resolution,pose[:2]);rows=[]
    assert len(candidates)==4
    for f in candidates:
        a,b=old.plan_to(c,pose,f[:2]),new.plan_to(c,pose,f[:2])
        rows.append(dict(target=f[:2],frontier_cells=int(f[5]),off_points=len(a),on_points=len(b),
            start_connector_clear=c.sweep_clear(pose,[*b[1],pose[2]]) if b else None))
    result=dict(snapshot=str(src/'costmap.npz'),snapshot_sha256=seal['costmap.npz'],t=150.3,
        prefix_trace_bytes_verified=736,rows=rows,off_paths=sum(r['off_points']>0 for r in rows),
        on_paths=sum(r['on_points']>0 for r in rows),input_unchanged=before==(c.raw.tobytes(),c.costs.tobytes()),
        gt_read=False,physics_runs=0,qualification='fixed-pose planning acceptance, not physical recovery or arrival')
    assert result['off_paths']==0 and result['on_paths']==4 and result['input_unchanged']
    dump(EXP/'results/replay.json',result);print(json.dumps(result,default=lambda x:x.tolist(),indent=2))

if __name__=='__main__':main()
