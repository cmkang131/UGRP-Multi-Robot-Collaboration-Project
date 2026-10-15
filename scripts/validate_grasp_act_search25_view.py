"""GCP pinhole/fisheye projection plus saved-state render, no physics steps."""
import argparse
import hashlib
import json
from pathlib import Path
import cv2
import mujoco
import numpy as np
from PIL import Image
from sim.masterpi_camera_profile import scaled_camera_matrix,CAMERA_FISHEYE_D
from sim.grasp_act_search25 import in_frame,VIEW_HALF_X_DEG,VIEW_HALF_Y_DEG
from scripts.replay_grasp_act_search18 import read
from scripts.audit_grasp_act_visibility import BandVisibility


def validate(root,out):
    out.mkdir(parents=True,exist_ok=True);K=scaled_camera_matrix(640,480);D=np.array(CAMERA_FISHEYE_D)
    # Include every boundary/corner of the proposed reserved rectangle.
    points=np.array([(x,y,1.) for x in np.linspace(-np.tan(np.deg2rad(VIEW_HALF_X_DEG)),np.tan(np.deg2rad(VIEW_HALF_X_DEG)),49)
                     for y in np.linspace(-np.tan(np.deg2rad(VIEW_HALF_Y_DEG)),np.tan(np.deg2rad(VIEW_HALF_Y_DEG)),37)])
    uv=points[:,:2]*np.diag(K)[:2]+K[:2,2]
    raw,_=cv2.fisheye.projectPoints(points.reshape(-1,1,3),np.zeros(3),np.zeros(3),K,D);raw=raw.reshape(-1,2)
    fits=lambda q:(q[:,0]>=0)&(q[:,0]<640)&(q[:,1]>=0)&(q[:,1]<480)
    report={'scope':'reserved frame projection + saved-state actual MuJoCo renderer; no dynamics',
            'grid_N':len(points),'outside_pinhole_N':int((~fits(uv)).sum()),'outside_fisheye_N':int((~fits(raw)).sum()),
            'half_fov_deg':[VIEW_HALF_X_DEG,VIEW_HALF_Y_DEG],'samples':[]}
    for p in sorted(root.glob('diagnostic*/episode-*/raw')):
        result=json.loads(read(p/'result.json'));plan=json.loads(read(p/'plan.json'))
        ev=[json.loads(x) for x in read(p/'eval-only.jsonl').splitlines()]
        m=mujoco.MjModel.from_xml_path(str(p/'scene.xml'));v=BandVisibility(m);v.restore_recorded_runtime_mount();data=mujoco.MjData(m)
        for i in sorted({round((len(ev)-1)*k/4) for k in range(5)}):
            data.qpos[:]=ev[i]['joints'];mujoco.mj_forward(m,data)
            for rid,end in plan['roles'].items():
                cid=v.cameras[rid];gid=v.bands[end]
                xyz=data.geom_xpos[gid]+v.probes[end]@data.geom_xmat[gid].reshape(3,3).T
                optical=((xyz-data.cam_xpos[cid])@data.cam_xmat[cid].reshape(3,3))*np.array([1.,-1.,-1.])
                n=int(sum(in_frame(q) for q in optical))
                report['samples'].append({'episode':p.parent.name,'rid':rid,'t':ev[i]['t'],
                                          'new_rectangle_probes':n,'actual_render_frame':v.measure(data,rid,end)})
        if not result['physical_success']:
            renderer=mujoco.Renderer(m,height=480,width=640);renderer.update_scene(data,camera='r1__robot_cam')
            target=out/(p.parent.name+'-render-check.jpg');Image.fromarray(renderer.render()).save(target)
            renderer.close();report.setdefault('rendered_failed_frames',[]).append({'path':str(target),
                'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
    assert report['outside_pinhole_N']==report['outside_fisheye_N']==0
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='samples'}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();validate(a.root,a.out)
