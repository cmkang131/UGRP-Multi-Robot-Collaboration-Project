"""Read-only reconstruction of old v8 events; never runs a new navigation policy."""
from pathlib import Path
import sys,math
from collections import Counter
import numpy as np
sys.path.insert(0,str(Path(__file__).parent/'code'))
from stop_common import *
from harness.public_navigation_monitor import MonitorActor,ApproachMonitor
from harness.public_navigation_unknown import footprint_cells
from harness.public_navigation_recovery import issued_twist
from harness.self_map_prob import V7CommandOdometry
from harness.self_odom_grid import transform
from grid_world import inverse,boxes_occupied
from diagnose_environment import rectangle_contacts


def velocity_at(commands,t):
    # Original command integrator, including implicit observation stops. No fix.
    odom=V7CommandOdometry()
    rows=[dict(c['command']) for c in commands if c['t']<=t+1e-8]
    rows += [dict(t=float(i*3),kind='stop') for i in range(int(t//3)+1)]
    for row in sorted(rows,key=lambda r:r['t']):
        if row['t']<=t+1e-8:odom.command(row)
    odom.advance(t)
    return odom._predictor.vel.copy()


def main():
    manifest=read(v8.v7.EXP/'cohort.json')
    output=[]
    for entry in manifest['rows']:
        name=f"s{entry['scenario']}-{entry['start']}-{entry['seed']}-own_frontier"
        folder=PRIOR/name
        result=read(folder/'result.json')
        if not (result['collisions'] or result['false_candidate_passage_attempts']):continue
        world=v8.v7.v6.RayOracleWorld(entry['scenario'],entry['pose'],entry['seed'],'confirmation')
        actor=MonitorActor('own_frontier',navigation='public_ros_v8')
        records=lines(folder/'actor.jsonl')
        commands=lines(folder/'commands.jsonl')
        contacts=lines(folder/'eval_contacts.jsonl')
        contact_samples={round(r['t']*10):r for r in lines(folder/'contact_inputs.jsonl')}
        details=[]
        contact_details=[]
        for a in records:
            actor.odom.correct(a['pose_odom'],np.zeros((3,3)))
            actor.t=a['t']
            actor.steps=a['frame']
            actor.receive(a['observation'],[])
            for cmd in [c for c in commands if c['frame']==a['frame']]:
                pose=np.array(cmd['pose_odom'])
                actor.odom.correct(pose,np.zeros((3,3)))
                actor.t=cmd['t']
                sample=contact_samples.get(round(cmd['t']*10))
                if sample is not None:actor.receive_contact(sample)
                cm=actor.make_costmap()
                if cmd['command']['kind']=='stop':continue
                twist=issued_twist(cmd['command'])
                world.pose=np.r_[transform([pose[:2]],world.start)[0],pose[2]+world.start[2]]
                world.events(cmd['t'])
                target=transform([twist[:2]*cmd['command']['duration_s']],pose)[0]
                old_false=world.false_candidate_attempts
                old_times=world.last_attempt.copy()
                plan={**a['plan'],'path_m':[pose[:2].tolist(),target.tolist()]}
                if np.linalg.norm(twist[:2])>1e-9:world.passage_intent(plan,pose,cmd['t'])
                relevant=[c for c in contacts if cmd['t']<c['t']<=cmd['t']+.100000001]
                if world.false_candidate_attempts==old_false and not relevant:continue
                def value(point):
                    cell=cm.world_to_map(point)
                    return None if cell is None else int(cm.raw[cell[1],cell[0]])
                end=np.r_[transform([target],world.start)[0],world.pose[2]+twist[2]*.1]
                sweep=sorted({x for p in np.linspace(world.pose,end,9)
                    for x in rectangle_contacts(p,world.rects,world.static['bounds_m'])})
                info=dict(case=name,t=cmd['t'],frame=a['frame'],pose_odom=pose.tolist(),
                    end_own=target.tolist(),requested_twist=twist.tolist(),
                    centerline_raw=[value(p) for p in np.linspace(pose[:2],target,9)],
                    requested_short_sweep_contacts=sweep)
                for candidate in plan['doors']:
                    if world.last_attempt.get(candidate['id'])!=cmd['t'] or old_times.get(candidate['id'])==cmd['t']:continue
                    centre=transform([candidate['center_m']],world.start)[0]
                    nearest=min((np.linalg.norm(centre-np.array(q['center_m'])) for q in world.static.get('passages',[])),default=math.inf)
                    if nearest>=.3:
                        details.append(dict(**info,candidate=candidate,candidate_raw=value(candidate['center_m']),
                            nearest_authored_passage_m=float(nearest) if math.isfinite(nearest) else None,
                            classification='gap_candidate_semantic_mismatch' if not sweep else 'candidate_sweep_overlaps_obstacle'))
                for contact in relevant:
                    points=transform(a['observation']['wall_xy'],a['pose_odom'])
                    wall=next(r for r in world.rects if r['id']==contact['contacts'][0])
                    world_points=transform(points,world.start)
                    on_obstacle=boxes_occupied(world_points,[dict(wall,half=np.asarray(wall['half'])+1e-5)])
                    proposed=np.r_[inverse([contact['proposed_pose_world'][:2]],world.start)[0],contact['proposed_pose_world'][2]-world.start[2]]
                    values=[value(actor.grid.point(cell)) for cell in footprint_cells(actor.grid,proposed)]
                    mon=ApproachMonitor(actor.navigator.core)
                    mon.observe(a['observation']['wall_xy'],a['pose_odom'],a['t'])
                    monitor=mon.filter(cmd['command'],pose,cmd['t'])[1]
                    velocity=velocity_at(commands,cmd['t'])
                    contact_details.append(dict(**info,contact=contact,
                        latest_observation_age_s=cmd['t']-a['t'],monitor=monitor,
                        footprint_raw_counts=dict(Counter(str(v) for v in values)),
                        observed_points_on_contact_obstacle=int(on_obstacle.sum()),
                        nearest_current_endpoint_m=float(np.linalg.norm(points-pose[:2],axis=1).min()),
                        original_model_velocity_at_command=velocity.tolist(),
                        requested_vs_model_translation_dot=float(twist[:2]@velocity[:2]),
                        classification='active_command_contact_after_prior_hold_contact'))
        assert len(details)==result['false_candidate_passage_attempts'],(name,len(details),result['false_candidate_passage_attempts'])
        output.append(dict(case=name,false_passages=details,action_contacts=contact_details))
    assert sum(len(r['false_passages']) for r in output)==10
    assert sum(len(r['action_contacts']) for r in output)==2
    write(EXP/'results/prior-events.json',dict(prior_source_sha=read(PRIOR/'source.json')['sha'],
        prior_results_sha256=sha(PRIOR/'results.json'),rows=output,
        source_scope='old v8 saved commands/observations only; no new policy or fixes',physics=0,model_calls=0))
    for row in output:
        for e in row['false_passages']:print('FALSE',e['case'],e['t'],e['candidate']['reason'],e['candidate_raw'],e['centerline_raw'],e['requested_short_sweep_contacts'],flush=True)
        for e in row['action_contacts']:print('CONTACT',e,flush=True)


if __name__=='__main__':main()
