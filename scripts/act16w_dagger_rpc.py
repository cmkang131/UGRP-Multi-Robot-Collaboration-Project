"""Keep privileged teacher labels out of the inherited own-RGB actor client."""
import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,'/home/ugrp/ugrp-sim/src/0362037280c6cbc4677f70366db43b9892b23690/scripts')
from warp_act_rpc import Client


class DaggerClient(Client):
    def reset(self, plans, indices=None):
        if not self.training or self.proc is not None or indices is not None:
            raise ValueError('private DAgger client: one fresh whole episode batch only')
        p=self.out/'initial-plans.json';p.write_text(json.dumps(dict(episodes=plans),indent=2)+'\n')
        argv=[self.python,'-u',str(Path(__file__).with_name('act16w_dagger_owner.py')),'--enabled','--training','--plans',str(p),'--out',str(self.out/'owner')]
        if os.environ.get('UGRP_ACT16W_NATIVE_GATE'):
            argv=[self.python,'-u',str(Path(__file__).with_name('act16w_native_run.py')),
                  '--enabled','--mode','dagger-owner','--native-gate',os.environ['UGRP_ACT16W_NATIVE_GATE'],
                  '--',*argv[3:]]
        for k,v in self.options.items():argv+=['--'+k.replace('_','-'),str(v)]
        self.stderr=(self.out/'owner.stderr.log').open('x')
        self.proc=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.stderr,text=True,bufsize=1)
        result=self.receive()
        if self.on_reset is not None:self.on_reset(tuple(range(self.nworld)))
        return result

    def labels_for_training_only(self, selected):
        self.proc.stdin.write(json.dumps(dict(oracle_student_selected_commands=selected),allow_nan=False)+'\n');self.proc.stdin.flush()
        line=self.proc.stdout.readline()
        if not line:raise RuntimeError('private oracle exited; inspect owner.stderr.log')
        response=json.loads(line)
        if set(response)!={'oracle_labels','audit'} or len(response['oracle_labels'])!=self.nworld:
            raise ValueError('private oracle label whitelist mismatch')
        return response['oracle_labels'],response['audit']
