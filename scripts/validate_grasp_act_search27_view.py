"""GCP saved-state renderer + analytic/OpenCV frame parity; no dynamics."""
import argparse
import hashlib
import json
from pathlib import Path
import cv2
import mujoco
import numpy as np
from PIL import Image
from sim.masterpi_camera_profile import scaled_camera_matrix,CAMERA_FISHEYE_D
from sim.grasp_act_search27 import in_frame,frame_pixels
from scripts.analyze_grasp_act_search24 import read
from scripts.audit_grasp_act_visibility import BandVisibility


def validate(raw,out):
    out.mkdir(parents=True,exist_ok=True);K=scaled_camera_matrix(640,480);D=np.array(CAMERA_FISHEYE_D)
    points=np.array([(x,y,1.) for x in np.linspace(-.7,.7,71) for y in np.linspace(-.6,.6,61)])
    uv=points[:,:2]*np.diag(K)[:2]+K[:2,2]
    fish,_=cv2.fisheye.projectPoints(points.reshape(-1,1,3),np.zeros(3),np.zeros(3),K,D);fish=fish.reshape(-1,2)
    fits=lambda q:(q[:,0]>=0)&(q[:,0]<640)&(q[:,1]>=0)&(q[:,1]<480)
    expected=fits(uv)&fits(fish);predicted=np.array([in_frame(q) for q in points])
    assert np.array_equal(expected,predicted)
    error=max(float(np.max(np.abs(np.array([frame_pixels(q)[1] for q in points])-fish))),
              float(np.max(np.abs(np.array([frame_pixels(q)[0] for q in points])-uv))))
    ev=[json.loads(x) for x in read(raw/'eval-only.jsonl').splitlines()];plan=json.loads(read(raw/'plan.json'))
    m=mujoco.MjModel.from_xml_path(str(raw/'scene.xml'));v=BandVisibility(m);v.restore_recorded_runtime_mount();data=mujoco.MjData(m)
    samples=[];artifacts=[]
    renderer=mujoco.Renderer(m,height=480,width=640)
    for i in sorted({0,len(ev)//2,len(ev)-1}):
        data.qpos[:]=ev[i]['joints'];mujoco.mj_forward(m,data)
        for rid,end in plan['roles'].items():
            cid=v.cameras[rid];gid=v.bands[end]
            xyz=data.geom_xpos[gid]+v.probes[end]@data.geom_xmat[gid].reshape(3,3).T
            optical=((xyz-data.cam_xpos[cid])@data.cam_xmat[cid].reshape(3,3))*np.array([1.,-1.,-1.])
            n=int(sum(in_frame(q) for q in optical));actual=v.measure(data,rid,end)
            # Include the renderer near plane, which cannot be inferred from a hypothetical future view.
            near_n=int(sum(in_frame(q) and q[2]>v.near for q in optical))
            assert near_n==actual['in_frame_probes']
            samples.append({'sample':i,'rid':rid,'predicted_in_frame':n,'near_clipped_in_frame':near_n,'actual_frame':actual})
            renderer.update_scene(data,camera=rid+'__robot_cam');p=out/f'{i:06d}-{rid}.jpg';Image.fromarray(renderer.render()).save(p)
            artifacts.append({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    renderer.close()
    report={'raw':str(raw),'grid_N':len(points),'frame_mismatches':0,'max_pixel_error':error,
        'render_N':len(artifacts),'samples':samples,'artifacts':artifacts,
        'scope':'same K-pinhole AND fisheye frame as renderer pipeline; saved-state render, no physics; future occlusion not proven'}
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ('samples','artifacts')}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('raw',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();validate(a.raw,a.out)
