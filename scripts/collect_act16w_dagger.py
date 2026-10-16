"""Default-off30SIM DAgger prefix; teacher labels never alter ACT commands."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import time
from act16w_runtime import ACT_SHA, frozen_source, require_gcp2, sha256
from act16w_dagger_rpc import DaggerClient

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser();p.add_argument('--enabled',action='store_true');p.add_argument('--interface-probe-only',action='store_true')
    for k in ('physics-python','qualified-source','teacher-source','qualification','references','compiled-reference','compiled-geometry','plans','actor-source','out'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--checkpoint',type=Path);p.add_argument('--dagger-starts',type=Path)
    a=p.parse_args()
    if not a.enabled:p.error('DAgger collection default OFF')
    host=require_gcp2(training=True);source=frozen_source(ROOT);frozen_source(a.actor_source,ACT_SHA)
    plans=json.loads(a.plans.read_text())['episodes']
    if a.interface_probe_only:
        if len(plans)!=1 or not 86820<=plans[0]['seed']<=86864:p.error('single TRAIN-world interface probe only')
    else:
        if a.checkpoint is None or a.dagger_starts is None:p.error('trained ACT checkpoint and preregistered TRAIN starts required')
        seeds=[x['seed'] for x in plans];registered=json.loads(a.dagger_starts.read_text())['seeds']
        if len(seeds)!=len(set(seeds)) or not set(seeds)<=set(registered) or any(not 86820<=s<=86864 for s in seeds):
            raise ValueError('DAgger visits must use preregistered D0 TRAIN starts')
        meta=json.loads((a.checkpoint/'adapter.json').read_text());prov=meta['provenance']
        if prov.get('synthetic_only') or prov.get('step')!=10000:raise ValueError('completed fixed10000-step research checkpoint required')
    sys.path.insert(0,str(a.actor_source))
    from harness.grasp_act_contract import validate_observation
    if not a.interface_probe_only:
        from harness.grasp_act_policy import ChunkExecutor
        from harness.grasp_act_rollout import SoloSequence
        from act16w_input import Act16wActor
        actor=Act16wActor.load(a.checkpoint,device='cuda');chunks=[ChunkExecutor(actor.predict) for _ in plans];seq=[SoloSequence(with_release=True) for _ in plans]
    client=DaggerClient(python=a.physics_python,qualified_source=a.qualified_source,teacher_source=a.teacher_source,
        qualification=a.qualification,references=a.references,compiled_reference=a.compiled_reference,compiled_geometry=a.compiled_geometry,
        out=a.out,nworld=len(plans),enabled=True,training=True)
    report=dict(status='running',complete=False,source_sha=source,host=host,interface_probe_only=a.interface_probe_only,training_data_admitted=False,
        checkpoint_sha256=sha256(a.checkpoint/'model.safetensors') if a.checkpoint else None,teacher_actions_executed=0,
        prefix_cap_SIM_s=30,scope='student-induced TRAIN states with h0-only pre-hover labels; capped prefix is not task success')
    streams=[];resource_cap=False
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
            for tick in range(300):  # preregistered coverage prefix, not task evaluation
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
                for i,((obs,jpgs),label) in enumerate(zip(observations,labels)):
                    if not active[i]:continue
                    folder=a.out/f'world-{i:03d}'
                    for ref,jpg in zip(obs['rgb'],jpgs):
                        path=folder/ref['path'];path.parent.mkdir(parents=True,exist_ok=True)
                        if not path.exists():path.write_bytes(jpg)
                    for stream,value in zip(streams[i],(obs,label,actions[i])):stream.write(json.dumps(value,allow_nan=False)+'\n');stream.flush()
                # This executes exactly the pre-query ACT selection, never the
                # teacher command. Labels are already isolated in separate files.
                client.step(actions)
                report.update(ticks=tick+1,oracle_audit=audit)
                if tick%10==0:(a.out/'progress.json').write_text(json.dumps(report)+'\n')
                if all(client.terminal):break
            report.update(status='cap_end' if resource_cap else 'prefix_complete',complete=not resource_cap,resource_cap_end=resource_cap,
                prefix_cap_end_worlds=[i for i,x in enumerate(client.terminal) if not x],task_success_claim=False)
    except BaseException as error:
        report.update(status='HOST_ERROR',error=repr(error));raise
    finally:
        for group in streams:
            for stream in group:stream.close()
        try:client.close('task_budget_cap_end' if resource_cap else 'dagger_prefix_cap_end')
        finally:(a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
