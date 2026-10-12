"""20 SIM-second staged wall-contact diagnostic, Azure only.

Saved truth sets the initial fixture and is read by the evaluator only.
The candidate receives its own sonar and command odometry. No E2E claim.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import time
from types import SimpleNamespace


def load(path):
    path=Path(path)
    return json.loads(path.read_bytes() if path.exists() else subprocess.check_output(['zstd','-dc',str(path)+'.zst']))


def run_case(bundle,option,dt,out):
    import mujoco
    import numpy as np
    from sim.e2e_ownmap_live import PhysicsBackend
    from sim.e2e_us_input import attach
    from harness.active_camera import SEARCH
    from harness.e2e_live_transport import Transport
    from harness.e2e_arm_clearance import Clearance
    from harness.e2e_pulse_admission import Admission
    from harness.owncam_pair_beam_v2 import pose_of
    from harness.self_pulse_odom import PulseOdometry
    from harness.e2e_result_writer import write
    out.mkdir(parents=True,exist_ok=False)
    profiles=load('configs/s2_v133_full_template.json')['pulse_calibration']['profiles']
    backend=PhysicsBackend(bundle,out,seed=61005);rows=[];result={};started=time.monotonic()
    robots={};odoms={}
    try:
        backend.reset(10.)
        # Static initial condition copied from v229 s61005, immediately before
        # SEARCH departure. This setup does not enter the candidate's own pose.
        m,d=backend.world.model,backend.world.data
        j=m.joint('r1__base_free');q=int(m.jnt_qposadr[j.id]);v=int(m.jnt_dofadr[j.id])
        yaw=2.9888941300084326
        d.qpos[q:q+7]=[2.3058508336151635,.2406592657924713,.03194707159033561,
                         math.cos(yaw/2),0.,0.,math.sin(yaw/2)]
        d.qvel[v:v+6]=0.;mujoco.mj_forward(m,d)
        m.opt.timestep=dt;backend.dt=dt
        origin=backend.now
        backend.set_deadline(origin+20.)
        for rid in ('r1','r2','r3'):
            odom=PulseOdometry();odom.command(dict(kind='initial_servo_command',t=0.,pulses=SEARCH))
            odoms[rid]=odom
            robots[rid]=SimpleNamespace(robot_id=rid,servo=dict(SEARCH),now=0.,wall_segments=[],
                goal=SimpleNamespace(explorer=SimpleNamespace(local_pose=np.zeros(3))))
        attach(backend,robots,seed=61005,out=out)
        tr=Transport(robots,None,profiles,dev_light=True,align_queues='per_robot_v1')
        tr.arm_clearance=Clearance(option);tr.camera_motion='slow_scan_v1'
        admission=Admission('finish_active_v1')
        for i in range(400):
            now=i*.05
            if i==20:tr._poses('r1',now,[(pose_of('p45'),.8,.6)])
            commands=tr.arm_clearance.filter(tr,now,tr._drain(now))
            for rid,a in admission.step(now,commands):
                backend.issue(rid,a);odoms[rid].command(dict(t=now,**a))
                if a['kind']=='arm':robots[rid].servo[a['servo_id']]=a['pulse']
                elif a['kind']=='look':robots[rid].servo[6]=a['pan_pulse']
            backend.advance_to(origin+(i+1)*.05)
            for rid,r in robots.items():r.goal.explorer.local_pose=np.asarray(odoms[rid].advance((i+1)*.05));r.now=(i+1)*.05
            body=d.body('r1__robot')
            contacts=[]
            for c in d.contact:
                names=[m.geom(int(g)).name for g in (c.geom1,c.geom2)]
                if any(n and n.startswith('r1__') for n in names) and any(n and 'zone_wall' in n for n in names):
                    contacts.append(dict(geoms=names,penetration_m=max(0.,-float(c.dist))))
            row=dict(t=(i+1)*.05,xyz=body.xpos.tolist(),tilt_deg=math.degrees(math.acos(float(np.clip(body.xmat[8],-1.,1.)))),wall_contacts=contacts)
            rows.append(row)
            if row['tilt_deg']>=10.:
                result['status']='ROBOT_TILT_LIMIT';break
        else:result['status']='COMPLETED_20SIM'
    except Exception as exc:
        import traceback
        result.update(status='HOST_ERROR',error=str(exc),traceback=traceback.format_exc())
    finally:
        backend.close()
        result.update(option=option,timestep_s=dt,sim_s=rows[-1]['t'] if rows else 0.,wall_s=time.monotonic()-started,
            max_tilt_deg=max((r['tilt_deg'] for r in rows),default=None),wall_contact_samples=sum(bool(r['wall_contacts']) for r in rows),
            scope='staged wall fixture; no policy camera, LLM, grasp, delivery or E2E success',source_fixture='v229 s61005 trajectory t316.95',
            events=tr.events if 'tr' in locals() else [])
        write(out/'evaluation.json',rows);write(out/'result.json',result)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--bundle',required=True);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--expected-source-sha',required=True);p.add_argument('--expected-workflow-id');p.add_argument('--execute',action='store_true')
    a=p.parse_args()
    if not a.execute or platform.system()!='Linux' or not platform.node().startswith('ugrp-sim-azure'):p.error('AZURE_ONLY_EXPLICIT_PROBE')
    sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    if sha!=a.expected_source_sha:p.error('FROZEN_SOURCE_REQUIRED')
    if not a.output.resolve().is_relative_to(Path.home()/'ugrp-sim/runs'):p.error('PERSISTENT_OUTPUT_REQUIRED')
    from harness.e2e_result_writer import write
    a.output.mkdir(parents=True,exist_ok=False)
    write(a.output/'RUN_META.json',dict(**{'class':'dev'},pr=461,sha=sha,branch='codex/e2e18',batch='arm-clearance-probe'))
    b=load(a.bundle)
    # Retain implicitfast/80 iterations, fixing dt instead of phase adaptation.
    b['e2e_options']['stage_physics']='off';b['e2e_options']['speed3']='dt2_v1'
    rows=[]
    for option,dt in [('off',.002),('range_v1',.002),('off',.00025),('range_v1',.00025)]:
        rows.append(run_case(b,option,dt,a.output/(option+'-'+str(dt))))
        write(a.output/'summary.json',dict(source_sha=sha,results=rows,complete=len(rows)==4,loadavg=os.getloadavg()))
    from scripts.probe_e2e_speed3_physics import compress_and_hash
    compress_and_hash(a.output)
    return int(any(r['status']=='HOST_ERROR' for r in rows))


if __name__=='__main__':raise SystemExit(main())
