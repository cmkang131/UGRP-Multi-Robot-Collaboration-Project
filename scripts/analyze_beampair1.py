"""GCP raw analysis, manifests, ordered funnels and failure-only review montage."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from scripts.audit_beampair1 import read, read_bytes, dump, recount, ordered_funnel


def blockers(candidate):
    return (candidate.get('failure_audit')
        or [d for d in candidate.get('collision_audit',[]) if d.get('blocked')]
        or candidate.get('path_memory_blockers')
        or (candidate.get('path_audit') or {}).get('blocked_obstacles',[]))


def rejection_rows(result):
    rows=[]
    for rid,t in result.get('teachers',{}).items():
        for event in t.get('search22_log',[]):
            candidates=event.get('candidates',[])
            group='endpoint' if any(c.get('reason')=='endpoint_feasible' for c in candidates) else 'full_or_retained'
            for c in candidates:
                reason=c.get('reason') or 'missing_reason'
                evidence=blockers(c)
                base=dict(robot=rid,t=event.get('t'),population=group,reason=reason,
                    reason_category=reason,blocked_object='not_applicable',min_gap_m=None,
                    gap_scope='not_a_geometric_rejection',candidate=c)
                if evidence:
                    for d in evidence:
                        rows.append({**base,'reason_category':d.get('category',reason),
                            'blocked_object':d.get('id',d.get('object','not_recorded')),
                            'min_gap_m':d.get('gap_m',d.get('min_gap_m')),
                            'gap_scope':'observed_model_clearance','blocker':d})
                elif reason.startswith(('blocked','no_path','unsafe','arm','connector')):
                    rows.append({**base,'blocked_object':'not_recorded',
                        'gap_scope':'source_missing_clearance_audit'})
                else:rows.append(base)
    return rows


def candidate_funnels(result):
    groups={}
    for rid,t in result.get('teachers',{}).items():
        for event in t.get('search22_log',[]):
            cs=event.get('candidates',[])
            group='endpoint' if any(c.get('reason')=='endpoint_feasible' for c in cs) else 'full_or_retained'
            counts=groups.setdefault(group,Counter())
            for c in cs:counts[c.get('reason') or 'missing_reason']+=1
    stages=('ik_unreachable','gripper_angle','outside_bounds','blocked_goal','blocked_retreat',
            'no_path','unsafe_body_sweep','band_not_visible','arm','endpoint_feasible',
            'connector','planning_budget','feasible')
    out={}
    for group,counts in groups.items():
        # These are original first-failure stages; terminal endpoint passes
        # leave this population and are never added to full-connector trials.
        remaining=sum(counts.values());steps=[]
        for stage in (*stages,*sorted(set(counts)-set(stages))):
            n=counts[stage];passed=n if stage in ('endpoint_feasible','feasible') else 0
            rejected=n-passed
            steps.append(dict(gate=stage,entered=remaining,rejected=rejected,
                terminal_pass=passed,continued=remaining-n));remaining-=n
        out[group]=dict(N=sum(counts.values()),reason_distribution=dict(counts),ordered_funnel=steps)
    return out


def montage(raw,out):
    from PIL import Image,ImageDraw
    fs={r:sorted((raw/'eval-own'/r).glob('*.jpg')) for r in ('r1','r2')}
    if any(not f for f in fs.values()):return None
    names=sorted(set(f.name for f in fs['r1']) & set(f.name for f in fs['r2']))
    selected=[names[round(i*(len(names)-1)/5)] for i in range(6)]
    canvas=Image.new('RGB',(960,1000));draw=ImageDraw.Draw(canvas);evidence=[]
    for i,name in enumerate(selected):
        x=(i%3)*320;y=(i//3)*500
        for j,rid in enumerate(('r1','r2')):
            p=raw/'eval-own'/rid/name
            canvas.paste(Image.open(p).resize((320,240)),(x,y+j*240))
            evidence.append(dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                robot=rid,elapsed_sim_s=int(Path(name).stem)/10))
        draw.text((x+5,y+480),f'{raw.parent.name} r1/r2 SIM{int(Path(name).stem)/10:g}',fill='white')
    canvas.save(out,quality=90)
    return dict(path=str(out),sha256=hashlib.sha256(out.read_bytes()).hexdigest(),frames=evidence)


def analyze(root,out):
    episodes=[];all_rejections=[];reasons=Counter();blocker_counts=Counter()
    rawdirs=sorted(root.glob('diagnostic/episode-*/raw'))
    batch=read(root/'batch-plan.json')
    for raw in rawdirs:
        entry=recount(raw);result=read(raw/'result.json')
        adapter=read(raw.parent/'adapter/beampair1-result.json')
        decoded,_,_=read_bytes(raw/'eval-only.jsonl')
        frames=[json.loads(line) for line in decoded.splitlines() if line.strip()]
        plan=read(raw/'plan.json')
        frame_N=len(frames)*2
        any_visible=sum(row['visibility'][rid]['visible_probes']>0 for row in frames for rid in ('r1','r2'))
        region_visible=sum(row['visibility'][rid]['visible_probes']>=5 for row in frames for rid in ('r1','r2'))
        admitted=sum(any(m['id']=='band_'+plan['roles'][rid]
            for m in row.get('visible_measurements',{}).get(rid,[])) for row in frames for rid in ('r1','r2'))
        entry['frame_funnel']=ordered_funnel(frame_N,[('any_assigned_probe',any_visible),
            ('meaningful_region_5_of_15',region_visible),('measurement_admitted_not_held',admitted)])
        entry['adapter_sha']=adapter['source_sha'];entry['dependency_sha']=adapter['dependency_sha']
        entry['candidate']=adapter['candidate'];entry['held_object_hidden_v1']=adapter['held_object_hidden_v1']
        entry['hidden_measurement_ticks']=adapter['hidden_measurement_ticks']
        entry['held_world_reads']=adapter['held_world_reads']
        entry['probe_burst_ticks']=adapter['probe_burst_ticks'];entry['probe_executed_ticks']=adapter['probe_executed_ticks']
        entry['adapter_manifest_verified_files']=__import__('scripts.audit_beampair1',fromlist=['verify_manifest']).verify_manifest(raw.parent/'adapter')
        rejection=rejection_rows(result);entry['candidate_populations']=candidate_funnels(result)
        for r in rejection:
            reasons[r['reason_category']]+=1;blocker_counts[r['blocked_object']]+=1
        all_rejections += [dict(episode=raw.parent.name,**r) for r in rejection]
        entry['montage']=montage(raw,out/(raw.parent.name+'.jpg'))
        entry['stages']={stage:all(any(e.get('to') in phases for e in t.get('events',[]))
            for t in result.get('teachers',{}).values()) if len(result.get('teachers',{}))==2 else False
            for stage,phases in [('both_align',('align','ready','pick','complete')),
                ('both_ready',('ready','pick','complete')),('both_pick',('pick','complete')),
                ('both_command_complete',('complete',))]}
        per_role=[]
        for rid,t in result.get('teachers',{}).items():
            states={e.get('to') for e in t.get('events',[])}
            cmds=entry['saved_command_phases'].get(rid,{})
            per_role.append(dict(robot=rid,ready=bool(states & {'ready','pick','complete'}),
                pick=bool(states & {'pick','complete'}),
                command_complete='complete' in states))
        entry['event_funnel']=ordered_funnel(2,[('own_ready',sum(e['ready'] for e in per_role)),
            ('own_pick_after_go_ack',sum(e['pick'] for e in per_role)),
            ('own_command_complete',sum(e['command_complete'] for e in per_role))])
        episodes.append(entry)
    passed=sum(e['legacy_success'] and e['strict_success'] and e.get('visible_eligible')
        and e['held_object_hidden_v1'] and e['held_world_reads']==0 for e in episodes)
    planned=batch['planned_N'];running=len(rawdirs)
    funnel=ordered_funnel(planned,[('started',running),
        *[(s,sum(e['stages'][s] for e in episodes)) for s in ('both_align','both_ready','both_pick','both_command_complete')],
        ('joint_hold_3s',sum(e['strict_success'] for e in episodes)),('input_eligible_success',passed)])
    missing=sum(r['gap_scope']=='source_missing_clearance_audit' or r['blocked_object']=='not_recorded'
                or r['reason']=='missing_reason' for r in all_rejections)
    report=dict(schema='ugrp.beampair1.round.v1',source_sha=batch['source_sha'],raw_root=str(root),
        planned_N=planned,N=len(episodes),n=passed,training_rgb=False,host='gcp1',machine_type='n4-highcpu-64',
        incomplete_N=sum(e['status']!='complete' for e in episodes),
        cap_end_N=sum(e.get('cap_end',False) for e in episodes),
        held_world_reads=sum(e['held_world_reads'] for e in episodes),
        invisible_measurements=sum((e.get('audit') or {}).get('invisible_measurements',0) for e in episodes),
        missing_rejection_audit_N=missing,reason_distribution=dict(reasons),blocked_object_distribution=dict(blocker_counts),
        runs=episodes,reproduce=f'python -m scripts.analyze_beampair1 {root} --out {out}')
    out.mkdir(parents=True,exist_ok=True)
    dump(out/'summary.json',report)
    dump(out/'rejection-table.json',dict(schema='ugrp.beampair1.funnel.v1',source_sha=batch['source_sha'],
        raw_root=str(root),episode_funnel=funnel,reason_distribution=dict(reasons),blocked_objects=dict(blocker_counts),
        candidate_populations={e['raw']:e['candidate_populations'] for e in episodes},
        frame_populations={e['raw']:e['frame_funnel'] for e in episodes},
        event_populations={e['raw']:e['event_funnel'] for e in episodes},
        missing_rejection_audit_N=missing,reproduce=report['reproduce']))
    dump(out/'candidate-rejections.json',all_rejections)
    print(json.dumps({k:v for k,v in report.items() if k!='runs'}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True);analyze(a.root,a.out)
