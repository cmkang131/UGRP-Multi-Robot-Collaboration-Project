"""gcp2-only windowless review: full2Hz + terminal10Hz, ffmpeg3x, ffprobe.

World0's MJWarp ring supplies recorded own RGB when available. Missing earlier
views and C references are explicitly marked C reconstruction. Overview is an
evaluation-only free camera and is never used for control.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from scripts.warpfit_analyze import model,dump


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fixture',type=Path,required=True)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--assets',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--world',type=int,default=0)
    a=p.parse_args()
    if not os.uname().nodename.startswith('ugrp-sim-gcp2'):raise ValueError('gcp2 review only')
    import cv2
    import numpy as np
    import mujoco
    from sim.masterpi_camera_profile import raw_fisheye_remap
    cv2.setNumThreads(1)
    m,meta,f=model(a.fixture,a.assets);d=mujoco.MjData(m)
    s=np.load(a.run/'states.npz');indices=[i for i,t in enumerate(s['t']) if abs(t*10-round(t*10))<1e-7]
    if not indices:raise ValueError('no10Hz recording')
    a.output.mkdir(parents=True,exist_ok=False);frames=a.output/'frames';frames.mkdir()
    stored={};manifest=a.run/'own-rgb-terminal/manifest.json'
    if manifest.exists() and a.world==0:
        for row in json.loads(manifest.read_text())['records']:
            stored[(round(row['t']*10),row['camera'])]=a.run/'own-rgb-terminal'/row['file']
    renderer=mujoco.Renderer(m,height=240,width=320);opt=mujoco.MjvOption();opt.geomgroup[4:]=0
    mx,my=raw_fisheye_remap(320,240);composites=[];timeline=[]
    for j,i in enumerate(indices):
        t=float(s['t'][i]);d.qpos[:]=s['qpos'][i,a.world];d.qvel[:]=s['qvel'][i,a.world];d.time=t
        mujoco.mj_forward(m,d)
        active=[m.body(r+'__robot').id for r in ('r1','r2') if mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_BODY,r+'__robot')>=0]
        cam=mujoco.MjvCamera();cam.lookat[:]=np.mean(d.xpos[active],axis=0);cam.distance=1.4;cam.azimuth=90;cam.elevation=-55
        renderer.update_scene(d,camera=cam,scene_option=opt)
        images=[('eval overview',cv2.cvtColor(renderer.render().copy(),cv2.COLOR_RGB2BGR))];origins={}
        for rid in ('r1','r2'):
            camera=rid+'__robot_cam';key=(round(t*10),camera)
            if key in stored:
                image=cv2.resize(cv2.imread(str(stored[key])),(320,240));origin='recorded MJWarp world0'
            elif mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_CAMERA,camera)>=0:
                renderer.update_scene(d,camera=camera,scene_option=opt);rgb=renderer.render().copy()
                rgb=cv2.remap(rgb,mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
                image=cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR);origin='C reconstruction'
            else:image=np.zeros((240,320,3),np.uint8);origin='not in reduced model'
            origins[rid]=origin;images.append((rid+' '+origin,image))
        panels=[]
        for label,pic in images:
            bar=np.zeros((24,320,3),np.uint8);cv2.putText(bar,f'{label} t={t:.2f}',(3,16),cv2.FONT_HERSHEY_SIMPLEX,.36,(255,255,255),1)
            panels.append(np.vstack([bar,pic]))
        combined=np.hstack(panels);cv2.imwrite(str(frames/f'{j:04d}.png'),combined)
        composites.append(combined);timeline.append(dict(t=t,origins=origins))
    renderer.close()
    def strips(selected,prefix):
        for start in range(0,len(selected),12):
            values=selected[start:start+12];h,w=values[0].shape[:2]
            page=np.zeros((((len(values)+1)//2)*h,2*w,3),np.uint8)
            for k,v in enumerate(values):page[(k//2)*h:(k//2+1)*h,(k%2)*w:(k%2+1)*w]=v
            cv2.imwrite(str(a.output/f'{prefix}-{start//12:02d}.jpg'),page,[cv2.IMWRITE_JPEG_QUALITY,88])
    strips(composites[::5],'full-2hz');strips(composites[-100:],'tail-10hz')
    video=a.output/'playback-3x.mp4'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-framerate','30','-i',str(frames/'%04d.png'),
        '-c:v','libx264','-crf','28','-pix_fmt','yuv420p','-movflags','+faststart',str(video)],check=True)
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(video)]))
    if video.stat().st_size>8*1024**2:raise ValueError('review video exceeds8MiB')
    dump(a.output/'receipt.json',dict(run=str(a.run),fixture=str(a.fixture),world=a.world,sim_range=[timeline[0]['t'],timeline[-1]['t']],
        timeline=timeline,frames=len(timeline),hz=10,speed=3,full_review_hz=2,tail_review_hz=10,
        bytes=video.stat().st_size,ffprobe=probe,control_feedback=0,overview='evaluator free camera',
        own_camera_source='per-frame origins recorded above; original mount/FOV and raw fisheye',
        reproduce=sys.argv,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
    dump(a.output/'SHA256.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in a.output.iterdir() if p.is_file()})
    print(json.dumps(dict(frames=len(timeline),video_bytes=video.stat().st_size)))


if __name__=='__main__':main()
