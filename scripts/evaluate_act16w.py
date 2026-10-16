"""Default-off ACT16 own-RGB evaluation; privileged scoring is post-action only."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,'/home/ugrp/ugrp-sim/src/0362037280c6cbc4677f70366db43b9892b23690/scripts')
from act16w_eval_rpc import EvaluationClient as Client
from act16w_runtime import require_gcp2,frozen_source,ACT_SHA,evaluation_seed_guard


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled', action='store_true')
    p.add_argument('--full-evaluation', action='store_true', help='opt-in90SIMs with frozen SoloSequence, including release')
    for key in ('physics-python', 'qualified-source', 'teacher-source', 'qualification', 'references',
                'compiled-reference', 'compiled-geometry', 'plans', 'actor-source', 'checkpoint', 'out'):
        p.add_argument('--'+key, type=Path, required=True)
    p.add_argument('--deadline-utc',required=True)
    p.add_argument('--protocol',type=Path,required=True)
    p.add_argument('--split',choices=['validation','final'],required=True)
    p.add_argument('--selection',type=Path)
    a = p.parse_args()
    from datetime import datetime
    import time
    deadline=datetime.fromisoformat(a.deadline_utc).timestamp()
    if deadline>datetime.fromisoformat('2026-10-16T13:47:00.019842+00:00').timestamp():p.error('task8h cap')
    if not a.enabled or not a.full_evaluation:p.error('explicit --enabled --full-evaluation required')
    if time.time()>=deadline:p.error('resource deadline already expired')
    import platform
    if platform.system() != 'Linux': p.error('Linux gcp2 only')
    host=require_gcp2(training=True);source=frozen_source(ROOT);frozen_source(a.actor_source,ACT_SHA)
    model = a.checkpoint/'model.safetensors'
    expected=hashlib.sha256(model.read_bytes()).hexdigest()
    plans = json.loads(a.plans.read_text())['episodes']
    meta=json.loads((a.checkpoint/'adapter.json').read_text())
    evaluation_seed_guard(meta['provenance'],[x['seed'] for x in plans],split=a.split,
        protocol=json.loads(a.protocol.read_text()),model_sha256=expected,
        selection=json.loads(a.selection.read_text()) if a.selection else None)
    sys.path.insert(0, str(a.actor_source))
    from harness.grasp_act_policy import ChunkExecutor
    from act16w_input import Act16wActor
    from harness.grasp_act_contract import validate_observation
    from harness.grasp_act_rollout import SoloSequence, SoloScore
    actor = Act16wActor.load(a.checkpoint, device='cuda')
    chunks = [ChunkExecutor(actor.predict) for _ in plans]
    sequences = [SoloSequence(with_release=True) for _ in plans]
    client = Client(python=a.physics_python, qualified_source=a.qualified_source, teacher_source=a.teacher_source,
        qualification=a.qualification, references=a.references, compiled_reference=a.compiled_reference,
        compiled_geometry=a.compiled_geometry, out=a.out, nworld=len(plans), enabled=True,
        on_reset=lambda indices: [chunks[i].reset() for i in indices])
    report = dict(status='running', complete=False,api_checks_passed=False, source_sha=source,host=host,checkpoint_sha256=expected,resource_cap_end=False,
                  split=a.split,scope='ACT16 full grasp/release evaluation, post-action truth scoring')
    try:
        client.reset(plans)
        actions_log = [];inputs_log=(a.out/'actor-inputs.jsonl').open('x')
        for step in range(900):  # frozen90SIMs /0.1SIMs
            if time.time()>=deadline:
                report['resource_cap_end']=True;break
            actions = []
            skills = []
            for i, chunk in enumerate(chunks):
                if client.terminal[i]:
                    obs, _ = client.read_actor(i)
                    actions.append(dict(command=dict(obs['issued'][-1], t=obs['t']), done=True))
                    skills.append(sequences[i].skill)
                    continue
                if client.read_actor(i)[0]['skill'] != sequences[i].skill:
                    client.instruct(i, sequences[i].skill); chunk.reset()
                obs, jpgs = client.read_actor(i); validate_observation(obs)
                folder=a.out/f'actor-inputs/world-{i:03d}'
                current=obs['rgb'][-1];image_path=folder/current['path'];image_path.parent.mkdir(parents=True,exist_ok=True)
                if not image_path.exists():image_path.write_bytes(jpgs[-1])
                inputs_log.write(json.dumps(dict(world=i,observation=obs))+'\n')
                command, done = chunk.step(obs, jpgs)
                skills.append(obs['skill'])
                terminal = sequences[i].update(obs['t'], done)
                actions.append(dict(command=command, done=terminal))
            client.step(actions); actions_log.append(dict(actions=actions, skills=skills))
            if step%10==0:(a.out/'progress.json').write_text(json.dumps(dict(step=step,elapsed_SIM=(step+1)*.1,terminal=client.terminal))+'\n')
            if all(client.terminal): break
        inputs_log.close()
        try: client.read_training(0)
        except RuntimeError: pass
        else: raise RuntimeError('training lane exposed to actor evaluator')
        report.update(status='complete', api_checks_passed=True, actions=actions_log, terminal=client.terminal,
                      actor_schema=client.read_actor(0)[0]['schema'], actual_inference=True,teacher_constructed=False,privileged_policy_inputs=0,
                      native_camera='640x480/10Hz; four own lags each resized320x240 then2x2 montage640x480')
        terminal_before_close=list(client.terminal)
        client.close('task_budget_cap_end' if report['resource_cap_end'] else 'evaluation_end')
        if a.full_evaluation:
            # Evaluation truth is read ONLY after all policy actions. Reuse the
            # checkpoint's exact evaluator; the owner's teacher Score is a
            # separate diagnostic, not silently substituted as student score.
            scores = [SoloScore() for _ in plans]
            for line in (a.out/'owner/evaluation-only.jsonl').read_text().splitlines():
                ev = json.loads(line)
                if 'min_z' not in ev: continue
                i = ev['world']; index = max(0, round(ev['elapsed_sim_s']/.1)-1)
                if not actions_log:continue
                skill = actions_log[min(index, len(actions_log)-1)]['skills'][i]
                scores[i].add(ev['t'], skill=skill, linear_speed=ev['speed'], clearance=ev['min_z'],
                              tilt=ev['tilt_deg'], forces=ev['finger_forces'], weld=ev['weld_active'])
            report['student_scores'] = []
            for i, (plan, score, seq) in enumerate(zip(plans, scores, sequences)):
                result = json.loads((a.out/'owner'/f'world-{i:03d}'/'result.json').read_text())
                report['student_scores'].append(dict(seed=plan['seed'], cap_end=result['cap_end'],
                    issued_sequence_complete=result['issued_done'],resource_cap_end=report['resource_cap_end'] and not terminal_before_close[i], **score.record(seq.done_times, with_release=True)))
            for row in report['student_scores']:
                row['task_success']=bool(row['physical_success'] and row['issued_sequence_complete'] and not row['cap_end'] and not row['resource_cap_end'])
            # All privileged instance scoring is consumed only after every
            # actor action and owner close. It never enters read_actor.
            instance_scores={}
            for line in (a.out/'owner/same-kind-evaluation-only.jsonl').read_text().splitlines():
                ev=json.loads(line);i=ev['world'];index=max(0,round(ev['elapsed_sim_s']/.1)-1)
                if not actions_log:continue
                key=(i,ev['item_id']);score=instance_scores.setdefault(key,SoloScore())
                score.add(ev['t'],skill=actions_log[min(index,len(actions_log)-1)]['skills'][i],
                    linear_speed=ev['speed'],clearance=ev['min_z'],tilt=ev['tilt_deg'],
                    forces=ev['finger_forces'],weld=ev['weld_active'])
            for i,(plan,row,seq) in enumerate(zip(plans,report['student_scores'],sequences)):
                items=[]
                for (world,item),score in instance_scores.items():
                    if world!=i:continue
                    value=score.record(seq.done_times,with_release=True)
                    value.update(item_id=item,task_success=bool(value['physical_success'] and row['issued_sequence_complete'] and not row['cap_end'] and not row['resource_cap_end']))
                    items.append(value)
                assigned=next(value for value in items if value['item_id']==plan['item_id'])
                if any(assigned[key]!=row[key] for key in ('lift_success','release_success','physical_success','task_success')):
                    raise ValueError('private same-kind evaluator changed assigned-item score')
                row.update(assigned_item_id=plan['item_id'],same_kind_items=items,
                    any_same_kind_success=any(value['task_success'] for value in items))
            visibility=json.loads((a.out/'owner/initial-same-kind-visibility.json').read_text())
            report['initial_same_kind_visibility']=visibility
            report['initial_2plus_same_kind_any_probe_n']=sum(x['any_probe_visible_count']>=2 for x in visibility['rows'])
            report['initial_2plus_same_kind_qualified_n']=sum(x['qualified_visible_count']>=2 for x in visibility['rows'])
            report['same_kind_visibility_N']=len(plans)
            report['n_any_same_kind']=sum(row['any_same_kind_success'] for row in report['student_scores'])
            report.update(complete=all(terminal_before_close) and not report['resource_cap_end'],status='cap_end' if report['resource_cap_end'] else 'complete',n=sum(x['task_success'] for x in report['student_scores']),N=len(plans),n_physical=sum(x['physical_success'] for x in report['student_scores']))
            report['scope'] = 'ACT16 full grasp/release evaluation on MJWarp; no teacher actions, no GT policy inputs'
    except BaseException as error:
        report.update(status='HOST_ERROR', error=repr(error)); raise
    finally:
        if 'inputs_log' in locals() and not inputs_log.closed:inputs_log.close()
        try: client.close('HOST_ERROR' if report['status']=='HOST_ERROR' else 'task_budget_cap_end' if report['resource_cap_end'] else 'evaluation_end' if a.full_evaluation else 'smoke_control_budget_end')
        except BaseException as error: report.update(status='HOST_ERROR', close_error=repr(error), api_checks_passed=False)
        finally:
            if 'actions' in report:
                with (a.out/'actor-actions.jsonl').open('x') as f:
                    for row in report.pop('actions'):f.write(json.dumps(row)+'\n')
            if report.get('student_scores'):
                rows=report['student_scores'];eligible=list(range(len(rows)));counts=[len(rows)]
                for predicate in [lambda i:'grasp' in sequences[i].done_times,lambda i:rows[i]['lift_success'],lambda i:rows[i]['release_success'],lambda i:rows[i]['task_success']]:
                    eligible=[i for i in eligible if predicate(i)];counts.append(len(eligible))
                table=dict(funnel=[dict(gate=g,passed=n,rejected=(counts[i-1]-n if i else 0)) for i,(g,n) in enumerate(zip(['requested','grasp_done','stable_lift','stable_release','task_success'],counts))],rejections=[dict(seed=x['seed'],category='cap_end' if x['cap_end'] or x['resource_cap_end'] else x.get('failure_reason') or 'sequence_not_complete',reason=x.get('failure_reason') or 'sequence_not_complete',blocking_object='not_attributed_before_playback',minimum_gap_m=None,minimum_gap_status='not measured; no geometric cause claim') for x in rows if not x['task_success']],raw=str(a.out),reproduce=sys.argv)
                (a.out/'rejection_table.json').write_text(json.dumps(table,indent=2)+'\n')
                report['rejection_table']=str(a.out/'rejection_table.json')
            (a.out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__': main()
