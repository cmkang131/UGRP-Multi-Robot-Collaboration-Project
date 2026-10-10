"""Evaluation-only, same-qpos comparison. No stepping, rendering or control port."""
from pathlib import Path
import hashlib
import json
import math
import subprocess
import sys
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial.transform import Rotation

ROOT=Path(__file__).resolve().parents[3]
EXP=Path(__file__).resolve().parents[1]
RAW=Path('/Users/changmin/projects/ugrp/outputs/camera-frame-audit-v1')
sys.path.insert(0,str(ROOT))
from harness import servo_camera_fk as fk
from harness import wall_parallax as parallax
from harness.wall_camera_calibration import calibration
from sim.masterpi_camera_profile import scaled_camera_matrix

JOINT_NAMES={6:'arm_yaw',5:'shoulder',4:'elbow',3:'wrist_pitch'}
BASE_RPY=[(0,0,0),(.1,0,0),(0,.1,0),(0,0,.2),(.1,-.1,.2)]
SCENE=Path('/Users/changmin/projects/ugrp/outputs/wall-parallax-texture-v1/tape-north/scene.xml')


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def write(p,value):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def transform(position,rotation):
    t=np.eye(4)
    t[:3,3]=position
    t[:3,:3]=rotation
    return t


def chain(joints,base=None):
    """Evaluate the existing v1 constants at supplied angles (audit only)."""
    spec=fk.model()
    t=transform(spec['floor_to_chassis_translation_m'],np.eye(3)) if base is None else base.copy()
    out={'robot':t.copy()}
    for link in spec['chain']:
        t=t@fk.fixed_transform(link)
        if 'servo' in link:
            t=t@transform([0,0,0],fk.axis_rotation(link['joint_axis'],joints[link['servo']]))
        out[link['name']]=t.copy()
    out['camera_mj']=t@fk.fixed_transform(spec['camera'])
    out['camera_cv']=out['camera_mj']@np.diag([1.,-1.,-1.,1.])
    return out


def pose_grid():
    for key in calibration()['camera_models']['unloaded']:
        servo={1:2000,**dict(zip((3,4,5,6),map(int,key.split(','))))}
        _,original=fk.commanded_joints(servo)
        for joint,delta in [(None,0.)]+[(k,d) for k in (6,5,4,3) for d in (-.05,.05)]:
            q=original.copy()
            if joint is not None:q[joint]+=delta
            valid=all(link['range_rad'][0]<=q[link['servo']]<=link['range_rad'][1]
                for link in fk.model()['chain'] if 'servo' in link)
            for rpy in BASE_RPY:
                yield dict(key=key,servo=servo,joint=joint,delta=delta,rpy=rpy,q=q,valid=valid)


def load_model():
    import mujoco
    return mujoco.MjModel.from_xml_path(str(SCENE))


def model_pose(model,data,q,base):
    import mujoco
    bid=model.body('r3__robot').id
    jid=int(model.body_jntadr[bid])
    assert model.jnt_type[jid]==mujoco.mjtJoint.mjJNT_FREE
    adr=int(model.jnt_qposadr[jid])
    data.qpos[:]=model.qpos0
    data.qpos[adr:adr+3]=base[:3,3]
    quat=Rotation.from_matrix(base[:3,:3]).as_quat()
    data.qpos[adr+3:adr+7]=quat[[3,0,1,2]]
    for servo,name in JOINT_NAMES.items():
        joint=model.joint('r3__'+name).id
        data.qpos[model.jnt_qposadr[joint]]=q[servo]
    mujoco.mj_kinematics(model,data)
    mujoco.mj_camlight(model,data)
    assert data.time==0.
    out={name:transform(data.body('r3__'+name).xpos,data.body('r3__'+name).xmat.reshape(3,3))
        for name in ['robot']+[x['name'] for x in fk.model()['chain']]}
    cam=data.camera('r3__robot_cam')
    out['camera_mj']=transform(cam.xpos,cam.xmat.reshape(3,3))
    out['camera_cv']=out['camera_mj']@np.diag([1.,-1.,-1.,1.])
    return out


def error(a,b):
    return dict(position_m=float(np.linalg.norm(a[:3,3]-b[:3,3])),
        rotation_matrix_max=float(np.abs(a[:3,:3]-b[:3,:3]).max()))


def native_intrinsic(model,camera_id):
    # MuJoCo 3.12 exposes these as model arrays, not named camera view fields.
    value=model.cam_intrinsic[camera_id]
    size=model.cam_sensorsize[camera_id]
    width,height=model.cam_resolution[camera_id]
    return np.array([[value[0]*width/size[0],0,width/2-value[2]*width/size[0]],
        [0,value[1]*height/size[1],height/2-value[3]*height/size[1]],[0,0,1.]])


def static_compare():
    import mujoco
    from sim.masterpi_dynamics_v2 import MasterPiDynamicsV2,_quat_to_rpy
    model=load_model()
    data=mujoco.MjData(model)
    spec=fk.model()
    structural=[]
    parent='robot'
    for link in spec['chain']:
        bid=model.body('r3__'+link['name']).id
        record=dict(name=link['name'],parent=model.body(model.body_parentid[bid]).name,
            fixed_position_max=float(np.abs(model.body_pos[bid]-link['translation_m']).max()),
            fixed_quaternion_max=float(np.abs(model.body_quat[bid]-link['quaternion_wxyz']).max()))
        assert record['parent']=='r3__'+parent
        if 'servo' in link:
            jid=model.joint('r3__'+JOINT_NAMES[link['servo']]).id
            record.update(axis=model.jnt_axis[jid].tolist(),anchor=model.jnt_pos[jid].tolist(),
                qpos_reference=float(model.qpos0[model.jnt_qposadr[jid]]))
            assert np.array_equal(model.jnt_axis[jid],link['joint_axis'])
            assert np.array_equal(model.jnt_pos[jid],np.zeros(3)) and record['qpos_reference']==0.
        structural.append(record)
        parent=link['name']
    cam=model.camera('r3__robot_cam')
    assert model.body(cam.bodyid[0]).name=='r3__gripper'
    structural.append(dict(name='camera_mj',parent='r3__gripper',
        fixed_position_max=float(np.abs(cam.pos-spec['camera']['translation_m']).max()),
        fixed_quaternion_max=float(np.abs(cam.quat-spec['camera']['quaternion_wxyz']).max())))
    rows=[]
    maxima={}
    excluded=0
    pulse_max=yaw_max=0.
    for entry in pose_grid():
        if not entry['valid']:
            excluded+=1
            continue
        original=MasterPiDynamicsV2.pulse_to_joint_targets(SimpleNamespace(physical_params={'servo6_center_pwm':1500.}),entry['servo'])
        q=fk.commanded_joints(entry['servo'])[1]
        pulse_max=max(pulse_max,max(abs(q[s]-original[n]) for s,n in ((6,'yaw'),(5,'shoulder'),(4,'elbow'),(3,'wrist'))))
        base=transform([.3,-.2,.0325],Rotation.from_euler('xyz',entry['rpy']).as_matrix())
        reference=model_pose(model,data,entry['q'],base)
        candidate=chain(entry['q'],base)
        diffs={k:error(v,reference[k]) for k,v in candidate.items()}
        for link,e in diffs.items():
            maxima.setdefault(link,dict(position_m=0.,rotation_matrix_max=0.))
            for key,value in e.items():maxima[link][key]=max(maxima[link][key],value)
        quaternion=Rotation.from_matrix(base[:3,:3]).as_quat()[[3,0,1,2]]
        yaw=_quat_to_rpy(quaternion)[2]
        yaw_max=max(yaw_max,abs(yaw-math.atan2(reference['robot'][1,0],reference['robot'][0,0])))
        rows.append(dict(key=entry['key'],perturbed_servo=entry['joint'],delta_rad=entry['delta'],
            base_rpy=entry['rpy'],qpos_arm=entry['q'],errors=diffs))
    same_qpos=all(max(e.values())<1e-10 for e in maxima.values())
    return dict(model_scene_sha256=sha(SCENE),mujoco=mujoco.__version__,structural=structural,
        poses=len(rows),excluded_outside_joint_range=excluded,max_by_link=maxima,
        pwm_target_max_rad=pulse_max,yaw_formula_max_rad=yaw_max,same_qpos_passed=same_qpos,
        camera_parent='r3__gripper',mj_step_calls=0,rows=rows)


def projection_compare():
    import mujoco
    model=load_model()
    data=mujoco.MjData(model)
    k=scaled_camera_matrix(640,480)
    servo={1:2000,3:740,4:2320,5:1320,6:1500}
    q=fk.commanded_joints(servo)[1]
    origin,rot=fk.transform_from_commands(servo,camera_pose='servo_fk_v1')[0]
    p0=np.array([.3,-.2,.2])
    p1=p0+[-.015,.15,.04]
    cams=[]
    for pose in (p0,p1):
        base=transform([*pose[:2],.0325],parallax.rz(pose[2]))
        cams.append(model_pose(model,data,q,base)['camera_cv'])
    # Known floor and elevated wall points, independent of the detector.
    world=[parallax.rz(p0[2])@np.array([x,y,z])+[*p0[:2],0.]
        for x in (.6,1.,2.) for y in (-.15,0.,.15) for z in (0.,.08)]
    errors=[]
    for w in world:
        uv=[]
        for cam in cams:
            cv=cam[:3,:3].T@(w-cam[:3,3])
            pixel=k@cv
            uv.append(pixel[:2]/pixel[2])
        expected=parallax.rz(p1[2]).T@(w-[*p1[:2],0.])
        actual=parallax.solve(*uv,p0,p1,origin,rot,k)
        errors.append(float(np.linalg.norm(expected-actual)))
    equality=[]
    for pose,cam in zip((p0,p1),cams):
        co,cr=parallax.camera(pose,origin,rot)
        equality.append(error(transform(co,cr),cam))
    c=model.camera('r3__robot_cam')
    # MuJoCo principal point uses OpenGL centered +right/+up. Convert to image +down.
    native=native_intrinsic(model,c.id)
    intrinsic_error=float(np.abs(native-k).max())
    return dict(points=len(world),dlt_max_m=max(errors),world_body_camera_errors=equality,
        intrinsic_max_px=intrinsic_error,opencv_K=k.tolist(),model_K=native.tolist(),
        axis_rule='CV optical = MJ camera @ diag(1,-1,-1); u right/v down, yaw CCW',
        passed=max(errors)<1e-8 and all(max(r.values())<1e-10 for r in equality) and intrinsic_error<1e-4)


def main():
    RAW.mkdir(parents=True,exist_ok=False)
    result=static_compare()
    write(RAW/'same-qpos.json',result)
    small={k:v for k,v in result.items() if k!='rows'}
    projection=projection_compare()
    write(RAW/'projection-conventions.json',projection)
    write(EXP/'results/same-qpos.json',small)
    write(EXP/'results/projection-conventions.json',projection)
    write(RAW/'source.json',dict(sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        hashes={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),EXP/'README.md',EXP/'REFERENCES.md',fk.MODEL,
            ROOT/'harness/servo_camera_fk.py',ROOT/'harness/wall_parallax.py']},physics_steps=0,model_calls=0))
    print(json.dumps(dict(same_qpos=small,projection=projection),indent=2))


if __name__=='__main__':main()
