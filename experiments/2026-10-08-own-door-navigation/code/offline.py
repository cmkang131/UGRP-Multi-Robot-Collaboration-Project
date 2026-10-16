"""Frozen-input door replay; GT scoring is a separate post-seal invocation."""
from pathlib import Path
from collections import Counter
import argparse,copy,hashlib,importlib.util,json,math,subprocess,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
EXP=Path(__file__).resolve().parents[1]
RAW=Path('/Users/changmin/projects/ugrp/outputs/own-door-navigation-v1')
BASE=Path('/Users/changmin/projects/ugrp/outputs')
COHORT={'46A':BASE/'frontier-duration-v1/A/new-seed','46B':BASE/'frontier-duration-v1/B/new-seed',
    '47':BASE/'navfn-start-recovery-v1/new-seed',**{str(s):BASE/f'own-map-return-repeat-v1/seed{s}' for s in range(49001,49007)}}
from harness.own_door_memory import DoorMemory,geometry,same
from harness.active_wall_mapping import compose,inverse
from harness.self_odom_grid import transform
from harness.grid_acceleration import using


def load(p):return json.loads(p.read_text())
def rows(p):return [json.loads(l) for l in p.open()] if p.exists() else []
def dump(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def predict(case):
    ep=COHORT[case];out=RAW/case;assert not (out/'prediction.json').exists(),'ONE_REPLAY_ONLY'
    trace=rows(ep/'own-controller.jsonl');byid={r['frame_id']:r for r in trace if r.get('pose') is not None}
    manifest=load(ep/'artifacts.sha256.json')
    inputs=['own-controller.jsonl','own-contacts.jsonl','return-navigation.json','remembered-goal.json']
    hashes={}
    for p in inputs:
        if not (ep/p).exists():continue
        hashes[p]=sha(ep/p)
        if p in manifest:assert hashes[p]==manifest[p]
    m=DoorMemory('r3');legacy=[];legacy_raw=0;legacy_ids=set();changes=[];reason=Counter();stages=Counter();rotation=Counter();miss=0
    with using('scalar_rays_v1'):
        for line in (ep/'own-contacts.jsonl').open():
            obs=json.loads(line);fid=obs['frame_id'];r=byid.get(fid)
            if r is None:miss+=1;continue
            pose=r.get('local_pose',r['pose']);updated=m.observe(robot_id='r3',t=obs['t'],frame_id=fid,pose=pose,observation=obs)
            for d in updated:reason[d['last_reason']]+=1
            if updated:changes.append(dict(t=obs['t'],frame_id=fid,doors=updated))
            stage=r.get('stage','explore');stages[stage]+=1
            if r.get('status')=='sensor_sweep':rotation[stage]+=1
            # The historical proposals are in graph/map coordinates. Undo ONLY
            # the robot's own map->odom TF, never a GT transform, before merging.
            tf=compose(pose,inverse(r['pose']))
            for d in r.get('doors',[]):
                legacy_raw+=1;legacy_ids.add(d['id'])
                c=np.asarray(d['center_m']);u=np.asarray(d['tangent']);ends=[c-u*d['width_m']/2,c+u*d['width_m']/2]
                p=dict(endpoints=transform(ends,tf).tolist(),width_m=d['width_m'],first_t=r['t'],id=d['id'],
                    confirmed_t=None,free_connection_observed=d['free_connection_observed'])
                if not any(same(p,q) for q in legacy):legacy.append(p)
    audit=None
    if (ep/'return-navigation.json').exists() and (ep/'remembered-goal.json').exists():
        events=load(ep/'return-navigation.json');goal=load(ep/'remembered-goal.json')
        if goal:
            hits=[i for i,e in enumerate(events) if e['reason']=='ABORTED_goal_blacklisted' and np.linalg.norm(np.array(e['target'])-goal['center_m'])<1e-6]
            audit=dict(goal=goal['center_m'],goal_blacklist_events=len(hits),
                next_frontier_requests=sum(e['reason']=='next_frontier_requested' for e in events),
                before=[events[max(0,i-8):i+3] for i in hits],
                direct_cause='controller_no_progress -> progress_timeout_sensor_sweep; requested mission blacklisted with unrelated frontier')
    report=dict(case=case,raw=str(ep),source_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        inputs=hashes,frames=len(m.seen),contacts_without_trace=miss,raw_candidates=m.raw_candidates,merged_candidates=len(m.tracks),
        legacy_raw_candidates=legacy_raw,legacy_ids=len(legacy_ids),legacy_merged_candidates=len(legacy),
        tracks=m.tracks,legacy_tracks=legacy,confirmation_opportunities=sum(d['confirmation_opportunities'] for d in m.tracks),
        confirmable_entities=sum(d['confirmation_opportunities']>0 for d in m.tracks),confirmed=sum(d['confirmed_t'] is not None for d in m.tracks),
        reasons=dict(reason),stages=dict(stages),sensor_sweep_frames=dict(rotation),blacklist_audit=audit,
        control_inputs='own projected RGB segments/floor and saved estimates; no GT; fixed trajectory, not policy roll-out')
    dump(out/'prediction.json',report);dump(out/'changes.json',changes)
    dump(out/'seal.json',dict(files={p:sha(out/p) for p in ('prediction.json','changes.json')}))
    print(case,'predictions sealed',report['frames'],flush=True)


def metrics(predictions,doors,origin,eligible):
    result=[];claimed=set()
    for r in sorted(predictions,key=lambda r:r['first_t']):
        p=copy.deepcopy(r);p['endpoints']=transform(p['endpoints'],origin).tolist();c,tangent,_=geometry(p)
        candidates=[]
        for i,d in enumerate(doors):
            axis=np.array([0.,1.]) if d['axis']=='x' else np.array([1.,0.])
            dist=float(np.linalg.norm(c-d['center_m']));angle=math.acos(float(np.clip(abs(tangent@axis),-1,1)))
            if dist<=.25 and angle<=math.radians(10) and abs(r['width_m']-d['width_m'])<=.25:candidates.append((dist,i))
        match=min(candidates)[1] if candidates else None
        unique=match is not None and match not in claimed
        if unique:claimed.add(match)
        result.append(dict(id=r['id'],world_center=c.tolist(),match=doors[match]['id'] if match is not None else None,tp=unique))
    matched_eligible=len(claimed&set(eligible));n=len(predictions)
    return dict(tp=len(claimed),fp=n-len(claimed),n=n,precision=len(claimed)/n if n else None,
        recall_all=len(claimed)/len(doors),recall_visible=matched_eligible/len(eligible) if eligible else None,
        eligible_tp=matched_eligible,eligible_n=len(eligible),matches=result)


def score(case):
    out=RAW/case
    for p,h in load(out/'seal.json')['files'].items():assert sha(out/p)==h
    pred=load(out/'prediction.json');ep=COHORT[case]
    truth=rows(ep/'eval_only/trajectory.jsonl');origin=[*truth[0]['robot_xyz_m'][:2],truth[0]['robot_yaw_rad']]
    static=load(ep/'inputs/static_map.json');doors=static['passages'];cameras=rows(ep/'eval_only/camera.jsonl')
    rects=np.array([r['center_m']+r['half_extents_m'] for r in static['obstacles'] if r.get('kind')=='wall'])
    spec=importlib.util.spec_from_file_location('visibility',ROOT/'experiments/2026-10-07-active-wall-map/code/score.py');vis=importlib.util.module_from_spec(spec);spec.loader.exec_module(vis)
    eligible=[];times={}
    for i,d in enumerate(doors):
        axis=np.array([0.,1.]) if d['axis']=='x' else np.array([1.,0.]);c=np.array(d['center_m'])
        points=[c-axis*d['width_m']/2,c+axis*d['width_m']/2]
        visible=[r['t'] for r in cameras if vis.in_view(points,[r],rects).all()]
        if visible:eligible.append(i);times[d['id']]=dict(first=visible[0],frames=len(visible))
    stats={label:metrics(items,doors,origin,eligible) for label,items in (
        ('off',pred['legacy_tracks']),('on',pred['tracks']),('confirmed',[d for d in pred['tracks'] if d['confirmed_t'] is not None]))}
    result=dict(case=case,frames=pred['frames'],raw_candidates=pred['raw_candidates'],merged_candidates=pred['merged_candidates'],
        legacy_raw_candidates=pred['legacy_raw_candidates'],legacy_ids=pred['legacy_ids'],legacy_merged_candidates=pred['legacy_merged_candidates'],
        confirmation_opportunities=pred['confirmation_opportunities'],confirmable_entities=pred['confirmable_entities'],confirmed=pred['confirmed'],
        visibility=times,visibility_limit='GT camera + wall-only occlusion; objects/self not modelled; potential visibility',
        metrics=stats,reasons=pred['reasons'],stages=pred['stages'],sensor_sweep_frames=pred['sensor_sweep_frames'],blacklist_audit=pred['blacklist_audit'],
        prediction_seal=sha(out/'seal.json'),source_sha=pred['source_sha'])
    dump(EXP/'results'/f'{case}.json',result)
    print(case,json.dumps({k:{z:v for z,v in a.items() if z!='matches'} for k,a in stats.items()}),flush=True)
    return result


def gate():
    allrows=[load(EXP/'results'/f'{s}.json') for s in range(49001,49007)]
    combined={}
    for label in ('off','on','confirmed'):
        c={k:sum(r['metrics'][label][k] for r in allrows) for k in ('tp','fp','n','eligible_tp','eligible_n')}
        c.update(precision=c['tp']/c['n'] if c['n'] else None,recall_visible=c['eligible_tp']/c['eligible_n'] if c['eligible_n'] else None,recall_all=c['tp']/12)
        combined[label]=c
    p=combined['on'];c=combined['confirmed'];checks=dict(candidate_precision=p['precision'] is not None and p['precision']>=.5,
        candidate_recall=p['recall_visible'] is not None and p['recall_visible']>=.5,
        confirmed_precision=c['precision'] is not None and c['precision']>=.9,
        zero_false_confirmations=c['fp']==0,nonempty_confirmed=c['tp']>=1)
    result=dict(passed=all(checks.values()),checks=checks,combined=combined,cohort_size=6,
        frozen_criteria_commit='4a03c66a',physical_runs_authorized_if_passed_only=True)
    dump(EXP/'results/gate.json',result);print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['predict','score','gate']);p.add_argument('--case',choices=list(COHORT));a=p.parse_args()
    if a.mode=='predict':predict(a.case)
    elif a.mode=='score':score(a.case)
    else:gate()
