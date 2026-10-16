"""Evaluator-only pulse/contact analysis. Run on gcp2, never control feedback."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys


def pose(q):
    import numpy as np
    quat=q[3:7]/np.linalg.norm(q[3:7]);w,x,y,z=quat
    return np.array([q[0],q[1],math.atan2(2*(w*z+x*y),1-2*(y*y+z*z))])


def tilt(q):
    import numpy as np
    w,x,y,z=q[3:7]/np.linalg.norm(q[3:7])
    return float(np.rad2deg(np.arccos(np.clip(1-2*(x*x+y*y),-1,1))))


def delta(a,b):
    import numpy as np
    v=pose(b)-pose(a);v[2]=(v[2]+math.pi)%(2*math.pi)-math.pi
    c,s=math.cos(pose(a)[2]),math.sin(pose(a)[2])
    v[:2]=np.array([[c,s],[-s,c]])@v[:2]
    return v


def stats(values):
    import numpy as np
    a=np.asarray(values)
    return None if not a.size else dict(min=float(a.min()),p50=float(np.median(a)),p95=float(np.percentile(a,95)),max=float(a.max()))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fixture',type=Path,required=True);p.add_argument('--runs',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if not os.uname().nodename.startswith('ugrp-sim-gcp2'):raise ValueError('gcp2 analysis only')
    import numpy as np
    import mujoco
    os.chdir('/home/ugrp/ugrp-sim/src/drivecheck-renderer-5974a181')
    m=mujoco.MjModel.from_xml_string((a.fixture/'scene.xml').read_text());d=mujoco.MjData(m)
    f=np.load(a.fixture/'fixture.npz');fixture=json.loads((a.fixture/'fixture.json').read_text())
    ba=int(m.jnt_qposadr[m.body_jntadr[m.body('r1__robot').id]])
    wa=[int(m.jnt_qposadr[m.actuator_trnid[w,0]]) for w in fixture['wheels']]
    r=.065/2  # Existing official MasterPi 65mm wheel diameter; source geometry_v3.
    from sim.masterpi_geometry_v3 import OFFICIAL_WHEEL_DIAMETER_M
    assert 2*r==OFFICIAL_WHEEL_DIAMETER_M
    centers=np.array([m.body('r1__wheel_'+n+'_body').pos for n in ('fl','fr','rl','rr')])
    lever=float(np.mean(np.abs(centers[:,0])+np.abs(centers[:,1])))
    params=fixture['drive_parameters'];kinetic=params['kinetic_fraction']
    omega=params['parameters']['no_load_rpm']*2*math.pi/60*(.35-kinetic)/(1-kinetic)
    allrows=[];runmeta=[];rejections=[]
    for folder in sorted(a.runs.iterdir()):
        if not folder.is_dir() or not (folder/'result.json').is_file():continue
        report=json.loads((folder/'result.json').read_text());runmeta.append(dict(name=folder.name,**report))
        if report['status']!='cap_end' or not report.get('planned_tape_complete'):
            rejections.append(dict(run=folder.name,category='HOST_ERROR',reason=report.get('error',{}),blocked_object='physics_engine',minimum_gap_m=None,gap_status='not_measured'));continue
        s=np.load(folder/'states.npz');contacts=np.load(folder/'contacts.npz')['records']
        def slips(indices):
            result=[]
            for idx in indices:
                ci=int(s['case'][idx]);t=float(s['t'][idx]);rows=contacts[(contacts[:,0]==ci)&np.isclose(contacts[:,1],t,atol=1e-9)]
                if not len(rows):continue
                d.qpos[:]=s['qpos'][idx];d.qvel[:]=s['qvel'][idx]
                mujoco.mj_kinematics(m,d);mujoco.mj_comPos(m,d);mujoco.mj_comVel(m,d)
                for contact in rows:
                    vs=[]
                    for gid in map(int,contact[2:4]):
                        bid=int(m.geom_bodyid[gid]);v=np.zeros(6)
                        mujoco.mj_objectVelocity(m,d,mujoco.mjtObj.mjOBJ_BODY,bid,v,0)
                        vs.append(v[3:]+np.cross(v[:3],contact[5:8]-d.xpos[bid]))
                    rel=vs[0]-vs[1];normal=contact[8:11]
                    result.append(float(np.linalg.norm(rel-normal*np.dot(normal,rel))))
            return stats(result)
        for ci,case in enumerate(report['cases']):
            indices=np.flatnonzero(s['case']==ci);t=s['t'][indices];qp=s['qpos'][indices]
            def at(tm):
                ids=np.flatnonzero(np.isclose(t,tm,atol=1e-9))
                if not len(ids):raise ValueError('missing exact boundary '+str((folder,case['id'],tm)))
                return ids[0]
            start=at(case['settle_s']);end=at(case['settle_s']+case['duration_s']);stop=len(t)-1
            for phase,j in [('pulse',end),('pulse_plus_stop',stop)]:
                ds=delta(qp[start,ba:ba+7],qp[j,ba:ba+7]);angles=qp[j,wa]-qp[start,wa]
                ideal=np.array([r*np.sum(angles)/4,r*np.dot([-1,1,1,-1],angles)/4,
                                r*np.dot([-1,1,-1,1],angles)/(4*lever)])
                pred=None
                if case['v122']:
                    v=case['v122'];duration=t[j]-t[start]
                    pred=np.array([np.interp(duration,v['times'],np.asarray(v['mean_curve'])[:,k]) for k in range(3)])
                isturn=case['axis']=='turn';actual=abs(ds[2]) if isturn else np.linalg.norm(ds[:2])
                predicted=None if pred is None else (abs(pred[2]) if isturn else np.linalg.norm(pred[:2]))
                cr=contacts[(contacts[:,0]==ci)&(contacts[:,1]>=t[start])&(contacts[:,1]<=t[j])]
                selected=indices[(t>=t[start])&(t<=t[j])]
                perwheel=[]
                for name in ('fl','fr','rl','rr'):
                    geoms={k for k in range(m.ngeom) if (m.geom(k).name or '').startswith('r1__wheel_'+name+'_roller_')}
                    wrows=cr[np.array([int(x[2]) in geoms or int(x[3]) in geoms for x in cr],dtype=bool)]
                    times=s['t'][selected]
                    counts=[int(np.count_nonzero(np.isclose(wrows[:,1],tm,atol=1e-9))) for tm in times]
                    normal=[float(wrows[np.isclose(wrows[:,1],tm,atol=1e-9),17].sum()) for tm in times]
                    tang=[float(np.linalg.norm(wrows[np.isclose(wrows[:,1],tm,atol=1e-9),18:20],axis=1).sum()) for tm in times]
                    perwheel.append(dict(wheel=name,contact_count=stats(counts),normal_N=stats(normal),tangent_N=stats(tang)))
                row=dict(run=folder.name,engine=report['engine'],mujoco=report['mujoco'],toggles=report['toggles'],
                    case=case['id'],axis=case['axis'],pulse_s=case['duration_s'],phase=phase,sim_range=[float(t[start]),float(t[j])],
                    delta_xyyaw=ds.tolist(),translation_mm=float(np.linalg.norm(ds[:2])*1000),yaw_deg=float(np.rad2deg(ds[2])),
                    tilt_initial_deg=tilt(qp[0,ba:ba+7]),tilt_settled_deg=tilt(qp[start,ba:ba+7]),
                    tilt_end_deg=tilt(qp[j,ba:ba+7]),tilt_phase_deg=stats([tilt(s['qpos'][i,ba:ba+7]) for i in selected]),
                    v122_delta=None if pred is None else pred.tolist(),actual_over_v122=None if not predicted else float(actual/predicted),
                    v122_over_actual=None if not predicted or not actual else float(predicted/actual),
                    ideal_from_actual_wheel_angles=ideal.tolist(),wheel_delta_rad=angles.tolist(),
                    no_load_motor_upper_distance_mm=float(r*omega*case['duration_s']*1000),
                    no_load_motor_upper_yaw_deg=float(np.rad2deg(r*omega*case['duration_s']/lever)),
                    wheel_floor=perwheel,contact_point_tangent_slip_m_s=slips(selected),
                    min_wheel_floor_contact_gap_m=None if not len(cr) else float(cr[:,4].min()))
                allrows.append(row)
                print(folder.name,case['id'],phase,round(row['translation_mm'],5),round(row['yaw_deg'],5),round(row['tilt_end_deg'],3),flush=True)
    a.out.mkdir(parents=True,exist_ok=True)
    def dump(name,value):
        raw=(json.dumps(value,indent=2,allow_nan=False)+'\n').encode();path=a.out/name;path.write_bytes(raw)
        if len(raw)>65536:
            import subprocess
            subprocess.run(['zstd','-q','-f',str(path)],check=True)
            restored=subprocess.check_output(['zstd','-dc',str(path)+'.zst'])
            if restored!=raw:raise ValueError('compression round trip')
            path.unlink()
    dump('pulse-table.json',allrows)
    dump('run-index.json',runmeta)
    dump('summary.json',dict(rows=len(allrows),runs=len(runmeta),rejections=rejections,
         mechanics=dict(wheel_radius_m=r,lever_m=lever,omega_no_load_command_rad_s=omega,velocity_no_load_command_m_s=r*omega,
                        basis='existing 65mm wheel and v7 no-load torque-speed model; upper reference, not traction prediction'),
         raw=str(a.runs),fixture=str(a.fixture),reproduce=sys.argv))
    dump('rejection_table.json',dict(stages=[dict(stage='run_results',cumulative_pass_n=len(runmeta),rejected_n=0),
         dict(stage='completed_tapes',cumulative_pass_n=len(runmeta)-len(rejections),rejected_n=len(rejections))],
         reasons=rejections,raw=str(a.runs),reproduce=sys.argv))


if __name__=='__main__':main()
