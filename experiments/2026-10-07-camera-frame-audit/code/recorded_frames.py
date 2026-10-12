"""Evaluation-only saved camera/robot frame audit. Never a robot pose source."""
from collections import defaultdict
from pathlib import Path
import math
import subprocess
import sys
import numpy as np
from scipy.spatial.transform import Rotation
import kinematics_audit as a

sys.path.insert(0,str(a.ROOT/'experiments/2026-10-05-ego-wall-map-probe/code'))
import v3_confidence_replay as old
from harness.self_odom_grid import motion_profiles
from harness.servo_camera_fk import commanded_joints,transform_from_commands

EPISODES={**old.EPISODES,
    's1050':Path('/Users/changmin/projects/ugrp/outputs/s2-realism-97fcb5d2-s1050-P1-2-place'),
    's1051':Path('/Users/changmin/projects/ugrp/outputs/s2-realism-c26e9afd-s1051-P1-2-place'),
    **{name:Path('/Users/changmin/projects/ugrp/outputs/wall-parallax-texture-v1')/name for name in ('tape-north','tape-south')}}


def rows(p):return old.base.read_rows(p)
def wrap(v):return (v+np.pi)%(2*np.pi)-np.pi
def pitch(r):return math.atan2(r[2,2],math.hypot(r[0,2],r[1,2]))
def stats(v):
    x=np.asarray(v,float)
    return dict(n=len(x),median=float(np.median(x)) if len(x) else None,
        p05=float(np.quantile(x,.05)) if len(x) else None,p95=float(np.quantile(x,.95)) if len(x) else None,
        max_abs=float(np.abs(x).max()) if len(x) else None)


def inverse_camera_chain(camera_cv,base,qcommand):
    """Analytic pose-inverse diagnostic, NOT recorded encoders or a control input.

    Camera mount is held at the model value. Root pose comes from evaluation.
    Planar two-link IK's branch is selected nearest commanded elbow angle.
    """
    mount=a.fk.fixed_transform(a.fk.model()['camera'])
    gripper=np.linalg.inv(base)@camera_cv@np.diag([1.,-1.,-1.,1.])@np.linalg.inv(mount)
    rot=gripper[:3,:3]
    yaw=math.atan2(-rot[0,1],rot[1,1])
    origin=np.array([.0482,0.,.0605+.0347])
    point=a.parallax.rz(-yaw)@(gripper[:3,3]-origin)
    x,_,z=point
    l2,l3=.065,.062
    cos=(x*x+z*z-l2*l2-l3*l3)/(2*l2*l3)
    if abs(cos)>1.+1e-8:return None
    elbows=[math.acos(np.clip(cos,-1,1)),-math.acos(np.clip(cos,-1,1))]
    elbow=min(elbows,key=lambda q:abs(wrap(q-qcommand[4])))
    shoulder=math.atan2(z,x)-math.atan2(l3*math.sin(elbow),l2+l3*math.cos(elbow))
    local=a.parallax.rz(-yaw)@rot
    total=math.atan2(local[2,0],local[0,0])
    wrist=wrap(total-shoulder-elbow)
    q={6:yaw,5:shoulder,4:elbow,3:wrist}
    reconstructed=a.chain(q,base)['camera_cv']
    return q,a.error(reconstructed,camera_cv)


def audit_case(case,ep,dest):
    frames=rows(ep/'robots/r3/frames.jsonl')
    camera_path=ep/'eval_only'/('camera.jsonl' if case.startswith('tape-') else 'camera-pose.jsonl')
    source_paths=[ep/'scene.xml',ep/'robots/r3/frames.jsonl',ep/'robots/r3/commands.jsonl',ep/'eval_only/trajectory.jsonl']
    if not camera_path.exists():return dict(case=case,actual_camera='NA',recorded_joint_qpos='NA')
    source_paths.append(camera_path)
    cameras={round(r['t'],6):r for r in rows(camera_path)}
    bodies={round(r['t'],6):r for r in rows(ep/'eval_only/trajectory.jsonl')}
    command_chain=[]
    # Predictions are serialized before accessing each frame's evaluation pose.
    for f in frames:
        servo={int(k):v for k,v in f['commanded_servo'].items()}
        _,q=commanded_joints(servo)
        t=a.chain(q)['camera_cv']
        command_chain.append(dict(frame_id=f['frame_id'],t=f['sim_time'],servo=servo,q=q,
            transform=t.tolist(),runtime_admitted=servo[1]>1600))
    pred=dest/(case+'-command-fk.json')
    a.write(pred,command_chain)
    seal=a.sha(pred)
    result=[]
    groups=defaultdict(lambda:defaultdict(list))
    interpolation=0
    for f,prediction in zip(frames,command_chain):
        servo=prediction['servo']
        pulse=f.get('actuator_state',{}).get('servo_pulses',{})
        different=any(int(pulse.get(str(k),v))!=v for k,v in servo.items())
        interpolation+=different
        t=round(f['sim_time'],6)
        if t not in cameras or t not in bodies:continue
        row=cameras[t]
        body=bodies[t]
        ryaw=a.parallax.rz(body['robot_yaw_rad'])
        level=a.transform([*body['robot_xyz_m'][:2],0.],ryaw)
        actual=(a.transform(row['camera_xyz'],np.array(row['camera_rotation']).reshape(3,3))@np.diag([1.,-1.,-1.,1.])
            if case.startswith('tape-') else a.transform(row['camera_from_body_xyz_m'],np.array(row['camera_from_body_optical_rotation'])))
        local=np.linalg.inv(level)@actual
        nominal=np.array(prediction['transform'])
        item=dict(frame_id=f['frame_id'],t=t,servo=servo,commanded_vs_port_pwm_different=different,
            runtime_admitted=prediction['runtime_admitted'],actual_pitch_deg=math.degrees(pitch(local[:3,:3])),
            command_pitch_deg=math.degrees(pitch(nominal[:3,:3])),
            pitch_actual_minus_command_deg=math.degrees(wrap(pitch(local[:3,:3])-pitch(nominal[:3,:3]))),
            height_actual_minus_command_mm=1000*(local[2,3]-nominal[2,3]),
            position_actual_minus_command_mm=(1000*(local[:3,3]-nominal[:3,3])).tolist(),
            recorded_joint_qpos=False)
        if case.startswith('tape-'):
            base=a.transform(row['body_xyz'],np.array(row['body_rotation']).reshape(3,3))
            base_angles=Rotation.from_matrix(base[:3,:3]).as_euler('xyz')
            item['body_roll_pitch_deg']=np.degrees(base_angles[:2]).tolist()
            item['yaw_log_minus_body_matrix_deg']=math.degrees(wrap(body['robot_yaw_rad']-base_angles[2]))
            body_local=np.linalg.inv(base)@actual
            item['pitch_body_relative_actual_minus_command_deg']=math.degrees(wrap(pitch(body_local[:3,:3])-pitch(nominal[:3,:3])))
            item['pitch_body_attitude_contribution_deg']=item['pitch_actual_minus_command_deg']-item['pitch_body_relative_actual_minus_command_deg']
            inverse=inverse_camera_chain(actual,base,prediction['q'])
            if inverse is not None:
                q,err=inverse
                item['eval_inverse_joints_rad']=q
                item['eval_inverse_joint_minus_command_deg']={s:math.degrees(wrap(v-prediction['q'][s])) for s,v in q.items()}
                item['inverse_camera_residual']=err
        else:
            gripper=a.transform(row['gripper_xyz_m'],np.array(row['gripper_rotation']).reshape(3,3))
            expected=gripper@a.fk.fixed_transform(a.fk.model()['camera'])@np.diag([1.,-1.,-1.,1.])
            item['actual_mount_error']=a.error(expected,actual)
            cached=a.transform(row['camera_cached_xyz_m'],np.array(row['camera_cached_optical_rotation']))
            item['cached_camera_error']=a.error(cached,actual)
        for group in ['all',('open' if servo[1]>1600 else 'closed'),','.join(str(servo[k]) for k in (3,4,5,6))]:
            for key,value in item.items():
                if isinstance(value,float):groups[group][key].append(value)
            for k,value in item.get('eval_inverse_joint_minus_command_deg',{}).items():
                groups[group]['eval_inverse_servo_'+str(k)+'_minus_command_deg'].append(value)
            for k,value in item.get('actual_mount_error',{}).items():groups[group]['mount_'+k].append(value)
            for k,value in item.get('cached_camera_error',{}).items():groups[group]['cache_'+k].append(value)
        result.append(item)
    a.write(dest/(case+'-frames.json'),result)
    assert a.sha(pred)==seal
    return dict(case=case,frames=len(frames),joined=len(result),recorded_joint_qpos='NA',
        actual_base_full_rotation=case.startswith('tape-'),command_port_pwm_different=interpolation,
        prediction_sha256=seal,source_hashes={str(p):a.sha(p) for p in source_paths},
        groups={k:{j:stats(v) for j,v in g.items()} for k,g in groups.items()})


def yaw_audit(case,ep):
    frames=rows(Path('/Users/changmin/projects/ugrp/outputs/wall-parallax-texture-v1/replay/parallax_v1')/case/'predictions.jsonl')
    body={round(r['t'],6):r for r in rows(ep/'eval_only/trajectory.jsonl')}
    commands=rows(ep/'robots/r3/commands.jsonl')
    first=body[round(frames[0]['t'],6)]
    output=[]
    for f in frames:
        b=body[round(f['t'],6)]
        output.append(dict(frame_id=f['frame_id'],t=f['t'],dr_yaw_rad=f['pose'][2],
            actual_yaw_from_start_rad=float(wrap(b['robot_yaw_rad']-first['robot_yaw_rad']))))
    pairs={r['frame_id']:r for r in output}
    x,y=pairs[35],pairs[53]
    issued=[r for r in commands if r['kind'] in ('drive','mecanum')]
    gain=np.array(motion_profiles()['motion']['gain'])
    cmd_components=[dict(t=r['t'],forward=r['forward'],left=r.get('left',0.),turn=r['turn'],
        target_yaw_rad_s_by_axis=(gain[2]*[r['forward'],r.get('left',0.),r['turn']]).tolist()) for r in issued]
    return dict(case=case,gain_yaw_row=gain[2].tolist(),nonzero_turn_commands=sum(r['turn']!=0. for r in issued),
        original_accepted_pair=dict(frame_ids=[35,53],times=[x['t'],y['t']],
            dr_delta_yaw_deg=math.degrees(wrap(y['dr_yaw_rad']-x['dr_yaw_rad'])),
            actual_delta_yaw_deg=math.degrees(wrap(y['actual_yaw_from_start_rad']-x['actual_yaw_from_start_rad']))),
        commands=cmd_components,frames=output,convention_corrected=False,adopted=False)


def main():
    dest=a.RAW/'recorded-frames'
    dest.mkdir(parents=True,exist_ok=False)
    out={case:audit_case(case,ep,dest) for case,ep in EPISODES.items()}
    yaw={case:yaw_audit(case,EPISODES[case]) for case in ('tape-north','tape-south')}
    a.write(dest/'summary.json',out)
    a.write(dest/'yaw.json',yaw)
    a.write(dest/'source.json',dict(sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        hashes={str(p.relative_to(a.ROOT)):a.sha(p) for p in (Path(__file__),Path(a.__file__))},
        own_control_inputs_added=False,physics_steps=0,model_calls=0))
    a.write(a.EXP/'results/recorded-frames.json',out)
    a.write(a.EXP/'results/yaw-summary.json',{case:{k:v for k,v in r.items() if k!='frames'} for case,r in yaw.items()})
    for case,row in out.items():
        group=row.get('groups',{}).get('all',{})
        print(case,row.get('joined',0),group.get('pitch_actual_minus_command_deg'),flush=True)
    print({k:v['original_accepted_pair'] for k,v in yaw.items()},flush=True)


if __name__=='__main__':main()
