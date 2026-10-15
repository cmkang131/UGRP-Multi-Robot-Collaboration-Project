"""gcp2 only: evaluation replay of saved states; never advances physics."""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
import numpy as np
import mujoco
from PIL import Image,ImageDraw
import cv2
from sim.masterpi_camera_profile import raw_fisheye_remap
p=argparse.ArgumentParser();p.add_argument('job',type=Path);p.add_argument('out',type=Path);a=p.parse_args()
assert sys.platform=='linux' and Path('/home/ugrp/ugrp-sim').exists()
job=a.job;out=a.out;out.mkdir(parents=True,exist_ok=False);raw=job/'world-000/raw'
states=np.load(job/'world0-states.npz');ticks=states['ticks'].astype(int)
m=mujoco.MjModel.from_xml_path(str(raw/'scene.xml'));d=mujoco.MjData(m)
cameras=json.loads((raw/'camera-runtime.json').read_text())['cameras']
for rid,c in cameras.items():
 i=m.camera(rid+'__robot_cam').id
 for key,field in [('pos','cam_pos'),('quat','cam_quat'),('intrinsic','cam_intrinsic'),('resolution','cam_resolution')]:getattr(m,field)[i]=c[key]
renderer=mujoco.Renderer(m,height=240,width=320);option=mujoco.MjvOption();option.geomgroup[:]=1;option.geomgroup[4:]=0
mx,my=raw_fisheye_remap(320,240)
tail=job/'world-000/adapter/failure-tail/manifest.json';original={}
if tail.exists():
 for f in json.loads(tail.read_text()).get('frames',[]):original[(round(f['t']*10),f['robot'])]=tail.parent/f['path']
frames=out/'frames';frames.mkdir();full=[];dense=[];noriginal=0
for k,tick in enumerate(ticks):
 d.qpos[:]=states['qpos'][k];d.qvel[:]=states['qvel'][k];d.time=tick/10
 mujoco.mj_kinematics(m,d);mujoco.mj_camlight(m,d)
 canvas=Image.new('RGB',(960,264));draw=ImageDraw.Draw(canvas)
 for j,cam in enumerate(('cctv_top','r1','r2')):
  if (tick,cam) in original:
   im=Image.open(original[tick,cam]);noriginal+=1;label=cam+' original10Hz'
  else:
   name=cam if j==0 else cam+'__robot_cam'
   renderer.update_scene(d,camera=name,scene_option=option);arr=renderer.render().copy()
   if j:arr=cv2.remap(arr,mx,my,interpolation=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
   im=Image.fromarray(arr);label=cam+' saved-state C312 render'
  canvas.paste(im,(j*320,24));draw.text((j*320+4,4),f't={tick/10:.1f} '+label,fill='white')
 f=frames/f'{k:05d}.jpg';canvas.save(f,quality=84)
 if (tick-ticks[0])%5==0 or k==len(ticks)-1:full.append(f)
 if tick>=ticks[-1]-100:dense.append(f)
renderer.close()
def sheets(files,name):
 result=[]
 for off in range(0,len(files),12):
  selected=files[off:off+12];sheet=Image.new('RGB',(1920,264*((len(selected)+1)//2)))
  for j,f in enumerate(selected):sheet.paste(Image.open(f),(j%2*960,j//2*264))
  target=out/f'{name}-{off//12:02d}.jpg';sheet.save(target,quality=90);result.append(str(target))
 return result
review=dict(whole_2hz=sheets(full,'whole2hz'),tail_10hz=sheets(dense,'tail10hz'))
video=out/'playback-3x.mp4'
subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-framerate','30','-i',str(frames/'%05d.jpg'),'-c:v','libx264','-preset','veryfast','-crf','29','-pix_fmt','yuv420p',str(video)],check=True)
probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(video)]))
assert video.stat().st_size<=8*1024**2
result=dict(raw=str(job),frames=len(ticks),absolute_sim_range=[ticks[0]/10,ticks[-1]/10],
 recording_scope='saved qpos/qvel reconstructed on C312 with exact recorded camera runtime; no mj_step; original own 10Hz tail preferred when present; reconstructed RGB is evaluation only, not original GPU RGB',
 original_own_tail_frames_used=noriginal,review=review,video=str(video),video_bytes=video.stat().st_size,ffprobe=probe,
 hashes={str(f.relative_to(out)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [video,*out.glob('*.jpg')]})
(out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('ffprobe','hashes')},indent=2))
