"""Evaluation-only saved-log audit. No new controller run, MuJoCo or tuning."""
from pathlib import Path
import sys,json,math
import numpy as np
EXP=Path(__file__).resolve().parents[1]
ROOT=EXP.parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'experiments/2026-10-07-mapfree-unknown-footprint/code')]
import unknown_common as v7
from harness.public_navigation_unknown import UnknownActor,footprint_cells
from harness.public_navigation_recovery import issued_twist
from harness.self_odom_grid import transform
from grid_world import inverse,project,SEARCH
from diagnose_environment import rectangle_contacts


def audit():
    raw=v7.RAW/'confirmation'
    manifest=v7.read(v7.EXP/'cohort.json')
    previous=v7.read(v7.EXP/'results/diagnosis.json')
    rows=[]
    for entry in manifest['rows']:
        name=f"s{entry['scenario']}-{entry['start']}-{entry['seed']}-own_frontier"
        folder=raw/name
        result=v7.read(folder/'result.json')
        if not (result['collisions'] or result['false_candidate_passage_attempts'] or result['status']!='B_confirmed'):continue
        world=v7.v6.RayOracleWorld(entry['scenario'],entry['pose'],entry['seed'],'confirmation')
        actor=UnknownActor('own_frontier',navigation='public_ros_v7')
        records=v7.lines(folder/'actor.jsonl');commands=v7.lines(folder/'commands.jsonl')
        contacts=v7.lines(folder/'eval_contacts.jsonl')
        details=[];contact_details=[]
        for a in records:
            actor.odom.correct(a['pose_odom'],np.zeros((3,3)));actor.t=a['t'];actor.steps=a['frame']
            actor.receive(a['observation'],[]) # no goal/nav evaluation required
            for cmd in [c for c in commands if c['frame']==a['frame']]:
                pose=np.array(cmd['pose_odom']);actor.odom.correct(pose,np.zeros((3,3)));actor.t=cmd['t'];actor.clear_footprint()
                command=cmd['command']
                if command['kind']=='stop':continue
                twist=issued_twist(command)
                if np.linalg.norm(twist[:2])<1e-9:continue
                world.pose=np.r_[transform([pose[:2]],world.start)[0],pose[2]+world.start[2]]
                world.events(cmd['t'])
                target=transform([twist[:2]*command['duration_s']],pose)[0]
                old_false=world.false_candidate_attempts
                old_times=world.last_attempt.copy()
                plan={**a['plan'],'path_m':[pose[:2].tolist(),target.tolist()]}
                world.passage_intent(plan,pose,cmd['t'])
                relevant=[c for c in contacts if cmd['t']<c['t']<=cmd['t']+.100000001]
                if world.false_candidate_attempts==old_false and not relevant:continue
                cm=actor.make_costmap()
                end=np.r_[transform([target],world.start)[0],world.pose[2]+twist[2]*.1]
                swept=[rectangle_contacts(p,world.rects,world.static['bounds_m']) for p in np.linspace(world.pose,end,9)]
                def value(p):
                    cell=cm.world_to_map(p)
                    return None if cell is None else int(cm.raw[cell[1],cell[0]])
                info=dict(t=cmd['t'],frame=a['frame'],own_pose=pose.tolist(),end_own=target.tolist(),
                    centerline_raw=[value(p) for p in np.linspace(pose[:2],target,9)],
                    actual_short_sweep_contacts=sorted({x for xs in swept for x in xs}))
                for p in plan['doors']:
                    if world.last_attempt.get(p['id'])==cmd['t'] and old_times.get(p['id'])!=cmd['t']:
                        center=transform([p['center_m']],world.start)[0]
                        if not any(np.linalg.norm(center-np.array(q['center_m']))<.3 for q in world.static.get('passages',[])):
                            details.append({**info,'candidate':p,'candidate_raw':value(p['center_m'])})
                for contact in relevant:
                    proposed=np.r_[inverse([contact['proposed_pose_world'][:2]],world.start)[0],contact['proposed_pose_world'][2]-world.start[2]]
                    fc=footprint_cells(actor.grid,proposed)
                    samples=[(np.array(c)+.5)*actor.grid.resolution for c in fc]
                    vals=[value(p) for p in samples]
                    # Cells intersected by the actual named obstacle; centre sampling stated explicitly.
                    wall=next(r for r in world.rects if r['id']==contact['contacts'][0])
                    from grid_world import boxes_occupied
                    inside=boxes_occupied(np.array(transform(samples,world.start)),[wall])
                    contact_details.append({**info,'contact':contact,'footprint_raw_counts':{str(v):vals.count(v) for v in set(vals)},
                        'actual_wall_cell_center_raw':[vals[i] for i in np.flatnonzero(inside)],
                        'latest_observation_age_s':cmd['t']-a['t'],'latest_wall_points':len(a['observation']['wall_xy'])})
        assert len(details)==result['false_candidate_passage_attempts'],(name,len(details),result['false_candidate_passage_attempts'])
        assert len(contact_details)==result['collisions'],(name,len(contact_details))
        old=next(r for r in previous if r['case']==name)
        visibility=[]
        if result['status']!='B_confirmed':
            region=world.static['regions']['zone_B'];cx,cy=region['center_m'];hx,hy=region['half_extents_m']
            x,y=np.meshgrid(np.arange(cx-hx,cx+hx+.001,.025),np.arange(cy-hy,cy+hy+.001,.025));pts=np.c_[x.ravel(),y.ravel()]
            for e in v7.lines(folder/'eval_only.jsonl'):
                world.pose=np.array(e['pose_world']);body=inverse(pts,world.pose)
                uv,valid,origin=project(body,SEARCH);_,_,unoccluded=world.visibility(pts,SEARCH)
                visibility.append(dict(t=e['t'],range_min_m=float(np.linalg.norm(body-origin[:2],axis=1).min()),
                    projected_in_fov=int(valid.sum()),unoccluded=int(unoccluded.sum())))
        rows.append(dict(case=name,status=result['status'],false_passages=details,contacts=contact_details,
            B_visibility=visibility,B_tracks=old['B_tracks'],terminal_frontiers=old.get('terminal_frontiers'),
            budget_s=900.,end_s=result['time_s']))
    assert sum(len(r['false_passages']) for r in rows)==14
    assert sum(len(r['contacts']) for r in rows)==2
    v7.write(EXP/'results/v7-event-diagnosis.json',dict(prior_source_sha=v7.read(raw/'source.json')['sha'],
        prior_results_sha256=v7.sha(raw/'results.json'),rows=rows,physics=0,model_calls=0))
    for r in rows:
        print(r['case'],r['status'],'false',[(round(p['t'],1),p['candidate']['reason'],p['centerline_raw'],p['actual_short_sweep_contacts']) for p in r['false_passages']],
            'contact',r['contacts'],'Bminrange',min([v['range_min_m'] for v in r['B_visibility']],default=None),
            'Bmaxfov',max([v['projected_in_fov'] for v in r['B_visibility']],default=None),
            'Bmaxunoccluded',max([v['unoccluded'] for v in r['B_visibility']],default=None),flush=True)

if __name__=='__main__':audit()
