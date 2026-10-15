"""JSON client for the physics owner; deployment imports no reward or critic.

The client constructs allowed histories from own JPEGs and actually issued
commands. Only an explicit training client may deserialize the private lane.
"""
from __future__ import annotations
import base64
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace


class Client:
    def __init__(self, *, python, teacher_source, actor_source, out, compiled_reference,
                 compiled_geometry, nworld, training=False):
        self.python,self.teacher_source,self.actor_source=map(str,(python,teacher_source,actor_source))
        self.out=Path(out);self.out.mkdir(parents=True,exist_ok=False)
        self.reference,self.geometry=map(str,(compiled_reference,compiled_geometry))
        self.nworld,self.training=nworld,training
        self.proc=None;self.histories=[None]*nworld;self.inputs=[None]*nworld
        self.terminal=[True]*nworld;self.private=None
        self.generations=[0]*nworld;self.plans=[None]*nworld
        from harness import grasp_act_contract as c
        from harness.grasp_act_rollout import OwnHistory
        self.c,self.OwnHistory=c,OwnHistory

    def receive(self):
        line=self.proc.stdout.readline()
        if not line:raise RuntimeError('physics owner exited; inspect '+str(self.out/'owner.stderr.log'))
        result=json.loads(line)
        required={'frames','terminal'}
        optional={'initial'} | ({'training'} if self.training else set())
        if not required<=set(result) or set(result)-required-optional:
            raise ValueError('owner response whitelist mismatch')
        if self.training and 'training' not in result:
            raise ValueError('missing separate training lane')
        if len(result['frames'])!=self.nworld or len(result['terminal'])!=self.nworld:
            raise ValueError('wrong owner batch size')
        self.terminal=result['terminal']
        if self.training:self.private=result['training']
        return result

    def exchange(self,request):
        self.proc.stdin.write(json.dumps(request,allow_nan=False)+'\n');self.proc.stdin.flush()
        return self.receive()

    def refresh(self,result,indices):
        for i in indices:
            frame=result['frames'][i]
            if set(frame)!={'t','jpeg','sha256'}:raise ValueError('own frame whitelist mismatch')
            jpeg=base64.b64decode(frame['jpeg'],validate=True)
            import hashlib
            if hashlib.sha256(jpeg).hexdigest()!=frame['sha256']:raise ValueError('own RGB transport hash mismatch')
            obs,jpegs,rel=self.histories[i].observe(frame['t'],jpeg,skill='grasp',
                object_kind=self.plans[i]['kind'],role=self.plans[i]['role'])
            self.c.validate_observation(obs)
            self.inputs[i]=(obs,tuple(jpegs))

    def reset(self,plans,*,indices):
        if (len(plans)!=len(indices) or not indices or len(set(indices))!=len(indices)
                or any(type(i) is not int or not 0<=i<self.nworld for i in indices)):
            raise ValueError('valid unique reset indices required')
        if self.proc is None:
            if set(indices)!=set(range(self.nworld)):raise ValueError('first reset initializes all worlds')
            initial=self.out/'initial-plans.json';initial.write_text(json.dumps({'episodes':plans},indent=2)+'\n')
            self.stderr=(self.out/'owner.stderr.log').open('x')
            argv=[self.python,'-u',str(Path(__file__).with_name('rl_act_warp.py')),'--enabled',
                '--teacher-source',self.teacher_source,'--actor-source',self.actor_source,
                '--plans',str(initial),'--out',str(self.out/'owner'),
                '--compiled-reference',self.reference,'--compiled-geometry',self.geometry]
            if self.training:argv.append('--training')
            self.proc=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.stderr,
                                       text=True,bufsize=1)
            result=self.receive()
        else:
            result=self.exchange({'reset':plans,'indices':list(indices)})
        if 'initial' not in result:raise ValueError('reset must return own issued initialization')
        for i,plan in zip(indices,plans):
            self.generations[i]+=1;self.plans[i]=plan
            self.histories[i]=self.OwnHistory('r1',f'rl1b-{plan["seed"]}-{i}-{self.generations[i]}',result['initial'][i])
        self.refresh(result,indices)

    def step(self,actions):
        before=[not v for v in self.terminal]
        for i,active in enumerate(before):
            if active:self.histories[i].issue(actions[i]['command'])
        result=self.exchange({'actions':actions})
        self.refresh(result,[i for i,v in enumerate(before) if v])
        return list(self.terminal)

    def read_actor(self,i):
        return self.inputs[i]

    def actor_inputs(self):
        return tuple(SimpleNamespace(observation=obs,jpegs=jpegs) for obs,jpegs in self.inputs)

    def read_training(self,i):
        if not self.training:raise RuntimeError('no privileged lane during evaluation')
        from scripts.rl_act_reward import TrainingTruth
        row=self.private[i]
        return TrainingTruth(**row['truth']),tuple(row['critic'])

    def close(self,reason='prefix_cap'):
        if self.proc is None:return
        try:
            if self.proc.poll() is None:
                self.proc.stdin.write(json.dumps({'close':reason})+'\n');self.proc.stdin.flush()
                try:self.proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    self.proc.terminate()
                    try:self.proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait()
            if self.proc.returncode:raise RuntimeError('physics owner failed: '+str(self.proc.returncode))
        finally:
            self.proc.stdin.close();self.proc.stdout.close();self.stderr.close()
