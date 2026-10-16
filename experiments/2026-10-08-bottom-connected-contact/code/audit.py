"""Report-only retained-point audit and fixed egomap37 RGB examples."""
from common import *
from harness.wall_bottom_connected import candidate_mask


def run(seed):
    off={r['frame_id']:r for r in rows(OLD_RAW/seed/'off/points.jsonl')}
    on={r['frame_id']:r for r in rows(RAW/seed/'comparison-complete/on-points.jsonl')}
    keys=set();new_after_linking=[]
    for frame,row in on.items():
        old=dict(zip(off[frame]['columns'],off[frame]['points']))
        for col,p in zip(row['columns'],row['points']):
            if col in old:assert p==old[col]
            else:new_after_linking.append(dict(frame_id=frame,column=col,point=p))
            keys.add((frame,col))
    diagnosis=load(OLD_RAW/seed/'diagnosis.json')
    total=Counter();kept=Counter()
    for row in diagnosis['false_points']:
        total[row['category']]+=1
        kept[row['category']]+=(row['frame_id'],row['column']) in keys
    sys.path.insert(0,str(ROOT/'experiments/2026-10-08-wall-contact-types/code'))
    from diagnose import Labels
    labels=Labels(seed);extra_false=[]
    for frame in sorted({r['frame_id'] for r in new_after_linking}):
        bad,_=labels.classify(on[frame])
        extra_false.extend(b for b in bad if (b['frame_id'],b['column']) not in {(r['frame_id'],r['column']) for r in diagnosis['false_points']})
    examples=load(ROOT/f'experiments/2026-10-08-wall-contact-types/results/{seed}-examples.json')['frames']
    examples=[r for r in examples if r['category']=='wall_tape']
    frames={f['frame_id']:f for f in rows(EPISODES[seed]/'robots/r3/frames.jsonl')}
    mp,hfw,_=modules();images=[];counts=[]
    for ex in examples:
        frame=frames[ex['frame_id']];servo={int(k):v for k,v in frame['commanded_servo'].items()}
        image=mp.undistort(cv2.cvtColor(rgb(EPISODES[seed],frame),cv2.COLOR_RGB2BGR))
        cols=mp.column_positions(96,2).astype(int);origin,rotation=camera_transform(servo)
        cm=mp.ColumnModel(tuple(sorted(servo.items())),0.,cols,camera_transform=(origin,rotation))
        strips=hfw.ColumnStrips(image,cols,2);top=hfw.surface_run_top(strips,10.,3)
        support=(mp.undistort(np.full_like(image,255))==255).all(-1)
        valid=np.stack([support[:,u-2:u+3].all(1) for u in cols],axis=1)
        self_top=hfw.self_top_mask(image,cm,loaded=False)
        r=np.arange(mp.HEIGHT-2,2,-1)[:,None]*np.ones((1,len(cols)))
        mask=candidate_mask(top,r,valid,self_top)
        for j,u in enumerate(cols):
            if mask[:,j].any():
                v=int(r[mask[:,j],j].max());cv2.circle(image,(u,v),2,(255,190,0),-1)
        for uv in off[frame['frame_id']]['uv']:cv2.circle(image,tuple(np.rint(uv).astype(int)),2,(0,0,255),-1)
        for uv in on[frame['frame_id']]['uv']:cv2.circle(image,tuple(np.rint(uv).astype(int)),3,(0,200,0),-1)
        cv2.rectangle(image,(0,0),(640,32),(255,255,255),-1)
        title=f'{seed} f{frame["frame_id"]}: cyan first edge | red off | green on'
        cv2.putText(image,title,(5,20),cv2.FONT_HERSHEY_SIMPLEX,.48,(0,0,0),1)
        images.append(image);counts.append(dict(frame_id=frame['frame_id'],first_boundaries=int(mask.any(0).sum()),
            off_points=len(off[frame['frame_id']]['points']),on_points=len(on[frame['frame_id']]['points'])))
    cv2.imwrite(str(EXP/f'figures/{seed}-first-boundary.jpg'),np.hstack(images),[cv2.IMWRITE_JPEG_QUALITY,85])
    dump(EXP/f'results/{seed}-retention.json',dict(seed=seed,shared_points_identical=True,new_after_linking=new_after_linking,extra_false_points=extra_false,
        off_points=sum(len(r['points']) for r in off.values()),on_points=len(keys),
        false_categories={c:dict(off=total[c],on=kept[c],removed=total[c]-kept[c]) for c in total},
        examples=counts,diagnosis_sha256=sha(OLD_RAW/seed/'diagnosis.json')))

if __name__=='__main__':run(sys.argv[1])
