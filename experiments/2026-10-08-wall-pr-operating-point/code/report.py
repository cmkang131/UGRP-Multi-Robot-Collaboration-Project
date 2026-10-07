"""Plots/tables from sealed results; no selection changes or new replay."""
import argparse,csv
from run import *
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


def devfig():
    data=load(EXP/'results/development.json')
    fig,axes=plt.subplots(1,2,figsize=(12,5),constrained_layout=True)
    table=[]
    for ax,(kind,r) in zip(axes,data['representations'].items()):
        for a,color in zip(ANGLES,['#285185','#55a868','#d6802b','#a04098','#9f2b2b']):
            values=[c for c in r['candidates'] if c['min_angle_deg']==a and c['metrics']['full']['precision_015'] is not None]
            ax.plot([c['metrics']['full']['wall_coverage'] for c in values],
                    [c['metrics']['full']['precision_015'] for c in values],'-o',ms=4,c=color,label=f'angle >= {a} deg')
        for c in r['candidates']:
            q=c['metrics'];table.append(dict(representation=kind,min_views=c['min_views'],min_angle_deg=c['min_angle_deg'],
                precision=q['full']['precision_015'],recall=q['full']['wall_coverage'],rmse_m=q['full']['wall_error_rmse_m'],
                cells=q['sample_count'],covered=q['covered_samples'],total=329,
                region_precision=q['region']['precision'],region_recall=q['region']['recall'],
                region_cells=q['region']['n'],region_visible=q['region']['visible']))
        chosen=r['selection'];q=chosen.get('development_metrics',{}).get('full',{})
        if q:
            ax.scatter([q['wall_coverage']],[q['precision_015']],marker='*',s=170,c='black',zorder=5)
            point=chosen['operating_point'];label=f'N={point["min_views"]}, A={point["min_angle_deg"]} deg\n'+('selected' if chosen['status']=='precision_feasible' else 'INFEASIBLE: diagnostic only')
            ax.annotate(label,(q['wall_coverage'],q['precision_015']),xytext=(15,-25),textcoords='offset points',fontsize=9)
        off=r['off']['full']
        ax.scatter([off['wall_coverage']],[off['precision_015']],marker='x',s=80,c='gray',label='unfiltered baseline')
        ax.axhline(.9,c='black',lw=.7,ls='--');ax.axvline(.7,c='black',lw=.7,ls='--')
        ax.set(xlim=(-.02,1.02),ylim=(-.02,1.04),xlabel='Full-wall recall (329 samples)',ylabel='Precision (0.1m cells)',title=f'31001 development only: {kind}')
        ax.legend(loc='lower right',fontsize=8)
        ax.grid(alpha=.15)
    fig.savefig(EXP/'figures/development-pr.png',dpi=150)
    with (EXP/'results/development-curve.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(table[0]));writer.writeheader();writer.writerows(table)


def finalfig():
    data=load(EXP/'results/held.json');evaluate=Evaluator('32002')
    folder=verify_prediction('32002')
    poses=rows(EPISODES['32002']/'frontend-covariances.jsonl')
    truth=rows(EPISODES['32002']/'eval_only/trajectory.jsonl')
    estimated=transform([p['pose'][:2] for p in poses],evaluate.origin)
    actual=np.array([p['robot_xyz_m'][:2] for p in truth])
    fig,axes=plt.subplots(2,2,figsize=(11,8),constrained_layout=True)
    all_points=[]
    for row,kind in enumerate(('grid','segments')):
        for col,(suffix,label) in enumerate((('', 'off'),('-selected','fixed point'))):
            value=load(folder/f'{kind}{suffix}.json');ax=axes[row,col]
            for x,y,hx,hy in evaluate.walls:ax.add_patch(Rectangle((x-hx,y-hy),2*hx,2*hy,color='.75'))
            ax.plot(actual[:,0],actual[:,1],c='green',lw=.6,label='actual path (eval)')
            ax.plot(estimated[:,0],estimated[:,1],c='orange',lw=.6,label='estimated path')
            if kind=='grid':
                xy=transform((np.array([c[:2] for c in value['cells'] if c[2]>0]).reshape(-1,2)+.5)*.1,evaluate.origin)
                ax.scatter(xy[:,0],xy[:,1],s=5,c='navy');all_points.extend(xy.tolist())
            else:
                for line in value['segments']:
                    xy=transform(line['endpoints_m'],evaluate.origin)
                    ax.plot(xy[:,0],xy[:,1],c='navy',lw=2);all_points.extend(xy.tolist())
            q=data['representations'][kind]['off' if suffix=='' else 'on']
            p=q['full']['precision_015'];r=q['full']['wall_coverage'];rmse=q['full']['wall_error_rmse_m']
            ptext='NA' if p is None else f'{p:.1%}';etext='NA' if rmse is None else f'{rmse:.3f}'
            ax.set(title=f'32002 {kind}, {label}\nP/R {ptext}/{r:.1%}, RMSE {etext}m, cells {q["sample_count"]}',xlabel='world x (eval only), m',ylabel='world y, m',aspect='equal')
    pts=np.array(all_points+[[x-hx,y-hy] for x,y,hx,hy in evaluate.walls]+[[x+hx,y+hy] for x,y,hx,hy in evaluate.walls])
    lo,hi=pts.min(0)-.3,pts.max(0)+.3
    for ax in axes.ravel():ax.set_xlim(lo[0],hi[0]);ax.set_ylim(lo[1],hi[1])
    axes[0,0].legend(fontsize=7)
    fig.savefig(EXP/'figures/held-maps.png',dpi=140)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['dev','held']);a=p.parse_args()
    devfig() if a.stage=='dev' else finalfig()
