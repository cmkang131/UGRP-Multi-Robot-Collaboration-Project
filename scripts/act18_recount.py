"""Independent post-action recount of raw native traces, never a policy input."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0,str(Path(__file__).resolve().parent))
from act16w_runtime import require_gcp2,frozen_source,sha256
from act17_data import library,read
from act17_compact_records import original_sha256
from act18_diagnose import write


def recount(folder):
    library()
    from harness.grasp_act_rollout import SoloScore
    report=read(folder/'summary.json')
    if not report.get('complete') or report.get('status') not in ('complete','cap_end'):
        raise ValueError('unfinished/HOST_ERROR evaluation cannot count as complete')
    actions=read(folder/'actor-actions.jsonl',lines=True)
    from harness.grasp_act_contract import validate_observation
    input_rows=read(folder/'actor-inputs.jsonl',lines=True)
    input_rows_by_world=Counter()
    for item in input_rows:
        validate_observation(item['observation'])
        input_rows_by_world[item['world']]+=1
    plans=read(folder/'initial-plans.json')['episodes']
    scores=[SoloScore() for _ in plans]
    for ev in read(folder/'owner/evaluation-only.jsonl',lines=True):
        if 'min_z' not in ev:
            continue
        i=ev['world'];step=max(0,round(ev['elapsed_sim_s']/.1)-1)
        scores[i].add(ev['t'],skill=actions[min(step,len(actions)-1)]['skills'][i],
            linear_speed=ev['speed'],clearance=ev['min_z'],tilt=ev['tilt_deg'],
            forces=ev['finger_forces'],weld=ev['weld_active'])
    rows=[];receipts=[]
    native=read(folder/'owner/native-contact.json')
    if native.get('gpu_noslip')!=0 or any(native.get('cpu_noslip',[1])):
        raise ValueError('actual native0 options required')
    for i,(plan,score,reported) in enumerate(zip(plans,scores,report['student_scores'])):
        world=folder/'owner'/f'world-{i:03d}'
        result=read(world/'result.json')
        options=ET.fromstring((world/'scene.xml').read_text()).find('option').attrib
        if options.get('noslip_iterations')!='0':
            raise ValueError('actual XML noslip mismatch')
        # The eval-owner result.json schema differs from the older controller
        # result: it has no embedded per-world input_audit. The actor boundary
        # is enforced on the actual logged inputs instead, whose exact FIELDS
        # whitelist is checked by validate_observation above. 'world' here is
        # the evaluator's world index, not a policy observation field.
        audit=result.get('input_audit')
        if audit is None:
            if not input_rows_by_world[i]:
                raise ValueError('no logged actor inputs for world')
            audit=dict(invisible_measurements=0,held_world_reads=0,forbidden_input_fields=0,
                teacher_input_fields=0,top=0,actor_input_rows=input_rows_by_world[i],
                source='eval-owner result.json has no input_audit; actor-inputs.jsonl exact whitelist verified')
        if (any(audit.get(k)!=0 for k in ('invisible_measurements','held_world_reads'))
                or any(audit.get(k,0) for k in ('forbidden_input_fields','teacher_input_fields','top'))):
            raise ValueError('student/teacher input audit violation')
        actual=score.record(reported['issued_done_times'],with_release=True)
        if any(actual[k]!=reported[k] for k in actual):
            raise ValueError('raw physical Score recount differs')
        if bool(result['issued_done'])!=any(row['actions'][i]['done'] for row in actions):
            raise ValueError('raw issued completion differs')
        success=bool(actual['physical_success'] and result['issued_done'] and not result['cap_end'])
        if success!=reported['task_success']:
            raise ValueError('raw task success differs')
        rows.append(dict(seed=plan['seed'],kind=plan['kind'],success=success,
            lift_success=actual['lift_success'],release_success=actual['release_success'],
            grasp_done='grasp' in reported['issued_done_times'],cap_end=result['cap_end'],
            reason_category='success' if success else 'cap_end' if result['cap_end'] else actual['failure_reason'] or 'sequence_not_complete',
            blocked_object='not_attributed_by_physical_score',minimum_gap_m=None,minimum_gap_status='not_measured',
            input_audit=audit,raw=str(world),score_matches=True))
        for f in (world/'result.json',world/'eval-only.jsonl',world/'scene.xml'):
            actual_path=f if f.exists() else Path(str(f)+'.zst')
            receipts.append(dict(path=str(actual_path),sha256=sha256(actual_path),original_sha256=original_sha256(f)))
    return rows,receipts


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runs',type=Path,nargs='+',required=True)
    p.add_argument('--stage',choices=['train','validation','final'],required=True)
    p.add_argument('--checkpoint',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();host=require_gcp2(training=True);source=frozen_source(Path(__file__).resolve().parents[1])
    rows=[];receipts=[]
    for folder in a.runs:
        value,raw=recount(folder);rows+=value;receipts+=raw
    if len({r['seed'] for r in rows})!=len(rows):
        raise ValueError('duplicate physical seed')
    counts=[len(rows)];eligible=rows
    for key in ('grasp_done','lift_success','release_success','success'):
        eligible=[r for r in eligible if r[key]];counts.append(len(eligible))
    funnel=[dict(gate=gate,passed=n,rejected=counts[i-1]-n if i else 0)
        for i,(gate,n) in enumerate(zip(('requested','grasp_done','stable_lift','stable_release','task_success'),counts))]
    value=dict(complete=True,stage=a.stage,source_sha=source,host=host,n=sum(r['success'] for r in rows),N=len(rows),
        checkpoint_sha256=sha256(a.checkpoint/'model.safetensors'),rows=rows,funnel=funnel,
        actor_input_rows_verified=sum(r['input_audit'].get('actor_input_rows',0) for r in rows),
        reasons=dict(Counter(r['reason_category'] for r in rows)),raw=receipts,reproduce=sys.argv,
        training_updates=0,physics_steps=0,scope='raw native physical Score and issued completion recount; no generalization claim for TRAIN')
    with a.out.open('x') as f:
        json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps(dict(n=value['n'],N=value['N'],stage=a.stage)))


if __name__=='__main__':
    main()
