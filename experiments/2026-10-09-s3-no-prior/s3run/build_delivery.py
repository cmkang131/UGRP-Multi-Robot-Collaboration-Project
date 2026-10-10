"""Derived result/video; raw and its sealed manifest stay untouched."""
import hashlib,json,pathlib,subprocess,collections
import cv2,numpy as np
B=pathlib.Path(__file__).parent;RAW=B.parent/'s3-host-heading-3daa830f-s14201-v146';VIEW=B/'views/v146';VIEW.mkdir(parents=True,exist_ok=True)
report=json.loads((B/'smoke-report.json').read_text());result=json.loads((RAW/'result.json').read_text());manifest=json.loads((RAW/'artifacts.sha256.json').read_text());total=0
for name,digest in manifest.items():
 p=RAW/name;assert hashlib.sha256(p.read_bytes()).hexdigest()==digest,name;total+=p.stat().st_size
proof=dict(raw=str(RAW),manifest_sha256=hashlib.sha256((RAW/'artifacts.sha256.json').read_bytes()).hexdigest(),files_verified=len(manifest),bytes_verified=total,all_hashes_match=True)
frames=[[json.loads(x) for x in (RAW/f'robots/{rid}/frames.jsonl').read_text().splitlines()] for rid in ['r1','r2','r3']]
video=VIEW/'execution.mp4';assert not video.exists()
p=subprocess.Popen(['/opt/homebrew/bin/ffmpeg','-v','error','-f','rawvideo','-pixel_format','bgr24','-video_size','1920x480','-framerate','20','-i','-','-an','-c:v','libx264','-preset','veryfast','-crf','28','-pix_fmt','yuv420p','-movflags','+faststart',str(video)],stdin=subprocess.PIPE)
count=0
try:
 for i,triple in enumerate(zip(*frames)):
  if i%4:continue
  assert len({x['sim_time'] for x in triple})==1
  images=[]
  for rid,row in zip(['r1','r2','r3'],triple):
   image=cv2.imread(str(RAW/row['path']));assert image is not None
   cv2.putText(image,f'{rid} | v146 SIM {row["sim_time"]:.2f}s | 4x',(12,25),cv2.FONT_HERSHEY_SIMPLEX,.6,(255,255,255),2);images.append(image)
  p.stdin.write(np.hstack(images).tobytes());count+=1
 p.stdin.close();assert p.wait()==0
finally:
 if p.stdin and not p.stdin.closed:p.stdin.close()
cap=cv2.VideoCapture(str(video));ok,first=cap.read();n=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));fps=cap.get(cv2.CAP_PROP_FPS);cap.release();assert ok and n==count and fps==20
cv2.imwrite(str(B/'video-first-frame.jpg'),first)
v=dict(path=str(video),sha256=hashlib.sha256(video.read_bytes()).hexdigest(),frames=count,fps=fps,playback=4,source_frames_per_robot=len(frames[0]),source='three own RGB recordings; no new render',duration_s=count/fps);(B/'video-verification.json').write_text(json.dumps(v,indent=2)+'\n');(B/'raw-verification.json').write_text(json.dumps(proof,indent=2)+'\n')
# All displayed outcomes are post-run DEV evaluation, with no robot success claim.
scalars={'offline/correct_convergence_n':sum(x['correct_convergence'] for x in report['evaluation']['robots'].values()),'offline/false_convergence_n':sum(bool(x['first_convergence'] and x['first_convergence']['wrong_mode']) for x in report['evaluation']['robots'].values()),'offline/delivered_orders':sum(x['complete'] for x in result['evaluation']['orders'].values()),'offline/collision_episodes':len(report['evaluation']['collision_episodes']),'offline/door_deadlock_episodes':len(report['evaluation']['door_deadlocks']),'offline/physical_runs':1,'offline/host_errors':int(result['status']=='HOST_ERROR')}
for rid,loc in report['localization'].items():
 scalars[f'offline/{rid}/xy_error_m']=loc['last']['xy_error_m'];scalars[f'offline/{rid}/sigma_xy_m']=loc['last']['std_xy_m'];scalars[f'offline/{rid}/door_wait_s']=report['evaluation']['door_wait_robot_s'][rid];scalars[f'offline/{rid}/would_stop_n']=sum(report['would_stop'][rid]['local_counts'].values())
src=B/'smoke-report.json';d=dict(schema='ugrp.s3_smoke_derived_view.v1',derived_view_only=True,source_sha=result['source_sha'],seed=14201,case='v146-host-heading',policy='S3-v3-host-heading',condition='DEV-mixed-three',clock='SIM',status=result['status'],success=False,success_definition='All three robots satisfy preregistered own localization and deliver both orders B; DEV simulator only',physical_success=None,sim_s=result['check_sim_s'],wall_s=result['wall_s'],commands=sum(result['commands_issued'].values()),model_calls=0,offline_source=dict(path=str(src),sha256=hashlib.sha256(src.read_bytes()).hexdigest()),offline_scalar_scope='Post-run eval_only scores of one physical simulator DEV smoke; not hardware or research cohort',offline_scalars=scalars,evaluation=report['evaluation'],hparam_metrics=['offline/correct_convergence_n','offline/delivered_orders','result/wall_s','result/sim_s','result/commands'],video=v)
(VIEW/'result.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');print(json.dumps(dict(raw=proof,video=v),indent=2))
