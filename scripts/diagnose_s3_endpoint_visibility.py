"""Evaluation-only saved camera/qpos projection. Never imported by control code."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import numpy as np
from sim.masterpi_camera_profile import scaled_camera_matrix


def project(points, position, rotation):
    # MuJoCo camera +x right,+y up,-z forward -> OpenCV optical frame.
    camera=(np.asarray(points)-position)@np.asarray(rotation).reshape(3,3)
    camera*=np.array([1.,-1.,-1.])
    uv=camera@scaled_camera_matrix(640,480).T
    uv=uv[:,:2]/uv[:,2:]
    inside=(camera[:,2]>0)&(uv[:,0]>=0)&(uv[:,0]<640)&(uv[:,1]>=0)&(uv[:,1]<480)
    return uv,inside


def events(x):
    if isinstance(x,dict):
        if x.get('event')=='beam_obs':yield x
        else:
            for v in x.values():yield from events(v)
    elif isinstance(x,list):
        for v in x:yield from events(v)


def diagnose(raw,out):
    import mujoco
    model=mujoco.MjModel.from_xml_path(str(raw/'scene.xml'));data=mujoco.MjData(model)
    obs=list(events(json.loads((raw/'student_record.json').read_text())))
    result={};out.mkdir(parents=True,exist_ok=False)
    for rid in ('r1','r2'):
        cameras={round(r['t'],6):r for r in map(json.loads,(raw/f'eval_only/{rid}/render_camera.jsonl').read_text().splitlines())}
        rows=[]
        for e in obs:
            if e['robot_id']!=rid:continue
            cam=cameras.get(round(e['sim_s'],6))
            if cam is None:raise ValueError('missing exact saved render pose')
            data.qpos[:]=cam['joint_qpos'];mujoco.mj_forward(model,data)
            ids=[mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_GEOM,'cargo_beam_1__band_'+s) for s in ('neg','pos')]
            g=min(ids,key=lambda g:np.linalg.norm(data.geom_xpos[g]-cam['world_position_m']))
            size=model.geom_size[g]
            local=np.array([[0.,0.,size[2]],*[[sx*size[0],sy*size[1],size[2]] for sx in (-1,1) for sy in (-1,1)]])
            world=local@data.geom_xmat[g].reshape(3,3).T+data.geom_xpos[g]
            uv,inside=project(world,cam['world_position_m'],cam['world_rotation'])
            category='visible' if e['end_visible'] else ('fov_clipped' if not inside.all() else 'in_fov_rejected')
            rows.append(dict(t=e['sim_s'],render_index=cam['render_index'],reason=e['reason'],category=category,
                band_center_inside=bool(inside[0]),band_corners_inside=int(inside[1:].sum()),
                pinhole_px=uv.tolist(),evaluated_gt_only=True))
        (out/f'{rid}.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
        result[rid]=dict(frames=len(rows),categories=dict(Counter(r['category'] for r in rows)),
            rejection_reasons=dict(Counter(r['reason'] for r in rows if r['category']!='visible')),
            rejected_center_outside=sum(not r['band_center_inside'] for r in rows if r['category']!='visible'))
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--cohort',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if platform.system()!='Linux' or platform.machine()!='x86_64':raise RuntimeError('saved replay only on oracle-x86')
    a.output.mkdir(parents=True,exist_ok=False)
    result={raw.parent.name:diagnose(raw,a.output/raw.parent.name) for raw in sorted(a.cohort.glob('*pair*/raw'))}
    (a.output/'summary.json').write_text(json.dumps(dict(host='oracle-x86',eval_only=True,cases=result),indent=2)+'\n')
    print(json.dumps(result))

if __name__=='__main__':main()
