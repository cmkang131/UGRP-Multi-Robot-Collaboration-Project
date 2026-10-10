"""Preregistered open-loop system identification; no student or GT feedback."""
import argparse,hashlib,json,math,time,traceback,os,platform
from pathlib import Path
import numpy as np
from scripts import run_s3_x86_probe as stage
from scripts.run_final_environment_checks import write
from scripts.run_s3_host import artifact_manifest
from sim.s3_visual_trim import PhysicsBackend,OPTION,DURATIONS


def sequence():
    return [dict(kind='mecanum',forward=0.,left=0.,turn=0.,duration_s=duration,**{})
        | {axis:sign*.35} for repeat in range(2) for duration in DURATIONS
        for axis in ('forward','left','turn') for sign in (1,-1)]


def pose(host,rid):
    b=host.world.data.body(rid+'__robot')
    return np.array([b.xpos[0],b.xpos[1],math.atan2(b.xmat[3],b.xmat[0])])


def measurement_setup(condition):
    from harness.owncam_pair_beam_v2 import pose_of
    setup=stage.varied_setup('pair',condition)
    for i,rid in enumerate(('r1','r2','r3')):
        row=setup['robots'][rid];p=row['pose'];p['robot_xyz_m'][:]=[2.8+.9*i,-1.,.0325]
        p['robot_yaw_rad']=(-.12,0.,.12)[condition%3]
        row['frame']['commanded_servo']={1:2000,**pose_of('inspect')}
    return setup


def run(sha,condition,out,*,path_check=False):
    b=stage.bundle(sha,'pair',condition=condition)
    b.update(execution_bundle_id='zone-s3-x86-pulse-measure-v157',workflow_version='7.50.0',
        schema='ugrp.s3_pulse_measure.v157',visual_trim=OPTION,
        student_control=False,concurrent_probe_limit=10,path_check=path_check,
        measurement='unloaded inspect posture; fixed command sequence; GT evaluation only')
    from harness.python_source_closure import source_closure
    for p in source_closure(stage.ROOT,['scripts/run_s3_x86_pulse_measure.py']):
        b['source_sha256'][p]=hashlib.sha256((stage.ROOT/p).read_bytes()).hexdigest()
    b['source_sha256']['configs/simulation_workflows.d/s3_x86_pulse_measure_v157.json']=hashlib.sha256((stage.ROOT/'configs/simulation_workflows.d/s3_x86_pulse_measure_v157.json').read_bytes()).hexdigest()
    out.mkdir(parents=True,exist_ok=False);write(out/'bundle.json',b)
    write(out/'environment.json',dict(host='oracle-x86',machine=platform.machine(),logical_cpus=os.cpu_count(),
        concurrent_probe_limit=10,loadavg_start=os.getloadavg(),MUJOCO_GL=os.environ.get('MUJOCO_GL')))
    host=None;rows=[];started=time.monotonic()
    result=dict(status='HOST_ERROR',host='oracle-x86',source_sha=sha,condition=condition,
        student_control=False,research_result=False,model_calls=0,path_check=path_check,
        sequence=sequence()[:6] if path_check else sequence())
    try:
        host=PhysicsBackend(b,out,seed=b['seed']);host.reset(b['reset_cap_s'])
        setup=measurement_setup(condition)
        # Empty east room, fixed setup owner; no feedback or correction during acquisition.
        stage.previous.restore_scene(host,setup)
        start=host.now;host.set_deadline(start+60.)
        for index,action in enumerate(result['sequence']):
            t=host.now;origins={r:pose(host,r) for r in ('r1','r2','r3')}
            curves={r:[] for r in origins};times=np.round(np.arange(0,.501,.01),8)
            for rid in origins:host.issue(rid,action)
            for dt in times:
                host.advance_to(round(t+float(dt),9));host.eval_sample()
                for rid,q0 in origins.items():
                    q=pose(host,rid);d=q-q0;c,s=math.cos(q0[2]),math.sin(q0[2])
                    curves[rid].append([c*d[0]+s*d[1],-s*d[0]+c*d[1],math.atan2(math.sin(d[2]),math.cos(d[2]))])
            rows.extend(dict(index=index,robot=rid,t=t,action=action,times=times.tolist(),curve=curve,
                measurement='eval_only body displacement; never returned to a controller') for rid,curve in curves.items())
        result.update(status='COLLECTED_UNQUALIFIED',sim_s=host.now-start,rows=len(rows))
    except Exception:result['failure']=traceback.format_exc()
    finally:
        if host:host.close()
        result['wall_s']=time.monotonic()-started
        write(out/'result.json',result)
        (out/'pulse-responses.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
        artifact_manifest(out)
    return result


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--condition',type=int,choices=range(6),default=0)
    p.add_argument('--path-check',action='store_true')
    p.add_argument('--execute',action='store_true');a=p.parse_args(argv)
    if not a.execute:print(json.dumps(dict(execution_started=False,host='oracle-x86',bundle_id='zone-s3-x86-pulse-measure-v157')));return 0
    stage.archive_guard(a.expected_source_sha,a.output)
    result=run(a.expected_source_sha,a.condition,a.output,path_check=a.path_check)
    print(json.dumps(result));return int(result['status']=='HOST_ERROR')


if __name__=='__main__':raise SystemExit(main())
