"""gcp5 evaluation-only MJWarp overview + ffmpeg review, no integration/UI."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys


def run(a):
    if not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('GCP5_ONLY')
    a.output.mkdir(parents=True,exist_ok=False);overview=a.output/'overview';overview.mkdir()
    sys.path[:0]=[str(a.renderer),str(a.renderer/'scripts')];os.chdir(a.renderer)
    import numpy as np
    import cv2
    import mujoco
    import mujoco_warp as mjw
    import warp as wp
    from scripts.warp5_render import Renderer
    from scripts.simalt_physics_compare import unused_efm
    states=np.load(a.input/'eval-state.npz')['qpos'];n=16
    m=mujoco.MjModel.from_xml_string((a.input/'scene.xml').read_text())
    if m.opt.noslip_iterations!=0:raise ValueError('NATIVE_NOSLIP0_ONLY')
    wp.init();wm=mjw.put_model(m);d=mujoco.MjData(m);d.qpos[:]=states[0];mujoco.mj_forward(m,d)
    with unused_efm(m,d):wd=mjw.put_data(m,d,nworld=n,nconmax=512,njmax=2048)
    rc=Renderer(m,wm,wd,[('overview','cctv_top',(640,480))],enabled=True,texture_after_lighting=True)
    for start in range(0,len(states),n):
        q=states[start:start+n];count=len(q);q=np.concatenate([q,np.repeat(q[-1:],n-count,axis=0)])
        wp.copy(wd.qpos,wp.array(q,dtype=wd.qpos.dtype));rgb=rc.render()['overview'][0]
        for j in range(count):
            cv2.imwrite(str(overview/f'overview-{start+j:05d}.jpg'),cv2.cvtColor(np.clip(rgb[j],0,255).astype(np.uint8),cv2.COLOR_RGB2BGR))
    commands=[]
    def ff(args):
        cmd=['ffmpeg','-nostdin','-loglevel','error',*map(str,args)];commands.append(cmd);subprocess.run(cmd,check=True)
    last=len(states)-1
    video=a.output/'review-3x.mp4'
    ff(['-framerate',30,'-i',overview/'overview-%05d.jpg','-framerate',30,'-i',a.input/'own-rgb/r1-%05d.jpg',
        '-framerate',30,'-i',a.input/'own-rgb/r2-%05d.jpg','-filter_complex',
        '[0:v]scale=320:240[a];[1:v]scale=320:240[b];[2:v]scale=320:240[c];[a][b][c]hstack=inputs=3[v]',
        '-map','[v]','-frames:v',len(states),'-an','-c:v','libx264','-crf',28,'-threads',1,'-pix_fmt','yuv420p',video])
    if video.stat().st_size>8*1024**2:raise ValueError('REVIEW_VIDEO_OVER_8MIB_SPLIT_REQUIRED')
    sheets=[]
    for kind,starts,step,width in [('whole2hz',range(0,last+1,100),5,100),
        ('terminal10hz',range(max(0,last-100),last+1,20),1,20)]:
        for start in starts:
            stop=min(last,start+width-1)
            for camera in ('r1','r2','overview'):
                source=overview/'overview-%05d.jpg' if camera=='overview' else a.input/'own-rgb'/(camera+'-%05d.jpg')
                path=a.output/f'{kind}-{start:05d}-{camera}.jpg'
                expression=f'between(n\\,{start}\\,{stop})*not(mod(n-{start}\\,{step}))'
                ff(['-framerate',10,'-i',source,'-vf',
                    f'drawtext=text=SIM_%{{pts}}:x=8:y=8:fontcolor=white:box=1:boxcolor=black@0.8,select={expression},scale=320:240,tile=5x4',
                    '-frames:v',1,'-threads',1,path])
                sheets.append(dict(path=path.name,frame_indices=list(range(start,stop+1,step)),camera=camera))
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(video)]))
    receipt=dict(raw=str(a.input),overview='evaluation-only post-render of saved states; never actor input',cpu_integration_steps=0,
        mjwarp_integration_steps=0,frames=len(states),sim_range=[0,last/10],speed=3,sheets=sheets,ffprobe=probe,reproduction=commands,
        files={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
            for p in a.output.iterdir() if p.is_file()})
    (a.output/'receipts.json').write_text(json.dumps(receipt,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('input','renderer','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
