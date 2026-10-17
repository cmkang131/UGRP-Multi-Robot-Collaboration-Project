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

sys.path.insert(0,str(Path(__file__).resolve().parent))
from act16w_runtime import require_gcp2,frozen_source,sha256
from act17_data import library,read
from act17_policy import Actor
from act17_v7 import ROOT


def main():
    p=argparse.ArgumentParser(description=__doc__,add_help=False)
    p.add_argument('--act17-v7',action='store_true')
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
    def guard(provenance,seeds,*,split,protocol,model_sha256,selection=None):
        if (provenance.get('cohort')!='act17-v7-native' or not provenance.get('training_complete')
                or provenance.get('step')!=protocol['training']['steps_round1']
                or provenance.get('protocol_sha256')!=sha256(protocol_path)):
            raise ValueError('completed registered v7 training provenance required')
        expected=protocol['validation8_seeds'] if split=='validation' else protocol['final_seeds']
        if not seeds or len(set(seeds))!=len(seeds) or not set(seeds)<=set(expected) or set(seeds)&set(protocol['train_seeds']):
            raise ValueError('v7 evaluation split/seed mismatch')
        if split=='final':
            s=selection or {}
            if (not s.get('frozen_before_final') or s.get('checkpoint_sha256')!=model_sha256
                    or s.get('validation_n')!=8 or s.get('validation_N')!=8
                    or sorted(s.get('completed_candidates',[]))!=['F','M','S']):
                raise ValueError('matched M/F/S complete and selected VAL8 pass required before fresh final40')
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
    act16w_input.Act16wActor=Actor
    act16w_eval_rpc.EvaluationClient=Client
    target=ROOT/'scripts/evaluate_act16w.py';sys.argv=[str(target),*args]
    try:
        runpy.run_path(str(target),run_name='__main__')
    finally:
        act16w_runtime.evaluation_seed_guard=original_guard
        act16w_input.Act16wActor=original_actor
        act16w_eval_rpc.EvaluationClient=original_client
        output=Path(args[args.index('--out')+1])
        if output.exists():
            (output/'act17-v7-evaluator.json').write_text(json.dumps(dict(source_sha=source,
                native_gate_sha256=sha256(gate_path),cohort='act17-v7-native',
                guard='registered v7 complete training; VAL8 before new final40',
                student_input_contract_unchanged=True,teacher_fallback=False),indent=2)+'\n')


if __name__=='__main__':main()
