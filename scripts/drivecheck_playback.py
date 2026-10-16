"""gcp2 evaluator-only, windowless 10Hz own-camera reconstruction and strips."""
import argparse
import json
import os
from pathlib import Path
import subprocess


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fixture',type=Path,required=True);p.add_argument('--run',type=Path,required=True)
    p.add_argument('--case',required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if not os.uname().nodename.startswith('ugrp-sim-gcp2'):raise ValueError('gcp2 only')
    import cv2
    import numpy as np
    import mujoco
    cv2.setNumThreads(1)
    os.chdir('/home/ugrp/ugrp-sim/src/drivecheck-renderer-5974a181')
    m=mujoco.MjModel.from_xml_string((a.fixture/'scene.xml').read_text());d=mujoco.MjData(m)
    f=np.load(a.fixture/'fixture.npz')
    for field in ('cam_pos','cam_quat','cam_resolution','cam_sensorsize','cam_intrinsic'):
        getattr(m,field)[:]=f[field]
    report=json.loads((a.run/'result.json').read_text());ci=[r['id'] for r in report['cases']].index(a.case)
    s=np.load(a.run/'states.npz');ids=np.flatnonzero(s['case']==ci)
    # Exact 10Hz grid, retaining pulse boundary extras in source state archive.
    ids=np.array([i for i in ids if abs(s['t'][i]*10-round(s['t'][i]*10))<1e-7])
    a.out.mkdir(parents=True,exist_ok=False);frames=a.out/'frames';frames.mkdir()
    renderer=mujoco.Renderer(m,height=240,width=320);opt=mujoco.MjvOption();opt.geomgroup[4:]=0
    from sim.masterpi_camera_profile import raw_fisheye_remap
    mx,my=raw_fisheye_remap(320,240)
    composites=[];times=[]
    for j,i in enumerate(ids):
        d.qpos[:]=s['qpos'][i];d.qvel[:]=s['qvel'][i];d.time=float(s['t'][i]);mujoco.mj_forward(m,d)
        images=[]
        for label,camera in [('overview','cctv_top'),('r1','r1__robot_cam'),('r2','r2__robot_cam')]:
            renderer.update_scene(d,camera=camera,scene_option=opt);rgb=renderer.render().copy()
            if label!='overview':rgb=cv2.remap(rgb,mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
            bgr=cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR)
            bar=np.zeros((24,320,3),dtype=np.uint8);cv2.putText(bar,f'{label} SIM {d.time:.2f}',(4,17),cv2.FONT_HERSHEY_SIMPLEX,.45,(255,255,255),1)
            images.append(np.vstack([bar,bgr]))
        combined=np.hstack(images);cv2.imwrite(str(frames/f'{j:04d}.png'),combined)
        composites.append(combined);times.append(float(d.time))
    renderer.close()
    def strips(values,prefix,per=12):
        for start in range(0,len(values),per):
            selected=values[start:start+per];h,w=selected[0].shape[:2];cols=2;rows=(len(selected)+1)//2
            out=np.zeros((rows*h,cols*w,3),np.uint8)
            for k,frame in enumerate(selected):out[(k//2)*h:(k//2+1)*h,(k%2)*w:(k%2+1)*w]=frame
            cv2.imwrite(str(a.out/f'{prefix}-{start//per:02d}.jpg'),out,[cv2.IMWRITE_JPEG_QUALITY,88])
    strips(composites[::5],'overview-2hz',per=14)
    # Every selected run <= 10 SIM s; entire 10Hz history is the terminal ring.
    strips(composites,'terminal-10hz')
    video=a.out/'playback-3x.mp4'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-framerate','30','-i',str(frames/'%04d.png'),
        '-c:v','libx264','-crf','28','-pix_fmt','yuv420p','-movflags','+faststart',str(video)],check=True)
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(video)]))
    if video.stat().st_size>8*1024**2:raise ValueError('video exceeds user 8MiB cap')
    receipt=dict(run=str(a.run),case=a.case,frames=len(times),times=times,video_bytes=video.stat().st_size,
        renderer='MuJoCo C3.12 rasterizer on recorded engine qpos/qvel; evaluator-only, not renderer parity',
        raw_own_fisheye=True,cameras=['overview','r1','r2'],hz=10,speed=3,ffprobe=probe,
        reconstructed_recording=True,control_feedback=0,reproduce=list(__import__('sys').argv))
    (a.out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:receipt[k] for k in ('frames','video_bytes','run','case')}))


if __name__=='__main__':main()
