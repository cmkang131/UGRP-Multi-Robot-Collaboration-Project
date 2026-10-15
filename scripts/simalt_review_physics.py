"""gcp1-only offline state replay; native C rendering, no physics steps."""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('source','fixture','run','out'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--case',required=True)
    p.add_argument('--gcp2-v1',action='store_true')
    p.add_argument('--failure-time-s',type=float,help='SIM time of evaluated failure; reconstruct preceding 10s at10Hz instead of episode-end window')
    a=p.parse_args()
    if a.gcp2_v1:
        from simalt_host import gcp2_identity
        gcp2_identity()
    elif socket.gethostname().split('.')[0]!='ugrp-sim-gcp1':p.error('gcp1-only review')
    sys.path.insert(0,str(a.source))
    import cv2
    import mujoco
    import numpy as np
    from PIL import Image,ImageDraw
    from sim.masterpi_camera_profile import raw_fisheye_remap
    from sim import masterpi_camera_review_v3 as camera
    a.out.mkdir(parents=True,exist_ok=False)
    xml=(a.fixture/'scene.xml').read_text()
    for prefix in ('/tmp/simalt1/source/','/home/changmin/ugrp-sim/runs/simalt2/runtime/source/'):
        xml=xml.replace(prefix,str(a.source.resolve())+'/')
    m=mujoco.MjModel.from_xml_string(xml);d=mujoco.MjData(m)
    for name in ('camera_bracket','camera_body','camera_lens_visual'):
        gid=mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_GEOM,'r1__'+name)
        if gid>=0:m.geom_group[gid]=5
    cid=m.camera('r1__robot_cam').id
    m.cam_pos[cid]=camera.POSITION_M;m.cam_quat[cid]=camera.QUAT_WXYZ
    samples=np.load(a.run/'states.npz')[a.case]
    mx,my=raw_fisheye_remap(640,480)
    renderer=mujoco.Renderer(m,height=480,width=640)
    native=mujoco.MjvOption();native.geomgroup[:]=1
    own=mujoco.MjvOption();own.geomgroup[:]=1;own.geomgroup[4:]=0  # parent multi_masterpi_production controller
    top=mujoco.MjvCamera();top.type=mujoco.mjtCamera.mjCAMERA_FREE
    top.lookat[:]=[-.05,-2.4,0.];top.distance=1.5;top.azimuth=90;top.elevation=-65
    full=list(range(4,len(samples),5))  # 2Hz, at SIM .5,1.0,...
    stop=len(samples) if a.failure_time_s is None else min(len(samples),round(a.failure_time_s*10))
    if stop<=0:p.error('review failure anchor must include a saved sample')
    end=list(range(max(0,stop-100),stop))
    selected=sorted(set(full+end));images={}
    try:
        for i in selected:
            d.qpos[:]=samples[i,:m.nq];d.qvel[:]=samples[i,m.nq:];d.time=(i+1)*.1
            mujoco.mj_forward(m,d)
            renderer.update_scene(d,camera=top,scene_option=native);overview=renderer.render().copy()
            renderer.update_scene(d,camera='r1__robot_cam',scene_option=own)
            rgb=cv2.remap(renderer.render().copy(),mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
            # The 1-robot reduced scene has no r2 camera. Do not invent its view.
            blank=np.zeros((240,320,3),dtype=np.uint8)
            im=Image.fromarray(np.concatenate([cv2.resize(overview,(320,240)),cv2.resize(rgb,(320,240)),blank],axis=1))
            draw=ImageDraw.Draw(im);draw.text((5,5),f'{a.run.name}/{a.case} SIM {(i+1)*.1:.1f}s | overview / r1 / r2 absent',fill='white',stroke_width=1,stroke_fill='black')
            im.save(a.out/f'frame-{i:04d}.jpg',quality=85);images[i]=im
        for label,indices,columns in [('whole-2hz',full,4),('last10-10hz',end,5)]:
            for page in range((len(indices)+39)//40):
                chunk=indices[page*40:(page+1)*40]
                sheet=Image.new('RGB',(480*columns,132*((len(chunk)+columns-1)//columns)), 'white')
                for j,i in enumerate(chunk):sheet.paste(images[i].resize((480,120)),((j%columns)*480,(j//columns)*132))
                sheet.save(a.out/f'{label}-{page}.jpg',quality=90)
        for j,i in enumerate(full):
            (a.out/f'play-{j:04d}.jpg').write_bytes((a.out/f'frame-{i:04d}.jpg').read_bytes())
        video=a.out/'review-4x.mp4'
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-framerate','8','-i',str(a.out/'play-%04d.jpg'),'-c:v','libx264','-crf','28','-pix_fmt','yuv420p',str(video)],check=True)
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration,size','-of','json',str(video)]))
        write={'range_sim_s':[.1,len(samples)*.1],'whole_sample_hz':2,'last_sample_hz':10,
               'last_range_sim_s':[(end[0]+1)*.1,(end[-1]+1)*.1],'whole_frame_count':len(full),
               'last_frame_count':len(end),'ffprobe':probe,'sha256':hashlib.sha256(video.read_bytes()).hexdigest(),
               'renderer':'offline C3.12; not MJWarp batch-render parity or throughput',
               'camera':'unchanged v3 mount and measured K/D; r2 absent by reduced-scene contract',
               'source_states':str(a.run/'states.npz'),'reproduce':sys.argv}
        write['failure_anchor_sim_s']=a.failure_time_s
        (a.out/'review.json').write_text(json.dumps(write,indent=2)+'\n')
    finally:renderer.close()


if __name__=='__main__':main()
