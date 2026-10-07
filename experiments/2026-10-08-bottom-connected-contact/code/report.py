"""Figures from saved predictions, no parameter selection or repeated scoring."""
from common import *
sys.path.insert(0,str(ROOT/'experiments/2026-10-08-wall-contact-types/code'))
from diagnose import Labels
from compare import evaluator
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

def samples(seed):
    labels=Labels(seed);data=rows(RAW/seed/'comparison-complete/on-points.jsonl')
    indices=[int((k+.5)*len(data)/6) for k in range(6)]
    ims=[];metadata=[];counts=Counter()
    for index in indices:
        row=data[index];bad,errors=labels.classify(row);counts.update(r['category'] for r in bad)
        frame=labels.frames[row['frame_id']]
        image=modules()[0].undistort(cv2.cvtColor(rgb(EPISODES[seed],frame),cv2.COLOR_RGB2BGR))
        for uv,e in zip(row['uv'],errors):
            cv2.circle(image,tuple(np.rint(uv).astype(int)),2,(0,0,255) if e>.15 else (0,180,0),-1)
        im=cv2.resize(image,(400,300));cv2.rectangle(im,(0,0),(400,24),(255,255,255),-1)
        cv2.putText(im,f'{seed} on frame{row["frame_id"]} t{row["t"]:.1f}s',(6,18),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,0,0),1)
        ims.append(im);metadata.append(dict(frame_id=row['frame_id'],t=row['t'],points=len(errors),false_points=len(bad),
            categories=dict(Counter(r['category'] for r in bad)),rgb_sha256=frame['sha256']))
    canvas=np.vstack([np.hstack(ims[:3]),np.hstack(ims[3:])])
    cv2.imwrite(str(EXP/f'figures/{seed}-on-rgb.jpg'),canvas,[cv2.IMWRITE_JPEG_QUALITY,85])
    dump(EXP/f'results/{seed}-on-rgb-audit.json',dict(selection='six fixed temporal mid-quantiles; visualization only; no threshold fit',
        frames=metadata,categories=dict(counts),total_false=sum(counts.values())))

def maps():
    fig,axes=plt.subplots(4,4,figsize=(15,14),constrained_layout=True)
    for si,seed in enumerate(EPISODES):
        evaluate=evaluator(seed);result=load(EXP/f'results/{seed}-comparison.json')
        ep=EPISODES[seed];folder=RAW/seed/'comparison-complete'
        truth=rows(ep/'eval_only/trajectory.jsonl');estimated=rows(ep/'frontend-covariances.jsonl')
        actual=np.array([r['robot_xyz_m'][:2] for r in truth]);path=transform([r['pose'][:2] for r in estimated],evaluate.origin)
        for selected in (False,True):
            rowindex=2*si+int(selected);bounds=[]
            for i,(kind,condition) in enumerate((('grid','off'),('grid','on'),('segments','off'),('segments','on'))):
                suffix='-selected' if selected else ''
                ax=axes[rowindex,i];value=load(folder/f'{condition}-{kind}{suffix}.json')
                c=result['conditions'][condition];q=(c['selected'] if selected else c)[kind]
                for x,y,hx,hy in evaluate.walls:
                    ax.add_patch(Rectangle((x-hx,y-hy),2*hx,2*hy,color='.75'))
                    bounds.extend([[x-hx,y-hy],[x+hx,y+hy]])
                ax.plot(actual[:,0],actual[:,1],c='green',lw=.5);ax.plot(path[:,0],path[:,1],c='orange',lw=.5)
                if kind=='grid':
                    points=transform((np.array([c[:2] for c in value['cells'] if c[2]>0]).reshape(-1,2)+.5)*.1,evaluate.origin)
                    ax.scatter(points[:,0],points[:,1],s=4,c='navy');bounds.extend(points.tolist())
                else:
                    for line in value['segments']:
                        points=transform(line['endpoints_m'],evaluate.origin);ax.plot(points[:,0],points[:,1],c='navy',lw=1.6);bounds.extend(points.tolist())
                p=q['full']['precision_015'];r=q['full']['wall_coverage'];rmse=q['full']['wall_error_rmse_m']
                text='empty' if p is None else f'P/R {p:.1%}/{r:.1%} RMSE {rmse:.3f}m, n={q["sample_count"]}'
                label='egomap36 point' if selected else 'multiview off'
                ax.set(title=f'{seed} {kind} {condition}, {label}\n{text}',xlabel='world x (eval), m',ylabel='world y, m',aspect='equal')
            lo,hi=np.array(bounds).min(0)-.3,np.array(bounds).max(0)+.3
            for ax in axes[rowindex]:ax.set_xlim(lo[0],hi[0]);ax.set_ylim(lo[1],hi[1])
    fig.savefig(EXP/'figures/maps.png',dpi=130)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['31001','32002','maps']);a=p.parse_args()
    maps() if a.stage=='maps' else samples(a.stage)
