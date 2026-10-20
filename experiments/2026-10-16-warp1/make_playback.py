"""gcp2-only: evaluation overview reconstruction + recorded own RGB, 3x playback."""
import argparse,json,os,platform,subprocess
from pathlib import Path
if platform.system()!='Linux':raise RuntimeError('remote gcp2 only')
os.environ['MUJOCO_GL']='osmesa';os.environ['LP_NUM_THREADS']='1'
import numpy as np
from PIL import Image,ImageDraw
import mujoco
p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
r=a.run;out=a.out;out.mkdir(parents=True,exist_ok=False)
z=np.load(r/'world0-states.npz');ticks=z['ticks'];indices={int(v):i for i,v in enumerate(ticks)}
m=mujoco.MjModel.from_xml_path(str(r/'world-000/scene.xml'));d=mujoco.MjData(m)
renderer=mujoco.Renderer(m,height=240,width=320)
frames=out/'frames';frames.mkdir()
rows=[]
for i,path in enumerate(sorted((r/'world-000/review-own').glob('*.jpg'))):
 tick=int(path.stem)
 if tick not in indices:continue
 idx=indices[tick];d.qpos[:]=z['qpos'][idx];d.qvel[:]=z['qvel'][idx];mujoco.mj_forward(m,d)
 renderer.update_scene(d,camera='cctv_top')
 top=Image.fromarray(renderer.render());own=Image.open(path).convert('RGB').resize((320,240))
 canvas=Image.new('RGB',(960,270),(20,20,20));canvas.paste(top,(0,30));canvas.paste(own,(320,30))
 draw=ImageDraw.Draw(canvas);draw.text((4,5),f'SIM {tick/10:.1f}s | overview: reconstructed evaluation only',fill='white');draw.text((324,5),'r1: recorded own RGB',fill='white');draw.text((650,110),'r2 N/A: solo r1 task',fill='white')
 target=frames/f'{len(rows):05d}.jpg';canvas.save(target,quality=82)
 rows.append(dict(tick=tick,path=str(target)))
renderer.close()
# Expected new runner acquisition is 2Hz; do not silently upsample older 1Hz runs.
diffs=np.diff([x['tick'] for x in rows]);hz=10/float(np.median(diffs)) if len(diffs) else 2.
subprocess.run(['ffmpeg','-y','-loglevel','error','-framerate',str(hz*3),'-i',str(frames/'%05d.jpg'),'-c:v','libx264','-crf','30','-pix_fmt','yuv420p',str(out/'playback-3x.mp4')],check=True)
# Full 2Hz timeline in chunks; every source frame is displayed, not a sparse sample.
for chunk in range(0,len(rows),40):
 sheet=Image.new('RGB',(960*4,270*10),(30,30,30))
 for j,row in enumerate(rows[chunk:chunk+40]):sheet.paste(Image.open(row['path']),((j%4)*960,(j//4)*270))
 sheet.resize((1920,1350)).save(out/f'full-timeline-{chunk//40:02d}.jpg',quality=84)
ring=sorted((r/'world-000/failure-rgb-buffer').glob('*.jpg'))
for chunk in range(0,len(ring),50):
 sheet=Image.new('RGB',(320*10,264*5),(30,30,30));draw=ImageDraw.Draw(sheet)
 for j,path in enumerate(ring[chunk:chunk+50]):
  x,y=(j%10)*320,(j//10)*264;sheet.paste(Image.open(path).resize((320,240)),(x,y+24));draw.text((x+3,y+4),f'SIM {int(path.stem)/10:.1f}s',fill='white')
 sheet.resize((1920,792)).save(out/f'terminal10hz-{chunk//50:02d}.jpg',quality=84)
probe=json.loads(subprocess.check_output(['ffprobe','-v','quiet','-show_format','-show_streams','-of','json',str(out/'playback-3x.mp4')]))
if (out/'playback-3x.mp4').stat().st_size>8_000_000:raise RuntimeError('video exceeds8MB')
meta=dict(run=str(r),scope='overview reconstructed posthoc from evaluation states; own camera actual acquisition; r2 not part of solo task',own_hz=hz,reviewed_range_candidate=[rows[0]['tick']/10,rows[-1]['tick']/10],full_frames=len(rows),terminal_frames=len(ring),video_bytes=(out/'playback-3x.mp4').stat().st_size,ffprobe=probe)
(out/'playback-meta.json').write_text(json.dumps(meta,indent=2)+'\n')
