"""Gcp2 CPU-only inspection of saved third-attempt GPU/CPU evaluator dump."""
import argparse,hashlib,json,datetime,os,platform
from pathlib import Path
import numpy as np

def main():
    p=argparse.ArgumentParser();p.add_argument('--dump',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--ngeom',type=int,required=True);p.add_argument('--world',type=int,required=True);a=p.parse_args()
    if platform.node().split('.')[0]!='ugrp-sim-gcp2':raise ValueError('gcp2 offline analysis only')
    lease=Path('/home/ugrp/ugrp-sim/leases/warp10-analysis.json')
    with lease.open('x') as f:json.dump(dict(task='warp10',pid=os.getpid(),started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),expected_end='finite saved dump analysis',concurrency=0),f)
    try:
        z=np.load(a.dump);nacon=min(int(z['nacon'][0]),len(z['contact.geom']))
        # Actual saved active types are all CONSTRAINT=1; refuse to guess
        # another upstream export mask for a different dump/backend.
        if np.unique(z['contact.type'][:nacon]).tolist()!=[1]:raise ValueError('different contact types: inspect pinned upstream mask')
        mask=z['contact.worldid'][:nacon]==a.world
        gpu=z['contact.geom'][:nacon][mask];cpu=np.stack((z['cpu_geom1'],z['cpu_geom2']),axis=1)
        if gpu.shape!=cpu.shape:raise ValueError('world/contact filter differs from saved export')
        invalid=lambda x:int(np.count_nonzero((x<0)|(x>=a.ngeom)))
        value=dict(raw=str(a.dump),sha256=hashlib.sha256(a.dump.read_bytes()).hexdigest(),ngeom=a.ngeom,
            bound_basis='same red scene native model valid indices0..1385, not a fitted tolerance',world=a.world,
            nacon=nacon,allocated_contact_slots=len(z['contact.geom']),world_contacts=len(gpu),
            active_gpu_invalid_geom_values=invalid(z['contact.geom'][:nacon]),cpu_invalid_geom_values=invalid(cpu),
            different_contact_rows=[dict(row=int(i),gpu=gpu[i].tolist(),cpu=cpu[i].tolist()) for i in np.flatnonzero(np.any(gpu!=cpu,axis=1))],
            nefc=z['nefc'].tolist(),scope='CPU export is corrupted while staged GPU geom IDs are in range; first bad write/binding mechanism remains unresolved. No physics correctness or root-cause proof.',
            integration_steps=0,model_calls=0,reproduction=['python',__file__,'--dump',str(a.dump),'--output',str(a.output),'--ngeom',str(a.ngeom),'--world',str(a.world)])
        a.output.write_text(json.dumps(value,indent=2)+'\n')
    finally:lease.unlink()
if __name__=='__main__':main()
