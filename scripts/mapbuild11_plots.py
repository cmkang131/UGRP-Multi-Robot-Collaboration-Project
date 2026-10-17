"""Plot sealed mapbuild11 evaluation in GCP5's existing analysis environment.

No filter rerun, pose fitting, physics or render. Causal own-map snapshots are
plotted as recorded; GT path/start gauge are labelled evaluation-only.
"""
import argparse
import json
import math
from pathlib import Path
import platform
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon


def read(p):return json.loads(p.read_text())


def transform(points,pose):
    c,s=math.cos(pose[2]),math.sin(pose[2])
    return np.asarray(points).reshape(-1,2)@np.array([[c,s],[-s,c]])+pose[:2]


def compose(a,b):
    xy=transform([b[:2]],a)[0]
    return [float(xy[0]),float(xy[1]),math.atan2(math.sin(a[2]+b[2]),math.cos(a[2]+b[2]))]


def main(a):
    if not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('ORIGINAL_GCP5_ONLY')
    rows=read(a.score/'frame-errors.json');summary=read(a.score/'summary.json');req=summary['requirements']
    names=['off','nav2_defaults_v1','nav2_rgb_field_v1'];route=[r for r in rows if r['stage']=='diagnostic_route']
    fig,axes=plt.subplots(2,1,figsize=(10,7),sharex=True)
    for name in names:
        rs=[r for r in route if r['models'][name]['xy_m'] is not None]
        axes[0].plot([r['route_path_m'] for r in rs],[r['models'][name]['xy_m']*1000 for r in rs],label=name,lw=1)
        axes[1].plot([r['route_path_m'] for r in rs],[r['models'][name]['yaw_deg'] for r in rs],label=name,lw=1)
    axes[0].axhline(req['position_error_m']*1000,color='k',ls='--',label='handoff XY budget')
    axes[0].set_ylabel('XY error (mm)');axes[1].set_ylabel('yaw error (deg)');axes[1].set_xlabel('actual route travel (m), evaluation only')
    for ax in axes:ax.grid();ax.legend(fontsize=8);ax.set_xticks(np.arange(0,summary['route_path_m']+.5,.5))
    fig.suptitle('Same recording; OFF initial gauge only; absolute AMCL candidates, unqualified')
    fig.tight_layout();fig.savefig(a.score/'error-curves.png',dpi=140);plt.close(fig)

    maps=read(a.score/'own-maps.json');static=read(a.input/'static-map.json');truth=read(a.input/'eval-only.json')['frames']
    fig,axes=plt.subplots(1,3,figsize=(12,7),sharex=True,sharey=True)
    all_points=[]
    for ax,name in zip(axes,names):
        samples=maps['nav2_defaults_v1'] if name=='off' else maps[name];points=[]
        for sample in samples:
            pose=compose(truth[0]['pose'],sample['own_odom']) if name=='off' else sample['pose']
            if pose is not None:points.extend(transform(sample['segments'],pose).tolist())
        pts=np.asarray(points).reshape(-1,2);all_points.extend(points)
        if len(pts):ax.scatter(pts[:,0],pts[:,1],s=.8,alpha=.25,c='tab:blue',rasterized=True)
        for wall in static['obstacles']:
            if 'wall' not in wall['id']:continue
            hx,hy=wall['half_extents_m'];p=transform([[-hx,-hy],[hx,-hy],[hx,hy],[-hx,hy]],[*wall['center_m'],wall.get('yaw_rad',0)])
            ax.add_patch(Polygon(p,closed=True,facecolor='grey',alpha=.4))
        gt=np.array([g['pose'][:2] for g in truth]);ax.plot(gt[:,0],gt[:,1],'k--',lw=.6,label='GT path: evaluation only')
        ax.set_title(name,fontsize=10);ax.set_aspect('equal');ax.grid();ax.set_xlabel('map x (m)')
    # Static navigation bounds are a declared display crop, not a map-quality
    # gate. Count excluded scan points explicitly rather than hiding outliers.
    x0,x1,y0,y1=static['bounds_m'];pts=np.asarray(all_points).reshape(-1,2)
    outside=int(((pts[:,0]<x0)|(pts[:,0]>x1)|(pts[:,1]<y0)|(pts[:,1]>y1)).sum()) if len(pts) else 0
    for ax in axes:ax.set_xlim(x0-.1,x1+.1);ax.set_ylim(y0-.1,y1+.1)
    axes[0].set_ylabel('map y (m)');axes[0].legend(fontsize=7)
    fig.suptitle('Causal own wall observations; static walls grey; unready candidates included\nDisplay: static bounds + 0.1m; no retrospective pose correction')
    fig.tight_layout();fig.savefig(a.score/'own-map-overlay.png',dpi=130);plt.close(fig)
    (a.score/'plot-review-metadata.json').write_text(json.dumps(dict(uses_sealed_predictions=True,filter_calls=0,
        physics_steps=0,render_calls=0,overview_camera=False,display_crop_m=[x0-.1,x1+.1,y0-.1,y1+.1],
        combined_map_points=len(pts),points_outside_navigation_bounds=outside,
        source='script mapbuild11_plots.py in existing rl1b-act-env; original score numerical outputs preserved'),indent=2)+'\n')
    print(json.dumps(dict(plots=2,filter_calls=0,combined_map_points=len(pts),outside_navigation_bounds=outside)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('input','score'):p.add_argument('--'+n,type=Path,required=True)
    main(p.parse_args())
