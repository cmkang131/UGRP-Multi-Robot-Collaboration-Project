"""Default-off two-tick actuator transport check; no ACT/teacher task score."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--enabled',action='store_true')
    for name in ('physics-python','api-source','qualified-source','teacher-source','qualification',
                 'references','compiled-reference','compiled-geometry','plans','out'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    if not a.enabled or sys.platform!='linux':p.error('default OFF, Linux gcp2 only')
    sys.path.insert(0,str(a.api_source/'scripts'))
    from warp_act_rpc import Client
    sys.path.insert(0,str(a.teacher_source))
    from harness.grasp_act_contract import command as validate_command, SERVOS
    # Exact frozen command() range:0 or absolute fraction0.31..0.40.
    # 0.40 is the allowed endpoint (40%), not a new controller threshold.
    drive=.40
    validate_command(dict(t=0.,wheels=[drive]*4,duration_s=[.1]*4,pwm={str(s):1500 for s in SERVOS}))
    import numpy as np
    import mujoco
    plans=json.loads(a.plans.read_text())['episodes'][:2]
    if len(plans)!=2:p.error('two compatible independent starts required')
    options={k:getattr(a,k) for k in ('qualified_source','teacher_source','qualification','references','compiled_reference','compiled_geometry')}
    c=Client(python=a.physics_python,out=a.out,nworld=2,enabled=True,audit_state=True,**options)
    report=dict(status='running',passed=False,scope='actuator transport diagnostic, not ACT performance or teacher gate',
                independent_teacher_N=0,probe_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    try:
        c.reset(plans)
        model=mujoco.MjModel.from_xml_string((a.out/'owner/world-000/scene.xml').read_text())
        wheels=[i for i in range(model.nu) if model.actuator(i).name.startswith('r1__wheel_')]
        if len(wheels)!=4:raise RuntimeError('expected exact four-wheel command interface')
        joint=int(model.body_jntadr[model.body('r1__robot').id]);pos=int(model.jnt_qposadr[joint])
        if model.jnt_type[joint]!=mujoco.mjtJoint.mjJNT_FREE:raise RuntimeError('expected free-base position metadata')
        with np.load(a.out/'owner/state-latest.npz') as z:before=z['qpos'].copy()
        # Existing0.1SIM RPC quantum and allowed command endpoint0.40.
        # Fixed two transactions, same count as the ACT smoke; no feedback
        # chooses commands and no new physical success tolerance is introduced.
        for _ in range(2):
            actions=[]
            for i in range(2):
                obs,_=c.read_actor(i);command=deepcopy(obs['issued'][-1]);command['t']=obs['t']
                command.update(wheels=[drive if i==0 else 0.]*4,duration_s=[.1 if i==0 else 0.]*4)
                actions.append(dict(command=command,done=False))
            c.step(actions)
        with np.load(a.out/'owner/state-latest.npz') as z:after=z['qpos'].copy();ctrl=z['ctrl'][:,wheels].copy()
        if not np.all(ctrl[0]!=0.) or not np.all(ctrl[1]==0.):raise RuntimeError('world-local wheel command did not reach GPU ctrl')
        report.update(status='complete',passed=True,wheel_actuator_names=[model.actuator(i).name for i in wheels],
                      gpu_wheel_ctrl=ctrl.tolist(),body_xy_delta_m=(after[:,pos:pos+2]-before[:,pos:pos+2]).tolist(),
                      camera='own native640x480/10Hz',command_ticks=2)
    except BaseException as error:report.update(status='HOST_ERROR',error=repr(error));raise
    finally:
        try:c.close('command_probe_control_budget_end')
        except BaseException as error:report.update(status='HOST_ERROR',passed=False,close_error=repr(error))
        report['raw_sha256']={str(x.relative_to(a.out)):hashlib.sha256(x.read_bytes()).hexdigest() for x in a.out.rglob('*') if x.is_file()}
        (a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
