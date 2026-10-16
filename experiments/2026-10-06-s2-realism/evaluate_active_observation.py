import json,hashlib,sys,bisect
from pathlib import Path
import numpy as np
ROOT=Path('/Users/changmin/projects/ugrp/outputs')
DEST=ROOT/'s2-active-observation-v58-20261009'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def evaluate(raw):
    r=read(raw/'result.json');record=read(raw/'student_record.json');active=record.get('active_localization',{})
    near=[];events=[]
    truth=[json.loads(q) for q in (raw/'eval_only/trajectory.jsonl').read_text().splitlines()]
    ts=np.array([q['t'] for q in truth]);xy=np.array([q['robot_xyz_m'][:2] for q in truth]);yaw=np.unwrap([q['robot_yaw_rad'] for q in truth])
    def gt(t):return np.array([np.interp(t,ts,xy[:,0]),np.interp(t,ts,xy[:,1]),np.interp(t,ts,yaw)])
    pe=r.get('posthoc_evaluation',{});carry=pe.get('carry_window')
    if (raw/'belief_snapshots.npz').exists():
        with np.load(raw/'belief_snapshots.npz') as clouds:
            for q in read(raw/'belief_snapshots.json')['periodic']:
                p,w=clouds[q['key']],clouds[q['key']+'w'];g=gt(q['t']);e=p-g;da=np.arctan2(np.sin(e[:,2]),np.cos(e[:,2]))
                good=(np.linalg.norm(e[:,:2],axis=1)<=.1)&(abs(da)<=np.deg2rad(5))
                near.append(dict(t=q['t'],mass=float(w[good].sum()),count=int(good.sum()),n=len(w),carry=bool(carry and carry[0]<=q['t']<=carry[1])))
    for e in active.get('events',[]):
        a=e['action'];start=e['t'];end=e.get('completed_t',record['poses'][-1]['t'])
        view=[start+a['pulses']*a['horizon_s']+.4,start+a['pulses']*a['horizon_s']+1.9]
        episode_updates=[q for q in record['amcl_update']['rows'] if start<=q['t']<=end and q.get('informative')]
        updates=[q for q in record['amcl_update']['rows'] if view[0]<=q['t']<=view[1] and q.get('informative')]
        lm=[q for q in record['sensor_landmarks']['rows'] if view[0]<=q['t']<=view[1]]
        actual=[q for q in truth if start<=q['t']<=end];g0=gt(start)
        max_yaw=max(abs(np.arctan2(np.sin(q['robot_yaw_rad']-g0[2]),np.cos(q['robot_yaw_rad']-g0[2]))) for q in actual)
        max_xy=max(np.linalg.norm(np.array(q['robot_xyz_m'][:2])-g0[:2]) for q in actual)
        events.append(dict(t=start,end=end,name=a['name'],state=e['state'],added_s=end-start,view=view,view_updates=len(updates),episode_updates=len(episode_updates),actual_max_yaw_deg=float(np.rad2deg(max_yaw)),actual_max_translation_m=float(max_xy),
                           features=[f for q in lm for f in q['features']],expected_gain=a['expected_reduction_nats'],clearance_m=a['clearance_m']))
    mass=[q['mass'] for q in near if q['carry']];elapsed=r['check_sim_s'];total=sum(e['added_s'] for e in events)
    u=r.get('unknown_start_evaluation',{});nees=u.get('nees_all_reported_covariances',{})
    summary=dict(seed=r.get('seed'),raw=str(raw),source_sha=r['source_sha'],bundle=r['execution_bundle_id'],options=r['options'],execution_status=r['status'],
        failure=r['failure'],**r.get('evaluation',{}),sim_s=elapsed,wall_s=r['wall_s'],wall_per_sim=r['wall_per_sim'],
        convergence=u.get('first_convergence'),nees_exceed_fraction=nees.get('exceed_fraction'),nees_valid=nees.get('valid'),
        unflagged_gt_25cm=u.get('unflagged_gt_25cm'),would_stop=r.get('conservative_stops'),
        carry_rmse_m=pe.get('carry_xy_rmse_m'),max_fix_gap_s=pe.get('max_update_gap_sim_s'),carry_updates=pe.get('visual_updates'),
        B_distance_m=pe.get('cargo_distance_to_B_center_m'),B_remaining_m=pe.get('cargo_remaining_to_B_region_m'),
        visible_fraction=pe.get('actual_visibility',{}).get('all_clear_fraction'),
        active_count=len(events),active_added_s=total,active_added_fraction=total/elapsed,
        active_view_updates=sum(e['view_updates'] for e in events),active_episode_updates=sum(e['episode_updates'] for e in events),
        near_truth_support_fraction=float(np.mean(np.array(mass)>0)) if mass else None,
        near_truth_median_mass=float(np.median(mass)) if mass else None,
        lock_released=read(raw/'lock.json')['status_after'] is None)
    out=dict(summary=summary,active_events=events,particle_series=near,result_sha256=sha(raw/'result.json'),
        record_sha256=sha(raw/'student_record.json'),belief_sha256=sha(raw/'belief_snapshots.npz'),gt_use='posthoc evaluation only')
    (DEST/f'physical-s{summary["seed"]}.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':evaluate(Path(sys.argv[1]))
