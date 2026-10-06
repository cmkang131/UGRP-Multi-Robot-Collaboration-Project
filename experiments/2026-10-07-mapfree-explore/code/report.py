"""Immutable offline result summary, source receipts and scientific figure."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

EXP = Path(__file__).resolve().parents[1]
ROOT = EXP.parents[1]


def dump(p,value):
    p.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def median(values):
    return float(np.median(values)) if values else None


def aggregate(rows):
    successes = [r for r in rows if r['status']=='B_confirmed']
    counts = Counter(r['status'] for r in rows)
    plans = Counter()
    reasons = Counter()
    for r in rows:
        plans.update(r['plans'])
        reasons.update(r['door_reasons'])
    return {'n':len(rows),'B_true':len(successes),'B_false':counts['B_false_confirmed'],
            'first_B_distance_m_median':median([r['first_B']['distance_m'] for r in successes]),
            'first_B_time_s_median':median([r['first_B']['time_s'] for r in successes]),
            'coverage_median':median([r['coverage'] for r in rows]),
            'collisions':sum(r['collisions'] for r in rows),
            'door_attempts':sum(r['door_attempts'] for r in rows),
            'wrong_door_attempts':sum(r['wrong_door_attempts'] for r in rows),
            'candidate_passage_attempts':sum(r['candidate_passage_attempts'] for r in rows),
            'false_candidate_passage_attempts':sum(r['false_candidate_passage_attempts'] for r in rows),
            'end_distance_m_median':median([r['distance_m'] for r in rows]),
            'end_time_s_median':median([r['time_s'] for r in rows]),
            'end_position_error_m_median':median([r['end_position_error_m'] for r in rows]),
            'statuses':dict(counts),'plans':dict(plans),'door_reasons':dict(reasons)}


def compare(rows):
    pairs = {}
    for r in rows:
        pairs.setdefault((r['scenario'],r['start'],r['seed']),{})[r['condition']] = r
    ratios_d,ratios_t = [],[]
    for p in pairs.values():
        if all(r['status']=='B_confirmed' for r in p.values()) and len(p)==2:
            b,a = p['static_map']['first_B'],p['own_frontier']['first_B']
            ratios_d.append(a['distance_m']/max(1e-9,b['distance_m']))
            ratios_t.append(a['time_s']/b['time_s'])
    return {'both_successful_pairs':len(ratios_d),'distance_ratio_median':median(ratios_d),
            'time_ratio_median':median(ratios_t)}


def report(dev,confirmation,out):
    out.mkdir(parents=True,exist_ok=True)
    all_rows,summary = [],{}
    for split,path in [('development',dev),('confirmation',confirmation)]:
        rows = json.loads((path/'results.json').read_text())
        all_rows.extend(rows)
        summary[split] = {condition:aggregate([r for r in rows if r['condition']==condition])
                          for condition in ('static_map','own_frontier')}
        summary[split]['paired'] = compare(rows)
    value = summary['confirmation']['own_frontier']
    pair = summary['confirmation']['paired']
    frozen = json.loads((EXP/'freeze.json').read_text())
    receipt = json.loads((confirmation/'source.json').read_text())
    checks = {'boundary':frozen['hashes']==receipt['hashes'],
              'B_confirmation':value['B_true']/value['n']>=.8 and value['B_false']==0,
              'efficiency':bool(pair['both_successful_pairs'] and pair['distance_ratio_median']<=2 and pair['time_ratio_median']<=2),
              'coverage':value['coverage_median']>=.4,
              'safety':value['collisions']==0 and value['wrong_door_attempts']==0 and
                       value['false_candidate_passage_attempts']==0 and value['door_attempts']>=1}
    # Frozen code equality supplements targeted off/input tests, not a complete information-flow proof.
    summary['checks'] = checks
    summary['criteria_passed'] = sum(checks.values())
    summary['scope'] = '2D model outcomes only; legacy wall error, unmeasured v7 process prior, idealized floor segmentation'
    dump(out/'summary.json',summary)
    dump(out/'results.json',all_rows)
    lines = ['| split | layout/start/seed | mode | outcome | first B m / s | coverage | collisions | door wrong / attempts |',
             '|---|---|---|---|---:|---:|---:|---:|']
    for r in all_rows:
        first = r['first_B']
        dt = f"{first['distance_m']:.2f} / {first['time_s']:.0f}" if first else 'N/A'
        lines.append(f"| {r['split']} | {r['scenario']}/{r['start']}/{r['seed']} | {r['condition']} | {r['status']} | {dt} | {r['coverage']:.1%} | {r['collisions']} | {r['wrong_door_attempts']} / {r['door_attempts']} |")
    (out/'tables.md').write_text('\n'.join(lines)+'\n')
    artifacts = {}
    for root in (dev,confirmation):
        for p in sorted(root.rglob('*')):
            if p.is_file():
                artifacts[str(p.resolve())] = {'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    dump(out/'artifacts.json',artifacts)
    return summary


def plot(confirmation,out):
    sys.path.insert(0,str(ROOT/'outputs/self-map-plot-deps'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    sys.path.insert(0,str(EXP/'code'))
    from grid_world import load_layout
    from run_grid import STARTS
    from harness.self_odom_grid import transform
    fig,axes = plt.subplots(2,2,figsize=(10,7))
    for ax,(scenario,start) in zip(axes.ravel(),[(1,'B'),(2,'D'),(4,'B'),(8,'D')]):
        _,static,rects,_ = load_layout(scenario)
        for r in rects:
            x,y=r['center'];hx,hy=r['half']
            ax.add_patch(Rectangle((x-hx,y-hy),2*hx,2*hy,angle=math.degrees(r['yaw']),rotation_point='center',
                                   color='0.35' if r['kind']=='wall' else '0.7'))
        b=static['regions']['zone_B'];x,y=b['center_m'];hx,hy=b['half_extents_m']
        ax.add_patch(Rectangle((x-hx,y-hy),2*hx,2*hy,color='royalblue',alpha=.25))
        for mode,color in [('static_map','darkorange'),('own_frontier','seagreen')]:
            p=confirmation/f's{scenario}-{start}-2701-{mode}'
            route=np.array(json.loads((p/'eval_path.json').read_text()))
            r=json.loads((p/'result.json').read_text())
            ax.plot(route[:,0],route[:,1],color=color,lw=1.3,label=f"{mode}: {r['status']}")
            ax.scatter(route[-1,0],route[-1,1],color=color,marker='x',s=35)
        ax.set_title(f's{scenario} / start {start} / seed 2701 (2D)')
        x0,x1,y0,y1=static['bounds_m'];ax.set_xlim(x0-.1,x1+.1);ax.set_ylim(y0-.1,y1+.1)
        ax.set_aspect('equal');ax.legend(fontsize=7,loc='lower right');ax.set_xlabel('evaluation world x (m)');ax.set_ylabel('y (m)')
    fig.suptitle('Frozen confirmation: modeled trajectories; not physical validation',fontsize=12)
    fig.tight_layout()
    fig.savefig(out/'confirmation-paths.png',dpi=135)
    plt.close(fig)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--development',type=Path,required=True)
    p.add_argument('--confirmation',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(report(a.development,a.confirmation,a.output),indent=2))
    plot(a.confirmation,a.output)
