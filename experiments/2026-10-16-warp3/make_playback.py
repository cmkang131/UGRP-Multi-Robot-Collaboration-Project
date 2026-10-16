"""gcp2-only offline replay: evaluation overview + actual r1 RGB; no stepping."""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess

if platform.system()!='Linux':raise RuntimeError('replay rendering is gcp2-only')
os.environ['MUJOCO_GL']='osmesa';os.environ['LP_NUM_THREADS']='1'
import numpy as np
from PIL import Image
import mujoco


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--world',type=int,required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args();out=a.out;out.mkdir(parents=True,exist_ok=False)
    world=a.run/f'world-{a.world:03d}';state_path=a.run/f'world-{a.world:03d}-states.npz'
    if not state_path.exists() and a.world==0:state_path=a.run/'world0-states.npz'
    state=np.load(state_path)
    index={int(t):i for i,t in enumerate(state['ticks'])}
    m=mujoco.MjModel.from_xml_string((world/'scene.xml').read_text());d=mujoco.MjData(m)
    summary=json.loads((a.run/'summary.json').read_text());camera=summary['camera'];cid=m.camera('r1__robot_cam').id
    m.cam_pos[cid]=camera['mount_pos'];m.cam_quat[cid]=camera['mount_quat']
    renderer=mujoco.Renderer(m,height=240,width=320)
    tops=out/'overview';tops.mkdir();own=out/'own';own.mkdir()
    selected=[]
    for path in sorted((world/'review-own').glob('*.jpg')):
        tick=int(path.stem)
        if tick not in index:continue
        i=index[tick];d.qpos[:]=state['qpos'][i];d.qvel[:]=state['qvel'][i]
        mujoco.mj_kinematics(m,d);mujoco.mj_camlight(m,d)
        renderer.update_scene(d,camera='cctv_top')
        n=len(selected);Image.fromarray(renderer.render()).save(tops/f'{n:05d}.png')
        (own/f'{n:05d}.jpg').write_bytes(path.read_bytes());selected.append(tick)
    renderer.close()
    if not selected:raise ValueError('no review frames/states')
    step=np.diff(selected);hz=10/float(np.median(step)) if len(step) else 2.
    if len(step) and not np.all(step==5):raise ValueError('review timeline must be actual2Hz')
    composed=out/'frames';composed.mkdir()
    filters="[0:v]drawtext=text='overview - reconstructed evaluation only':x=4:y=4:fontsize=12:fontcolor=white[a];[1:v]drawtext=text='r1 recorded own RGB':x=4:y=4:fontsize=14:fontcolor=white[b];color=c=0x202020:s=320x240:r=2,drawtext=text='r2 N/A - solo r1 task':x=8:y=110:fontsize=18:fontcolor=white[c];[a][b][c]hstack=inputs=3:shortest=1[v]"
    subprocess.run(['ffmpeg','-y','-loglevel','error','-framerate',str(hz),'-i',str(tops/'%05d.png'),
        '-framerate',str(hz),'-i',str(own/'%05d.jpg'),'-filter_complex',filters,'-map','[v]',
        '-frames:v',str(len(selected)),str(composed/'%05d.jpg')],check=True)
    video=out/'playback-3x.mp4'
    subprocess.run(['ffmpeg','-y','-loglevel','error','-framerate',str(hz*3),'-start_number','1','-i',str(composed/'%05d.jpg'),
        '-c:v','libx264','-crf','30','-pix_fmt','yuv420p',str(video)],check=True)
    for start in range(0,len(selected),24):
        subprocess.run(['ffmpeg','-y','-loglevel','error','-start_number',str(start+1),'-i',str(composed/'%05d.jpg'),
            '-vf','scale=480:120,tile=4x6','-frames:v','1',str(out/f'full-2hz-{start//24:02d}.jpg')],check=True)
    ring=sorted((world/'failure-rgb-buffer').glob('*.jpg'))
    for start in range(0,len(ring),20):
        subset=out/f'ring-{start//20:02d}';subset.mkdir()
        for i,path in enumerate(ring[start:start+20]):(subset/f'{i:03d}.jpg').write_bytes(path.read_bytes())
        subprocess.run(['ffmpeg','-y','-loglevel','error','-i',str(subset/'%03d.jpg'),
            '-vf',f"scale=320:240,drawtext=text='SIM {int(ring[start].stem)/10:.1f} + %{{n}}/10s':x=4:y=4:fontsize=15:fontcolor=white:box=1:boxcolor=black@0.7,tile=5x4",'-frames:v','1',str(out/f'last10s-10hz-{start//20:02d}.jpg')],check=True)
    probe=json.loads(subprocess.check_output(['ffprobe','-v','quiet','-show_format','-show_streams','-of','json',str(video)]))
    if video.stat().st_size>8_000_000:raise ValueError('video exceeds8MB limit')
    (out/'playback-meta.json').write_text(json.dumps(dict(run=str(a.run),world=a.world,sim_range=[selected[0]/10,selected[-1]/10],
        full_2hz_frames=len(selected),terminal_10hz_frames=len(ring),video_bytes=video.stat().st_size,ffprobe=probe,
        scope='overview uses frozen cctv_top and reconstructed evaluation states, may not cover every negative-coordinate start; r1 own RGB is actual, r2 not an actor; no native physics step'),indent=2)+'\n')


if __name__=='__main__':main()
