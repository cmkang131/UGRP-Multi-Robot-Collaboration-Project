"""Report immutable 2D environment ablations; no actor/evaluator execution."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT/'experiments/2026-10-07-mapfree-explore'
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(EXP/'code'))
from report import aggregate, compare
from grid_world import load_layout
from scripts.score_mapfree_passage_commands import rescore

RUNS = {
    'seen_before_noisy':'mapfree-explore-confirmation-v1',
    'seen_before_oracle':'mapfree-explore-environment-diagnostic-v1',
    'seen_envfix_noisy':'mapfree-explore-env-v2-noisy',
    'seen_envfix_oracle':'mapfree-explore-env-v2-oracle',
    'development_v2_noisy':'mapfree-explore-v2-development-noisy',
    'development_v2_oracle':'mapfree-explore-v2-development-oracle',
    'fresh_v2_noisy':'mapfree-explore-v2-confirmation-noisy',
    'fresh_v2_oracle':'mapfree-explore-v2-confirmation-oracle',
}


def dump(path,value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def funnel(folder, rows):
    output = []
    for r in rows:
        name = f"{r['scenario']}-{r['start']}-{r['seed']}-{r['condition']}"
        p = folder/name
        actor = [json.loads(s) for s in (p/'actor.jsonl').read_text().splitlines()]
        truth = [json.loads(s) for s in (p/'eval_only.jsonl').read_text().splitlines()]
        tracks = {}
        for log,evaluation in zip(actor,truth):
            for patch,true in zip(log['patches'],evaluation['B_component_truth']):
                if true:
                    tracks.setdefault(patch['track_id'],[]).append((log['t'],log['pose_odom']))
        baselines = [max(np.linalg.norm(np.array(pose[:2])-poses[0][1][:2]) for _,pose in poses)
                     for poses in tracks.values() if len(poses)>=3]
        output.append(dict(episode=name,condition=r['condition'],first_plan_has_path=bool(actor and actor[0]['plan']['path_m']),
            frames_with_path=sum(len(l['plan']['path_m'])>1 for l in actor),
            B_visible_frames=r['sensor_draws']['B_positive_frames'],B_detected_frames=r['sensor_draws']['B_detections'],
            true_tracks=len(tracks),true_tracks_3views=len(baselines),true_tracks_3views_translation=sum(bool(x>=.05) for x in baselines),
            max_3view_track_translation_m=float(max(baselines,default=0.)),status=r['status']))
    return output


def figure(out):
    sys.path.insert(0,str(ROOT/'outputs/self-map-plot-deps'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon,Rectangle
    from harness.self_odom_grid import transform
    fig,axs = plt.subplots(2,2,figsize=(11,7.6),layout='constrained')
    examples = [
        ('seen_before_noisy','s1-B-2701-static_map','Original noisy static'),
        ('seen_envfix_oracle','s1-B-2701-static_map','Corrected collision / oracle static'),
        ('development_v2_oracle','s2-A-1701-own_frontier','v2 oracle: B confirmed'),
        ('development_v2_oracle','s1-A-1701-own_frontier','v2 oracle: repeated frontier route'),
    ]
    for ax,(key,name,title) in zip(axs.ravel(),examples):
        p = ROOT/'outputs'/RUNS[key]/name
        r = json.loads((p/'result.json').read_text())
        path = np.array(json.loads((p/'eval_path.json').read_text()))
        _,world,rects,_ = load_layout(int(r['scenario'][1:]))
        for obstacle in rects:
            pts = transform(np.array([[-1,-1],[-1,1],[1,1],[1,-1]])*obstacle['half'],(*obstacle['center'],obstacle['yaw']))
            ax.add_patch(Polygon(pts,color='#474e58' if obstacle['kind']=='wall' else '#c28439'))
        goal=world['regions']['zone_B']
        half=np.array(goal['half_extents_m'])
        ax.add_patch(Rectangle(np.array(goal['center_m'])-half,*2*half,color='#3c91cc',alpha=.5))
        ax.plot(path[:,0],path[:,1],color='#d64c4c',lw=1.4)
        ax.scatter(*path[0,:2],c='#208b52',marker='o',s=25,zorder=5)
        ax.scatter(*path[-1,:2],c='#111',marker='x',s=35,zorder=5)
        x0,x1,y0,y1=world['bounds_m']
        ax.set(xlim=(x0,x1),ylim=(y0,y1),aspect='equal',xlabel='world x (m), evaluation only',ylabel='world y (m)',
               title=f"{title}\n{name}: {r['status']}, coverage {r['coverage']:.1%}")
    fig.savefig(out/'environment-diagnosis.png',dpi=140)
    plt.close(fig)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    summary,all_rows,details,receipts = {},{}, {},[]
    table=['| cohort | mode | n | B true/false | B distance/time median | coverage | collisions | wrong/door attempts |',
           '|---|---|---:|---:|---|---:|---:|---:|']
    per_episode=['| cohort | scenario | start | seed | mode | status | B distance/time | coverage | collision | wrong/doors |',
                 '|---|---|---|---:|---|---|---|---:|---:|---:|']
    frozen=json.loads((EXP/'freeze-v2.json').read_text())
    for cohort,dirname in RUNS.items():
        folder=ROOT/'outputs'/dirname
        raw_rows=json.loads((folder/'results.json').read_text())
        rows=[rescore(folder,r) for r in raw_rows]
        # Repeated input/config dictionaries remain in the hashed raw result files.
        all_rows[cohort]=[{k:v for k,v in row.items() if k not in ('sources','options')} for row in rows]
        details[cohort]=funnel(folder,rows)
        stats={m:aggregate([r for r in rows if r['condition']==m]) for m in ('static_map','own_frontier')}
        stats['paired']=compare(rows)
        stats['pre_command_plan_counters']={mode:{key:sum(r[key] for r in raw_rows if r['condition']==mode)
            for key in ('door_attempts','wrong_door_attempts','candidate_passage_attempts','false_candidate_passage_attempts')}
            for mode in ('static_map','own_frontier')}
        for mode in ('static_map','own_frontier'):
            r=stats[mode]
            dt='N/A' if r['B_true']==0 else f"{r['first_B_distance_m_median']:.3f} m / {r['first_B_time_s_median']:.1f} s"
            table.append(f"| {cohort} | {mode} | {r['n']} | {r['B_true']}/{r['B_false']} | {dt} | {r['coverage_median']:.2%} | {r['collisions']} | {r['wrong_door_attempts']}/{r['door_attempts']} |")
        for r in rows:
            b=r['first_B']
            dt='N/A' if b is None else f"{b['distance_m']:.3f} m / {b['time_s']:.1f} s"
            per_episode.append(f"| {cohort} | {r['scenario']} | {r['start']} | {r['seed']} | {r['condition']} | {r['status']} | {dt} | {r['coverage']:.2%} | {r['collisions']} | {r['wrong_door_attempts']}/{r['door_attempts']} |")
        if cohort.startswith('fresh'):
            own,pair=stats['own_frontier'],stats['paired']
            receipt=json.loads((folder/'source.json').read_text())
            checks=dict(boundary=receipt['hashes']==frozen['hashes'],
                B_confirmation=own['B_true']/own['n']>=.8 and own['B_false']==0,
                efficiency=bool(pair['both_successful_pairs'] and pair['distance_ratio_median']<=2 and pair['time_ratio_median']<=2),
                coverage=own['coverage_median']>=.4,
                safety=own['collisions']==0 and own['wrong_door_attempts']==0 and own['false_candidate_passage_attempts']==0 and own['door_attempts']>=1)
            stats.update(checks=checks,criteria_passed=sum(checks.values()))
            assert receipt['starts']==frozen['starts']
            assert len(rows)==64
        summary[cohort]=stats
        for path in sorted(folder.rglob('*')):
            if path.is_file():
                receipts.append(dict(path=str(path.relative_to(ROOT)),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    dump(args.output/'summary.json',summary)
    dump(args.output/'results.json',all_rows)
    dump(args.output/'funnels.json',details)
    dump(args.output/'artifacts.json',receipts)
    (args.output/'tables.md').write_text('\n'.join(table)+'\n\nModeled time; failed first-B values stay N/A. Cohorts are not pooled.\n'
        'Door counts use issued_translation_v2 post-hoc scoring. Raw pre-command plan counters are preserved separately in summary/results.\n\n'+'\n'.join(per_episode)+'\n')
    figure(args.output)
    print(json.dumps({k:v for k,v in summary.items() if k.startswith('fresh')},indent=2))


if __name__=='__main__':
    main()
