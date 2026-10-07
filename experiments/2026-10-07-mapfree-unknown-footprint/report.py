"""Saved-output audit/figures only. No mission execution or parameter selection."""
from collections import Counter
import csv
import math
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).parent/'code'))
from unknown_common import *
from gate import summary
from grid_world import load_layout
from harness.self_odom_grid import transform
from harness.floor_goal_v3 import FloorGoalV3Options,compatible
from harness.public_navigation_unknown import UnknownCore,UnknownCostmap


def name(r):return f"{r['scenario']}-{r['start']}-{r['seed']}-{r['condition']}"


def track_diagnosis(records):
    options = FloorGoalV3Options(**read(ROOT/'experiments/2026-10-07-mapfree-goal-floor/v3-selection.json')['selected']['options'])
    tracks,epsilon_breaks = {},[]
    for row in records:
        for patch in row['patches']:
            k = patch['track_id']
            if k not in tracks:
                candidates = []
                for old in tracks.values():
                    dt = row['t']-old['t']
                    ok,reason,residual,overlap = compatible(old['hull'],old['anchor'],np.array(patch['hull_odom_m']),np.array(patch['center_odom_m']),options)
                    if ok and 3. < dt < 3.+1e-9:
                        candidates.append(dict(previous_track=old['id'],gap_s=dt,excess_s=dt-3.,residual_m=residual,overlap=overlap))
                if candidates:
                    epsilon_breaks.append(dict(frame=row['frame'],new_track=k,compatible_previous=candidates))
                tracks[k] = dict(id=k,anchor=np.array(patch['center_odom_m']),poses=[])
            tracks[k].update(t=row['t'],hull=np.array(patch['hull_odom_m']))
            tracks[k]['poses'].append(np.array(row['pose_odom'][:2]))
    counts = [len(t['poses']) for t in tracks.values()]
    return dict(tracks=len(tracks),max_views=max(counts,default=0),view_counts=counts,
        subnanosecond_gap_breaks=epsilon_breaks,
        max_track_translation_m=max((max(np.linalg.norm(p-t['poses'][0]) for p in t['poses']) for t in tracks.values()),default=0.))


def terminal_frontiers(folder,records,events):
    stored = read(folder/'own_grid.json')
    cells = np.array(stored['cells'])
    r = stored['resolution_m']
    pose = np.array(records[-1]['pose_odom'])
    bounds = np.vstack([cells[:,:2],np.floor(pose[:2]/r)])
    lo,hi = bounds.min(0).astype(int)-math.ceil(1/r),bounds.max(0).astype(int)+math.ceil(1/r)+1
    raw = np.full(tuple((hi-lo)[::-1]),255,np.uint8)
    for x,y,odds in cells:
        if odds:raw[int(y)-lo[1],int(x)-lo[0]] = 254 if odds>0 else 0
    cm = UnknownCostmap(raw,lo*r,r)
    core = UnknownCore()
    fronts = core.frontiers(cm.raw,cm.origin,r,pose[:2])
    blocked = [np.array(e['target']) for e in events if e['reason']=='progress_timeout_blacklist' or e['reason'].startswith('ABORTED_')]
    out = []
    for f in fronts:
        goal = cm.world_to_map(f[:2])
        out.append(dict(centroid=f[:2].tolist(),size=int(f[5]),blacklisted=any(np.all(np.abs(f[:2]-b)<5*r) for b in blocked),
            raw_goal=None if goal is None else int(cm.raw[goal[1],goal[0]]),
            inflated_goal=None if goal is None else int(cm.costs[goal[1],goal[0]])))
    return dict(frontiers=out,blacklist_size=len(blocked),all_remaining_blacklisted=bool(len(fronts) and all(f['blacklisted'] for f in out)))


def development_figure():
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Polygon,Patch
    from development_unknown import prepare
    item = read(v6.prior.EXP/'cohort.json')['rows'][0]
    case = f"s{item['scenario']}-{item['start']}-{item['seed']}-own_frontier"
    record = lines(v6.PRIOR_RAW/case/'actor.jsonl')[0]
    world = v6.RayOracleWorld(item['scenario'],item['pose'],item['seed'],'confirmation')
    world.advance(dict(t=0.,kind='stop'),2.)
    obs,patches,_ = world.observe(0)
    assert not patches and {k:v for k,v in obs.items() if not k.endswith('_origins_xy')}==record['observation']
    record = {**record,'observation':obs}
    old,new = v6.RaytraceActor('own_frontier',navigation='public_ros_v6'),UnknownActor('own_frontier',navigation='public_ros_v7')
    maps = [prepare(a,record)[0] for a in (old,new)]
    fig,axes = plt.subplots(1,2,figsize=(9,4),layout='constrained')
    pose = np.array([0.,0.,0.])
    endpoint = np.array([.025,.025,0.])
    for ax,cm,version in zip(axes,maps,('v6: connector rejected','v7: connector allowed')):
        state = np.where(cm.raw==255,0,np.where(cm.raw==254,2,1))
        extent = [cm.origin[0],cm.origin[0]+cm.raw.shape[1]*cm.resolution,cm.origin[1],cm.origin[1]+cm.raw.shape[0]*cm.resolution]
        ax.imshow(state,origin='lower',extent=extent,cmap=ListedColormap(['#b7bdc6','white','#333333']),vmin=0,vmax=2,interpolation='nearest')
        for p,color,style in [(pose,'#1c6b95','-'),((pose+endpoint)/2,'#b3294b','--')]:
            _,poly = cm.footprint_mask(p)
            ax.add_patch(Polygon(poly,fill=False,color=color,lw=1.5,ls=style))
        ax.plot([0,.025],[0,.025],'o-',color='#b3294b',ms=3)
        ax.set(title=version,xlabel='Own x (m)',ylabel='Own y (m)',xlim=(-.22,.5),ylim=(-.3,.3),aspect='equal')
        ax.grid(alpha=.2)
        assert cm.sweep_clear(pose,endpoint) == (version.startswith('v7'))
    axes[0].legend(handles=[Patch(color='#b7bdc6',label='Unknown (still 255 in v7)'),Patch(facecolor='white',edgecolor='gray',label='Ray free / body support')],fontsize=7,loc='lower right')
    fig.savefig(EXP/'figures/footprint-policy.png',dpi=150)
    plt.close(fig)


def overview(rows, manifest):
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon
    own = [r for r in rows if r['condition']=='own_frontier' and r['seed']==7701]
    # Deterministic descriptive selection, never a tuning/eligibility decision.
    chosen = []
    for subset in ([r for r in own if r['status']=='B_confirmed'],[r for r in own if r['status']!='B_confirmed'],
                   [r for r in own if r['collisions'] or r['false_candidate_passage_attempts']],list(reversed(own))):
        if subset:
            entry = next((r for r in subset if r not in chosen),None)
            if entry is not None:chosen.append(entry)
    chosen = chosen[:4]
    fig,axes = plt.subplots(1,len(chosen),figsize=(4*len(chosen),4.8),squeeze=False,layout='constrained')
    for ax,r in zip(axes[0],chosen):
        folder = RAW/'confirmation'/name(r)
        _,static,rects,_ = load_layout(int(r['scenario'][1:]))
        entry = next(q for q in manifest['rows'] if (q['scenario'],q['start'],q['seed'])==(int(r['scenario'][1:]),r['start'],r['seed']))
        for box in rects:
            c,s = math.cos(box['yaw']),math.sin(box['yaw'])
            corners = (np.array([[-1,-1],[1,-1],[1,1],[-1,1]])*box['half'])@np.array([[c,s],[-s,c]])+box['center']
            ax.add_patch(Polygon(corners,color='#999999' if box['kind']=='wall' else '#baaa9a',alpha=.6))
        grid = read(folder/'own_grid.json')
        cells = np.array(grid['cells'])
        points = transform((cells[:,:2]+.5)*grid['resolution_m'],entry['pose'])
        mask = cells[:,2]>0
        ax.scatter(points[mask,0],points[mask,1],s=3,c='#156f96',label='Own occupied cells')
        path = np.array(read(folder/'eval_path.json'))
        ax.plot(path[:,0],path[:,1],color='#c14f22',lw=1.2,label='Path')
        ax.scatter(*path[0,:2],s=25,c='#258748',marker='o',label='Start')
        goal = static['regions']['zone_B']
        ax.scatter(*goal['center_m'],marker='*',s=85,c='#9a278e',label='B (evaluation)')
        x0,x1,y0,y1 = static['bounds_m']
        ax.set(xlim=(x0-.1,x1+.1),ylim=(y0-.1,y1+.1),aspect='equal',xlabel='World x (m)',ylabel='World y (m)',
            title=f"{r['scenario']}/{r['start']}: {r['status']}\ncoverage {100*r['coverage']:.1f}% | contacts {r['collisions']}")
    axes[0,0].legend(fontsize=7,loc='lower left')
    fig.savefig(EXP/'figures/oracle-paths.png',dpi=150)
    plt.close(fig)
    return [name(r) for r in chosen]


def main():
    import matplotlib
    matplotlib.use('Agg')
    source = read(RAW/'confirmation/source.json')
    freeze = read(EXP/'freeze.json')
    assert hashes()==source['hashes']==freeze['hashes']
    assert SETTINGS==source['settings']==freeze['settings']
    rows = read(RAW/'confirmation/results.json')
    decision = summary(rows,True)
    assert decision==read(RAW/'confirmation/gate.json') and decision['complete']
    manifest = read(EXP/'cohort.json')
    details,pose_errors,inputs = [],[],[]
    for r in rows:
        folder = RAW/'confirmation'/name(r)
        assert read(folder/'result.json')==r
        actors,evaluation,events = (lines(folder/(p+'.jsonl')) for p in ('actor','eval_only','navigation_events'))
        entry = next(q for q in manifest['rows'] if (q['scenario'],q['start'],q['seed'])==(int(r['scenario'][1:]),r['start'],r['seed']))
        assert len(actors)==len(evaluation)==r['observations']
        for a,b in zip(actors,evaluation):
            actual = transform([a['pose_odom'][:2]],entry['pose'])[0]
            error = np.linalg.norm(actual-np.array(b['pose_world'][:2]))
            pose_errors.append(float(error))
        if r['condition']=='own_frontier':
            details.append(dict(case=name(r),status=r['status'],B_visible=r['sensor_draws']['B_positive_frames'],
                B_detected=r['sensor_draws']['B_detections'],first_B=r['first_B'],coverage=r['coverage'],
                distance_m=r['distance_m'],time_s=r['time_s'],collisions=r['collisions'],
                false_passage=r['false_candidate_passage_attempts'],wrong_doors=r['wrong_door_attempts'],
                nav_events=r['navigation_events'],last_events=events[-12:],
                last_plan=actors[-1]['plan'] if actors else None,contacts=lines(folder/'eval_contacts.jsonl')))
            details[-1]['B_tracks'] = track_diagnosis(actors)
            if r['status']!='B_confirmed':details[-1]['terminal_frontiers'] = terminal_frontiers(folder,actors,events)
    assert max(pose_errors)<1e-8 and 'mujoco' not in sys.modules
    out = EXP/'results'
    write(out/'gate.json',decision)
    write(out/'episodes.json',rows)
    write(out/'diagnosis.json',details)
    fields = ['scenario','start','seed','condition','status','distance_m','time_s','coverage','collisions',
        'wrong_door_attempts','false_candidate_passage_attempts','door_attempts','observations']
    with (out/'episodes.csv').open('w') as f:
        w = csv.DictWriter(f,fieldnames=fields,extrasaction='ignore',lineterminator='\n')
        w.writeheader()
        w.writerows(rows)
    table = ['|맵/시작(seed 7701/7702 동일 여부 별도)|정적 B|frontier B|frontier m / s|coverage|충돌|거짓 passage|',
             '|---|---:|---:|---:|---:|---:|---:|']
    for i in range(1,9):
        for start in ('M','N'):
            pair = [r for r in rows if r['scenario']==f's{i}' and r['start']==start]
            own = [r for r in pair if r['condition']=='own_frontier']
            base = [r for r in pair if r['condition']=='static_map']
            table.append(f"|s{i}/{start}|{sum(r['status']=='B_confirmed' for r in base)}/2|{sum(r['status']=='B_confirmed' for r in own)}/2|{np.median([r['distance_m'] for r in own]):.3f} / {np.median([r['time_s'] for r in own]):.1f}|{100*np.median([r['coverage'] for r in own]):.2f}%|{sum(r['collisions'] for r in own)}|{sum(r['false_candidate_passage_attempts'] for r in own)}|")
    (out/'table.md').write_text('\n'.join(table)+'\n')
    (EXP/'figures').mkdir(exist_ok=True)
    development_figure()
    chosen = overview(rows,manifest)
    files = [dict(path=str(p.relative_to(RAW)),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(RAW.rglob('*')) if p.is_file()]
    write(out/'raw-manifest.json',dict(root=str(RAW),files=files,total_bytes=sum(f['bytes'] for f in files)))
    identical = 0
    for i in range(1,9):
        for start in ('M','N'):
            for mode in ('static_map','own_frontier'):
                a,b = [RAW/'confirmation'/f's{i}-{start}-{seed}-{mode}' for seed in (7701,7702)]
                identical += int(all(sha(a/f)==sha(b/f) for f in ('actor.jsonl','commands.jsonl','eval_path.json')))
    write(out/'verification.json',dict(frozen_source_sha=source['sha'],frozen_files=len(source['hashes']),
        hashes_unchanged=True,raw_episode_equality=len(rows),oracle_pose_samples=len(pose_errors),
        oracle_xy_max_error_m=max(pose_errors),identical_seed_pairs=identical,total_seed_pairs=32,
        selected_plot_cases=chosen,physics=0,model_calls=0,noisy_runs=0,raw_files=len(files),raw_bytes=sum(f['bytes'] for f in files)))
    print(json.dumps(decision,indent=2))


if __name__=='__main__':main()
