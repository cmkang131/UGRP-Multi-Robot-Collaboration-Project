"""GCP-only search25 evaluator geometry and raw rejection decomposition.

No teacher is stepped and no truth is sent to a controller. Output includes
every finite IRM stance and obstacle gap; zero extra margin is a diagnostic,
not a controller setting or a continuous-space impossibility proof.
"""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import subprocess

from scripts.replay_grasp_act_search18 import read, KW
from harness.grasp_act_visible_world import VisibleWorld
from harness.static_keepouts import rect_distance
from sim.grasp_act_search15_modes import ALL_MODES
from sim.grasp_act_search18 import body_clearance
from sim.grasp_act_search23 import BodyNavigation
from sim.grasp_act_search24 import reachability_map
from sim.grasp_act_goal_set import geometry
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def evidence(c):
    return (c.get('failure_audit') or [d for d in c.get('collision_audit', []) if d['blocked']]
            or c.get('path_memory_blockers') or (c.get('path_audit') or {}).get('blocked_obstacles', []))


def funnel(result):
    """Separate endpoint enumeration and full connector validation populations."""
    groups=defaultdict(Counter)
    reasons=('ik_unreachable','gripper_angle','outside_bounds','blocked_goal','blocked_retreat',
             'no_path','unsafe_body_sweep','band_not_visible','arm','endpoint_feasible',
             'connector','planning_budget','feasible')
    for t in result.get('teachers', {}).values():
        for e in t.get('search22_log', []):
            cs=e.get('candidates', [])
            group='endpoint' if any(c.get('reason')=='endpoint_feasible' for c in cs) else 'full_or_retained'
            for c in cs:
                reason=c['reason']
                key=reason if reason in reasons else 'connector' if reason.startswith('connector') else 'arm' if reason.startswith('arm_') else reason
                groups[group][key]+=1
    out={}
    for name, counts in groups.items():
        remaining=sum(counts.values());steps=[]
        for gate in (*reasons, *sorted(set(counts)-set(reasons))):
            rejected=counts[gate] if gate not in ('feasible','endpoint_feasible') else 0
            passed_terminal=counts[gate] if gate in ('feasible','endpoint_feasible') else 0
            steps.append({'gate':gate,'entered':remaining,'rejected':rejected,
                          'terminal_pass':passed_terminal,'continued':remaining-rejected-passed_terminal})
            remaining-=rejected+passed_terminal
        out[name]={'N_rows':sum(counts.values()),'terminal_reason_counts':dict(counts),'ordered_funnel':steps}
    return out


def truth_geometry(row, rid, end, walls, current_margins):
    w={**deepcopy(row), 'walls':[r for _,r in walls]}
    candidates=[]
    for angle,distance,_,_ in reachability_map(row['beam']['ends'][end][2]):
        _,point,yaw,goal=geometry(w,rid,end,(angle,distance));pose=(*goal,yaw)
        gaps=[]
        for name,o in row['objects'].items():
            if name=='beam_1':continue
            # Evaluator's authored landing envelope, without navigation padding.
            gap=body_clearance(pose,[(*o['xy'],o['radius'])],[])
            padding=.005  # Search23's oriented footprint always adds 5mm.
            gaps.append({'id':name,'kind':'cargo','gap_m':gap,
                         'current_gap_m':gap-padding,'margin_m':current_margins.get(name,.005)})
        for name,r in row['robots'].items():
            if name==rid:continue
            # Existing planner's .17m circle is explicit, not called hardware.
            gap=body_clearance(pose,[(*r['pose'][:2],.17)],[])
            gaps.append({'id':name,'kind':'peer','gap_m':gap,'current_gap_m':gap,
                         'margin_m':current_margins.get(name,.005)})
        for name,rect in walls:
            gap=body_clearance(pose,[],[rect])
            gaps.append({'id':name,'kind':'wall','gap_m':gap,'current_gap_m':gap,
                         'margin_m':current_margins.get(name,.005)})
        x,y,a=row['beam']['pose']
        ds=[(x+q*math.cos(a),y+q*math.sin(a),.02) for q in (-.27,-.135,0,.135,.27)]
        gap=body_clearance(pose,ds,[])
        gaps.append({'id':'beam_1','kind':'target','gap_m':gap,'current_gap_m':gap,
                     'margin_m':current_margins.get('band_'+end,.005)})
        for g in gaps:
            g.update(blocked_zero=g['gap_m']<0,blocked_current=g['current_gap_m']<g['margin_m'])
        candidates.append({'offset_deg':math.degrees(angle),'distance_m':distance,'pose':pose,
            'zero_free':all(not g['blocked_zero'] for g in gaps),
            'zero_static_free':all(not g['blocked_zero'] for g in gaps if g['kind']!='peer'),
            'current_free':all(not g['blocked_current'] for g in gaps),
            'min_gap_m':min(g['gap_m'] for g in gaps),'gaps':gaps})
    return candidates


def analyze(root,out):
    out.mkdir(parents=True,exist_ok=True)
    map_data=json.loads(Path('maps/zones/zone_wide_door_geometry_v3.json').read_text())
    walls=[('zone_'+o['id'],(*o['center_m'],*o['half_extents_m'],o.get('yaw_rad',0.))) for o in map_data['obstacles']]
    summaries=[];all_counts=Counter();all_blockers=Counter();all_physical=Counter();funnels=[]
    for raw in sorted(root.glob('diagnostic*/episode-*/raw')):
        res=json.loads(read(raw/'result.json'));plan=json.loads(read(raw/'plan.json'))
        ev=[json.loads(x) for x in read(raw/'eval-only.jsonl').splitlines()]
        led={r:[json.loads(x) for x in read(raw/f'teacher-{r}.jsonl').splitlines()] for r in plan['roles']}
        counts=Counter();blockers=Counter();physical=Counter();memory=defaultdict(list);unique=set();events=[]
        for rid,t in res['teachers'].items():
            for event in t.get('search22_log',[]):
                events.append((event['t'],rid))
                for c in event.get('candidates',[]):
                    category=c.get('rejection_category',c['reason']);counts[category]+=1
                    if category in ('feasible','endpoint_feasible'):continue
                    for d in evidence(c):
                        if d.get('gap_m') is None:continue
                        key=(category,d['id']);blockers['|'.join(key)]+=1
                        gap=d['gap_m'];fresh=d.get('fresh')
                        if category in ('current_geometry','memory_margin'):
                            physical['overlap' if gap<0 else 'fresh_inflation' if fresh else 'remembered_inflation']+=1
                        if not fresh and 'seen_t' in d:
                            memory[d['id']].append({'t':event['t'],'age_s':event['t']-d['seen_t'],
                                'gap_m':gap,'margin_m':d.get('margin_m'),'rid':rid})
                        unique.add((rid,event['t'],c.get('offset_deg'),c.get('distance_m'),d['id']))
        samples={0,len(ev)-1}
        if events:
            for ts in (min(e[0] for e in events),max(e[0] for e in events)):
                samples.add(min(range(len(ev)),key=lambda i:abs(ev[i]['t']-ts)))
        modes={k:res.get(k,'off') for k in ALL_MODES}
        models={r:VisibleWorld(r,e,odometry=modes['search17_odometry'],search22=modes['search22'],search23=modes['search23']) for r,e in plan['roles'].items()}
        snapshots=[]
        for i,row in enumerate(ev):
            for rid,end in plan['roles'].items():
                w=models[rid].observe(row['visible_measurements'][rid],row['t'])
                if i in samples:
                    t=VisibleOnlyGraspTeacher(rid,end,{int(k):v for k,v in led[rid][max(0,i-1)]['applied_command']['pwm'].items()},**KW,**modes)
                    nav=BodyNavigation(t,w,admission=True)
                    margins={d['id']:d['margin_m'] for d in nav.audit_details}
                    cs=truth_geometry(row,rid,end,walls,margins)
                    if i==0:
                        # Additional endpoint gates, no dynamics. Actual issued
                        # pick cloud, evaluator truth only; no teacher inputs.
                        from sim.grasp_act_pregrasp import band_view,collision_reason
                        truth={**deepcopy(row),'walls':[r for _,r in walls],
                               'visibility':{rid:{'observations':{}}}}
                        for c in cs:
                            c['endpoint_arm_free']=False;c['retreat_zero_free']=False
                            if not c['zero_free']:continue
                            x,y,yaw=c['pose'];pwm=nav.pwm
                            _,view=band_view(truth,rid,end,c['pose'],pwm)
                            cloud=nav.pick_cloud(view,c['distance_m'],row['beam']['ends'][end][2])
                            audit=[];reason=collision_reason(truth,rid,c['pose'],*cloud,audit=audit)
                            c.update(endpoint_arm_free=reason is None,arm_reason=reason or 'clear',arm_blockers=audit)
                            # Retreat body geometry at 2mm samples; no extra
                            # margin, explicitly sampled evaluator diagnostic.
                            c['retreat_zero_free']=True
                            for j in range(31):
                                pose=(x-.06*j/30*math.cos(yaw),y-.06*j/30*math.sin(yaw),yaw)
                                ds=[(*o['xy'],o['radius']) for k,o in row['objects'].items() if k!='beam_1']
                                ds += [(*r['pose'][:2],.17) for k,r in row['robots'].items() if k!=rid]
                                if body_clearance(pose,ds,[r for _,r in walls])<0:
                                    c['retreat_zero_free']=False;break
                    detail={'rid':rid,'t':row['t'],'N':len(cs),'zero_free':sum(c['zero_free'] for c in cs),
                        'zero_static_free':sum(c['zero_static_free'] for c in cs),
                        'current_free':sum(c['current_free'] for c in cs),
                        'arm_and_retreat_zero_free':sum(c.get('endpoint_arm_free',False) and c.get('retreat_zero_free',False) for c in cs) if i==0 else None,
                        'best_gap_m':max(c['min_gap_m'] for c in cs),
                        'zero_blockers':dict(Counter(g['id'] for c in cs for g in c['gaps'] if g['blocked_zero'])),
                        'target_to_cargo_surface_m':min((math.dist(row['beam']['ends'][end][:2],o['xy'])-o['radius'] for k,o in row['objects'].items() if k!='beam_1'),default=None),
                        'target_to_wall_m':min(rect_distance(row['beam']['ends'][end][:2],r) for _,r in walls),
                        'target_to_peers_m':{r:math.dist(row['beam']['ends'][end][:2],v['pose'][:2]) for r,v in row['robots'].items() if r!=rid}}
                    snapshots.append(detail)
                    dump(out/'candidates'/raw.parent.name/f'{rid}-{i:04d}.json',{'summary':detail,'candidates':cs})
                models[rid].issue(led[rid][i]['applied_command'])
        memory_stats={k:{'N_obstacle_occurrences':len(v),'max_age_s':max(x['age_s'] for x in v),
                         'min_gap_m':min(x['gap_m'] for x in v),
                         'max_required_margin_m':max(x['margin_m'] or 0 for x in v)} for k,v in memory.items()}
        f={'episode':raw.parent.name,'raw':str(raw),'populations':funnel(res)};funnels.append(f)
        summary={'episode':raw.parent.name,'seed':plan['seed'],'cargo_scene':plan.get('cargo_scene','off'),
            'success':res['physical_success'],'raw':str(raw),'categories':dict(counts),
            'obstacle_occurrences':dict(blockers),'physical_decomposition_occurrences':dict(physical),
            'unique_rid_tick_candidate_obstacle':len(unique),'memory':memory_stats,'geometry_samples':snapshots,
            'decoded_sha256':{n:hashlib.sha256(read(raw/n)).hexdigest() for n in ('result.json','eval-only.jsonl','plan.json')}}
        summaries.append(summary);all_counts.update(counts);all_blockers.update(blockers);all_physical.update(physical)
        print(json.dumps({'episode':raw.parent.name,'success':res['physical_success'],'categories':dict(counts),
                          'geometry':[{k:d[k] for k in ('rid','t','N','zero_free','current_free','best_gap_m')} for d in snapshots]}),flush=True)
    command=f'.venv-sim/bin/python -m scripts.analyze_grasp_act_search25 {root} --out {out}'
    table={'schema':'ugrp.search25.funnel.v1','raw_root':str(root),'source_sha':(root/'SOURCE_SHA').read_text().strip(),
           'reproduce':command,'categories':dict(all_counts),'episodes':funnels,
           'scope':'raw row populations; endpoint/full stages kept separate, repeated replans are not independent candidates'}
    dump(out/'rejection_table.json',table)
    result={'schema':'ugrp.search25.analysis.v1','source_sha':table['source_sha'],'raw_root':str(root),
            'reproduce':command,'categories':dict(all_counts),'obstacle_occurrences':dict(all_blockers),
            'physical_decomposition_occurrences':dict(all_physical),'episodes':summaries,
            'limits':['endpoint body geometry only; no path, retreat or arm completeness claim',
                      'finite IRM only, no continuous-space impossibility proof',
                      'current margins reconstructed from visible+issued history without teacher free-space caches',
                      'zero uses authored landing circles; peers retain explicitly labelled planner .17m circles',
                      'truth is evaluation-only; all candidates stay on gcp1']}
    dump(out/'summary.json',result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();analyze(a.root,a.out)
