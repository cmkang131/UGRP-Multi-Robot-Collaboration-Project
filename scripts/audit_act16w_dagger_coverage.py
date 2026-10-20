"""Audit actual DAgger h0 coverage, exclusions and student-issued departures.

No teacher query, physics, new tolerance or policy change. A noninitial valid
label after an issued action differing from the oracle establishes existence
of student-induced command-history coverage, not sufficient data or recovery.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

from act16w_runtime import ACT_SHA,require_gcp2,frozen_source,sha256
from act16w_dagger import prepare_single_step

ROOT=Path(__file__).resolve().parents[1]
ACT=Path('/home/ugrp/ugrp-sim/src')/ACT_SHA


def read(p):return json.loads(p.read_text())
def lines(p):return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--collection',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();host,source=require_gcp2(training=True),frozen_source(ROOT);frozen_source(ACT,ACT_SHA)
    sys.path.insert(0,str(ACT));from harness import grasp_act_contract as c
    batch=read(a.collection/'summary.json')
    if not batch['complete'] or batch['N']!=20:raise ValueError('completed registered20 prefixes required')
    rows=[];reasons=Counter();route_rejections=[];raw=[dict(path=str(a.collection/'summary.json'),sha256=sha256(a.collection/'summary.json'))];audits=[]
    for collection in map(Path,batch['collections']):
        summary=read(collection/'summary.json');audit=read(collection/'owner/oracle-audit.json');audits.append(audit)
        if not summary['complete'] or audit['integration_and_actor_inputs_unchanged'] is not True:
            raise ValueError('completed state/input invariant collection required')
        plans=read(collection/'initial-plans.json')['episodes']
        raw.extend(dict(path=str(x),sha256=sha256(x)) for x in (collection/'summary.json',collection/'initial-plans.json'))
        for i,plan in enumerate(plans):
            folder=collection/f'world-{i:03d}'
            obs=lines(folder/'student-r1.jsonl');labels=lines(folder/'teacher-r1.jsonl');actions=lines(folder/'student-actions.jsonl')
            if len(obs)!=len(actions):raise ValueError('student observation/action counts differ')
            targets,table=prepare_single_step(obs,labels,contract=c,audit=audit)
            valid={x['observation_index'] for x in targets};departed=False;noninitial=0;induced=0
            for j,(ob,label) in enumerate(zip(obs,labels)):
                if j:
                    if ob['issued'][-1]!=actions[j-1]['command']:raise ValueError('history not actual student command')
                    previous=labels[j-1].get('teacher_command')
                    if previous is not None:
                        departed |= any(actions[j-1]['command'][k]!=previous[k] for k in ('wheels','duration_s','pwm'))
                if j in valid and j>0:
                    noninitial+=1;induced+=int(departed)
                route_rejections.extend(dict(seed=plan['seed'],**x) for x in label.get('route_rejections',[]))
            reasons.update({x['category']:x['count'] for x in table['rejections']})
            rows.append(dict(seed=plan['seed'],kind=plan['kind'],observations=len(obs),valid_h0=len(valid),
                valid_noninitial=noninitial,valid_after_different_student_command=induced,
                teacher_phase_counts=dict(Counter(labels[j]['teacher_phase'] for j in valid)),
                target_visible_valid_N=sum(labels[j].get('target_visible') is True for j in valid),
                last_valid_elapsed_SIM_s=(obs[max(valid)]['t']-obs[0]['t']) if valid else None,
                planned_prefix_cap_end=i in summary['prefix_cap_end_worlds']))
            raw.extend(dict(path=str(x),sha256=sha256(x)) for x in (folder/'student-r1.jsonl',folder/'teacher-r1.jsonl',folder/'student-actions.jsonl',collection/'owner/oracle-audit.json'))
    if len(rows)!=20 or {x['seed'] for x in rows}!=set(batch['requested_seeds']):raise ValueError('exact20 coverage required')
    total=sum(x['observations'] for x in rows);accepted=sum(x['valid_h0'] for x in rows);induced=sum(x['valid_after_different_student_command'] for x in rows)
    report=dict(status='complete',complete=True,host=host,source_sha=source,N=20,
        observations=total,valid_h0=accepted,valid_noninitial=sum(x['valid_noninitial'] for x in rows),
        valid_after_different_student_command=induced,student_induced_command_history_coverage_exists=induced>0,
        planned_prefix_cap_end_N=sum(x['planned_prefix_cap_end'] for x in rows),
        audit_totals={k:sum(x[k] for x in audits) for k in ('invisible_measurements','held_world_reads','teacher_actions_executed')},
        rejection_counts=dict(reasons),route_rejections=route_rejections,rows=rows,raw=raw,
        funnel=[dict(gate='student_oracle_pairs',passed=total,rejected=0),dict(gate='valid_h0',passed=accepted,rejected=total-accepted)],
        scope='actual pre-hover h0-only coverage; issued-command differences do not measure physical pose distance or demonstrate recovery/success; no validation/final states admitted',reproduce=sys.argv)
    with a.out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps({k:report[k] for k in ('status','N','observations','valid_h0','valid_noninitial','valid_after_different_student_command','student_induced_command_history_coverage_exists','rejection_counts')}))


if __name__=='__main__':main()
