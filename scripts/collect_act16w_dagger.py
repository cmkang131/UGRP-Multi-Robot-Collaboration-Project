"""Default-off30SIM DAgger prefix; label-only by default, optional C1 takeover.

Without ``--takeover`` teacher labels never alter ACT commands. With it, a
preregistered trigger executes a fresh teacher (2 s hold by default override)
through the same owner.step path and records the executed commands separately.
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import time
from act16w_runtime import ACT_SHA, frozen_source, require_gcp2, sha256
from act16w_dagger_rpc import DaggerClient
from act18_chunk8 import contract_chunk_predict, pilot_checkpoint_chunk

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser();p.add_argument('--enabled',action='store_true');p.add_argument('--interface-probe-only',action='store_true')
    for k in ('physics-python','qualified-source','teacher-source','qualification','references','compiled-reference','compiled-geometry','plans','actor-source','out'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--checkpoint',type=Path);p.add_argument('--dagger-starts',type=Path)
    p.add_argument('--native-protocol',type=Path)
    p.add_argument('--takeover',action='store_true');p.add_argument('--takeover-hold-s',type=float,default=3.0)
    p.add_argument('--takeover-after-s',type=float,default=6.0);p.add_argument('--max-ticks',type=int,default=300)
    p.add_argument('--takeover-pilot',action='store_true')
    p.add_argument('--plan-seeds',type=int,nargs='+')
    # Default OFF: admit only a checkpoint whose declared ACT horizon already
    # equals the frozen contract (R8).  R100 chunk100 is rejected, never sliced.
    p.add_argument('--contract-chunk8',action='store_true')
    a=p.parse_args()
    if not a.enabled:p.error('DAgger collection default OFF')
    if a.takeover_pilot and not a.takeover:p.error('--takeover-pilot requires explicit --takeover')
    if a.contract_chunk8 and not a.takeover_pilot:p.error('--contract-chunk8 is takeover-pilot-only')
    if a.plan_seeds and not a.takeover_pilot:p.error('--plan-seeds is takeover-pilot-only')
    if a.plan_seeds and len(set(a.plan_seeds))!=len(a.plan_seeds):p.error('unique pilot seeds required')
    if a.takeover_pilot and a.max_ticks!=900:p.error('takeover pilot uses the unchanged 90 SIM s owner cap (--max-ticks 900)')
    if a.takeover and a.interface_probe_only:p.error('takeover requires the applied student rollout lane, not an interface probe')
    if not 0<a.takeover_hold_s<=60:p.error('takeover hold must be in (0, 60] SIM s')
    if a.takeover_after_s<0:p.error('takeover delay must be nonnegative')
    if not 1<=a.max_ticks<=900:p.error('1..900 SIM ticks (the unchanged owner cap is 90 SIM s)')
    host=require_gcp2(training=True);source=frozen_source(ROOT);frozen_source(a.actor_source,ACT_SHA)
    plans=json.loads(a.plans.read_text())['episodes']
    if a.plan_seeds:
        by_seed={plan['seed']:plan for plan in plans}
        missing=[seed for seed in a.plan_seeds if seed not in by_seed]
        if missing:raise ValueError('pilot seeds missing from reference plans: '+repr(missing))
        plans=[by_seed[seed] for seed in a.plan_seeds]
    checkpoint_chunk=None
    if a.interface_probe_only:
        if len(plans)!=1 or not 86820<=plans[0]['seed']<=86864:p.error('single TRAIN-world interface probe only')
    else:
        if a.checkpoint is None or a.dagger_starts is None:p.error('trained ACT checkpoint and preregistered TRAIN starts required')
        seeds=[x['seed'] for x in plans];registered=json.loads(a.dagger_starts.read_text())['seeds']
        if a.native_protocol:
            protocol_meta=json.loads(a.native_protocol.read_text())
            keys=('train_seeds','train4_seeds') if a.takeover_pilot else ('train_seeds',)
            allowed=set().union(*(set(protocol_meta.get(k,[])) for k in keys))
        else:allowed=list(range(86820,86865))
        if len(seeds)!=len(set(seeds)) or not set(seeds)<=set(registered) or not set(seeds)<=set(allowed):
            raise ValueError('DAgger visits must use preregistered D0 TRAIN starts')
        meta=json.loads((a.checkpoint/'adapter.json').read_text());prov=meta['provenance']
        act18_checkpoint=meta.get('schema')=='ugrp.act18.adapter.v1'
        if prov.get('synthetic_only'):raise ValueError('completed non-synthetic student checkpoint required')
        if act18_checkpoint:
            # C1 pilot/training lane: the registered act18 candidate (e.g. co-r2
            # best 68k) is complete but is not the fixed10000-step D0 checkpoint.
            if not a.takeover_pilot:raise ValueError('act18 checkpoint requires explicit takeover-pilot lane')
            if not prov.get('training_complete'):raise ValueError('completed act18 training schedule required')
        elif prov.get('step')!=10000:raise ValueError('completed fixed10000-step research checkpoint required')
        if bool(a.native_protocol) != bool(os.environ.get('UGRP_ACT16W_NATIVE_GATE')) or bool(a.native_protocol) != (prov.get('contact_profile')=='warp_native_contact_v1'):
            raise ValueError('native DAgger model/protocol/physics must all match')
    sys.path.insert(0,str(a.actor_source))
    from harness.grasp_act_contract import validate_observation
    if not a.interface_probe_only:
        # Resolve the chunk only after the pinned actor source is on sys.path,
        # so this guard and the executor both read the frozen contract package.
        checkpoint_chunk=pilot_checkpoint_chunk(meta,takeover_pilot=a.takeover_pilot,
            enabled=a.contract_chunk8)
        from harness.grasp_act_policy import ChunkExecutor
        from harness.grasp_act_rollout import SoloSequence
        if act18_checkpoint:
            from act18_policy import Actor as PolicyActor
            actor=PolicyActor.load(a.checkpoint,device='cuda')
        else:
            from act16w_input import Act16wActor
            actor=Act16wActor.load(a.checkpoint,device='cuda')
        predict=contract_chunk_predict(actor.predict,enabled=a.contract_chunk8)
        chunks=[ChunkExecutor(predict) for _ in plans];seq=[SoloSequence(with_release=True) for _ in plans]
    client=DaggerClient(python=a.physics_python,qualified_source=a.qualified_source,teacher_source=a.teacher_source,
        qualification=a.qualification,references=a.references,compiled_reference=a.compiled_reference,compiled_geometry=a.compiled_geometry,
        out=a.out,nworld=len(plans),enabled=True,training=True,takeover=a.takeover,
        takeover_hold_s=a.takeover_hold_s,takeover_after_s=a.takeover_after_s)
    report=dict(status='running',complete=False,source_sha=source,host=host,interface_probe_only=a.interface_probe_only,training_data_admitted=False,
        checkpoint_sha256=sha256(a.checkpoint/'model.safetensors') if a.checkpoint else None,teacher_actions_executed=0,
        prefix_cap_SIM_s=a.max_ticks/10,contract_chunk8=bool(a.contract_chunk8),checkpoint_chunk=checkpoint_chunk,
        takeover=dict(enabled=bool(a.takeover),hold_s=a.takeover_hold_s,
        after_s=a.takeover_after_s,max_ticks=a.max_ticks,trigger='elapsed>=after_s and 20 consecutive moving/stopped issued ticks'),
        takeover_ticks=0,takeover_worlds=[],
        scope=('executed teacher takeover on student-induced TRAIN states; labels are the executed teacher commands; capped prefix is not task success'
               if a.takeover else 'student-induced TRAIN states with h0-only pre-hover labels; capped prefix is not task success'))
    streams=[];resource_cap=False
    takeover_log=(a.out/'takeover-actions.jsonl').open('x') if a.takeover else None
    try:
        client.reset(plans)
        if a.interface_probe_only:
            before=[client.read_actor(0)];selected=[before[0][0]['issued'][-1]]
            labels,audit=client.labels_for_training_only(selected)
            if before!=[client.read_actor(0)] or not audit['integration_and_actor_inputs_unchanged']:raise ValueError('oracle affected actor state')
            report.update(status='complete',complete=True,labels=labels,oracle_audit=audit,student_actions=0,research_optimizer_steps=0)
            # A synthetic checkpoint may test the actual RGB transport/adapter,
            # but its commands are NEVER applied and no pair is admitted as data.
            if a.checkpoint:
                import numpy as np
                from act16w_input import Act16wActor
                from act16w_dagger import prepare_single_step
                from harness import grasp_act_contract as c
                actor=Act16wActor.load(a.checkpoint,device='cuda')
                obs,jpgs=before[0];prediction=np.asarray(actor.predict(obs,jpgs))
                if prediction.shape!=(8,14) or not np.isfinite(prediction).all():raise ValueError('native ACT prediction failed')
                folder=a.out/'probe-actor';folder.mkdir()
                (folder/'observation.json').write_text(json.dumps(obs,indent=2)+'\n')
                for ref,jpeg in zip(obs['rgb'],jpgs):
                    path=folder/ref['path'];path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(jpeg)
                pairs,pair_audit=prepare_single_step([obs],labels,contract=c,audit=audit)
                if len(pairs)!=1:raise ValueError('native initial pair not admitted by h0 target boundary')
                report.update(native_policy_probe=dict(checkpoint_synthetic=bool(json.loads((a.checkpoint/'adapter.json').read_text())['provenance'].get('synthetic_only')),
                    serialized_history_mode=actor.mode,prediction_shape=list(prediction.shape),native_jpeg_sha256s=[r['sha256'] for r in obs['rgb']],
                    valid_target_horizons=int((~pairs[0]['action_is_pad']).sum()),future7_padded=True,pair_audit=pair_audit,policy_commands_executed=0,data_admitted=False))
        else:
            for i in range(len(plans)):
                folder=a.out/f'world-{i:03d}';folder.mkdir()
                streams.append(((folder/'student-r1.jsonl').open('x'),(folder/'teacher-r1.jsonl').open('x'),(folder/'student-actions.jsonl').open('x')))
            for tick in range(a.max_ticks):  # preregistered coverage prefix, not task evaluation
                active=[not x for x in client.terminal];actions=[];observations=[]
                for i in range(len(plans)):
                    if active[i] and client.read_actor(i)[0]['skill']!=seq[i].skill:
                        client.instruct(i,seq[i].skill);chunks[i].reset()
                    obs,jpgs=client.read_actor(i);validate_observation(obs);observations.append((obs,jpgs))
                    if active[i]:
                        command,done=chunks[i].step(obs,jpgs);terminal=seq[i].update(obs['t'],done)
                    else:command,terminal=dict(obs['issued'][-1],t=obs['t']),True
                    actions.append(dict(command=command,done=terminal))
                labels,audit=client.labels_for_training_only([x['command'] for x in actions])
                takeover=client.takeover_commands
                if takeover is not None:
                    if not a.takeover:raise RuntimeError('takeover commands outside explicit takeover mode')
                    for i,item in enumerate(takeover):
                        if item is None:continue
                        if labels[i].get('takeover') is not True:raise RuntimeError('takeover command without takeover label')
                        actions[i]=dict(command=item['command'],done=bool(item['done']))
                        takeover_log.write(json.dumps(dict(world=i,t=item['command']['t'],command=item['command'],
                            done=item['done'],sample_id=labels[i]['sample_id'],hold_s=labels[i].get('hold_s'),
                            teacher_phase=labels[i].get('teacher_phase'),phase_after=labels[i].get('phase_after'),
                            rgb_holding=labels[i].get('rgb_holding')),allow_nan=False)+'\n');takeover_log.flush()
                        report['takeover_ticks']+=1
                        if i not in report['takeover_worlds']:report['takeover_worlds'].append(i)
                for i,((obs,jpgs),label) in enumerate(zip(observations,labels)):
                    if not active[i]:continue
                    folder=a.out/f'world-{i:03d}'
                    for ref,jpg in zip(obs['rgb'],jpgs):
                        path=folder/ref['path'];path.parent.mkdir(parents=True,exist_ok=True)
                        if not path.exists():path.write_bytes(jpg)
                    for stream,value in zip(streams[i],(obs,label,actions[i])):stream.write(json.dumps(value,allow_nan=False)+'\n');stream.flush()
                # Default lane executes exactly the pre-query ACT selection;
                # takeover worlds execute only the teacher command returned by
                # the host for this exact state, through the same owner.step.
                client.step(actions)
                report.update(ticks=tick+1,oracle_audit=audit,
                    teacher_actions_executed=int(audit.get('teacher_actions_executed',0)),
                    takeover_worlds=sorted(report['takeover_worlds']))
                if tick%10==0:(a.out/'progress.json').write_text(json.dumps(report)+'\n')
                if all(client.terminal):break
            report.update(status='cap_end' if resource_cap else 'prefix_complete',complete=not resource_cap,resource_cap_end=resource_cap,
                prefix_cap_end_worlds=[i for i,x in enumerate(client.terminal) if not x],task_success_claim=False)
    except BaseException as error:
        report.update(status='HOST_ERROR',error=repr(error));raise
    finally:
        for group in streams:
            for stream in group:stream.close()
        if takeover_log is not None:takeover_log.close()
        try:client.close('task_budget_cap_end' if resource_cap else 'dagger_prefix_cap_end')
        finally:(a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
