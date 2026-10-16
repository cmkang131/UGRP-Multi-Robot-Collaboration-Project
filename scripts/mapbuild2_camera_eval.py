"""Evaluator-only camera sag audit. Closed nominal is NEVER an actor calibration."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import numpy as np


def nominal_unqualified(servo):
    from harness.servo_camera_fk import model,commanded_joints,fixed_transform,axis_rotation
    spec=model();_,joints=commanded_joints(servo);t=np.eye(4)
    t[:3,3]=spec['floor_to_chassis_translation_m']
    for link in spec['chain']:
        t=t@fixed_transform(link)
        if 'servo' in link:
            joint=np.eye(4);joint[:3,:3]=axis_rotation(link['joint_axis'],joints[link['servo']]);t=t@joint
    t=t@fixed_transform(spec['camera'])
    return t[:3,3],t[:3,:3]@np.diag([1.,-1.,-1.])


def run(a):
    sys.path.insert(0,str(a.vision_source))
    import mujoco
    from scripts import probe_scene_tex2 as scene_tools
    from scripts.generate_scene_textures import MAPS
    from harness.servo_camera_fk import transform_from_commands
    m,scene,hw,xml,audit=scene_tools.build_model(MAPS[0],'walls_floor_contrast_v5_indigo110_s80')
    d=mujoco.MjData(m);body=m.body('r1__robot').id;camera=m.camera('r1__robot_cam').id
    qpos=np.load(a.input/'eval-state.npz')['qpos']
    manifest=json.loads((a.input/'own.json').read_text());names=list(dict.fromkeys(r['sequence'] for r in manifest['frames']))
    rows=[]
    for frame in manifest['frames']:
        index=names.index(frame['sequence']);d.qpos[:]=qpos[frame['frame_id'],index];mujoco.mj_forward(m,d)
        servo={int(k):v for k,v in frame['servo'].items()};qualification=transform_from_commands(servo,camera_pose='servo_fk_v1')[1]
        origin,rotation=nominal_unqualified(servo)
        body_r=d.xmat[body].reshape(3,3)
        actual_r=body_r.T@d.cam_xmat[camera].reshape(3,3)@np.diag([1.,-1.,-1.])
        actual_origin=body_r.T@(d.cam_xpos[camera]-d.xpos[body])
        # Structural FK includes nominal floor-to-body height; compare camera
        # relative translation using that same structural offset convention.
        from harness.servo_camera_fk import model
        nominal_local=origin-np.asarray(model()['floor_to_chassis_translation_m'])
        angle=math.degrees(math.acos(float(np.clip((np.trace(rotation.T@actual_r)-1)/2,-1,1))))
        rows.append(dict(sequence=frame['sequence'],frame_id=frame['frame_id'],t=frame['t'],
            qualification=qualification,camera_floor_height_m=float(d.cam_xpos[camera,2]),
            nominal_floor_height_m=float(origin[2]),relative_translation_error_m=float(np.linalg.norm(actual_origin-nominal_local)),
            relative_orientation_error_deg=angle,body_floor_height_m=float(d.xpos[body,2])))
    def stats(values):return dict(p50=float(np.median(values)),p95=float(np.percentile(values,95)),max=float(max(values)))
    summary={name:{key:stats([r[key] for r in rows if r['sequence']==name]) for key in
        ('relative_translation_error_m','relative_orientation_error_deg','camera_floor_height_m','body_floor_height_m')} for name in names}
    a.output.write_text(json.dumps(dict(scope='evaluation-only; actual carried load not exercised; no runtime calibration produced',
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),summary=summary,frames=rows),indent=2,allow_nan=False)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True)
    p.add_argument('--vision-source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('NEW_EVALUATOR_OUTPUT_REQUIRED')
    run(a)
