"""Summarize frozen public-core 2D evaluations, never rerun or tune an actor."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'experiments/2026-10-07-mapfree-public-navigation/code'))
from run_public import write,hashes
from scripts.report_mapfree_environment import funnel


def describe(folder):
    rows=json.loads((folder/'results.json').read_text())
    true=[r for r in rows if r['status']=='B_confirmed']
    med=lambda a:float(np.median(a)) if len(a) else None
    return dict(total=len(rows),true_B=len(true),false_B=sum(r['status']=='B_false_confirmed' for r in rows),
        statuses=dict(Counter(r['status'] for r in rows)),collisions=sum(r['collisions'] for r in rows),
        coverage_median=med([r['coverage'] for r in rows]),
        B_distance_median=med([r['first_B']['distance_m'] for r in true]),
        B_time_median=med([r['first_B']['time_s'] for r in true]),
        end_position_error_max=max(r['end_position_error_m'] for r in rows),
        door_attempts=sum(r['door_attempts'] for r in rows),wrong_door_attempts=sum(r['wrong_door_attempts'] for r in rows),
        plans=dict(sum((Counter(r['plans']) for r in rows),Counter())),
        events=dict(sum((Counter(r['navigation_events']) for r in rows),Counter())),
        B_visible_frames=sum(r['sensor_draws']['B_positive_frames'] for r in rows),
        B_detected_frames=sum(r['sensor_draws']['B_detections'] for r in rows))


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--development',type=Path,required=True)
    p.add_argument('--confirmation',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    manifest=[]
    for folder in [a.development,a.confirmation]:
        source=json.loads((folder/'source.json').read_text())
        if source['hashes']!=hashes():
            raise ValueError('EVALUATED_RUNTIME_CHANGED')
        for f in sorted(folder.rglob('*')):
            if f.is_file():
                manifest.append(dict(path=str(f.resolve()),bytes=f.stat().st_size,sha256=hashlib.sha256(f.read_bytes()).hexdigest()))
    report={key:describe(folder) for key,folder in [('development',a.development),('confirmation',a.confirmation)]}
    report['gate']=json.loads((a.confirmation/'gate.json').read_text())
    report['main_five_criteria']='NOT_EVALUATED: stage b/c blocked' if not report['gate']['passed'] else 'pending'
    write(a.output/'summary.json',report)
    write(a.output/'artifacts.json',dict(files=manifest,count=len(manifest),verified=True))
    tables=[]
    for name,folder in [('development',a.development),('confirmation',a.confirmation)]:
        rows=json.loads((folder/'results.json').read_text())
        write(a.output/(name+'-results.json'),[{k:v for k,v in r.items() if k not in ('sources','options')} for r in rows])
        write(a.output/(name+'-funnel.json'),funnel(folder,rows))
        tables += [f'## {name}: oracle static only','',
            '| pair | status | B time s | B distance m | coverage % | collision | wrong/issued door |',
            '|---|---|---:|---:|---:|---:|---:|']
        for r in rows:
            b=r['first_B']
            t=f"{b['time_s']:.1f}" if b else 'N/A'
            d=f"{b['distance_m']:.3f}" if b else 'N/A'
            tables.append(f"| {r['scenario']}/{r['start']}/{r['seed']} | {r['status']} | {t} | {d} | {100*r['coverage']:.2f} | {r['collisions']} | {r['wrong_door_attempts']}/{r['door_attempts']} |")
        tables += ['']
    (a.output/'tables.md').write_text('\n'.join(tables)+'\n')
    # Raw geometry and paths are evaluation-only, used solely in this explanatory figure.
    sys.path.insert(0,str(ROOT/'outputs/self-map-plot-deps'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle,Polygon
    from grid_world import load_layout
    from harness.self_odom_grid import transform
    fig,axes=plt.subplots(1,2,figsize=(10,4.5),constrained_layout=True)
    for ax,index,start in zip(axes,[1,4],['G','G']):
        scenario,static,rects,_=load_layout(index)
        for rect in rects:
            corners=np.array([[-1,-1],[1,-1],[1,1],[-1,1]])*rect['half']
            points=transform(corners,[*rect['center'],rect['yaw']])
            ax.add_patch(Polygon(points,color='gray' if rect['kind']=='wall' else '#c78b2b'))
        reg=static['regions']['zone_B']
        half=np.array(reg['half_extents_m'])
        ax.add_patch(Rectangle(np.array(reg['center_m'])-half,*list(2*half),facecolor='cyan',alpha=.3))
        folder=a.confirmation/f's{index}-{start}-4701-static_map'
        path=np.asarray(json.loads((folder/'eval_path.json').read_text()))
        row=json.loads((folder/'result.json').read_text())
        ax.plot(path[:,0],path[:,1],color='#2467b1',label='evaluation path')
        ax.scatter(path[0,0],path[0,1],marker='o',c='green')
        ax.scatter(path[-1,0],path[-1,1],marker='x',c='red')
        ax.set(xlim=static['bounds_m'][:2],ylim=static['bounds_m'][2:],xlabel='world x (m)',ylabel='world y (m)',
               title=f's{index}/{start}: {row["status"]}\ncoverage {100*row["coverage"]:.1f}%')
        ax.set_aspect('equal')
    fig.suptitle('Public cores / zero-noise oracle / new confirmation (evaluation only)')
    fig.savefig(a.output/'paths.png',dpi=130)
    plt.close(fig)
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
