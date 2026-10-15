"""Finite default-OFF gcp2 ACT15 signal pilot; standard manager adapter.

Probe/train/evaluate are distinct processes. Evaluation imports no reward,
critic or environment module; only the RGB JSON client and actor are loaded.
One shared receipt covers ALL GPU-host setup/JIT/probe/train/evaluation time.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


class BudgetEnd(RuntimeError):pass
class AdmissionBlock(RuntimeError):pass


def write(path,value):
    Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled',action='store_true')
    p.add_argument('--mode',choices=['probe','train','evaluate'],required=True)
    for name in ('actor-source','teacher-source','checkpoint','physics-python','plans','training-plans',
                 'compiled-reference','compiled-geometry','calibration','budget','out'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--seal',type=Path)
    p.add_argument('--residual',type=Path)
    a=p.parse_args()
    from scripts.simalt_host import gcp2_identity
    host=gcp2_identity()
    if not a.enabled or host['instance']!='ugrp-act-l4-gcp2':p.error('explicit Linux gcp2 L4 opt-in required')
    receipt=json.loads(a.budget.read_text())
    if receipt['deadline_epoch_s']-receipt['started_epoch_s']>3600 or receipt['project']!='ugrp-sim-b-1014':
        p.error('single <=1h gcp2 GPU receipt required')
    step_allowance=0.
    def check():
        # Resource-only reserve: Client.close waits30s, then terminate waits10s.
        # No physical/controller acceptance threshold is introduced here.
        if time.time()+40.+step_allowance>=receipt['deadline_epoch_s']:
            raise BudgetEnd('shared one-hour GPU resource cap, including owner cleanup')
    check()
    a.out.mkdir(parents=True,exist_ok=False)
    sha=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
    if subprocess.check_output(['git','-C',str(ROOT),'status','--porcelain','--untracked-files=no']):
        p.error('committed clean execution source required')
    # Establish our scripts package before adding the frozen actor module root.
    from scripts.rl_act_actor import FrozenACT,ResidualPolicy
    from scripts.rl_act_rpc import Client
    import numpy as np
    import torch
    torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.manual_seed(20261016)
    plans=json.loads(a.plans.read_text())['episodes']
    if len(plans)!=8:p.error('sealed short cohort is8worlds')
    n=len(plans)
    frozen=FrozenACT(a.actor_source,a.checkpoint,n,device='cuda')
    limits=np.asarray(json.loads(a.calibration.read_text())['residual_limits'],np.float64)
    client=Client(python=a.physics_python,teacher_source=a.teacher_source,actor_source=a.actor_source,
        out=a.out/'client',compiled_reference=a.compiled_reference,compiled_geometry=a.compiled_geometry,
        nworld=n,training=a.mode=='train')
    report=dict(status='running',mode=a.mode,source_sha=sha,host=host,nworld=n,seed=20261016,
        actor_model_sha256='d90a2b545709df6cd1a5972874db2e20c264007f9a798888f1bdccac22882ed1',
        actor_input='own RGB+issued history+instruction+own chunk/done memory',
        physics_backend='mjwarp',scene='ACT15 frozen6f S1 cyan_1 floor_light_v1; no scene-v5 pooling',
        shared_scene_seed_v1=plans[0].get('shared_scene_seed_v1'),
        budget=str(a.budget),gpu_deadline_epoch_s=receipt['deadline_epoch_s'])
    write(a.out/'RUN_META.json',dict(**{'class':'dev'},pr=530,branch='claude/rl-act',sha=sha,batch='rl1b-'+a.mode))
    public=(a.out/'actor-inputs.jsonl').open('x');losses=(a.out/'learning.jsonl').open('x')
    phase_started=time.monotonic();learner=None
    def log_inputs(inputs,actions,active):
        for i,(item,action,on) in enumerate(zip(inputs,actions,active)):
            if not on:continue
            folder=a.out/'inputs'/f'world-{i:03d}'/f'generation-{client.generations[i]:03d}'
            ref=item.observation['rgb'][-1]['path'];path=folder/ref;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(item.jpegs[-1])
            public.write(json.dumps(dict(world=i,generation=client.generations[i],input_root=str(folder),
                observation=item.observation,**action),allow_nan=False)+'\n')
        public.flush()
    try:
        if a.mode in ('probe','evaluate'):
            client.reset(plans,indices=tuple(range(n)))
            residual=ResidualPolicy(a.residual,frozen,device='cuda') if a.residual else None
            if residual is not None:limits=residual.limits
            if a.mode=='probe':count=8
            else:
                sealed=json.loads(a.seal.read_text());count=sealed['prefix_ticks']
                step_allowance=max(sealed['probe_tick_wall_s'])
            latencies=[]
            for tick in range(count):
                check();before=time.monotonic();active=[not t for t in client.terminal]
                if not any(active):break
                inputs=client.actor_inputs();features,base=frozen.prepare(inputs,active=active)
                delta=residual.select(features) if residual else np.zeros((n,14))
                actions,_=frozen.issue(inputs,base,delta,limits,active=active)
                log_inputs(inputs,actions,active);client.step(actions)
                latencies.append(time.monotonic()-before)
                step_allowance=max(latencies)
                write(a.out/'progress.json',dict(ticks=tick+1,phase_wall_s=time.monotonic()-phase_started))
            if a.mode=='probe':
                report['wall_per_sim_median']=float(np.median(latencies)/.1)
                report['aggregate_sim_s_per_wall_s']=n*.1*len(latencies)/sum(latencies)
                report['formal_30sim_speed_gate']='not measured by eight-tick correctness probe'
                all_train=json.loads(a.training_plans.read_text())['episodes']
                new=next(r for r in all_train if r['setup_fingerprint']!=plans[0]['setup_fingerprint'])
                check();client.reset([new],indices=(0,))
                report['partial_reset']='immediate integration/RGB isolation checked by owner; next-step dynamics unverified'
                if report['wall_per_sim_median']>6.:
                    raise AdmissionBlock('PRELIMINARY_SPEED_BLOCK: eight-tick median exceeds6; do not submit learning')
                # Resource allocation only. Seal a SIM-tick prefix BEFORE any fit
                # or fresh evaluation. CPU-style wall caps never steer actions.
                remaining=receipt['deadline_epoch_s']-time.time()-40.
                prefix_ticks=min(900,int(remaining/(4*max(latencies))))
                # Three curriculum tiers each need at least two ACT chunks:
                # one initial chunk plus first motion. This is a compute floor,
                # not a physical success/acceptance tolerance.
                if prefix_ticks<3*2*8:raise BudgetEnd('cannot fit three2-chunk tiers and paired evaluation')
                seal=dict(schema='ugrp.rl1b.prefix.v1',prefix_ticks=prefix_ticks,period_sim_s=.1,
                    full_task_cap_ticks=900,prefix_only=True,source_sha=sha,
                    probe_tick_wall_s=latencies,allocation='remaining GPU budget /4; three equal phases + update/export allowance',
                    sealed_epoch_s=time.time(),outcomes_used_for_horizon_selection=False,
                    evaluation_seeds=list(range(918000,918008)))
                write(a.out/'prefix-seal.json',seal)
                report['prefix_seal']=seal
            report.update(status='prefix_complete',ticks=len(latencies),phase_wall_s=time.monotonic()-phase_started,
                forbidden_loaded_modules=[m for m in sys.modules if m in ('scripts.rl_act_reward','scripts.rl_act_learning','scripts.rl_act_env','mujoco','mujoco_warp')])
        else:
            if a.seal is None:p.error('training requires a prefit sealed SIM prefix')
            from scripts.rl_act_env import ActorEnv
            from scripts.rl_act_reward import Heuristics
            from scripts.rl_act_curriculum import Curriculum,Start
            from scripts.rl_act_learning import Replay,Transition,ResidualTD3
            all_train=json.loads(a.training_plans.read_text())['episodes']
            sealed=json.loads(a.seal.read_text());ticks=sealed['prefix_ticks'];limit=n*ticks
            step_allowance=max(sealed['probe_tick_wall_s'])
            curriculum=Curriculum([Start(r['seed'],r['curriculum_setup_distance_m'],r['curriculum_setup_yaw_rad'],r) for r in all_train],
                evaluation_seeds=range(918000,918040),transition_limit=limit,rng_seed=20261016,h4_curriculum_v1=True)
            d95=float(np.quantile([r['curriculum_setup_distance_m'] for r in all_train],.95))
            env=ActorEnv(client,frozen.c.validate_observation,frozen.c.command,nworld=n,enabled=True,
                training=True,heuristics=Heuristics(True,True,True),distance_p95=d95)
            collected=0;debt=0;replay=None;resets=[];terms=Counter()
            wave1=math.ceil(ticks/3);lengths=[wave1,wave1,ticks-2*wave1]
            def optimize():
                nonlocal debt
                while debt and replay.size>=128:
                    check();losses.write(json.dumps(learner.update(replay))+'\n');debt-=1
            for wave,length in enumerate(lengths):
                check();selected=curriculum.sample(collected,n)
                inputs=env.reset(selected);frozen.reset(range(n))
                resets.append(dict(wave=wave,collected=collected,pool=len(curriculum.pool(collected)),seeds=[r['seed'] for r in selected]))
                private=env.critic_snapshot()
                if learner is None:
                    learner=ResidualTD3(frozen.feature_dim,len(private[0]),limits,frozen.c.decode_action,frozen.c.encode_action,enabled=True)
                    replay=Replay(n,frozen.feature_dim,len(private[0]),capacity=limit)
                pending=[None]*n
                def resolve(features,base):
                    nonlocal debt
                    for i,row in enumerate(pending):
                        if row is not None:
                            replay.push(i,Transition(row[0],row[1],row[2],row[3],row[4],
                                features[i],base[i],row[5],False));debt+=1;pending[i]=None
                for tick in range(length):
                    check();active=[not t for t in env.terminal]
                    features,base=frozen.prepare(inputs,active=active)
                    resolve(features,base);optimize()
                    private=env.critic_snapshot()
                    delta=learner.select(features,explore=True)
                    actions,actual=frozen.issue(inputs,base,delta,limits,active=active)
                    log_inputs(inputs,actions,active)
                    inputs,terminal,training=env.step(actions)
                    for i,on in enumerate(active):
                        if not on:continue
                        result=training[i];reward=result.reward
                        losses.write(json.dumps(dict(kind='transition',world=i,wave=wave,tick=tick,**reward))+'\n')
                        terms.update(reward['heuristic_terms']);collected+=1
                        if terminal[i]:
                            replay.push(i,Transition(features[i],base[i],np.asarray(private[i]),actual[i],reward['reward'],
                                np.zeros(frozen.feature_dim),np.zeros(14),np.asarray(result.critic),True));debt+=1
                        else:pending[i]=(features[i].copy(),base[i].copy(),np.asarray(private[i]),actual[i].copy(),reward['reward'],np.asarray(result.critic))
                    finished=[i for i,v in enumerate(terminal) if v]
                    if finished and tick+1<length:
                        selected=curriculum.sample(collected,len(finished));env.reset(selected,indices=finished);frozen.reset(finished)
                        resets.append(dict(wave=wave,collected=collected,pool=len(curriculum.pool(collected)),seeds=[r['seed'] for r in selected]))
                        inputs=env.actor_inputs()
                    write(a.out/'progress.json',dict(wave=wave,tick=tick+1,new_transitions=collected,optimizer_steps=learner.steps))
                features,base=frozen.prepare(inputs,active=[not t for t in env.terminal])
                resolve(features,base)
                for i in range(n):replay.truncate(i)
                optimize();losses.flush()
            metadata=dict(source_sha=sha,scope='rl1b short prefix; not full-task adoption',new_transitions=collected,
                          prefix_ticks=ticks,scene=report['scene'],baseline_sha256=report['actor_model_sha256'])
            learner.save(a.out/'training-checkpoint.pt',metadata)
            learner.export_actor(a.out/'residual-actor',frozen,metadata)
            report.update(status='training_complete',new_transitions=collected,optimizer_steps=learner.steps,
                replay_rows=replay.total,heuristic_reward_sums=dict(terms),individual_policy_effect='unmeasured; joint candidate only',
                curriculum_resets=resets,privileged_reward_reads=env.training_privileged_reward_reads,
                privileged_critic_reads=env.training_privileged_critic_reads)
    except AdmissionBlock as error:
        report.update(status='BLOCKED',reason=str(error),comparison_complete=False)
    except BudgetEnd as error:
        report.update(status='cap_end',reason=str(error),comparison_complete=False)
    except BaseException as error:
        report.update(status='HOST_ERROR',error_type=type(error).__name__,error=str(error),comparison_complete=False)
        raise
    finally:
        if learner is not None:
            report['optimizer_steps']=learner.steps
            report['new_transitions']=collected
            if report['status']!='training_complete':
                try:
                    learner.save(a.out/'interrupted-checkpoint.pt',dict(source_sha=sha,status=report['status'],
                        new_transitions=collected,not_evaluated=True))
                    report['interrupted_checkpoint']='interrupted-checkpoint.pt'
                except BaseException as error:report['checkpoint_unavailable']=str(error)
        public.close();losses.close()
        try:
            client.close('prefix_cap' if report['status']!='HOST_ERROR' else 'HOST_ERROR')
        except BaseException as error:
            previous=report['status']
            report.update(status='HOST_ERROR',close_error=str(error),comparison_complete=False)
            if previous!='HOST_ERROR':raise
        finally:
            report.update(phase_wall_s=time.monotonic()-phase_started,receipt_elapsed_s=time.time()-receipt['started_epoch_s'])
            write(a.out/'summary.json',report)


if __name__=='__main__':main()
