"""Opt-in ACT18 adapter around unchanged native ACT evaluator and Score.

TRAIN is explicitly a fitting diagnostic, never a held-out success result.
The legacy CLI spelling --split validation is adapted only after an exact
TRAIN4 seed guard; the final receipt always reports the real stage.
"""
import argparse
from collections import defaultdict, deque
import json
import numpy as np
import os
from pathlib import Path
import runpy
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parent))
from act16w_runtime import require_gcp2, frozen_source, sha256
from act17_data import library, read
from act17_v7 import ROOT


DIAG_SCHEMA='ugrp.act18.c2c_prereg.v1'


def diag_holdout(prereg_path, protocol):
    """Fail-closed HO4 admission from a committed diag prereg.

    Only the seeds written in the prereg are admitted, and they must not touch
    TRAIN4, VAL8 or FINAL40. This never opens any promotion gate.
    """
    value=read(prereg_path)
    if value.get('schema')!=DIAG_SCHEMA:
        raise ValueError('registered C2c diag prereg schema required')
    holdout=value.get('holdout')
    if not isinstance(holdout,dict):
        raise ValueError('diag prereg holdout block required')
    name=holdout.get('name');seeds=holdout.get('seeds')
    if not isinstance(name,str) or not name or not isinstance(seeds,list) or not seeds:
        raise ValueError('diag holdout name and seeds required')
    if any(type(seed) is not int for seed in seeds) or len(set(seeds))!=len(seeds):
        raise ValueError('unique integer diag seeds required')
    locked=set(protocol['train4_seeds'])|set(protocol['validation8_seeds'])|set(protocol['final_seeds'])
    overlap=sorted(set(seeds)&locked)
    if overlap:
        raise ValueError(f'diag seeds overlap locked gate seeds: {overlap}')
    expected=holdout.get('expected_worlds')
    if expected is not None and expected!=len(seeds):
        raise ValueError('diag seed count differs from prereg')
    return dict(name=name,seeds=seeds,path=str(prereg_path),sha256=sha256(prereg_path))


def allowed_seeds(protocol, stage, selection, checkpoint_sha, diag=None):
    if stage=='diag':
        if diag is None:
            raise ValueError('diag prereg required for the diag stage')
        return set(diag['seeds'])
    if stage=='train':
        return set(protocol['train4_seeds'])
    if stage=='validation':
        if (selection.get('TRAIN_n')!=4 or selection.get('TRAIN_N')!=4
                or selection.get('checkpoint_sha256')!=checkpoint_sha
                or not selection.get('TRAIN_raw_recount_verified')):
            raise ValueError('raw-recounted TRAIN4 fit required before VAL8')
        receipt=selection.get('TRAIN_recount',{})
        if not receipt.get('path') or sha256(receipt['path'])!=receipt.get('sha256'):
            raise ValueError('actual TRAIN recount receipt required')
        evidence=read(Path(receipt['path']))
        if (evidence.get('n')!=4 or evidence.get('N')!=4 or evidence.get('stage')!='train'
                or evidence.get('checkpoint_sha256')!=checkpoint_sha):
            raise ValueError('TRAIN recount result differs')
        return set(protocol['validation8_seeds'])
    if (selection.get('VAL_n')!=8 or selection.get('VAL_N')!=8
            or not selection.get('VAL_raw_recount_verified')
            or not selection.get('frozen_before_final')
            or selection.get('checkpoint_sha256')!=checkpoint_sha):
        raise ValueError('raw-recounted8/8 frozen selection required before FINAL40')
    receipt=selection.get('VAL_recount',{})
    if not receipt.get('path') or sha256(receipt['path'])!=receipt.get('sha256'):
        raise ValueError('actual VAL recount receipt required')
    evidence=read(Path(receipt['path']))
    if (evidence.get('n')!=8 or evidence.get('N')!=8 or evidence.get('stage')!='validation'
            or evidence.get('checkpoint_sha256')!=checkpoint_sha):
        raise ValueError('VAL recount result differs')
    return set(protocol['final_seeds'])


DONE_PROB_ENV='UGRP_ACT18_DONE_PROB'


def done_prob_log_path():
    value=os.environ.get(DONE_PROB_ENV)
    return Path(value) if value else None


def done_prob_row(observation,world,probabilities):
    """Default-off evaluation record of the decoded done probability per chunk step.

    The last decoded action dimension is the balanced-BCE completion probability
    (decode_action thresholds it at .65). Recording hook only: adds no input and
    does not change the executed command, temporal ensemble or scoring.
    """
    values=[float(x) for x in probabilities]
    if not values or not all(0.0<=x<=1.0 for x in values):
        raise ValueError('decoded done probabilities must be a nonempty list within [0,1]')
    return dict(schema='ugrp.act18.done_prob_row.v1',
        world=int(world),sample_id=observation.get('sample_id'),t=observation.get('t'),
        skill=observation.get('skill'),robot_id=observation.get('robot_id'),
        chunk=len(values),done_probs=[round(x,6) for x in values])


CLOCK_STATS=dict(instances=0,resets=0,max_pwm_elapsed_s=0.)


class DeadbandIssuedClock:
    """v7 own-issued clock: ignore servo moves inside a ±DEADBAND PWM band.

    ``DEADBAND=2`` keeps the clock running through ±1/±2 jitter and resets only
    when one servo moves by at least 3 PWM from the previously observed issued
    value. That is the same threshold as C2b S2's ``|Δ|>=3`` clock; the flag
    names the tolerated band rather than the reset threshold. Only own issued
    PWM history is read (no measured joint or simulator state).
    """
    DEADBAND=0

    def __init__(self):
        CLOCK_STATS['instances']+=1
        self.skill=None;self.started=None;self.changed=None;self.pwm=None

    def observe(self,instruction,now,issued_pwm):
        now=float(now)
        if instruction!=self.skill or self.started is None:
            self.skill=instruction;self.started=now
        if self.changed is None:
            self.changed=now
        elif any(abs(int(issued_pwm[str(s)])-int(self.pwm[str(s)]))>self.DEADBAND
                 for s in (1,3,4,5,6)):
            self.changed=now;CLOCK_STATS['resets']+=1
        self.pwm={str(s):int(issued_pwm[str(s)]) for s in (1,3,4,5,6)}
        skill_elapsed=now-self.started;pwm_elapsed=now-self.changed
        CLOCK_STATS['max_pwm_elapsed_s']=max(CLOCK_STATS['max_pwm_elapsed_s'],pwm_elapsed)
        return {'skill_elapsed_s':skill_elapsed,'pwm_elapsed_s':pwm_elapsed}


def c2c_observation_clock(observation,clock):
    """Replace only pwm_elapsed_s with the v7 own-issued clock value.

    The physics owner builds its own observation in a separate process, so the
    evaluator re-applies the same clock to the received allowed observation
    before the policy sees it. ``skill_elapsed_s`` and every other field are
    left untouched.
    """
    value=dict(observation)
    value['pwm_elapsed_s']=clock.observe(
        (observation['skill'],observation['object_kind'],observation['role'],
         observation['destination_zone']),
        observation['t'],observation['issued'][-1]['pwm'])['pwm_elapsed_s']
    return value


def install_issued_clock(contract, deadband):
    """Process-local monkeypatch of the contract clock; returns the original."""
    original=contract.IssuedClock
    if deadband:
        if deadband not in (2,):
            raise ValueError('registered deadband 2 required')
        DeadbandIssuedClock.DEADBAND=deadband
        contract.IssuedClock=DeadbandIssuedClock
    return original


def clock_receipt(deadband):
    return dict(mode='deadband' if deadband else 'v6',deadband=deadband,
        flag=f'--issued-clock-deadband {deadband}',reset_threshold=deadband+1,
        resets=CLOCK_STATS['resets'] if deadband else None,
        max_pwm_elapsed_s=(round(CLOCK_STATS['max_pwm_elapsed_s'],6) if deadband else None),
        scope='own issued PWM history only; no measured joint or simulator state')


# carry-cand-2 (A-c2, H-A1): one-shot own-history normalisation at release entry,
# default off. Tournament A prereg draft lives on dsh/act18-carry-cand-1:
# experiments/2026-10-17-act18/CARRY_TOURNAMENT_A_PREREG_DRAFT.json.
HISTORY_RESET_STATS=dict(entries=0,policy_ticks_changed=0)


def reset_history(observation,template):
    """Policy-visible issued history with entries up to the release-entry command
    replaced by that command (timestamps kept). Reads only ``observation['issued']``
    and the template, which itself came from the same robot's issued history."""
    cutoff=template['t']
    issued=[]
    for item in observation['issued']:
        if item['t']<=cutoff+1e-9:
            issued.append(dict(t=item['t'],wheels=list(template['wheels']),
                               duration_s=list(template['duration_s']),pwm=dict(template['pwm'])))
        else:
            issued.append(item)
    value=dict(observation);value['issued']=issued
    return value


class ReleaseHistoryReset:
    """Fill the 16-command history once, on the release-entry tick, with the current
    own command repeated (a stationary history). Later commands append normally, so
    the synthetic part leaves the window after 16 ticks. Own issued history only."""
    def __init__(self):
        self.template=None
    def apply(self,observation):
        if observation['skill']!='release':
            self.template=None
            return observation
        if self.template is None or observation['t']<self.template['entry_t']:
            last=observation['issued'][-1]
            self.template=dict(t=last['t'],wheels=list(last['wheels']),duration_s=list(last['duration_s']),
                               pwm=dict(last['pwm']),entry_t=observation['t'])
            HISTORY_RESET_STATS['entries']+=1
        value=reset_history(observation,self.template)
        if value['issued']!=observation['issued']:
            HISTORY_RESET_STATS['policy_ticks_changed']+=1
        return value


def candidate_executor(base,*,release_history_reset=False):
    """Deployed te1 executor (n_action_steps 1, coeff .01) plus the default-off reset."""
    class Executor(base):
        def __init__(self,predict):
            # Public ACT temporal ensemble; no additional motion guard/fallback.
            super().__init__(predict,n_action_steps=1,temporal_ensemble_coeff=.01)
            self.history_reset=ReleaseHistoryReset() if release_history_reset else None
        def step(self,observation,jpegs,*,interrupt=False):
            if self.history_reset is not None:
                observation=self.history_reset.apply(observation)
            return super().step(observation,jpegs,interrupt=interrupt)
    return Executor


def history_reset_receipt(enabled):
    return dict(candidate='A-c2' if enabled else None,enabled=bool(enabled),
        flag=f'--release-history-reset {"on" if enabled else "off"}',
        rule='release-entry tick: 16 issued contents := own last issued command (timestamps kept), once',
        entries=HISTORY_RESET_STATS['entries'] if enabled else None,
        policy_ticks_changed=HISTORY_RESET_STATS['policy_ticks_changed'] if enabled else None,
        logging='actor-inputs.jsonl keeps the owner observation; the policy-visible history is a deterministic function of it',
        scope='own issued command history only; no measured joint, simulator or teacher state')


def post_lift_max_pe(out):
    """Evaluation-only receipt from the recorded actor inputs and owner truth."""
    inputs=out/'actor-inputs.jsonl';truth=out/'owner/evaluation-only.jsonl'
    if not inputs.exists() or not truth.exists():return None
    by_world=defaultdict(list)
    for line in inputs.read_text().splitlines():
        row=json.loads(line);obs=row['observation']
        by_world[row['world']].append((float(obs['t']),float(obs['pwm_elapsed_s'])))
    stable=defaultdict(list)
    for line in truth.read_text().splitlines():
        event=json.loads(line)
        if 'min_z' not in event:continue
        good=(event['min_z']>=.012 and event['tilt_deg']<=10.
              and min(event['finger_forces'])>=.5)
        stable[event['world']].append((float(event['t']),good))
    result={}
    for world,rows in by_world.items():
        onset=None;previous_t=None;previous_good=False;stable_s=0.
        for t,good in stable[world]:
            dt=0. if previous_t is None else t-previous_t
            if not 0<=dt<=.15+1e-8:
                stable_s=0.;previous_good=False
            stable_s=stable_s+dt if good and previous_good else 0.
            if good and stable_s>=3.-1e-8:
                onset=t-3.;break
            previous_t,previous_good=t,good
        if onset is not None:
            values=[pe for t,pe in rows if t>=onset-1e-8]
            result[str(world)]=round(max(values),6) if values else None
    return result or None


def main():
    p=argparse.ArgumentParser(description=__doc__,add_help=False)
    p.add_argument('--act18-reference-v1',action='store_true')
    p.add_argument('--stage',choices=['train','validation','final','diag'],required=True)
    p.add_argument('--diag-prereg',type=Path)
    p.add_argument('--issued-clock-deadband',type=int,choices=[0,2],default=0)
    # carry-cand-2: default off. on = fill the 16 issued history once at release entry.
    p.add_argument('--release-history-reset',choices=['off','on'],default='off')
    p.add_argument('--baseline-act17',action='store_true')
    # User requirement: last10 SIM seconds at10Hz; recording only, no policy field.
    p.add_argument('--failure-camera-window-s',type=float,default=10.)
    p.add_argument('--fit-selection',type=Path)
    # Default OFF: record decoded done probabilities per tick for diagnosis only.
    p.add_argument('--record-done-prob',type=Path)
    # act18-doneh (Lead-approved B4): own-command-history done module. The external
    # issued_done format and scoring contract are unchanged; the module only decides
    # whether the current tick is emitted as done.
    p.add_argument('--done-head',type=Path)
    p.add_argument('--done-head-threshold',type=float,default=.65)
    p.add_argument('--done-head-log',type=Path)
    # act18-loop (Lead-approved B5): frozen closed-loop transition overlay that only
    # post-processes the student's own issued base commands (own command history
    # only; no teacher/GT/top-camera input). Params are pre-registered constants.
    p.add_argument('--loop-overlay',action='store_true')
    p.add_argument('--loop-overlay-log',type=Path)
    a,args=p.parse_known_args()
    if not a.act18_reference_v1 or a.failure_camera_window_s!=10.:
        raise ValueError('explicit reference toggle and user10SIMs camera window required')
    history_reset=a.release_history_reset=='on'
    if history_reset and (a.done_head is not None or a.loop_overlay):
        raise ValueError('--release-history-reset is registered with the plain te1 executor only')
    if a.done_head is not None and a.done_head_threshold!=.65:
        raise ValueError('frozen done-head threshold .65 required')
    done_log_path=done_prob_log_path() if a.record_done_prob is None else a.record_done_prob
    if done_log_path is not None:
        if os.environ.get(DONE_PROB_ENV) not in (None,str(done_log_path)):
            raise ValueError('conflicting done-prob recording paths')
        os.environ[DONE_PROB_ENV]=str(done_log_path)
    require_gcp2(training=True);source=frozen_source(ROOT);library()
    value=lambda flag:Path(args[args.index(flag)+1])
    protocol_path=value('--protocol');protocol=read(protocol_path)
    checkpoint=value('--checkpoint');digest=sha256(checkpoint/'model.safetensors')
    meta=read(checkpoint/'adapter.json')
    selection=read(a.fit_selection) if a.fit_selection else {}
    diag=None
    if a.stage=='diag':
        if a.diag_prereg is None:
            raise ValueError('diag stage requires --diag-prereg')
        diag=diag_holdout(a.diag_prereg,protocol)
    elif a.diag_prereg is not None:
        raise ValueError('--diag-prereg is only valid with --stage diag')
    allowed=allowed_seeds(protocol,a.stage,selection,digest,diag)
    if a.baseline_act17 and a.stage!='train':
        raise ValueError('old models may only diagnose TRAIN, not enter new comparison')
    gate_path=Path(os.environ['UGRP_ACT16W_NATIVE_GATE']);gate=read(gate_path)
    if not gate.get('passed') or gate.get('training_rgb') is not False or gate.get('n')!=40 or gate.get('N')!=40:
        raise ValueError('original successful v7 camera-off40 gate required')
    for receipt in gate['raw_results']:
        if sha256(receipt['path'])!=receipt['sha256']:
            raise ValueError('teacher gate raw hash mismatch')
    import act16w_runtime,act16w_input,act16w_eval_rpc
    from harness import grasp_act_contract as contract
    from harness import grasp_act_policy as pm
    from harness import grasp_act_rollout as rm
    from act17_policy import Actor as OldActor
    from act18_policy import Actor
    originals=(act16w_runtime.evaluation_seed_guard,act16w_input.Act16wActor,
        act16w_eval_rpc.EvaluationClient,pm.ChunkExecutor,rm.SoloSequence,contract.CHUNK,
        contract.IssuedClock)
    CLOCK_STATS.update(instances=0,resets=0,max_pwm_elapsed_s=0.)
    HISTORY_RESET_STATS.update(entries=0,policy_ticks_changed=0)
    install_issued_clock(contract,a.issued_clock_deadband)
    actor_class=OldActor if a.baseline_act17 else Actor
    chunk=8 if a.baseline_act17 else meta['chunk']
    contract.CHUNK=chunk
    done_log=dict(handle=(open(done_log_path,'x') if done_log_path is not None else None),world=None)
    done_head=None;done_head_log=dict(handle=None);executor_counter=[0]
    loop_log=dict(handle=(open(a.loop_overlay_log,'x') if a.loop_overlay_log is not None else None))
    if a.done_head is not None:
        from act18_done_head import DoneHead,done_fires,apply_done_override
        done_head=DoneHead.load(a.done_head,device='cpu')
        if a.done_head_log is not None:
            done_head_log['handle']=open(a.done_head_log,'x')
    sequences=[];buffers=defaultdict(lambda:deque(maxlen=round(10./contract.PERIOD_S)+1))
    inference=dict(attempts=0,completed=0,wall_s=0.,first30=dict(attempts=0,completed=0,wall_s=0.))
    class TrackedActor(actor_class):
        def predict(self,*args):
            started=time.perf_counter()
            first30=args[0]['skill_elapsed_s']<=30 and args[0]['skill']=='grasp'
            inference['attempts']+=1
            if first30:inference['first30']['attempts']+=1
            try:
                result=super().predict(*args)
                inference['completed']+=1
                if first30:inference['first30']['completed']+=1
                if done_log['handle'] is not None:
                    if done_log['world'] is None:
                        raise ValueError('done-prob recorder lost world context')
                    row=done_prob_row(args[0],done_log['world'],[action[-1] for action in result])
                    done_log['handle'].write(json.dumps(row)+'\n');done_log['handle'].flush()
                return result
            finally:
                elapsed=time.perf_counter()-started;inference['wall_s']+=elapsed
                if first30:inference['first30']['wall_s']+=elapsed
    from act18_loop_overlay import LoopOverlay, overlay_receipt
    Executor=candidate_executor(originals[3],release_history_reset=history_reset)
    class DoneHeadExecutor(Executor):
        def __init__(self,predict):
            super().__init__(predict)
            self.world=executor_counter[0];executor_counter[0]+=1
            self.last_t=None
            self.overlay=LoopOverlay() if a.loop_overlay else None
        def step(self,observation,jpegs,*,interrupt=False):
            if self.last_t is not None and observation['t']<=self.last_t:
                done_head.reset()
                if self.overlay is not None: self.overlay.reset(observation['skill'])
            self.last_t=observation['t']
            value,done=super().step(observation,jpegs,interrupt=interrupt)
            if interrupt or done:
                return value,done
            if self.overlay is not None:
                value,event=self.overlay.step(observation['skill'],value)
                if event is not None and loop_log['handle'] is not None:
                    loop_log['handle'].write(json.dumps(dict(t=value['t'],skill=observation['skill'],**event))+'\n')
                    loop_log['handle'].flush()
            probability=done_head.update(value,observation['skill'])
            fired=done_fires(probability,a.done_head_threshold)
            if fired:
                value=apply_done_override(value,True)
            if done_head_log['handle'] is not None:
                done_head_log['handle'].write(json.dumps(dict(world=self.world,t=observation['t'],
                    skill=observation['skill'],done_prob=round(probability,6),fired=fired,
                    threshold=a.done_head_threshold))+'\n');done_head_log['handle'].flush()
            return value,done or fired
    class LoopExecutor(Executor):
        def __init__(self,predict):
            super().__init__(predict)
            self.last_t=None
            self.overlay=LoopOverlay()
        def step(self,observation,jpegs,*,interrupt=False):
            if self.last_t is not None and observation['t']<=self.last_t:
                self.overlay.reset(observation['skill'])
            self.last_t=observation['t']
            value,done=super().step(observation,jpegs,interrupt=interrupt)
            if interrupt or done:
                return value,done
            value,event=self.overlay.step(observation['skill'],value)
            if event is not None and loop_log['handle'] is not None:
                loop_log['handle'].write(json.dumps(dict(t=value['t'],skill=observation['skill'],**event))+'\n')
                loop_log['handle'].flush()
            return value,done
    class Sequence(originals[4]):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs);sequences.append(self)

    def guard(provenance,seeds,**_):
        if not seeds or len(set(seeds))!=len(seeds) or not set(seeds)<=allowed:
            raise ValueError('exact registered stage seeds required')
        if a.baseline_act17:
            if (provenance.get('cohort')!='act17-v7-native' or provenance.get('step')!=10000
                    or provenance.get('candidate') not in ('F','S') or not provenance.get('training_complete')):
                raise ValueError('complete old F/S model required')
        elif (provenance.get('cohort')!='act18-v7-reference' or not provenance.get('training_complete')
                or provenance.get('protocol_sha256')!=sha256(protocol_path)):
            raise ValueError('complete registered100k reference model required')
        elif provenance.get('step')!=100000:
            from act18_policy import registered_pilot_checkpoint
            continuation=(provenance.get('candidate')=='act18-co' and provenance.get('resume')
                          and isinstance(provenance.get('step'),int) and 20000<=provenance['step']<=100000)
            if not continuation and not registered_pilot_checkpoint(provenance,sha256(protocol_path)):
                raise ValueError('complete registered100k reference model required')
    clocks={}
    class Client(originals[2]):
        def reset(self,plans,indices=None):
            if self.training or self.audit_state or self.proc is not None or len(plans)!=self.nworld or indices not in (None,list(range(self.nworld))):
                raise ValueError('fresh own-only evaluation required')
            clocks.clear()
            path=self.out/'initial-plans.json';path.write_text(json.dumps(dict(episodes=plans),indent=2)+'\n')
            argv=[self.python,'-u',str(ROOT/'scripts/act17_v7.py'),'--enabled','--action','launch','--',
                '--enabled','--mode','eval-owner','--native-gate',str(gate_path),'--',
                '--enabled','--plans',str(path),'--out',str(self.out/'owner')]
            for key,v in self.options.items():
                argv+=['--'+key.replace('_','-'),str(v)]
            self.stderr=(self.out/'owner.stderr.log').open('x')
            self.proc=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.stderr,text=True,bufsize=1)
            result=self.receive()
            if self.on_reset is not None:
                self.on_reset(tuple(range(self.nworld)))
            return result
        def read_actor(self,index):
            obs,jpgs=super().read_actor(index)
            done_log['world']=index
            if a.issued_clock_deadband:
                # The owner subprocess builds observations; re-apply the v7
                # own-issued clock here so only the policy's pwm_elapsed_s changes.
                clock=clocks.get(index)
                if clock is None:
                    clock=DeadbandIssuedClock();clocks[index]=clock
                obs=c2c_observation_clock(obs,clock)
            buffer=buffers[index]
            if not buffer or obs['t']!=buffer[-1][0]['t']:
                buffer.append((obs,jpgs[-1]))
            return obs,jpgs
    act16w_runtime.evaluation_seed_guard=guard
    act16w_input.Act16wActor=TrackedActor
    act16w_eval_rpc.EvaluationClient=Client
    pm.ChunkExecutor=(DoneHeadExecutor if done_head is not None else (LoopExecutor if a.loop_overlay else Executor));rm.SoloSequence=Sequence
    target=ROOT/'scripts/evaluate_act16w.py';sys.argv=[str(target),*args]
    try:
        runpy.run_path(str(target),run_name='__main__')
    finally:
        if loop_log['handle'] is not None:
            loop_log['handle'].close();loop_log['handle']=None
        if done_head_log['handle'] is not None:
            done_head_log['handle'].close();done_head_log['handle']=None
        if done_log['handle'] is not None:
            done_log['handle'].close();done_log['handle']=None
        (act16w_runtime.evaluation_seed_guard,act16w_input.Act16wActor,
         act16w_eval_rpc.EvaluationClient,pm.ChunkExecutor,rm.SoloSequence,contract.CHUNK,
         contract.IssuedClock)=originals
        out=value('--out')
        if out.exists():
            clock=clock_receipt(a.issued_clock_deadband)
            clock['post_lift_max_pe']=post_lift_max_pe(out)
            ring=[]
            for world,frames in buffers.items():
                folder=out/f'failure-camera-window/world-{world:03d}';folder.mkdir(parents=True,exist_ok=False)
                for index,(obs,jpeg) in enumerate(frames):
                    f=folder/f'{index:03d}.jpg';f.write_bytes(jpeg)
                    ring.append(dict(world=world,t=obs['t'],path=str(f),sha256=sha256(f),bytes=len(jpeg)))
            (out/'failure-camera-window.json').write_text(json.dumps(dict(period_SIM_s=.1,window_SIM_s=10.,
                control_path_unchanged=True,rows=ring,total_bytes=sum(r['bytes'] for r in ring)),indent=2)+'\n')
            path=out/'summary.json'
            if path.exists():
                report=read(path)
                report.update(cohort='act18-v7-reference',stage=a.stage,split=a.stage,
                    TRAIN_fit_diagnostic=a.stage=='train',gate_eligible=a.stage!='diag',
                    baseline_act17=a.baseline_act17,candidate=meta['provenance']['candidate'],
                    actual_ACT_inference=inference,chunk=chunk,n_action_steps=1,temporal_ensemble_coeff=.01,
                    LLM_calls=0,LLM_prompt_tokens=0,LLM_total_tokens=0,
                    static_map_use='none',handwritten_nearfield_fallback=False,policy_ground_truth_fields=0,
                    native_camera='own640x480 at10Hz; identical current_full_v1 transform',
                    issued_clock=clock,git_sha=source,
                    release_history_reset=history_reset_receipt(history_reset),
                    scope=('TRAIN fit only, not generalization' if a.stage=='train' else
                           'HO4 diagnostic holdout only; not a promotion gate; no pooling' if a.stage=='diag'
                           else 'held-out native ACT stage'))
                if diag is not None:
                    report['diag_prereg']=diag
                if report.get('student_scores'):
                    for row,seq in zip(report['student_scores'],sequences):
                        row.update(grasp_done_requested='grasp' in seq.done_times,release_done_requested='release' in seq.done_times,
                            issued_done_times=seq.done_times,candidate=meta['provenance']['candidate'])
                path.write_text(json.dumps(report,indent=2)+'\n')
            done_head_receipt=None
            if a.done_head is not None:
                done_meta=read(a.done_head/'metadata.json')
                done_head_receipt=dict(path=str(a.done_head),model_sha256=sha256(a.done_head/'done-head.pt'),
                    threshold=a.done_head_threshold,persistence=done_meta.get('persistence'),
                    feature_spec=done_meta.get('feature_spec'),history=done_meta.get('history'),
                    validation_auc=done_meta.get('validation_auc'),
                    scope='own-command-history done module combined with unchanged ACT action policy; not an ACT-learned done head')
            loop_receipt=None
            if a.loop_overlay:
                loop_receipt=overlay_receipt()
            (out/'act18-evaluator.json').write_text(json.dumps(dict(source_sha=source,stage=a.stage,
                git_sha=source,issued_clock=clock,diag_prereg=diag,loop_overlay=loop_receipt,
                release_history_reset=history_reset_receipt(history_reset),
                allowed_seeds=sorted(allowed),checkpoint_sha256=digest,native_gate_sha256=sha256(gate_path),
                failure_recording_only=True,recorded_bytes=sum(r['bytes'] for r in ring),
                done_head=done_head_receipt),indent=2)+'\n')


if __name__=='__main__':
    main()
