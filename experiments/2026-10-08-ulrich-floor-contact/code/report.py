"""Post-seal diagnostic labels/figures; no detector rerun or parameter selection."""
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
    assert (EXP/f'results/{seed}-comparison.json').exists()
    label=Labels(seed);data=rows(folder/'on-points.jsonl');records=[];counts=Counter();perframe=[]
    for index,row in enumerate(data):
        bad,error=label.classify(row);counts.update(r['category'] for r in bad)
        records.extend({k:r[k] for k in ('frame_id','t','column','uv','gt_body_error_m','category','subtype')} for r in bad)
        perframe.append(dict(frame_id=row['frame_id'],points=len(error),false_points=len(bad),
            categories=dict(Counter(r['category'] for r in bad))))
        if index%200==0:print(seed,'post-seal type audit',index,flush=True)
    queues=load(folder/'histogram-queues.json');promoted=sorted({f for r in queues for f in r['promoted']})
    # Sparse GT-only audit of promoted reference patches, not used to relabel or retrain.
    reference_audit=[]
    for frameid in promoted:
        f=label.frames[frameid];t=round(f['sim_time'],6);camera=label.camera[t]
        mask=cv2.imread(str(folder/f'masks/{frameid:05}.png'))[:,:,2]>0
        v,u=np.where(mask[::12,::12]);u=u*12;v=v*12
        origin=np.array(camera['camera_xyz']);rot=np.array(camera['camera_rotation']).reshape(3,3)@np.diag([1,-1,-1])
        rays=np.c_[u,v,np.ones(len(u))]@np.linalg.inv(label.K).T@rot.T
        sem,_=label.surface(origin,rays,label.truth[t])
        reference_audit.append(dict(frame_id=frameid,samples=len(u),surfaces=dict(Counter(sem))))
    result=load(EXP/f'results/{seed}-comparison.json')['conditions']['on']['points']
    assert sum(counts.values())==result['points']-result['correct']
    dump(target,dict(seed=seed,false_points=records,frames=perframe,promoted_reference_audit=reference_audit))
    summary=dict(seed=seed,false_points=sum(counts.values()),categories={c:counts[c] for c in CATEGORIES},
        promoted_reference_samples=dict(sum((Counter(r['surfaces']) for r in reference_audit),Counter())),
        promoted_reference_frames=len(promoted),raw=str(target),sha256=sha(target))
    dump(EXP/f'results/{seed}-diagnosis.json',summary)
    print(summary,flush=True)


def figures(seed):
    folder=RAW/seed/'comparison';labels=Labels(seed)
    data={r['frame_id']:r for r in rows(folder/'on-points.jsonl')}
    diag=load(RAW/seed/'diagnosis.json');queue={r['frame_id']:r for r in load(folder/'histogram-queues.json')}
    # Fixed selection rule: most false examples of three types + most border censored.
    selection=[]
    for category in ('floor_checker','wall_tape','floor_colour'):
        ranking=sorted(diag['frames'],key=lambda r:(-r['categories'].get(category,0),r['frame_id']))
        if ranking[0]['categories'].get(category,0):selection.append((category,ranking[0]['frame_id']))
    warm=[r for r in queue.values() if r['reason']=='classified']
    if warm:selection.append(('border_censored',max(warm,key=lambda r:(r['border_censored_columns'],-r['frame_id']))['frame_id']))
    if not selection:selection=[('untrained',next(iter(data)))]
    fig,axes=plt.subplots(len(selection),3,figsize=(13,3.3*len(selection)),squeeze=False,constrained_layout=True)
    saved=[]
    for ix,(category,frameid) in enumerate(selection):
        f=labels.frames[frameid];row=data[frameid]
        bgr=modules()[0].undistort(cv2.cvtColor(rgb(EPISODES[seed],f),cv2.COLOR_RGB2BGR))
        mask=cv2.imread(str(folder/f'masks/{frameid:05}.png'));support=mask[:,:,0]>0;floor=mask[:,:,1]>0;ref=mask[:,:,2]>0
        bad,errors=labels.classify(row)
        overlay=bgr.copy()
        for uv,error in zip(row['uv'],errors):cv2.circle(overlay,tuple(np.rint(uv).astype(int)),2,(0,0,255) if error>.15 else (0,220,0),-1)
        contour,_=cv2.findContours(ref.astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(overlay,contour,-1,(0,255,255),1)
        classes=np.zeros_like(bgr);classes[support]=[160,0,160];classes[floor]=[230,230,230]
        cv2.drawContours(classes,contour,-1,(0,255,255),1)
        axes[ix,0].imshow(cv2.cvtColor(overlay,cv2.COLOR_BGR2RGB));axes[ix,0].set_title(f'{seed} f{frameid} {category}: green TP, red FP\nyellow reference, points={len(errors)}')
        axes[ix,1].imshow(cv2.cvtColor(classes,cv2.COLOR_BGR2RGB));axes[ix,1].set_title('white=floor, purple=obstacle, black=invalid')
        q=queue[frameid];hist=np.array(q['local_intensity_histogram']);ax=axes[ix,2]
        ax.plot(hist,c='blue',lw=.8,label='current reference (not yet trusted)')
        for n in q['accepted_intensity_bins']:ax.axvspan(n-.5,n+.5,color='green',alpha=.25,lw=0)
        ax.axhline(80,c='red',ls='--',lw=.7,label='I threshold=80')
        refs=q['reference_frame_ids']
        ax.set(title=f'Validated references: n={len(refs)}, IDs {min(refs)}–{max(refs)}' if refs else 'No validated references',xlabel='intensity bin (256)',ylabel='smoothed count',xlim=(0,255));ax.legend(fontsize=7)
        for ax in axes[ix,:2]:ax.axis('off')
        saved.append(dict(category=category,frame_id=frameid,points=len(errors),false_points=len(bad),
            reference_pixels=q['reference_pixels'],border_censored=q['border_censored_columns'],rgb_sha256=f['sha256']))
    fig.savefig(EXP/f'figures/{seed}-examples.jpg',dpi=110)
    plt.close(fig)
    dump(EXP/f'results/{seed}-examples.json',dict(selection='largest per type, then earliest; most border-censored classified frame; report only',frames=saved))
    # All-frame learned support, not a hand-picked successful patch.
    q=list(queue.values());a=np.zeros((len(q),256))
    for j,r in enumerate(q):a[j,r['accepted_intensity_bins']]=1
    fig,ax=plt.subplots(figsize=(8,3),constrained_layout=True)
    ax.imshow(a.T,origin='lower',aspect='auto',extent=[q[0]['t'],q[-1]['t'],0,255],cmap='Greens',vmin=0,vmax=1)
    ax.set(xlabel='time (s)',ylabel='accepted I bins',title=f'{seed}: OR of last 10 validated references; white = unlearned intensity')
    fig.savefig(EXP/f'figures/{seed}-learned-bins.png',dpi=120);plt.close(fig)
    # Fixed time quantiles, including startup; independent of success or failure.
    frameids=list(data);fig,axes=plt.subplots(2,3,figsize=(12,6),constrained_layout=True)
    chosen=[frameids[int(i)] for i in np.linspace(0,len(frameids)-1,6)]
    for ax,frameid in zip(axes.flat,chosen):
        f=labels.frames[frameid];row=data[frameid]
        bgr=modules()[0].undistort(cv2.cvtColor(rgb(EPISODES[seed],f),cv2.COLOR_RGB2BGR))
        _,errors=labels.classify(row)
        for uv,error in zip(row['uv'],errors):cv2.circle(bgr,tuple(np.rint(uv).astype(int)),2,(0,0,255) if error>.15 else (0,220,0),-1)
        ax.imshow(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB));ax.axis('off')
        ax.set_title(f'{seed} f{frameid}, t={f["sim_time"]:.1f}s\n{queue[frameid]["reason"]}, n={len(errors)}')
    fig.savefig(EXP/f'figures/{seed}-time-quantiles.jpg',dpi=100);plt.close(fig)


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
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['audit','figures','maps']);p.add_argument('seed',nargs='?',choices=EPISODES)
    a=p.parse_args();maps() if a.stage=='maps' else (audit if a.stage=='audit' else figures)(a.seed)
