"""Evaluation-only fixed-cohort map overview, no estimator imports of truth."""
import sys
import numpy as np
from replay import ROOT,EXP,OUT,RAW,load,rows,transform,sha
sys.path.insert(0,str(ROOT/'outputs/self-map-plot-deps'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


def main():
    truth=list(rows(RAW/'eval_only/trajectory.jsonl'))
    origin=[*truth[0]['robot_xyz_m'][:2],truth[0]['robot_yaw_rad']]
    actual=np.array([r['robot_xyz_m'][:2] for r in truth])
    walls=[w for w in load(RAW/'inputs/static_map.json')['obstacles'] if w.get('kind')=='wall']
    predictions={mode:load(OUT/mode/'prediction.json') for mode in ('off','on')}
    vmax=max(c[2] for p in predictions.values() for c in p['grid']['cells'])
    fig,axes=plt.subplots(1,2,figsize=(10,4.5),sharex=True,sharey=True)
    for mode,ax in zip(('off','on'),axes):
        assert sha(OUT/mode/'prediction.json')==load(OUT/mode/'seal.json')['sha256']
        pred=predictions[mode]
        for w in walls:
            x,y=w['center_m'];hx,hy=w['half_extents_m']
            ax.add_patch(Rectangle((x-hx,y-hy),2*hx,2*hy,color='.8'))
        cells=np.array([c for c in pred['grid']['cells'] if c[2]>0]).reshape(-1,3)
        xy=transform((cells[:,:2]+.5)*.1,origin)
        im=ax.scatter(*xy.T,c=cells[:,2],s=18,marker='s',cmap='Blues',vmin=0,vmax=vmax)
        path=transform([r['pose'][:2] for r in pred['poses']],origin)
        ax.plot(*actual.T,'k-',lw=1,label='Recorded true path (evaluation)')
        ax.plot(*path.T,color='#dd681e',lw=1,label='Estimated path')
        ax.set(title=f'{mode}: {len(pred["ledger"])} inserted scans, {len(cells)} occupied cells',xlabel='World x (m)',aspect='equal')
        ax.legend(fontsize=6,loc='lower right')
    axes[0].set_ylabel('World y (m)')
    fig.suptitle(f'Same 891 observations; grey = true walls, blue = log-odds (shared scale 0 to {vmax:.2g}, not correctness)',fontsize=9)
    fig.tight_layout()
    (EXP/'figures').mkdir(exist_ok=True)
    fig.savefig(EXP/'figures/maps.png',dpi=140)
    plt.close(fig)


if __name__=='__main__':main()
