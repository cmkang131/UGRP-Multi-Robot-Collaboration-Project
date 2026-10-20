"""Keep privileged teacher labels out of the inherited own-RGB actor client."""
import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,'/home/ugrp/ugrp-sim/src/0362037280c6cbc4677f70366db43b9892b23690/scripts')
from warp_act_rpc import Client


class DaggerClient(Client):
    def __init__(self, *, takeover=False, takeover_hold_s=3.0, takeover_after_s=6.0, **options):
        super().__init__(**options)
        if not 0<takeover_hold_s<=60:raise ValueError('takeover hold must be in (0, 60] SIM s')
        if takeover_after_s<0:raise ValueError('takeover delay must be nonnegative')
        self.takeover=bool(takeover);self.takeover_hold_s=float(takeover_hold_s)
        self.takeover_after_s=float(takeover_after_s);self.takeover_commands=None

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
        if self.takeover:argv+=['--takeover','--takeover-hold-s',str(self.takeover_hold_s),'--takeover-after-s',str(self.takeover_after_s)]
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
        keys=set(response)
        if (keys not in ({'oracle_labels','audit'},{'oracle_labels','audit','takeover_commands'})
                or len(response['oracle_labels'])!=self.nworld):
            raise ValueError('private oracle label whitelist mismatch')
        labels,audit=response['oracle_labels'],response['audit']
        commands=response.get('takeover_commands')
        if commands is not None:
            if not self.takeover:raise ValueError('takeover commands without explicit takeover opt-in')
            if len(commands)!=self.nworld:raise ValueError('one takeover command per world required')
            for item in commands:
                if item is not None and (set(item)!={'command','done'} or type(item['done']) is not bool):
                    raise ValueError('takeover command whitelist mismatch')
        self.takeover_commands=commands
        return labels,audit
