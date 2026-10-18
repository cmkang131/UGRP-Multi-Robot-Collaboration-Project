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


def allowed_seeds(protocol, stage, selection, checkpoint_sha):
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


def main():
    p=argparse.ArgumentParser(description=__doc__,add_help=False)
    p.add_argument('--act18-reference-v1',action='store_true')
    p.add_argument('--stage',choices=['train','validation','final'],required=True)
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
    allowed=allowed_seeds(protocol,a.stage,selection,digest)
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
        act16w_eval_rpc.EvaluationClient,pm.ChunkExecutor,rm.SoloSequence,contract.CHUNK)
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
    class Executor(originals[3]):
        def __init__(self,predict):
            # Public ACT temporal ensemble; no additional motion guard/fallback.
            super().__init__(predict,n_action_steps=1,temporal_ensemble_coeff=.01)
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
                value=self.overlay.step(observation['skill'],value)
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
            return self.overlay.step(observation['skill'],value),done
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
    class Client(originals[2]):
        def reset(self,plans,indices=None):
            if self.training or self.audit_state or self.proc is not None or len(plans)!=self.nworld or indices not in (None,list(range(self.nworld))):
                raise ValueError('fresh own-only evaluation required')
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
         act16w_eval_rpc.EvaluationClient,pm.ChunkExecutor,rm.SoloSequence,contract.CHUNK)=originals
        out=value('--out')
        if out.exists():
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
                report.update(cohort='act18-v7-reference',split=a.stage,TRAIN_fit_diagnostic=a.stage=='train',
                    baseline_act17=a.baseline_act17,candidate=meta['provenance']['candidate'],
                    actual_ACT_inference=inference,chunk=chunk,n_action_steps=1,temporal_ensemble_coeff=.01,
                    LLM_calls=0,LLM_prompt_tokens=0,LLM_total_tokens=0,
                    static_map_use='none',handwritten_nearfield_fallback=False,policy_ground_truth_fields=0,
                    native_camera='own640x480 at10Hz; identical current_full_v1 transform',
                    scope='TRAIN fit only, not generalization' if a.stage=='train' else 'held-out native ACT stage')
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
                loop_overlay=loop_receipt,
                allowed_seeds=sorted(allowed),checkpoint_sha256=digest,native_gate_sha256=sha256(gate_path),
                failure_recording_only=True,recorded_bytes=sum(r['bytes'] for r in ring),
                done_head=done_head_receipt),indent=2)+'\n')


if __name__=='__main__':
    main()
