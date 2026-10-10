"""Save RGB examples of every nonzero type; no detector/evaluation mutation."""
from common import *
from collections import defaultdict

def examples(seed):
    data=load(RAW/seed/'diagnosis.json');by=defaultdict(lambda:defaultdict(list))
    frames={f['frame_id']:f for f in rows(EPISODES[seed]/'robots/r3/frames.jsonl')}
    for p in data['false_points']:by[p['category']][p['frame_id']].append(p)
    ims=[];selected=[]
    for category,group in sorted(by.items(),key=lambda item:-sum(len(v) for v in item[1].values())):
        # Largest occurrence first, then one distant-in-time example of same type.
        chosen=[]
        for frame,points in sorted(group.items(),key=lambda pair:(-len(pair[1]),pair[0])):
            if any(abs(frames[frame]['sim_time']-frames[c]['sim_time'])<5 for c in chosen):continue
            chosen.append(frame)
            f=frames[frame];und=modules()[0].undistort(cv2.cvtColor(rgb(EPISODES[seed],f),cv2.COLOR_RGB2BGR))
            original=und.copy()
            for p in points:cv2.circle(und,tuple(np.rint(p['uv']).astype(int)),3,(0,0,255),1)
            u,v=map(int,np.rint(points[len(points)//2]['uv']))
            x=max(0,min(480,u-80));y=max(0,min(360,v-60))
            crop=cv2.resize(und[y:y+120,x:x+160],(320,240),interpolation=cv2.INTER_NEAREST)
            full=cv2.resize(und,(480,360));side=np.full((360,320,3),245,np.uint8);side[:240]=crop
            cv2.putText(side,'Red: GT-body false points',(5,270),cv2.FONT_HERSHEY_SIMPLEX,.45,(0,0,0),1)
            cv2.putText(side,f'count {len(points)}',(5,295),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,0,0),1)
            canvas=np.vstack([np.full((28,800,3),255,np.uint8),np.hstack([full,side])])
            cv2.putText(canvas,f'{seed}: {category} / frame {frame} / t {f["sim_time"]:.1f}s',(6,20),cv2.FONT_HERSHEY_SIMPLEX,.55,(0,0,0),1)
            ims.append(canvas);selected.append(dict(category=category,frame_id=frame,t=f['sim_time'],rgb_sha256=f['sha256'],crop=[x,y,160,120]))
            if len(chosen)==2:break
    out=RAW/seed/'examples';out.mkdir(exist_ok=True)
    for i,im in enumerate(ims):cv2.imwrite(str(out/f'{i:02}.jpg'),im,[cv2.IMWRITE_JPEG_QUALITY,90])
    dump(EXP/f'results/{seed}-examples.json',dict(selection='largest count then >=5s apart, up to two per nonzero type',frames=selected))
    print(seed,selected,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('seed',choices=EPISODES);a=p.parse_args();examples(a.seed)
