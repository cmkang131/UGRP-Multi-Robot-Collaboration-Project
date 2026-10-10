"""Diagnostics of sealed Lorigo predictions; no candidate selection or rerun."""
from common import *
from compare import evaluator
sys.path.insert(0,str(ROOT/'experiments/2026-10-08-wall-contact-types/code'))
from diagnose import Labels,CATEGORIES
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


def audit(seed):
    folder=RAW/seed/'comparison';target=RAW/seed/'diagnosis.json'
    if target.exists():raise FileExistsError(target)
    seal=load(folder/'seal.json')
    for n,h in seal['files'].items():assert sha(folder/n)==h
    result=load(EXP/f'results/{seed}-comparison.json')
    labels=Labels(seed);counts=Counter();records=[];frames=[]
    for ix,row in enumerate(rows(folder/'on-points.jsonl')):
        bad,error=labels.classify(row);counts.update(r['category'] for r in bad)
        records.extend({k:r[k] for k in ('frame_id','t','column','uv','category','subtype','gt_body_error_m')} for r in bad)
        frames.append(dict(frame_id=row['frame_id'],points=len(error),false_points=len(bad),categories=dict(Counter(r['category'] for r in bad))))
        if ix%200==0:print(seed,'post-seal audit',ix,flush=True)
    assert sum(counts.values())==result['conditions']['on']['points']['points']-result['conditions']['on']['points']['correct']
    dump(target,dict(seed=seed,false_points=records,frames=frames))
    dump(EXP/f'results/{seed}-diagnosis.json',dict(seed=seed,categories={c:counts[c] for c in CATEGORIES},
        false_points=sum(counts.values()),raw=str(target),sha256=sha(target)))
    print(dict(counts),flush=True)


def figures(seed):
    folder=RAW/seed/'comparison';labels=Labels(seed)
    points={r['frame_id']:r for r in rows(folder/'on-points.jsonl')}
    diag=load(folder/'window-diagnostics.json');index={r['frame_id']:i for i,r in enumerate(diag)}
    distances=np.load(folder/'window-distances.npz')['distances']
    # Exactly the earlier egomap39 example frames, never selected for new success.
    selected=load(ROOT/f'experiments/2026-10-08-ulrich-floor-contact/results/{seed}-examples.json')['frames']
    chosen=[r['frame_id'] for r in selected]
    fig,axes=plt.subplots(len(chosen),3,figsize=(13,3.3*len(chosen)),constrained_layout=True,squeeze=False)
    for i,fid in enumerate(chosen):
        f=labels.frames[fid];row=points[fid];d=diag[index[fid]]
        rgb_image=rgb(EPISODES[seed],f)
        bgr=modules()[0].undistort(cv2.cvtColor(rgb_image,cv2.COLOR_RGB2BGR))
        overlay=bgr.copy();_,errors=labels.classify(row)
        for uv,error in zip(row['uv'],errors):cv2.circle(overlay,tuple(np.rint(uv).astype(int)),2,(0,0,255) if error>.15 else (0,220,0),-1)
        axes[i,0].imshow(cv2.cvtColor(overlay,cv2.COLOR_BGR2RGB));axes[i,0].set_title(f'{seed} f{fid}, n={len(errors)}, TP green / FP red',fontsize=9)
        ax=axes[i,1];ax.imshow(cv2.cvtColor(cv2.resize(bgr,(64,64),interpolation=cv2.INTER_AREA),cv2.COLOR_BGR2RGB))
        xs=np.arange(10,55);colours=['yellow','cyan','magenta']
        for k,name in enumerate(('gradient','RG','HS')):
            v=np.array(d['module_rows'][k]);ax.plot(xs[v>0],v[v>0],c=colours[k],lw=.8,label=name)
        v=np.array(d['fused_rows']);ax.plot(xs[v>0],v[v>0],c='red',lw=1,label='median')
        x=22;y=d['reference_top'][x]
        if y>=0:ax.add_patch(Rectangle((x-.5,y-.5),20,10,fill=False,edgecolor='lime',lw=.8))
        ax.set_title('64x64: three modules / median, green=reference',fontsize=9);ax.legend(fontsize=6,loc='upper right')
        ax=axes[i,2]
        for k,name in enumerate(('gradient','RG','HS')):
            values=distances[index[fid],k,:,x];valid=values>=0
            ax.plot(values[valid],np.arange(55)[valid]+5,label=name,lw=1)
        ax.axvline(80,c='red',ls='--',lw=.8);ax.set(xlabel='window L1 count',ylabel='window centre row',ylim=(64,0))
        ax.set_title('Central slice: threshold 80 (frozen)',fontsize=9);ax.legend(fontsize=7)
        for ax in axes[i,:2]:ax.axis('off')
    fig.savefig(EXP/f'figures/{seed}-examples.jpg',dpi=110);plt.close(fig)
    dump(EXP/f'results/{seed}-examples.json',dict(selection='same frame IDs as egomap39; no outcome selection',frames=chosen))


def weights(seed):
    ledger=load(RAW/seed/'comparison/on-ledger.json')
    evidence=[r for frame in ledger for r in frame['wall_confidence']]
    result=dict(seed=seed,segments=len(evidence),positive_weight=sum(r['weight']>0 for r in evidence),
        zero_factors={k:sum(r['factors'][k]==0 for r in evidence) for k in evidence[0]['factors']} if evidence else {},
        weights=[r['weight'] for r in evidence])
    dump(EXP/f'results/{seed}-weights.json',result)
    print(result,flush=True)


def maps():
    fig,axes=plt.subplots(2,3,figsize=(12,8),constrained_layout=True)
    for j,seed in enumerate(EPISODES):
        ev=evaluator(seed);folder=RAW/seed/'comparison';result=load(EXP/f'results/{seed}-comparison.json')
        truth=rows(EPISODES[seed]/'eval_only/trajectory.jsonl');estimated=rows(EPISODES[seed]/'frontend-covariances.jsonl')
        path=transform([r['pose'][:2] for r in estimated],ev.origin);actual=np.array([r['robot_xyz_m'][:2] for r in truth])
        bounds=[]
        for col,condition in enumerate(('historical','off','on')):
            ax=axes[j,col];grid=load(folder/f'{condition}-grid.json')
            q=result['historical_grid'] if condition=='historical' else result['conditions'][condition]['grid']
            pts=transform((np.array([r[:2] for r in grid['cells'] if r[2]>0]).reshape(-1,2)+.5)*.1,ev.origin)
            for x,y,hx,hy in ev.walls:
                ax.add_patch(Rectangle((x-hx,y-hy),2*hx,2*hy,color='.75'));bounds.extend([[x-hx,y-hy],[x+hx,y+hy]])
            ax.plot(actual[:,0],actual[:,1],c='green',lw=.7);ax.plot(path[:,0],path[:,1],c='orange',lw=.7)
            ax.scatter(pts[:,0],pts[:,1],s=4,c='navy');bounds.extend(pts.tolist())
            p,r=q['full']['precision_015'],q['full']['wall_coverage']
            text='empty' if p is None else f'P {p:.1%} / coverage {r:.1%}, n={len(pts)}'
            ax.set(title=f'{seed} {condition}\n{text}',xlabel='world x (eval), m',ylabel='world y, m',aspect='equal')
        lo,hi=np.min(bounds,0)-.3,np.max(bounds,0)+.3
        for ax in axes[j]:ax.set_xlim(lo[0],hi[0]);ax.set_ylim(lo[1],hi[1])
    fig.savefig(EXP/'figures/maps.png',dpi=120);plt.close(fig)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['audit','figures','maps','weights']);p.add_argument('seed',nargs='?',choices=EPISODES)
    a=p.parse_args();maps() if a.stage=='maps' else {'audit':audit,'figures':figures,'weights':weights}[a.stage](a.seed)
