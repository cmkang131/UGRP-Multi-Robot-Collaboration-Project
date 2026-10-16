"""Offline synthetic sensor generator; evaluator truth never enters the planner.

The r80 geometric-error proxy determines corruption rates independently of
peer-message quality. This is a stress test, not a measured task fact detector.
"""
import argparse
import collections
import copy
import hashlib
import json
import random
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.task_planner_cost_rules import FACT_KEYS, SPECS


def select_dev(gold, seed=2026101404):
    rng=random.Random(seed)
    selected=[g['case_id'] for g in gold if not g['ambiguous'] and g['quality'] in ('stale','wrong')]
    assert len(selected)==110
    strata=collections.defaultdict(list)
    for g in gold:
        if not g['ambiguous'] and g['quality'] not in ('stale','wrong'):
            strata[g['domain'],g['quality']].append(g['case_id'])
    for values in strata.values():rng.shuffle(values)
    keys=sorted(strata);rng.shuffle(keys)
    while len(selected)<200:
        for key in keys:
            if strata[key] and len(selected)<200:selected.append(strata[key].pop())
    return sorted(selected)


def category(s):
    if not s['available']:return 'absent'
    return ('stale' if s['stale'] else 'fresh')+'_'+(
        'large_error' if s.get('evaluation_only',{}).get('large_error') else
        'small_error' if 'evaluation_only' in s else 'unscored')


def allocate(ids, calibration, rng):
    groups=collections.defaultdict(list)
    for s in calibration['samples']:groups[category(s)].append(s)
    exact={k:len(ids)*len(v)/calibration['N'] for k,v in groups.items()}
    counts={k:int(v) for k,v in exact.items()}
    for k in sorted(counts,key=lambda k:exact[k]-counts[k],reverse=True)[:len(ids)-sum(counts.values())]:counts[k]+=1
    pool=[]
    for k,n in counts.items():
        values=groups[k][:];rng.shuffle(values)
        pool.extend(values[i%len(values)] for i in range(n))
    rng.shuffle(pool)
    return dict(zip(sorted(ids),pool))


def augment(source, gold, calibration, seed, dev_ids=None):
    rng=random.Random(seed); gs={g['case_id']:g for g in gold}
    dev_ids=set(dev_ids or []); others=set(gs)-dev_ids
    samples={**allocate(dev_ids,calibration,rng),**allocate(others,calibration,rng)}
    own_by_id={}; audit=[]
    for cid in sorted(gs):
        g=gs[cid];s=samples[cid];fact=None; now=1000.
        # Shift clocks, not ages; actual r80 pose values remain noisy estimates.
        env=s['allowed_envelope']; stamp=env['own_rgb']['t_sim']
        rgb={k:v for k,v in env['own_rgb'].items() if k!='sha256'}
        rgb.update(robot_id='r1',t_sim=now-(s['sim_s']-stamp),source='synthetic format sample; no image supplied')
        pose=copy.deepcopy(env['own_map_summary']['pose'])
        pose.pop('sources',None)
        commands=copy.deepcopy(env['own_command_history'][-2:])
        for command in commands:command['issued_at_sim_s']+=now-s['sim_s']
        own=dict(rgb=rgb,pose=pose,command_history=commands,observed_facts=[],
                 local_view='task fact not observed',observation_kind='synthetic RGB/command-derived hypothesis')
        if s['available'] and 'evaluation_only' in s:
            domain=g['domain'];ws=SPECS[domain]['worlds'];value=g['world']
            if s['evaluation_only']['large_error']:
                value=rng.choice([v for v in ws if v!=value])
            subject,predicate=FACT_KEYS[domain]
            fact=dict(subject=subject,predicate=predicate,value=value,
                observed_at=now-s['age_s'],source='own RGB + issued commands (synthetic inference)',
                entity=dict(id=subject),pose_own_m=s['observation']['pose_own_m'],
                observer_pose_own_m=s['observation']['observer_pose_own_m'],
                rgb=dict(robot_id='r1',frame_id=s['observation']['rgb']['frame_id'],t_sim=now-s['age_s']))
            own['observed_facts']=[fact];own['local_view']='remembered visual task hypothesis; may be stale or mistaken'
        own_by_id[cid]=own
        audit.append(dict(case_id=cid,calibration_category=category(s),run=s['run'],request_id=s['request_id'],
            synthetic_fact_present=fact is not None,synthetic_fact_matches=fact is not None and fact['value']==g['world'],
            age_s=s.get('age_s'),assumption='gross geometric error maps to an incorrect categorical hypothesis; private intent inferred from visible task cues is unvalidated'))
    result=[]
    for original in source:
        row=copy.deepcopy(original);v=row['input'];v['now_s']=1000.
        v['self_state'].update(copy.deepcopy(own_by_id[row['case_id']]))
        for m in v.get('messages',[]):
            m['observation_time_s']+=900
            if isinstance(m['body'],dict) and 'observed_at_sim_s' in m['body']:m['body']['observed_at_sim_s']+=900
        result.append(row)
    return result,audit


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True)
    ap.add_argument('--gold',type=Path,required=True);ap.add_argument('--calibration',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True);ap.add_argument('--seed',type=int,default=2026101404)
    ap.add_argument('--dev',action='store_true');a=ap.parse_args()
    if a.out.exists():raise SystemExit('new directory required')
    source=json.loads((a.source/'cases_public.json').read_text());gold=json.loads(a.gold.read_text())
    cal=json.loads(a.calibration.read_text());ids=select_dev(gold) if a.dev else []
    public,audit=augment(source,gold,cal,a.seed,ids);a.out.mkdir(parents=True)
    for name,data in [('cases_public.json',public),('eval_only.json',gold),('observations_eval_only.json',audit),('dev_ids.json',ids)]:
        (a.out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    manifest=dict(seed=a.seed,dev_ids=ids,source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [a.source/'cases_public.json',a.gold,a.calibration]},
        all_counts=dict(collections.Counter(x['calibration_category'] for x in audit)),
        dev_counts=dict(collections.Counter(x['calibration_category'] for x in audit if x['case_id'] in ids)),
        limitation=cal['limitation'],generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (a.out/'generation.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({k:v for k,v in manifest.items() if k!='dev_ids'},indent=2))
