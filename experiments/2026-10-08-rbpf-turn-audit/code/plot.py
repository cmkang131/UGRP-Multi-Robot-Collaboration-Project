"""Evaluation figures: fixed-cohort frontend and switchable graph separately."""
import sys
import numpy as np
from replay import ROOT,EXP,OUT,RAW,MODES,load,rows,transform,sha
sys.path.insert(0,str(ROOT/'outputs/self-map-plot-deps'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


def main():
    curves=load(OUT/'curves.json')
    (EXP/'figures').mkdir(exist_ok=True)
    fig,ax=plt.subplots(figsize=(9,3.5))
    for mode in MODES:
        c=curves[mode]['frontend'];line,=ax.plot(c['t'],c['yaw_error_deg'],label=mode+' frontend')
        b=curves[mode]['graph'];ax.plot(b['t'],b['yaw_error_deg'],':',color=line.get_color(),label=mode+' graph')
    ax.axvspan(35.7,39.9,color='.85');ax.axhline(0,color='.5',lw=.6)
    ax.set(xlabel='Recorded time (s)',ylabel='Yaw error (degrees)',title='Same recorded trajectory; shaded = largest single turn discrepancy')
    ax.legend(fontsize=7,ncol=3);fig.tight_layout();fig.savefig(EXP/'figures/yaw.png',dpi=130);plt.close(fig)
    truth=list(rows(RAW/'eval_only/trajectory.jsonl'));origin=[*truth[0]['robot_xyz_m'][:2],truth[0]['robot_yaw_rad']]
    actual=np.array([r['robot_xyz_m'][:2] for r in truth])
    walls=[w for w in load(RAW/'inputs/static_map.json')['obstacles'] if w.get('kind')=='wall']
    graphs={mode:load(OUT/mode/'graph.json') for mode in MODES}
    vmax=max(c[2] for g in graphs.values() for c in g['grid']['cells'])
    fig,axes=plt.subplots(1,3,figsize=(12,4.5),sharex=True,sharey=True)
    for mode,ax in zip(MODES,axes):
        assert sha(OUT/mode/'graph.json')==load(OUT/mode/'seal.json')['files']['graph.json']
        p=graphs[mode]
        for w in walls:
            x,y=w['center_m'];hx,hy=w['half_extents_m'];ax.add_patch(Rectangle((x-hx,y-hy),2*hx,2*hy,color='.8'))
        cells=np.array([c for c in p['grid']['cells'] if c[2]>0]).reshape(-1,3)
        xy=transform((cells[:,:2]+.5)*.1,origin)
        ax.scatter(*xy.T,c=cells[:,2],s=11,marker='s',cmap='Blues',vmin=0,vmax=vmax)
        path=transform([r['pose'][:2] for r in p['poses']],origin)
        ax.plot(*actual.T,'k-',lw=1,label='Actual (evaluation)')
        ax.plot(*path.T,color='#dd681e',lw=1,label='Graph path')
        ax.set(title=f'{mode}: {len(cells)} occupied cells',xlabel='World x (m)',aspect='equal')
        ax.legend(fontsize=7,loc='lower right')
    axes[0].set_ylabel('World y (m)')
    fig.suptitle('Switchable graph outputs; grey true walls, blue positive log-odds (not correctness confidence)',fontsize=10)
    fig.tight_layout();fig.savefig(EXP/'figures/maps.png',dpi=130,bbox_inches='tight');plt.close(fig)


if __name__=='__main__':main()
