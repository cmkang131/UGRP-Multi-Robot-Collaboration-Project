"""GCP-only CPU arena isolation; native forward, zero integration/GPU calls."""
import argparse,json,os,datetime,platform
from pathlib import Path
import mujoco

def main():
    p=argparse.ArgumentParser();p.add_argument('--scene',required=True);a=p.parse_args()
    if platform.node().split('.')[0]!='ugrp-act-l4-gcp4':raise ValueError('matching native ABI required')
    lease=Path('/home/ugrp/ugrp-sim/leases/warp10-native-check.json')
    with lease.open('x') as f:json.dump(dict(task='warp10',pid=os.getpid(),started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),expected_end='finite native arena check',concurrency=0),f)
    try:
        m=mujoco.MjModel.from_xml_string(Path(a.scene).read_text());rows=[]
        for reset in (False,True):
            d=mujoco.MjData(m);mujoco.mj_forward(m,d)
            initial=dict(ncon=d.ncon,nefc=d.nefc,nisland=d.nisland,nidof=d.nidof)
            # One additional contact/four rows is an allocation test, never
            # a robot acceptance threshold or a physical contact simulation.
            ncon,nefc,nisland,nidof=d.ncon+1,d.nefc+4,d.nisland,d.nidof
            if reset:mujoco.mj_resetData(m,d)
            mujoco._functions._realloc_con_efc(d,ncon=ncon,nefc=nefc,nJ=nefc*m.nv)
            needs=nisland>0 and (d.island_idofadr.shape[0]<nisland or d.ifrc_smooth.shape[0]<nidof or d.map_efc2iefc.shape[0]<nefc)
            if needs:mujoco._functions._realloc_island(d,nisland=nisland,nidof=nidof)
            d.ncon=ncon;d.nisland=nisland;d.nidof=nidof
            d.contact.geom1[:]=0;d.contact.geom2[:]=0;d.ifrc_smooth[:]=1
            rows.append(dict(reset=reset,initial=initial,reallocated_island=bool(needs),
                bad_geom1=d.contact.geom1[d.contact.geom1!=0].tolist(),bad_geom2=d.contact.geom2[d.contact.geom2!=0].tolist(),
                geom1_address=d.contact.geom1.ctypes.data,island_force_address=d.ifrc_smooth.ctypes.data))
        print(json.dumps(dict(mujoco=mujoco.__version__,native_forward_calls=2,integration_steps=0,gpu_calls=0,rows=rows),indent=2))
    finally:lease.unlink()
if __name__=='__main__':main()
