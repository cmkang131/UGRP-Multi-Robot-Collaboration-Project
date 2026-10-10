"""Offline traversal-graph overlay on retained egomap49 failure; no new physics."""
from pathlib import Path
import json,subprocess,sys,hashlib
import cv2
import numpy as np
from offline import legacy,RAW,EXP
BASE,load,rows,sha=legacy.BASE,legacy.load,legacy.rows,legacy.sha
from harness.self_odom_grid import transform


def movie(case='49001'):
    ep=BASE/f'seed{case}';out=RAW/case;sealed=load(out/'seal.json')
    assert sha(out/'prediction.json')==sealed['sha256']
    graph=load(out/'prediction.json')['graph']
    frames=rows(ep/'robots/r3/frames.jsonl');trace=rows(ep/'own-controller.jsonl');truth=rows(ep/'eval_only/trajectory.jsonl')
    snapshots=rows(ep/'online-maps.jsonl')
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
    text(base,'egomap52 OFFLINE graph | frozen recorded motion',20)
    text(base,'Blue: traveled / green: accepted rejoin / red: B view',40)
    text(base,'Gray walls / cyan doors: GT EVALUATION ONLY',60)
    own=[r for r in trace if r.get('pose') is not None];times=np.array([r['t'] for r in own]);xy=transform([r.get('local_pose',r['pose'])[:2] for r in own],origin)
    si=ti=-1;layer=base.copy();checks=[];output=out/'wrist-map-graph-4x.mp4';assert not output.exists()
    cmd=['ffmpeg','-nostdin','-v','error','-f','rawvideo','-pixel_format','bgr24','-video_size','1280x480','-framerate','20','-i','pipe:0','-an','-c:v','libx264','-preset','fast','-crf','22','-pix_fmt','yuv420p','-movflags','+faststart',str(output)]
    proc=subprocess.Popen(cmd,stdin=subprocess.PIPE)
    try:
        for i,f in enumerate(frames):
            t=f['sim_time']
            while si+1<len(snapshots) and snapshots[si+1]['t']<=t:
                si+=1;s=snapshots[si];layer=base.copy();cells=np.array([r for r in s['grid']['cells'] if r[2]>0]).reshape(-1,3)
                for uv in pixels(transform((cells[:,:2]+.5)*s['grid']['resolution_m'],origin)):
                    cv2.circle(layer,tuple(uv),2,(230,165,100),-1)
            while ti+1<len(trace) and trace[ti+1]['t']<=t:ti+=1
            right=layer.copy();r=trace[ti] if ti>=0 else {}
            pp=pixels(xy[times<=t])
            if len(pp)>1:cv2.polylines(right,[pp],False,(0,120,245),2)
            nodes=[n for n in graph['nodes'] if n['t']<=t]
            edges=[e for e in graph['edges'] if graph['nodes'][e['b']]['t']<=t]
            for e in edges:
                line=pixels(transform([q['pose'][:2] for q in e['samples']],origin))
                if len(line)>1:cv2.polylines(right,[line],False,(50,155,40) if e.get('kind') else (180,60,30),3 if e.get('kind') else 2)
            for n in nodes:
                uv=pixels(transform([n['pose'][:2]],origin))[0]
                cv2.circle(right,tuple(uv),4,(10,20,220) if n['entities'] else (0,140,230),-1)
            if graph['goal'] and graph['goal']['t_sim']<=t:
                uv=pixels(transform([graph['goal']['center_m']],origin))[0]
                cv2.drawMarker(right,tuple(uv),(10,20,220),cv2.MARKER_STAR,14,2)
            right[:100]=base[:100]
            right[430:]=base[430:]
            text(right,f't={t-frames[0]["sim_time"]:.1f}s | nodes {len(nodes)} | edges {len(edges)}',82)
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
    cv2.imwrite(str(figures/'final-graph.jpg'),checks[-1],[cv2.IMWRITE_JPEG_QUALITY,88])
    report=dict(path=str(output),sha256=sha(output),bytes=output.stat().st_size,frames=len(frames),duration_s=float(info['format']['duration']),fps=20,
        qualification='egomap52 offline reconnection overlay on egomap49 original failure; no new physical run, no success video',full_decode=True)
    (EXP/'results/video.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))

if __name__=='__main__':movie()
