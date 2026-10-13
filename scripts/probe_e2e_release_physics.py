"""Finite VM3-only unloaded setdown diagnostic. Truth is setup/evaluation only."""
import argparse
import copy
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import time


def run(bundle,fixture,option,out):
    import mujoco
    import numpy as np
    from sim.e2e_ownmap_live import PhysicsBackend
    from sim.e2e_stage_physics import update
    from harness.owncam_pair_beam_v2 import pose_of
    from scripts.probe_e2e_speed3_physics import PhysicsAudit
    out.mkdir()
    b=copy.deepcopy(bundle);b['e2e_options']['stage_physics']=option
    backend=PhysicsBackend(b,out,seed=61006);rows=[];started=time.monotonic()
    result=dict(option=option,status='RUNNING',renders=0,model_calls=0)
    try:
        backend.reset(40.)
        for rid in ('r1','r2'):
            for sid,pulse in pose_of('search').items():
                backend.issue(rid,dict(kind='look',pan_pulse=pulse) if sid==6 else dict(kind='arm',servo_id=sid,pulse=pulse))
        backend.advance_to(backend.now+1.4)
        m,d=backend.world.model,backend.world.data
        # Replay a fixed evaluator pose only as a diagnostic initial condition.
        for rid,a in fixture['robots'].items():
            j=m.joint(rid+'__base_free');q=int(m.jnt_qposadr[j.id]);v=int(m.jnt_dofadr[j.id]);yaw=a['robot_yaw_rad']
            d.qpos[q:q+7]=[*a['robot_xyz_m'],math.cos(yaw/2),0.,0.,math.sin(yaw/2)]
            d.qvel[v:v+6]=0.
        body=m.body(backend.objects['beam_1']['body_name']);joint=int(m.body_jntadr[body.id])
        q=int(m.jnt_qposadr[joint]);v=int(m.jnt_dofadr[joint]);cargo=fixture['cargo']['items']['beam_1'];yaw=cargo['yaw']
        offset=float(d.xipos[body.id,2]-d.xpos[body.id,2])
        d.qpos[q:q+7]=[cargo['x'],cargo['y'],cargo['z']-offset,math.cos(yaw/2),0.,0.,math.sin(yaw/2)]
        d.qvel[v:v+6]=0.;mujoco.mj_forward(m,d)
        # Identical post-grasp latch, but both grippers have been commanded open.
        backend._stage_contact_latched=True
        origin=backend.now;backend.set_deadline(origin+12.)
        audit=PhysicsAudit(backend.world)
        for i in range(200):
            update(backend,'relook')
            if i%48==0:
                for rid in ('r1','r2'):
                    backend.issue(rid,dict(kind='look',pan_pulse=[1500,1250,1750][(i//48)%3]))
            backend.advance_to(origin+(i+1)*.05);audit.sample()
            rows.append(dict(t=(i+1)*.05,dt=backend.dt,cargo_z_m=float(d.xipos[body.id,2]),
                             cargo_tilt_deg=math.degrees(math.acos(float(np.clip(d.xmat[body.id,8],-1,1))))))
        result.update(status='COMPLETED_10SIM',audit=audit.record(),
                      cargo_z_range_m=[min(r['cargo_z_m'] for r in rows),max(r['cargo_z_m'] for r in rows)],
                      max_cargo_tilt_deg=max(r['cargo_tilt_deg'] for r in rows),
                      applied_dt_s=sorted(set(r['dt'] for r in rows)))
        result['plausible']=result['audit']['max_penetration_m']<=.01 and result['audit']['max_robot_tilt_deg']<10 and result['max_cargo_tilt_deg']<10 and .01<=min(r['cargo_z_m'] for r in rows)<=max(r['cargo_z_m'] for r in rows)<=.03
    except Exception as exc:
        result.update(status='HOST_ERROR',error=type(exc).__name__+': '+str(exc),plausible=False)
    finally:
        backend.close();result.update(wall_s=time.monotonic()-started,sim_s=rows[-1]['t'] if rows else 0.)
        (out/'evaluation.json').write_text(json.dumps(rows)+'\n')
        (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle',required=True,type=Path);p.add_argument('--fixture',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path);p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--execute',action='store_true');a=p.parse_args()
    if not a.execute or platform.system()!='Linux' or platform.node()!='ugrp-sim-azure3':p.error('VM3_ONLY_EXPLICIT_PHYSICS_DIAGNOSTIC')
    sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    if sha!=a.expected_source_sha or subprocess.check_output(['git','status','--porcelain'],text=True).strip():p.error('COMMITTED_FROZEN_SOURCE_REQUIRED')
    if not a.output.resolve().is_relative_to(Path.home()/'ugrp-sim/runs'):p.error('PERSISTENT_OUTPUT_REQUIRED')
    a.output.mkdir(exist_ok=False)
    (a.output/'RUN_META.json').write_text(json.dumps(dict(**{'class':'dev'},pr=461,sha=sha,branch='codex/e2e18',batch='release-physics-probe'))+'\n')
    (a.output/'fixture.json').write_bytes(a.fixture.read_bytes())
    rows=[run(json.loads(a.bundle.read_text()),json.loads(a.fixture.read_text()),option,a.output/option)
          for option in ['pregrasp_dt1_v1','release_dt1_v1']]
    result=dict(source_sha=sha,qualification='staged unloaded setdown only; no E2E/paired grasp/transport evidence',
                n=sum(r['plausible'] for r in rows),N=2,results=rows,loadavg=os.getloadavg())
    (a.output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    from scripts.probe_e2e_speed3_physics import compress_and_hash
    compress_and_hash(a.output)
    print(json.dumps(result));return int(result['n']!=2)


if __name__=='__main__':raise SystemExit(main())
