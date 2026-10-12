"""Offline door overlay on retained egomap49 failure; not a new policy run."""
from pathlib import Path
import json,subprocess,sys,hashlib
import cv2
import numpy as np
from offline import COHORT,RAW,EXP,load,rows,sha
from harness.self_odom_grid import transform


def movie(case='49001'):
    ep=COHORT[case];out=RAW/case;sealed=load(out/'seal.json')
    assert all(sha(out/p)==h for p,h in sealed['files'].items())
    frames=rows(ep/'robots/r3/frames.jsonl');trace=rows(ep/'own-controller.jsonl');truth=rows(ep/'eval_only/trajectory.jsonl')
    snapshots=rows(ep/'online-maps.jsonl');changes=load(out/'changes.json')
    static=load(ep/'inputs/static_map.json');walls=[r for r in static['obstacles'] if r.get('kind')=='wall']
    origin=[*truth[0]['robot_xyz_m'][:2],truth[0]['robot_yaw_rad']]
    lo=np.min([np.array(r['center_m'])-r['half_extents_m'] for r in walls],0)-.4
    hi=np.max([np.array(r['center_m'])+r['half_extents_m'] for r in walls],0)+.4
    scale=min(580/(hi[0]-lo[0]),325/(hi[1]-lo[1]));center=(lo+hi)/2
    def pixels(points):
        a=(np.asarray(points).reshape(-1,2)-center)*scale
        return np.rint(np.c_[320+a[:,0],260-a[:,1]]).astype(int)
    def text(im,s,y,color=(35,35,35)):
        cv2.putText(im,s,(12,y),cv2.FONT_HERSHEY_SIMPLEX,.47,color,1,cv2.LINE_AA)
    base=np.full((480,640,3),250,np.uint8)
    for r in walls:
        a,b=pixels([np.array(r['center_m'])-r['half_extents_m'],np.array(r['center_m'])+r['half_extents_m']])
        cv2.rectangle(base,tuple(a),tuple(b),(180,180,180),-1)
    for d in static['passages']:
        c=np.array(d['center_m']);v=np.array([0,1]) if d['axis']=='x' else np.array([1,0])
        a,b=pixels([c-v*d['width_m']/2,c+v*d['width_m']/2]);cv2.line(base,tuple(a),tuple(b),(200,150,20),4)
    text(base,'egomap50 OFFLINE overlay | frozen recorded motion',20)
    text(base,'Yellow: candidate / green: confirmed (own evidence)',40)
    text(base,'Gray walls / cyan doors: GT EVALUATION ONLY',60)
    own=[r for r in trace if r.get('pose') is not None];times=np.array([r['t'] for r in own]);xy=transform([r.get('local_pose',r['pose'])[:2] for r in own],origin)
    si=di=ti=-1;layer=base.copy();doors={};checks=[];output=out/'wrist-map-doors-4x.mp4';assert not output.exists()
    cmd=['ffmpeg','-nostdin','-v','error','-f','rawvideo','-pixel_format','bgr24','-video_size','1280x480','-framerate','20','-i','pipe:0','-an','-c:v','libx264','-preset','fast','-crf','22','-pix_fmt','yuv420p','-movflags','+faststart',str(output)]
    proc=subprocess.Popen(cmd,stdin=subprocess.PIPE)
    try:
        for i,f in enumerate(frames):
            t=f['sim_time']
            while si+1<len(snapshots) and snapshots[si+1]['t']<=t:
                si+=1;s=snapshots[si];layer=base.copy();cells=np.array([r for r in s['grid']['cells'] if r[2]>0]).reshape(-1,3)
                for uv in pixels(transform((cells[:,:2]+.5)*s['grid']['resolution_m'],origin)):
                    cv2.circle(layer,tuple(uv),2,(230,165,100),-1)
            while di+1<len(changes) and changes[di+1]['t']<=t:
                di+=1
                for d in changes[di]['doors']:doors[d['id']]=d
            while ti+1<len(trace) and trace[ti+1]['t']<=t:ti+=1
            right=layer.copy();r=trace[ti] if ti>=0 else {}
            pp=pixels(xy[times<=t])
            if len(pp)>1:cv2.polylines(right,[pp],False,(0,120,245),2)
            for d in doors.values():
                ends=pixels(transform(d['endpoints'],origin));color=(30,170,30) if d['confirmed_t'] is not None else (0,185,220)
                cv2.line(right,tuple(ends[0]),tuple(ends[1]),color,2)
            text(right,f't={t-frames[0]["sim_time"]:.1f}s | doors {len(doors)} | confirmed {sum(d["confirmed_t"] is not None for d in doors.values())}',82)
            text(right,'Recorded baseline failure; no new arrival trial',440)
            text(right,str(r.get('status','settle')),461)
            left=cv2.imread(str(ep/f['path']));assert left.shape==(480,640,3)
            cv2.rectangle(left,(0,0),(640,32),(20,20,20),-1);text(left,f'Own wrist RGB | seed{case} | 4x retained failure',22,(245,245,245))
            pair=np.hstack([left,right]);proc.stdin.write(pair.tobytes())
            if i in (0,len(frames)//2,len(frames)-1):checks.append(pair.copy())
            if i%500==0:print('movie',i,'/',len(frames),flush=True)
    finally:proc.stdin.close();code=proc.wait()
    assert code==0
    info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(output)]))
    assert info['streams'][0]['r_frame_rate']=='20/1' and abs(float(info['format']['duration'])-len(frames)/20)<.05
    subprocess.run(['ffmpeg','-v','error','-i',str(output),'-f','null','-'],check=True)
    figures=EXP/'figures';figures.mkdir(exist_ok=True)
    cv2.imwrite(str(figures/'video-check.jpg'),np.vstack(checks),[cv2.IMWRITE_JPEG_QUALITY,80])
    cv2.imwrite(str(figures/'final-doors.jpg'),checks[-1],[cv2.IMWRITE_JPEG_QUALITY,88])
    report=dict(path=str(output),sha256=sha(output),bytes=output.stat().st_size,frames=len(frames),duration_s=float(info['format']['duration']),fps=20,
        qualification='offline overlay on egomap49 original failure; no new physical run, no success video',full_decode=True)
    (EXP/'results/video.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))

if __name__=='__main__':movie()
