"""Opt-in v7 model/RPC adapter to the frozen own-observation evaluator.

New seed/model guards replace the ACT16 protocol-specific guards explicitly.
The action loop, Score, ChunkExecutor and student observation whitelist stay
unchanged. No teacher action or private evaluator field reaches the student.
"""
import argparse
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parent))
from act16w_runtime import require_gcp2,frozen_source,sha256
from act17_data import library,read
from act17_policy import Actor
from act17_v7 import ROOT


def main():
    p=argparse.ArgumentParser(description=__doc__,add_help=False)
    p.add_argument('--act17-v7',action='store_true')
    p.add_argument('--model-assignments',type=Path,help='default-off independent candidate worlds in one qualified native batch')
    a,args=p.parse_known_args()
    if not a.act17_v7:raise ValueError('ACT17 v7 evaluation is default OFF')
    require_gcp2(training=True);source=frozen_source(ROOT);library()
    protocol_path=Path(args[args.index('--protocol')+1]);protocol=read(protocol_path)
    gate_path=Path(os.environ['UGRP_ACT16W_NATIVE_GATE']);gate=read(gate_path)
    if gate.get('cohort')!='act17-v7-native' or not gate.get('passed') or gate.get('training_rgb') is not False:
        raise ValueError('new v7 camera-off gate required')
    import act16w_runtime
    import act16w_input
    import act16w_eval_rpc
    original_guard=act16w_runtime.evaluation_seed_guard
    original_actor=act16w_input.Act16wActor
    original_client=act16w_eval_rpc.EvaluationClient
    from harness import grasp_act_policy as policy_module
    from harness import grasp_act_rollout as rollout_module
    original_executor,original_sequence=policy_module.ChunkExecutor,rollout_module.SoloSequence
    sequence_instances=[];actors={};assignment=None;model_info={}
    if a.model_assignments:
        from act17_world_assignment import validate_assignment
        spec=read(a.model_assignments);assignment=spec['world_candidates']
        plans=read(Path(args[args.index('--plans')+1]))['episodes'];validate_assignment(plans,assignment)
        for name in sorted(set(assignment)):
            folder=Path(spec['checkpoints'][name]['path']);meta=read(folder/'adapter.json');digest=sha256(folder/'model.safetensors')
            if digest!=spec['checkpoints'][name]['sha256'] or meta['provenance'].get('candidate')!=name:raise ValueError('candidate model assignment differs')
            model_info[name]=dict(path=str(folder),sha256=digest,meta=meta)
    inference=dict(attempts=0,completed=0,wall_s=0.,first_observation_t=None,
        first30=dict(attempts=0,completed=0,wall_s=0.))
    class TrackedActor(Actor):
        @classmethod
        def load(cls,root,*,device='cpu'):
            value=super().load(root,device=device);value.candidate_name=read(Path(root)/'adapter.json')['provenance']['candidate'];return value
        def predict(self,observation,jpegs):
            started=time.perf_counter();inference['attempts']+=1
            if inference['first_observation_t'] is None:inference['first_observation_t']=observation['t']
            first30=observation['t']-inference['first_observation_t']<=30+1e-8
            if first30:inference['first30']['attempts']+=1
            try:
                result=super().predict(observation,jpegs);inference['completed']+=1
                if first30:inference['first30']['completed']+=1
                return result
            finally:
                elapsed=time.perf_counter()-started;inference['wall_s']+=elapsed
                if first30:inference['first30']['wall_s']+=elapsed
    def single_guard(provenance,seeds,*,split,protocol,model_sha256,selection=None):
        if (provenance.get('cohort')!='act17-v7-native' or provenance.get('contact_profile')!='warp_native_contact_v1'
                or provenance.get('synthetic_only') or not provenance.get('training_complete')
                or provenance.get('step')!=protocol['training']['steps_round1']
                or provenance.get('protocol_sha256')!=sha256(protocol_path)):
            raise ValueError('completed registered v7 training provenance required')
        expected=protocol['validation8_seeds'] if split=='validation' else protocol['final_seeds']
        if not seeds or len(set(seeds))!=len(seeds) or not set(seeds)<=set(expected) or set(seeds)&set(protocol['train_seeds']):
            raise ValueError('v7 evaluation split/seed mismatch')
        if split=='final':
            s=selection or {}
            # Operator interpretation of user "VAL8 ... FINAL40 after pass":
            # every one of the requested8 task cases passes. This is a finite
            # development gate, not the teacher95% rule or a population claim.
            if (not s.get('frozen_before_final') or s.get('checkpoint_sha256')!=model_sha256
                    or s.get('validation_n')!=8 or s.get('validation_N')!=8
                    or sorted(s.get('completed_candidates',[]))!=['F','M','S']):
                raise ValueError('matched M/F/S complete and selected VAL8 pass required before fresh final40')
            from act17_selection import validate_final_selection
            validate_final_selection(s,protocol,model_sha256)
    def guard(provenance,seeds,*,split,protocol,model_sha256,selection=None):
        if assignment is None:return single_guard(provenance,seeds,split=split,protocol=protocol,model_sha256=model_sha256,selection=selection)
        if seeds!=[p['seed'] for p in plans]:raise ValueError('expanded physical plans differ from assignment')
        if model_sha256 not in [v['sha256'] for v in model_info.values()]:raise ValueError('bootstrap model is not assigned')
        for name,info in model_info.items():
            selected=[seed for seed,c in zip(seeds,assignment) if c==name]
            single_guard(info['meta']['provenance'],selected,split=split,protocol=protocol,model_sha256=info['sha256'],selection=selection)
    class CompositeActor:
        @classmethod
        def load(cls,_root,*,device='cpu'):
            for name,info in model_info.items():actors[name]=TrackedActor.load(info['path'],device=device)
            return cls()
        def predict(self,*_):raise RuntimeError('candidate must use its own per-world frozen executor')
    class TrackedSequence(original_sequence):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs);sequence_instances.append(self)
    class Client(original_client):
        def reset(self,plans,indices=None):
            if self.training or self.audit_state or self.proc is not None or len(plans)!=self.nworld or indices not in (None,list(range(self.nworld))):
                raise ValueError('fresh own-only v7 evaluation owner required')
            path=self.out/'initial-plans.json';path.write_text(json.dumps(dict(episodes=plans),indent=2)+'\n')
            argv=[self.python,'-u',str(ROOT/'scripts/act17_v7.py'),'--enabled','--action','launch','--',
                '--enabled','--mode','eval-owner','--native-gate',str(gate_path),'--',
                '--enabled','--plans',str(path),'--out',str(self.out/'owner')]
            for key,value in self.options.items():argv+=['--'+key.replace('_','-'),str(value)]
            self.stderr=(self.out/'owner.stderr.log').open('x')
            self.proc=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.stderr,text=True,bufsize=1)
            result=self.receive()
            if self.on_reset is not None:self.on_reset(tuple(range(self.nworld)))
            return result
    act16w_runtime.evaluation_seed_guard=guard
    act16w_input.Act16wActor=TrackedActor if assignment is None else CompositeActor
    act16w_eval_rpc.EvaluationClient=Client
    rollout_module.SoloSequence=TrackedSequence
    if assignment is not None:
        from act17_world_assignment import executor_factory
        policy_module.ChunkExecutor=executor_factory(original_executor,actors,assignment)
    target=ROOT/'scripts/evaluate_act16w.py';sys.argv=[str(target),*args]
    try:
        runpy.run_path(str(target),run_name='__main__')
    finally:
        act16w_runtime.evaluation_seed_guard=original_guard
        act16w_input.Act16wActor=original_actor
        act16w_eval_rpc.EvaluationClient=original_client
        policy_module.ChunkExecutor=original_executor;rollout_module.SoloSequence=original_sequence
        output=Path(args[args.index('--out')+1])
        if output.exists():
            checkpoint=Path(args[args.index('--checkpoint')+1]);meta=read(checkpoint/'adapter.json')
            summary=output/'summary.json'
            if summary.exists():
                value=read(summary)
                value['legacy_native_camera_template']=value.pop('native_camera',None)
                value.update(cohort='act17-v7-native',native_camera='own640x480/10Hz; '+meta['image_mode'],
                    effective_model_image_hw=meta['model_image_hw'],effective_source_image_hw=meta['image_hw'],
                    actual_ACT_inference=inference,LLM_calls=0,
                    scope='ACT17 v7 own-only native evaluation; private truth scored after all actions')
                rows=value.get('student_scores',[])
                if rows and len(rows)!=len(sequence_instances):raise ValueError('per-world sequence reporting differs')
                for i,row in enumerate(rows):
                    row.update(candidate=assignment[i] if assignment is not None else meta['provenance']['candidate'],
                        grasp_done_requested='grasp' in sequence_instances[i].done_times,
                        release_done_requested='release' in sequence_instances[i].done_times,
                        issued_done_times=sequence_instances[i].done_times)
                if assignment is not None:
                    value.update(checkpoint_sha256=None,world_candidates=assignment,
                        native_camera='own640x480/10Hz, per-world serialized image mode',
                        assigned_models={k:dict(path=v['path'],sha256=v['sha256'],image_mode=v['meta']['image_mode']) for k,v in model_info.items()},
                        effective_model_image_hw={k:v['meta']['model_image_hw'] for k,v in model_info.items()},
                        effective_source_image_hw={k:v['meta']['image_hw'] for k,v in model_info.items()})
                summary.write_text(json.dumps(value,indent=2)+'\n')
            (output/'act17-v7-evaluator.json').write_text(json.dumps(dict(source_sha=source,
                native_gate_sha256=sha256(gate_path),cohort='act17-v7-native',
                guard='registered v7 complete training; VAL8 before new final40',
                student_input_contract_unchanged=True,teacher_fallback=False),indent=2)+'\n')


if __name__=='__main__':main()
