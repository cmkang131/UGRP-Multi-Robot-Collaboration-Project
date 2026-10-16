"""GCP-only native allocation/copy regression: zero physics or rendering calls."""
import hashlib,json,platform
from types import SimpleNamespace as S
import mujoco,numpy as np
from scripts.warp10_control import mirror,restore,packet_exact

def main():
    if platform.node().split('.')[0]!='ugrp-act-l4-gcp4':raise ValueError('matching gcp4 native ABI required')
    m=mujoco.MjModel.from_xml_string('<mujoco><size memory="16M"/><worldbody><body><freejoint/><geom type="sphere" size=".1"/></body></worldbody></mujoco>')
    child=dict(world=S(model=m,data=mujoco.MjData(m)))
    # Explicit growth/shrink/zero transitions exercise arena topology, not a
    # new robot acceptance threshold. Include repeated identical capacities.
    sequence=[(1,4,1,6),(2,8,1,6),(2,8,1,6),(0,0,0,0),(4,16,1,6),(1,4,1,6)]
    checked=[]
    for epoch,(ncon,nefc,nisland,nidof) in enumerate(sequence*4):
        d=mujoco.MjData(m)
        mujoco._functions._realloc_con_efc(d,ncon=ncon,nefc=nefc,nJ=nefc*m.nv)
        if nisland:mujoco._functions._realloc_island(d,nisland=nisland,nidof=nidof)
        d.ncon=ncon;d.nisland=nisland;d.nidof=nidof
        paths=[('qpos',),('qvel',),('time',),('ncon',),('nisland',),('nidof',)]
        for name in ('pos','frame','geom1','geom2','dist','friction'):
            value=getattr(d.contact,name);value[:]=epoch if value.dtype.kind=='f' else 0
            paths.append(('contact',name))
        if nisland:
            for name in ('island_idofadr','island_nv','map_efc2iefc','map_iefc2efc','ifrc_smooth'):
                value=getattr(d,name);value[:]=epoch;paths.append((name,))
        packet=mirror(dict(world=S(data=d)),sorted(paths));restore(child,packet)
        if not packet_exact(child,packet):raise AssertionError('mirror differs at epoch '+str(epoch))
        checked.append(dict(epoch=epoch,counts=packet['counts'],exact=True,
            contact_sha256=hashlib.sha256(child['world'].data.contact.geom1.tobytes()).hexdigest()))
    print(json.dumps(dict(mujoco=mujoco.__version__,physics_steps=0,render_calls=0,epochs=checked),indent=2))
if __name__=='__main__':main()
