"""Evaluation-only consistency of inferred joint droop and model gravity."""
import subprocess
import numpy as np
import kinematics_audit as a
from recorded_frames import EPISODES,rows,stats


def descendants(model,root):
    out=[]
    for body in range(1,model.nbody):
        parent=body
        while parent and parent!=root:parent=int(model.body_parentid[parent])
        if parent==root:out.append(body)
    return out


def gravity_moment(axis,anchor,centres,masses,gravity):
    return float(np.sum(np.cross(centres-anchor,masses[:,None]*gravity)@axis))


def main():
    import mujoco
    dest=a.RAW/'gravity-check'
    dest.mkdir(parents=True,exist_ok=False)
    model=a.load_model()
    data=mujoco.MjData(model)
    out={}
    for case in ('tape-north','tape-south'):
        inferred=a.read(a.RAW/'recorded-frames'/f'{case}-frames.json')
        actual={round(r['t'],6):r for r in rows(EPISODES[case]/'eval_only/camera.jsonl')}
        results=[]
        for r in inferred:
            old=actual[r['t']]
            base=a.transform(old['body_xyz'],np.array(old['body_rotation']).reshape(3,3))
            q={int(k):v for k,v in r['eval_inverse_joints_rad'].items()}
            command=a.fk.commanded_joints(r['servo'])[1]
            calculated=a.model_pose(model,data,q,base)
            reference=a.transform(old['camera_xyz'],np.array(old['camera_rotation']).reshape(3,3))
            values={}
            for s,name in ((5,'shoulder'),(4,'elbow'),(3,'wrist')):
                joint=model.joint('r3__'+a.JOINT_NAMES[s]).id
                actuator=model.actuator('r3__servo_'+name).id
                ids=descendants(model,int(model.jnt_bodyid[joint]))
                gravity=gravity_moment(data.xaxis[joint],data.xanchor[joint],data.xipos[ids],model.body_mass[ids],model.opt.gravity)
                kp=float(model.actuator_gainprm[actuator,0])
                assert model.actuator_biasprm[actuator,1]==-kp
                torque=kp*(command[s]-q[s])
                values[str(s)]=dict(kp_nm_rad=kp,command_error_deg=float(np.degrees(command[s]-q[s])),
                    position_servo_static_nm=torque,gravity_nm=gravity,residual_nm=torque+gravity,
                    gravity_equivalent_error_deg=float(np.degrees(-gravity/kp)))
            results.append(dict(frame_id=r['frame_id'],t=r['t'],joints=values,
                camera_mj_error=a.error(calculated['camera_mj'],reference),qpos_is_evaluation_inverse=True))
        a.write(dest/(case+'.json'),results)
        out[case]=dict(frames=len(results),frame35=next(r for r in results if r['frame_id']==35),
            camera_position_max_m=max(r['camera_mj_error']['position_m'] for r in results),
            camera_rotation_matrix_max=max(r['camera_mj_error']['rotation_matrix_max'] for r in results),
            joints={s:{key:stats([r['joints'][s][key] for r in results]) for key in results[0]['joints'][s]}
                for s in ('5','4','3')})
    a.write(dest/'source.json',dict(sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        source_sha256=a.sha(__file__),registration_sha256=a.sha(a.EXP/'GRAVITY_CHECK.md'),physics_steps=0,fit=False))
    a.write(a.EXP/'results/gravity-check.json',out)
    print({k:v['frame35'] for k,v in out.items()})


if __name__=='__main__':main()
