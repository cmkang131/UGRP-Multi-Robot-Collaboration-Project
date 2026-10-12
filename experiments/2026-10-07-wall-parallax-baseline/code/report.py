"""Read sealed evaluation output; no inference, fitting, physics or model calls."""
import json,math
from pathlib import Path
import numpy as np
import diagnose_baseline as d

EXP,RAW=d.EXP,d.RAW
EVAL=RAW/'evaluation-joint-covariance'
MODES=('command_baseline',*d.MODES)
LABELS=('Command DR','GT XY only','GT length only')


def wrap(x):return (x+math.pi)%(2*math.pi)-math.pi


def main():
    d.source.verify()
    (EXP/'figures').mkdir(exist_ok=True)
    rows=[]
    diagnostics={}
    reports={}
    trajectories={}
    for case in d.CASES:
        frames=d.c.old.base.read_rows(RAW/'capture/parallax_v1'/case/'predictions.jsonl')
        events=d.c.old.base.read_rows(RAW/'capture/parallax_v1'/case/'track-history.jsonl')
        truth=d.c.old.current_truth(d.c.EPISODES[case])
        first=d.c.old.base.read_rows(d.c.EPISODES[case]/'eval_only/trajectory.jsonl')[0]
        start=np.r_[first['robot_xyz_m'][:2],first['robot_yaw_rad']]
        gt=np.array([truth[round(r['t'],6)] for r in frames])
        xy=(gt[:,:2]-start[:2])@d.geometry.rz(start[2])[:2,:2]
        command=np.array([r['pose'] for r in frames])
        actual_yaw=np.array([wrap(x-start[2]) for x in gt[:,2]])
        yaw_error=np.array([wrap(a-b) for a,b in zip(command[:,2],actual_yaw)])
        trajectories[case]=(command,xy,np.array([r['t'] for r in frames]),yaw_error)
        times={r['frame_id']:r['t'] for r in frames}
        intervals={}
        for e in events:
            if e['reason']!='accepted':continue
            a,b=e['history'][0],e['history'][-1]
            key=(a['frame_id'],b['frame_id'])
            if key in intervals:continue
            g0,g1=truth[round(times[key[0]],6)],truth[round(times[key[1]],6)]
            cb=float(np.linalg.norm(np.array(b['pose'])[:2]-a['pose'][:2]))
            gb=float(np.linalg.norm(g1[:2]-g0[:2]))
            cy,gy=wrap(b['pose'][2]-a['pose'][2]),wrap(g1[2]-g0[2])
            intervals[key]=dict(frames=key,t=[times[k] for k in key],
                command_baseline_m=cb,gt_baseline_m=gb,command_over_gt=cb/gb,
                command_delta_yaw_deg=math.degrees(cy),gt_delta_yaw_deg=math.degrees(gy),
                delta_yaw_disagreement_deg=math.degrees(wrap(cy-gy)))
        diag=dict(accepted_intervals=list(intervals.values()),
            yaw_error_deg=d.frozen.stats(np.degrees(np.abs(yaw_error))),
            eligible_frame_y_span_m=dict(command=float(np.ptp(command[:,1])),gt=float(np.ptp(xy[:,1]))))
        reports[case]={}
        for mode in MODES:
            report=d.c.read(EVAL/case/(mode+'.json'))
            reports[case][mode]=report
            d.c.dump(EXP/'results'/f'{case}-{mode}.json',report)
            p=report['reports']['candidate']['points']
            a=report['reports']['candidate']['annotated']['all']
            rows.append(dict(case=case,mode=mode,**p,annotation_recall=a['recall'],
                annotation_precision=a['precision'],positive_columns=a['positive'],
                own_only=report['own_only'],adopted=False))
            if mode!='command_baseline':
                paired=report['same_original_accepted']
                values=[r['new_error_m'] for r in paired if r['new_error_m'] is not None]
                diag[mode]=dict(original_accepted=len(paired),still_accepted=len(values),
                    rejected=len(paired)-len(values),errors=d.frozen.stats(values),
                    precision=float(np.mean(np.array(values)<=.15)) if values else None)
        diagnostics[case]=diag
    gate=d.c.read(RAW/'diagnosis-gate.json')
    assert gate['next_step']=='STOP_BASELINE_ONLY_INSUFFICIENT' and gate['recovered_cases']==0
    d.c.dump(EXP/'results/summary.json',dict(rows=rows,diagnostics=diagnostics,gate=gate,
        sources=dict(capture='206269b1',preregistration='f4887ad3',covariance_preregistration='34d55300',evaluation='0f65ed58'),
        physics=0,model_calls=0,map_replays=0,motion_option_added=False,model_fitted=False))

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    colors=['#4169a1','#d16c37','#548f68']
    fig,axes=plt.subplots(1,2,figsize=(10.5,4.8),sharey=True)
    for ax,case in zip(axes,d.CASES):
        paired=reports[case][d.MODES[0]]['same_original_accepted']
        other=reports[case][d.MODES[1]]['same_original_accepted']
        for a,b in zip(paired,other):
            assert a['track_id']==b['track_id']
            ax.plot([0,1,2],[a['old_error_m'],a['new_error_m'],b['new_error_m']],color='#adb5bd',lw=.8,zorder=1)
        for x,mode in enumerate(MODES):
            name='command_points.jsonl' if x==0 else mode+'-points.jsonl'
            pts=[p for p in d.c.old.base.read_rows(EVAL/case/name) if p['mode']=='candidate']
            ax.scatter(np.full(len(pts),x),[p['error_m'] for p in pts],s=35,color=colors[x],zorder=3)
            p=reports[case][mode]['reports']['candidate']['points']
            ax.plot([x-.13,x+.13],[p['median']]*2,lw=2.5,color=colors[x])
            ax.text(x,.65,f"P={100*p['precision']:.1f}%\nn={p['n']}",ha='center',va='top',fontsize=9)
        ax.axhline(.1,color='#ae2633',ls='--',label='Median gate 0.10 m')
        ax.axhline(.15,color='#888',ls=':',label='Point precision cutoff 0.15 m')
        ax.set_xticks(range(3),LABELS)
        ax.set_title(case+' | annotated recall: 0% in every condition')
        ax.set_ylim(0,.67)
        ax.grid(axis='y',alpha=.18)
    axes[0].set_ylabel('Distance to nearest true wall boundary (m)')
    axes[0].legend(loc='lower right',fontsize=8)
    fig.suptitle('Baseline-only oracle diagnosis — frozen parallax_v1, evaluation only',fontsize=13)
    fig.text(.5,.01,'Dots: all accepted points. Gray links: same original 5 / 6 points. Thick ticks: all-point median.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.045,1,.96))
    fig.savefig(EXP/'figures/baseline-only-errors.png',dpi=160)
    plt.close(fig)

    fig,axes=plt.subplots(2,2,figsize=(10.5,7))
    for j,case in enumerate(d.CASES):
        command,xy,t,yaw=trajectories[case]
        ax=axes[0,j]
        ax.plot(command[:,0],command[:,1],label='Command DR (M1)',color=colors[0])
        ax.plot(xy[:,0],xy[:,1],label='GT translation (evaluation)',color=colors[1])
        ax.scatter([0],[0],marker='s',color='black',s=20,label='Start')
        ax.set_aspect('equal',adjustable='datalim')
        ax.set_xlabel('Start-frame x (m)')
        ax.set_ylabel('Start-frame y (m)')
        ax.set_title(case+' | start-frame trajectory')
        ax.legend(fontsize=8)
        axes[1,j].plot(t,np.degrees(yaw),color=colors[0])
        axes[1,j].axhline(0,color='#888',lw=.8)
        axes[1,j].axvline(6.5,color=colors[1],ls='--',label='All original accepted points')
        axes[1,j].set_xlabel('Recording time (s)')
        axes[1,j].set_ylabel('Unchanged DR yaw minus GT (deg)')
        axes[1,j].legend(fontsize=8)
    for ax in axes.flat:ax.grid(alpha=.18)
    fig.suptitle('Evaluation-only trajectory / residual yaw audit — no GT control input',fontsize=13)
    fig.tight_layout(rect=(0,0,1,.96))
    fig.savefig(EXP/'figures/trajectory-and-yaw.png',dpi=160)
    plt.close(fig)
    for path in (EXP/'figures').glob('*.png'):assert path.stat().st_size<=1024**2

    # Includes the retained failed attempt; never deletes or rewrites raw files.
    files=[dict(path=str(p.relative_to(RAW)),bytes=p.stat().st_size,sha256=d.c.sha(p))
        for p in sorted(RAW.rglob('*')) if p.is_file()]
    d.c.dump(EXP/'results/raw-manifest.json',dict(root=str(RAW),files=files,
        total_bytes=sum(r['bytes'] for r in files),remote_backup=False))
    print(json.dumps(dict(gate=gate,files=len(files),bytes=sum(r['bytes'] for r in files),diagnostics=diagnostics),indent=2))


if __name__=='__main__':main()
