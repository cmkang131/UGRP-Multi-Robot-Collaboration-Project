"""New immutable derived views and four-speed own-camera videos."""
import argparse,hashlib,json,subprocess
from pathlib import Path
import cv2,numpy as np
p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();R=a.raw;O=a.output;O.mkdir(parents=True,exist_ok=False)
r=json.loads(a.report.read_text());b=json.loads((R/'bundle.json').read_text());result=json.loads((R/'result.json').read_text())
frames=[[json.loads(s) for s in (R/f'robots/{rid}/frames.jsonl').read_text().splitlines()] for rid in ('r1','r2','r3')]
video=O/'execution.mp4';pipe=subprocess.Popen(['/opt/homebrew/bin/ffmpeg','-v','error','-f','rawvideo','-pixel_format','bgr24','-video_size','1920x480','-framerate','20','-i','-','-an','-c:v','libx264','-threads','1','-preset','veryfast','-crf','28','-pix_fmt','yuv420p','-movflags','+faststart',str(video)],stdin=subprocess.PIPE);n=0
for i,triple in enumerate(zip(*frames)):
 if i%4:continue
 images=[]
 for rid,f in zip(('r1','r2','r3'),triple):
  im=cv2.imread(str(R/f['path']));assert im is not None
  cv2.putText(im,f'{rid} | {result["case"]} {result["servo_option"]} | SIM {f["sim_time"]:.2f}s | 4x',(8,25),cv2.FONT_HERSHEY_SIMPLEX,.44,(255,255,255),1);images.append(im)
 pipe.stdin.write(np.hstack(images).tobytes());n+=1
pipe.stdin.close();assert pipe.wait()==0
cap=cv2.VideoCapture(str(video));ok,first=cap.read();count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));fps=cap.get(cv2.CAP_PROP_FPS);cap.release();assert ok and count==n and fps==20
cv2.imwrite(str(O/'first-frame.jpg'),first)
v=dict(path=str(video),sha256=hashlib.sha256(video.read_bytes()).hexdigest(),fps=fps,frames=n,duration_s=n/fps,playback=4,source='saved own RGB only')
scalars={'offline/stage_pass_n':sum(x['stage_pass'] for x in r['robots'].values()),'offline/hover_n':sum(x['hover'] is not None for x in r['robots'].values()),'offline/descent_n':sum(x['descent'] is not None for x in r['robots'].values()),'offline/close_n':sum(x['close'] is not None for x in r['robots'].values()),'offline/host_errors':int(r['status']=='HOST_ERROR'),'offline/physical_runs':1,'offline/wall_per_sim':r['wall_s']/r['sim_s'] if r['sim_s'] else 0}
for rid,x in r['robots'].items():
 for key in ('moving_commands','short_commands','mixed_commands','beam_observations','beam_visible'):scalars[f'offline/{rid}/{key}']=x[key]
view=dict(schema='ugrp.s3_stage_probe_derived_view.v1',derived_view_only=True,source_sha=r['source_sha'],seed=14201,case=result['case']+'-'+str(b['stage_source_t'] if 'stage_source_t' in b else 532.1),condition=result['servo_option'],policy='staged-S3-own-RGB',status=r['status'],success=r['all_stage_pass'],success_definition='Stage entry through hover/descent/close only, not E2E or delivery; physical held result is separate',physical_success=None,clock='SIM',sim_s=r['sim_s'],wall_s=r['wall_s'],commands=sum(x['moving_commands'] for x in r['robots'].values()),model_calls=0,offline_source=dict(path=str(a.report),sha256=hashlib.sha256(a.report.read_bytes()).hexdigest()),offline_scalar_scope='Post-run stage probe evaluation; reconstructed scene and fresh controller, no exact resume or mission success',offline_scalars=scalars,hparam_metrics=['offline/hover_n','offline/descent_n','offline/close_n','result/wall_s','result/sim_s','result/commands'],video=v,evaluation=r)
(O/'result.json').write_text(json.dumps(view,indent=2)+'\n');(O/'video-verification.json').write_text(json.dumps(v,indent=2)+'\n');print(json.dumps(v))
