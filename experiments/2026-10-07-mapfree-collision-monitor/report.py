"""Saved evidence only; plotting is matplotlib, never MuJoCo rendering."""
from pathlib import Path
import sys,json,math,csv
from collections import Counter
import numpy as np
sys.path.insert(0,str(Path(__file__).parent/'code'))
from monitor_common import *
from harness.public_navigation_unknown import UnknownActor,footprint_cells
from harness.public_navigation_monitor import ApproachMonitor
from harness.public_navigation_recovery import issued_twist
from harness.self_odom_grid import transform
from grid_world import inverse,load_layout
from diagnose_environment import rectangle_contacts
from gate import summary


def case(r):return f"{r['scenario']}-{r['start']}-{r['seed']}-{r['condition']}"


def collision_figure():
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Polygon
    entry=next(r for r in read(v7.EXP/'cohort.json')['rows'] if (r['scenario'],r['start'],r['seed'])==(3,'M',7701))
    raw=v7.RAW/'confirmation/s3-M-7701-own_frontier'
    contacts=lines(raw/'eval_contacts.jsonl');contact=contacts[0]
    records=lines(raw/'actor.jsonl');commands=lines(raw/'commands.jsonl')
    cmd=next(c for c in commands if c['t']<contact['t']<=c['t']+.100000001 and c['command']['kind']!='stop')
    actor=UnknownActor('own_frontier',navigation='public_ros_v7')
    erase_events=[]
    for a in records:
        if a['t']>cmd['t']:break
        actor.odom.correct(a['pose_odom'],np.zeros((3,3)));actor.t=a['t'];actor.steps=a['frame']
        actor.receive(a['observation'],[])
        for c in [c for c in commands if c['frame']==a['frame'] and c['t']<=cmd['t']]:
            actor.odom.correct(c['pose_odom'],np.zeros((3,3)))
            changed=[list(cell) for cell in footprint_cells(actor.grid,actor.odom.pose) if actor.grid.odds.get(cell,0)>0]
            if changed:erase_events.append(dict(t=c['t'],cells=changed))
            actor.clear_footprint()
        last=a
    actor.t=cmd['t'];cm=actor.make_costmap();pose=np.array(cmd['pose_odom'])
    monitor=ApproachMonitor();monitor.observe(last['observation']['wall_xy'],last['pose_odom'],last['t'])
    _,info=monitor.filter(cmd['command'],pose,cmd['t'])
    points=transform(last['observation']['wall_xy'],last['pose_odom'])
    _,static,rects,_=load_layout(3)
    wall=next(r for r in rects if r['id']=='wall_divider_1')
    c,s=math.cos(wall['yaw']),math.sin(wall['yaw'])
    polygon=(np.array([[-1,-1],[1,-1],[1,1],[-1,1]])*wall['half'])@np.array([[c,s],[-s,c]])+wall['center']
    wall_own=inverse(polygon,entry['pose'])
    physical=rectangle_contacts(contact['pose_world'],[wall],static['bounds_m'])
    # Report padded outline vs real robot separately, no feedback into the actor.
    proposed=np.r_[inverse([contact['proposed_pose_world'][:2]],entry['pose'])[0],contact['proposed_pose_world'][2]-entry['pose'][2]]
    fig,axes=plt.subplots(1,2,figsize=(10,4.3),layout='constrained')
    extent=[cm.origin[0],cm.origin[0]+cm.raw.shape[1]*.05,cm.origin[1],cm.origin[1]+cm.raw.shape[0]*.05]
    state=np.where(cm.raw==255,0,np.where(cm.raw==254,2,1))
    for ax in axes:
        ax.imshow(state,origin='lower',extent=extent,cmap=ListedColormap(['#b7bdc6','white','#3b6d88']),vmin=0,vmax=2,interpolation='nearest')
        ax.add_patch(Polygon(wall_own,fc='#777777',alpha=.7,label='Actual wall (eval only)'))
        for p,color,label in [(pose,'#166999','Current padded footprint'),(proposed,'#ce3e3e','Contact proposal padded footprint')]:
            _,poly=cm.footprint_mask(p);ax.add_patch(Polygon(poly,fill=False,ec=color,lw=1.4,label=label))
        ax.scatter(points[:,0],points[:,1],s=10,c='#e39417',label='Latest own wall endpoints')
        ax.set(aspect='equal',xlabel='Own x (m)',ylabel='Own y (m)')
    axes[0].set(xlim=(pose[0]-.3,pose[0]+.4),ylim=(pose[1]-.4,pose[1]+.3),title='v7 s3/M: contact despite free footprint cells')
    axes[1].set(xlim=(min(pose[0]-.5,points[:,0].min()-.2),max(pose[0]+.5,points[:,0].max()+.2)),ylim=(min(pose[1]-.5,points[:,1].min()-.2),max(pose[1]+.5,points[:,1].max()+.2)),title=f"Same-frame default monitor: {info['reason']}, TTC={info['ttc_s']:.1f}")
    axes[1].legend(fontsize=7,loc='upper right')
    (EXP/'figures').mkdir(exist_ok=True)
    fig.savefig(EXP/'figures/v7-contact.png',dpi=140);plt.close(fig)
    report=dict(case='s3-M-7701-own_frontier',equivalent_seed=7702,monitor_same_saved_frame=info,
        latest_wall_point_min_body_distance_m=float(np.linalg.norm(points-pose[:2],axis=1).min()),
        actual_unpadded_pre_contact_overlap=physical,occupied_cells_cleared_by_current_padded_footprint=erase_events,
        caution='Saved-frame monitor check only, not a counterfactual navigation outcome.')
    write(EXP/'results/v7-contact-monitor-audit.json',report)
    return report


def outcome_figure(rows):
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon
    manifest=read(v7.EXP/'cohort.json')['rows']
    fig,axes=plt.subplots(1,3,figsize=(12,4.5),layout='constrained')
    for ax,(index,start) in zip(axes,[(3,'M'),(4,'M'),(5,'M')]):
        entry=next(e for e in manifest if (e['scenario'],e['start'],e['seed'])==(index,start,7701))
        _,static,rects,_=load_layout(index)
        for box in rects:
            c,s=math.cos(box['yaw']),math.sin(box['yaw'])
            polygon=(np.array([[-1,-1],[1,-1],[1,1],[-1,1]])*box['half'])@np.array([[c,s],[-s,c]])+box['center']
            ax.add_patch(Polygon(polygon,fc='#888888',alpha=.65))
        for root,color,label in [(v7.RAW/'confirmation','#537487','v7 (existing)'),(RAW/'development','#d05120','v8 (development)')]:
            name=f's{index}-{start}-7701-own_frontier'
            path=np.array(read(root/name/'eval_path.json'))
            ax.plot(path[:,0],path[:,1],c=color,lw=1.2,label=label)
        r=next(r for r in rows if (r['scenario'],r['start'],r['seed'],r['condition'])==(f's{index}',start,7701,'own_frontier'))
        contacts=lines(RAW/'development'/case(r)/'eval_contacts.jsonl')
        for q in contacts:ax.scatter(*q['pose_world'][:2],c='#aa1515',marker='x',s=40)
        ax.scatter(*static['regions']['zone_B']['center_m'],c='#982d98',marker='*',s=100,label='B (eval only)')
        x0,x1,y0,y1=static['bounds_m']
        ax.set(xlim=(x0-.1,x1+.1),ylim=(y0-.1,y1+.1),aspect='equal',xlabel='World x (m)',ylabel='World y (m)',
            title=f"s{index}/{start}: {r['status']}\ncontacts={r['collisions']}, coverage={100*r['coverage']:.1f}%")
    axes[0].legend(fontsize=8)
    fig.savefig(EXP/'figures/development-paths.png',dpi=140);plt.close(fig)


def contact_timing(folder):
    # Evaluation-only attribution; no collision labels are passed to the actor.
    events=lines(folder/'eval_contacts.jsonl');actors=lines(folder/'actor.jsonl')
    report=[]
    for e in events:
        last=max((a for a in actors if a['t']<=e['t']),key=lambda a:a['t'])
        age=e['t']-last['t']
        report.append(dict(**e,since_latest_camera_s=age,
            phase='observation_hold' if age>=1.-1e-8 else 'action',
            source_age_gt_1s=age>1.,latest_wall_points=len(last['observation']['wall_xy'])))
    return report


def clock_only_audit():
    from harness.public_navigation.actor import MeasurementMemory
    from integer_episode import observation_time
    options=read(ROOT/'experiments/2026-10-07-mapfree-goal-floor/v3-selection.json')['selected']['options']
    out=[]
    for seed in (7701,7702):
        raw=v7.RAW/f'confirmation/s3-M-{seed}-own_frontier'
        records=lines(raw/'actor.jsonl')
        for mode in ('saved_float','integer_ticks'):
            memory=MeasurementMemory('r1',options=options);first=None
            for a in records:
                patches=[]
                for p in a['patches']:
                    # Interior points were popped by frozen memory before logging.
                    # Hull vertices suffice for unused cell-union bookkeeping;
                    # all confirmation inputs (hull, centre, pose, frame) are exact.
                    q={k:p[k] for k in ('component','pixels','center_body_m','hull_body_m','confidence')}
                    q['_points_body_m']=p['hull_body_m'];patches.append(q)
                t=a['t'] if mode=='saved_float' else observation_time(a['frame'])
                accepted=memory.add(patches,t,a['frame'],a['pose_odom'])
                if first is None and any(p['confirmed_t'] is not None for p in accepted):first=t
            out.append(dict(seed=seed,clock=mode,tracks=len(memory.tracks),first_confirmed_s=first,
                            max_views=max([len(t['views']) for t in memory.tracks],default=0)))
    assert all(r['first_confirmed_s'] is None for r in out if r['clock']=='saved_float')
    write(EXP/'results/clock-only-audit.json',dict(rows=out,
        scope='Same saved trajectory and patch geometry; time-only memory audit, not a new navigation outcome or precision evaluation.'))


def main():
    import matplotlib
    matplotlib.use('Agg')
    collision_figure()
    clock_only_audit()
    if '--diagnose-only' in sys.argv:return
    raw=RAW/'development';source=read(raw/'source.json');rows=read(raw/'results.json')
    assert source['hashes']==hashes()==read(EXP/'freeze.json')['hashes']
    decision=summary(rows,True);decision.update(split='development',next_stage='REGISTER_NEW_COHORT' if decision['passed'] else 'STOP_NO_TUNING')
    assert decision==read(raw/'gate.json')
    write(EXP/'results/gate.json',decision);write(EXP/'results/episodes.json',rows)
    with (EXP/'results/episodes.csv').open('w') as f:
        keys=['scenario','start','seed','condition','status','time_s','distance_m','coverage','collisions','false_candidate_passage_attempts','wrong_door_attempts','door_attempts']
        w=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore',lineterminator='\n');w.writeheader();w.writerows(rows)
    monitor_counts={};reasons=[]
    for r in rows:
        folder=raw/case(r);assert read(folder/'result.json')==r
        mon=read(folder/'monitor.json');counts=Counter(q['reason'] for q in mon)
        monitor_counts[case(r)]=dict(counts)
        if r['condition']=='own_frontier' and (r['status']!='B_confirmed' or r['collisions'] or r['false_candidate_passage_attempts']):
            a=lines(folder/'actor.jsonl');events=lines(folder/'navigation_events.jsonl')
            reasons.append(dict(case=case(r),status=r['status'],B_visible=r['sensor_draws']['B_positive_frames'],B_detected=r['sensor_draws']['B_detections'],
                collisions=r['collisions'],false_passage=r['false_candidate_passage_attempts'],
                monitor=counts,end_s=r['time_s'],last_events=events[-10:],contacts=contact_timing(folder),
                max_observation_gap_s=max([b['t']-a0['t'] for a0,b in zip(a,a[1:])],default=None)))
    write(EXP/'results/failure-types.json',reasons);write(EXP/'results/monitor-counts.json',monitor_counts)
    tables=['|map/start|v7 B|v8 B|v8 m / s (all)|coverage|contacts|false passage|','|---|---:|---:|---:|---:|---:|---:|']
    old=read(v7.RAW/'confirmation/results.json')
    for i in range(1,9):
        for start in ['M','N']:
            a=[r for r in old if r['scenario']==f's{i}' and r['start']==start and r['condition']=='own_frontier']
            b=[r for r in rows if r['scenario']==f's{i}' and r['start']==start and r['condition']=='own_frontier']
            tables.append(f"|s{i}/{start}|{sum(r['status']=='B_confirmed' for r in a)}/2|{sum(r['status']=='B_confirmed' for r in b)}/2|{np.median([r['distance_m'] for r in b]):.3f} / {np.median([r['time_s'] for r in b]):.1f}|{100*np.median([r['coverage'] for r in b]):.2f}%|{sum(r['collisions'] for r in b)}|{sum(r['false_candidate_passage_attempts'] for r in b)}|")
    (EXP/'results/table.md').write_text('\n'.join(tables)+'\n')
    outcome_figure(rows)
    files=[dict(path=str(p.relative_to(RAW)),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(RAW.rglob('*')) if p.is_file()]
    write(EXP/'results/raw-manifest.json',dict(root=str(RAW),files=files,total_bytes=sum(r['bytes'] for r in files)))
    write(EXP/'results/verification.json',dict(source_sha=source['sha'],source_files=len(source['hashes']),
        v7_preserved_files=121,episode_raw_equality=len(rows),physics=0,model_calls=0,
        prior_results_unchanged=sha(v7.RAW/'confirmation/results.json')==read(EXP/'freeze.json')['development_prior_results_sha256'],
        fresh_confirmation_runs=0,noisy_runs=0))
    print(json.dumps(decision,indent=2))

if __name__=='__main__':main()
