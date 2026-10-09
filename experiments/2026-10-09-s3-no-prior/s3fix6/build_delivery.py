"""Derived result/video; raw and its sealed manifest stay untouched."""
import hashlib,json,pathlib,subprocess,collections
import cv2,numpy as np
import argparse
p=argparse.ArgumentParser();p.add_argument('--raw',type=pathlib.Path,required=True);p.add_argument('--report-dir',type=pathlib.Path,required=True);a=p.parse_args()
B=a.report_dir;RAW=a.raw;VIEW=B/'views/v151';VIEW.mkdir(parents=True,exist_ok=False)
report=json.loads((B/'smoke-report.json').read_text());result=json.loads((RAW/'result.json').read_text());manifest=json.loads((RAW/'artifacts.sha256.json').read_text());total=0
for name,digest in manifest.items():
 p=RAW/name;assert hashlib.sha256(p.read_bytes()).hexdigest()==digest,name;total+=p.stat().st_size
proof=dict(raw=str(RAW),manifest_sha256=hashlib.sha256((RAW/'artifacts.sha256.json').read_bytes()).hexdigest(),files_verified=len(manifest),bytes_verified=total,all_hashes_match=True)
frames=[[json.loads(x) for x in (RAW/f'robots/{rid}/frames.jsonl').read_text().splitlines()] for rid in ['r1','r2','r3']]
video=VIEW/'execution.mp4';assert not video.exists()
p=subprocess.Popen(['/opt/homebrew/bin/ffmpeg','-v','error','-f','rawvideo','-pixel_format','bgr24','-video_size','1920x480','-framerate','20','-i','-','-an','-c:v','libx264','-threads','1','-preset','veryfast','-crf','28','-pix_fmt','yuv420p','-movflags','+faststart',str(video)],stdin=subprocess.PIPE)
count=0
try:
 for i,triple in enumerate(zip(*frames)):
  if i%4:continue
  assert len({x['sim_time'] for x in triple})==1
  images=[]
  for rid,row in zip(['r1','r2','r3'],triple):
   image=cv2.imread(str(RAW/row['path']));assert image is not None
   cv2.putText(image,f'{rid} | v151 SIM {row["sim_time"]:.2f}s | 4x',(12,25),cv2.FONT_HERSHEY_SIMPLEX,.6,(255,255,255),2);images.append(image)
  p.stdin.write(np.hstack(images).tobytes());count+=1
 p.stdin.close();assert p.wait()==0
finally:
 if p.stdin and not p.stdin.closed:p.stdin.close()
cap=cv2.VideoCapture(str(video));ok,first=cap.read();n=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));fps=cap.get(cv2.CAP_PROP_FPS);cap.release();assert ok and n==count and fps==20
cv2.imwrite(str(B/'video-first-frame.jpg'),first)
v=dict(path=str(video),sha256=hashlib.sha256(video.read_bytes()).hexdigest(),frames=count,fps=fps,playback=4,source_frames_per_robot=len(frames[0]),source='three own RGB recordings; no new render',duration_s=count/fps);(B/'video-verification.json').write_text(json.dumps(v,indent=2)+'\n');(B/'raw-verification.json').write_text(json.dumps(proof,indent=2)+'\n')

scalars={'offline/startup_point_accurate_n':sum(bool(v and v['accurate']) for v in report['first_location'].values()),
    'offline/would_stop_n':sum(report['would_stop_counts'].values()),
    'offline/correct_convergence_n':sum(x['correct_convergence'] for x in report['evaluation']['robots'].values()),
    'offline/false_convergence_n':sum(bool(x['first_convergence'] and (x['first_convergence']['actual_xy_error_m'] > .25 or x['first_convergence']['actual_yaw_error_deg'] > 15)) for x in report['evaluation']['robots'].values()),
    'offline/delivered_orders':sum(x['complete'] for x in result['evaluation']['orders'].values()),
    'offline/collision_episodes':len(report['evaluation']['collision_episodes']),
    'offline/door_deadlock_episodes':len(report['evaluation']['door_deadlocks']),
    'offline/physical_runs':1,'offline/host_errors':int(result['status']=='HOST_ERROR'),
    'offline/wall_per_sim':result['wall_per_sim'],
    'offline/invalid_pose_exclusions':sum(report['invalid_pose_exclusions'].values())}
for rid,loc in report['first_location'].items():
    if loc is None: continue
    scalars[f'offline/{rid}/first_xy_error_m']=loc['xy_error_m']
    scalars[f'offline/{rid}/first_sigma_xy_m']=loc['sigma_xy_m']
    scalars[f'offline/{rid}/startup_s']=loc['elapsed_from_first_frame_s']
    scalars[f'offline/{rid}/door_wait_s']=report['evaluation']['door_wait_robot_s'].get(rid,0)
    scalars[f'offline/{rid}/would_stop_n']=sum(report['would_stop'][rid].values())
src=B/'smoke-report.json'
d=dict(schema='ugrp.s3_smoke_derived_view.v1',derived_view_only=True,source_sha=result['source_sha'],seed=14201,
    case='v151-pose-validity',policy='S3-heading-coupled-exception',condition='DEV-mixed-three',clock='SIM',
    status=result['status'],success=all(r['success'] for r in report['evaluation']['robots'].values()),success_definition='All three robots satisfy preregistered localization and deliver both orders B; DEV simulator only',physical_success=None,
    sim_s=result['check_sim_s'],wall_s=result['wall_s'],commands=sum(result['commands_issued'].values()),model_calls=0,model_response_time_s=0.,
    offline_source=dict(path=str(src),sha256=hashlib.sha256(src.read_bytes()).hexdigest()),
    offline_scalar_scope='Post-run eval_only of one DEV physical simulator run; not hardware or research evidence',
    offline_scalars=scalars,evaluation=report['evaluation'],
    hparam_metrics=['offline/startup_point_accurate_n','offline/correct_convergence_n','offline/delivered_orders','result/wall_s','result/sim_s','result/commands'],video=v)
(VIEW/'result.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
