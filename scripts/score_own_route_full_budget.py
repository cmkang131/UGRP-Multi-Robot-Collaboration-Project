"""egomap64 post-hoc GT evaluation and issued-command audit, never control."""
from pathlib import Path
from collections import Counter
import importlib.util,json,math
import numpy as np

ROOT=Path(__file__).resolve().parents[1]


def load_old():
    spec=importlib.util.spec_from_file_location('egomap64_old_score',ROOT/'experiments/2026-10-10-own-route-particle-stages/code/score.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def command_metrics(rows,headings):
    counts=Counter();turns=[];groups=[];group=[];last_turn=None;reversals=0;within=0
    heading_by_t={round(r['t'],6):r for r in headings}
    reasons=Counter();heading_turns=0;target_changes=[];prior_heading=None
    for row in rows:
        cmd=row['command'];kind='hold'
        if cmd.get('turn',0):kind='turn'
        elif cmd.get('forward',0)>0:kind='forward'
        elif cmd.get('forward',0)<0:kind='backward'
        elif cmd.get('left',0):kind='lateral'
        counts[kind]+=1
        if kind=='turn':
            sign=math.copysign(1,cmd['turn'])
            reversals+=last_turn is not None and sign!=last_turn
            within+=bool(group) and sign!=group[-1]
            last_turn=sign;turns.append(sign);group.append(sign)
            h=heading_by_t.get(round(row['t'],6))
            if h:
                heading_turns+=1;reasons[h.get('reason','unknown')]+=1
                target=h.get('plan',{}).get('heading_rad')
                if target is not None:
                    if prior_heading is not None:target_changes.append(abs((target-prior_heading+math.pi)%(2*math.pi)-math.pi))
                    prior_heading=target
        elif kind not in ('hold',):
            if group:groups.append(len(group));group=[]
    if group:groups.append(len(group))
    n=sum(counts.values());moving=n-counts['hold']
    return dict(commands=n,counts={k:counts[k] for k in ('turn','forward','backward','lateral','hold')},
        turn_fraction=counts['turn']/n if n else None,forward_fraction=counts['forward']/n if n else None,
        turn_moving_fraction=counts['turn']/moving if moving else None,
        turn_sign_reversals=int(reversals),within_alignment_reversals=int(within),
        turn_groups=len(groups),repeat_turn_groups=sum(v>=2 for v in groups),max_turn_group=max(groups,default=0),
        shared_heading_turns=heading_turns,heading_reasons=dict(reasons),
        heading_target_step_deg_median=float(np.degrees(np.median(target_changes))) if target_changes else None)


def boundary_distance(xy,region):
    return float(np.linalg.norm(np.maximum(np.abs(np.asarray(xy)-region['center_m'])-region['half_extents_m'],0)))


def score(p):
    m=load_old();r=m.score(p)
    if not r.get('samples'):return r
    result=m.read(p/'result.json');start=result['start_sim_s'];events=m.read(p/'utility-events.json')
    transition=next((e for e in events if e['reason']=='registered_return_stage_started' and e['t']>=start),None)
    cut=transition['t'] if transition else start+270.
    truthrows=m.rows(p/'eval_only/trajectory.jsonl');truth={round(x['t'],6):x for x in truthrows}
    rows=[x for x in m.rows(p/'own-controller.jsonl') if x['t']>=start and round(x['t'],6) in truth]
    origin=[*truthrows[0]['robot_xyz_m'][:2],truthrows[0]['robot_yaw_rad']]
    actual=np.array([truth[round(x['t'],6)]['robot_xyz_m'][:2] for x in rows])
    error=np.linalg.norm(m.transform([x['local_pose'][:2] for x in rows],origin)-actual,axis=1)
    sigma=np.array([x['sigma_xy'] for x in rows]);ratio=error/np.maximum(sigma,1e-12)
    phase={};headings=[h for h in m.read(p/'heading-decisions.json') if h['t']>=start]
    B=m.read(p/'inputs/static_map.json')['regions']['zone_B']
    for name,mask in [('approach',np.array([x['t']<cut for x in rows])),('return',np.array([x['t']>=cut for x in rows]))]:
        selected=[x for x,yes in zip(rows,mask) if yes]
        phase[name]=dict(samples=int(mask.sum()),over_3sigma=int((ratio[mask]>3).sum()),
            over_3sigma_rate=float((ratio[mask]>3).mean()) if mask.any() else None,
            final_error_m=float(error[mask][-1]) if mask.any() else None,
            final_sigma_m=float(sigma[mask][-1]) if mask.any() else None,
            commands=command_metrics(selected,headings))
    before=[x for x in truthrows if start<=x['t']<=cut and x['t']<=result['total_sim_s']]
    distances=[boundary_distance(x['robot_xyz_m'][:2],B) for x in before]
    r.update(per_phase=phase,command_audit=command_metrics(rows,headings),return_transition=transition,
        B_initial_boundary_distance_m=distances[0] if distances else None,B_nearest_boundary_distance_m=min(distances) if distances else None,
        approach_sim_s=min(cut,result['total_sim_s'])-start,return_sim_s=max(0,result['total_sim_s']-cut),
        both_arrived=r['B_arrived'] and r['returned'],stage_schedule=result.get('stage_schedule'),
        B_declared_before_return=bool(transition and transition['cause']=='own_B_declared'))
    return r
