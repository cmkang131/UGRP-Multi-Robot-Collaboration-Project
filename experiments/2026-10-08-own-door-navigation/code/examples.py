"""Saved RGB and projected doorway hypotheses, all labels post-seal only."""
from offline import *
import cv2
from harness.active_wall_vision import modules


def main():
    panels=[]
    for case,truth in [('46A',True),('46A',False),('49001',False),('49002',False)]:
        p=load(RAW/case/'prediction.json');r=load(EXP/'results'/f'{case}.json');ep=COHORT[case]
        ids={m['id'] for m in r['metrics']['on']['matches'] if m['tp']==truth}
        choices=[d for d in p['tracks'] if d['id'] in ids]
        d=max(choices,key=lambda d:(d['confirmation_opportunities'],len(d['observations'])))
        frame=d['observations'][0]['frame_id'];meta=next(x for x in rows(ep/'robots/r3/frames.jsonl') if x['frame_id']==frame)
        own=next(x for x in rows(ep/'own-controller.jsonl') if x['frame_id']==frame)
        obs=None
        for line in (ep/'own-contacts.jsonl').open():
            x=json.loads(line)
            if x['frame_id']==frame:obs=x;break
        xy=transform(d['endpoints'],inverse(own.get('local_pose',own['pose'])))
        optical=(np.c_[xy,np.zeros(2)]-np.array(obs['camera_origin']))@np.array(obs['camera_rotation'])
        project=optical@modules()[0].K.T;uv=project[:,:2]/project[:,2,None]
        im=cv2.imread(str(ep/meta['path']));color=(30,180,30) if truth else (40,60,240)
        for point in uv:
            if np.isfinite(point).all() and np.linalg.norm(point)<1e5:cv2.circle(im,tuple(np.rint(point).astype(int)),6,color,2)
        if np.isfinite(uv).all() and np.linalg.norm(uv)<1e5:cv2.line(im,tuple(np.rint(uv[0]).astype(int)),tuple(np.rint(uv[1]).astype(int)),color,2)
        strip=np.full((94,640,3),245,np.uint8)
        for y,text in [(20,f'{case} f{frame} | '+('GT-matched candidate' if truth else 'False candidate')+' | '+d['kind']),
                       (43,f'width {d["width_m"]:.2f}m | {d["id"]} | t {d["first_t"]:.1f}s'),
                       (67,f'Frontal opportunities: {d["confirmation_opportunities"]}; confirmed: {d["confirmed_t"] is not None}'),
                       (88,'Last rejection: '+d['last_reason'])]:
            cv2.putText(strip,text,(10,y),cv2.FONT_HERSHEY_SIMPLEX,.45,(35,35,35),1,cv2.LINE_AA)
        panels.append(np.vstack([im,strip]))
    target=EXP/'figures/examples.jpg';target.parent.mkdir(exist_ok=True)
    cv2.imwrite(str(target),np.vstack([np.hstack(panels[:2]),np.hstack(panels[2:])]),[cv2.IMWRITE_JPEG_QUALITY,88])

if __name__=='__main__':main()
