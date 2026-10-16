"""Post-run chronological wrist | own map and temporal path, 4x."""
from pathlib import Path
import json,hashlib,subprocess,sys
import cv2
import numpy as np
ROOT=Path('/Users/changmin/projects/ugrp-wt/ego-wall-map');sys.path.insert(0,str(ROOT))
from harness.self_odom_grid import transform
from scripts.run_goal_route_preflight import RAW,EXP
from scripts.run_active_wall_rotleft import dump

def load(p):return json.loads(p.read_text())
def rows(p):return [json.loads(l) for l in p.read_text().splitlines()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def movie(seed):
 ep=RAW/f'seed{seed}';out=ep/'wrist-map-route-4x.mp4';assert not out.exists()
 data=load(ep/'route-map.json');graph=data['graph'];trace=rows(ep/'own-controller.jsonl')
 frames=rows(ep/'robots/r3/frames.jsonl');truth=rows(ep/'eval_only/trajectory.jsonl');snapshots=rows(ep/'online-maps.jsonl')
 static=load(ep/'inputs/static_map.json');walls=[r for r in static['obstacles'] if r.get('kind')=='wall']
 origin=[*truth[0]['robot_xyz_m'][:2],truth[0]['robot_yaw_rad']]
 lo=np.min([np.array(w['center_m'])-w['half_extents_m'] for w in walls],axis=0)-.4
 hi=np.max([np.array(w['center_m'])+w['half_extents_m'] for w in walls],axis=0)+.4
 center=(lo+hi)/2;scale=min(590/(hi[0]-lo[0]),330/(hi[1]-lo[1]))
 def px(points):
  p=(np.asarray(points).reshape(-1,2)-center)*scale
  return np.rint(np.c_[320+p[:,0],265-p[:,1]]).astype(int)
 def text(im,s,y,color=(35,35,35)):cv2.putText(im,s,(10,y),cv2.FONT_HERSHEY_SIMPLEX,.44,color,1,cv2.LINE_AA)
 base=np.full((480,640,3),250,np.uint8)
 for w in walls:
  a,b=px([np.array(w['center_m'])-w['half_extents_m'],np.array(w['center_m'])+w['half_extents_m']])
  cv2.rectangle(base,tuple(a),tuple(b),(185,185,185),-1)
 text(base,'egomap58 | continuous own tracking | own origin frame',18)
 text(base,'Gray: GT walls (evaluation) / blue: own occupied cells',38)
 text(base,'Orange: own path / green: temporal route / star: own target',58)
 trace_times=np.array([r['t'] for r in trace]);xy=transform([r['local_pose'][:2] for r in trace],origin)
 ti=si=-1;layer=base.copy();checks=[]
 cmd=['ffmpeg','-nostdin','-v','error','-f','rawvideo','-pixel_format','bgr24','-video_size','1280x480','-framerate','20','-i','pipe:0','-an','-c:v','libx264','-preset','fast','-crf','22','-pix_fmt','yuv420p','-movflags','+faststart',str(out)]
 proc=subprocess.Popen(cmd,stdin=subprocess.PIPE)
 try:
  for i,f in enumerate(frames):
   t=f['sim_time']
   while si+1<len(snapshots) and snapshots[si+1]['t']<=t:
    si+=1;g=snapshots[si]['grid'];cells=np.array([p for p in g['cells'] if p[2]>0]).reshape(-1,3);layer=base.copy()
    for uv,v in zip(px(transform((cells[:,:2]+.5)*g['resolution_m'],origin)),cells[:,2]):
     cv2.circle(layer,tuple(uv),2,(225,150-int(min(90,max(0,v)*15)),80),-1)
   while ti+1<len(trace) and trace[ti+1]['t']<=t:ti+=1
   r=trace[ti] if ti>=0 else {};right=layer.copy()
   for e in graph['edges']:
    if graph['nodes'][e['b']]['t']>t:continue
    line=px(transform([p['pose'][:2] for p in e['samples']],origin))
    if len(line)>1:cv2.polylines(right,[line],False,(95,150,65) if not e['uncertain'] else (130,90,150),1)
   line=px(xy[trace_times<=t])
   if len(line)>1:cv2.polylines(right,[line],False,(0,135,245),2)
   for name,entity in r.get('remembered_entities',{}).items():
    uv=px(transform([entity['center_m']],origin))[0];cv2.drawMarker(right,tuple(uv),(20,20,220),cv2.MARKER_STAR,15,2)
    cv2.putText(right,name,tuple(uv+[6,-6]),cv2.FONT_HERSHEY_SIMPLEX,.5,(20,20,220),1)
   right[:78]=base[:78];right[430:]=base[430:]
   text(right,f"t={t-frames[0]['sim_time']:.1f}s | {r.get('stage','settle')} | nodes {r.get('route',{}).get('nodes',0)}",80)
   text(right,f"B declared: {r.get('declared_goal',False)} | returned: {r.get('declared_return',False)}",448)
   text(right,str(r.get('status','initial settling'))[:90],468)
   left=cv2.imread(str(ep/f['path']));assert left.shape==(480,640,3)
   cv2.rectangle(left,(0,0),(640,30),(20,20,20),-1);text(left,f'Own wrist RGB | seed{seed} | 4x',21,(245,245,245))
   pair=np.hstack([left,right]);proc.stdin.write(pair.tobytes())
   if i in (0,len(frames)//2,len(frames)-1):checks.append(pair.copy())
 finally:proc.stdin.close();code=proc.wait()
 assert code==0
 info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(out)]))
 assert abs(float(info['format']['duration'])-len(frames)/20)<.05
 subprocess.run(['ffmpeg','-v','error','-i',str(out),'-f','null','-'],check=True)
 dest=EXP/'figures';dest.mkdir(exist_ok=True)
 cv2.imwrite(str(dest/f'{seed}-video-check.jpg'),np.vstack(checks),[cv2.IMWRITE_JPEG_QUALITY,80])
 cv2.imwrite(str(dest/f'{seed}-final.jpg'),checks[-1],[cv2.IMWRITE_JPEG_QUALITY,88])
 dump(EXP/'results'/f'{seed}-video.json',dict(path=str(out),sha256=sha(out),bytes=out.stat().st_size,frames=len(frames),duration_s=float(info['format']['duration']),fps=20,full_decode=True))
if __name__=='__main__':movie(int(sys.argv[1]))
