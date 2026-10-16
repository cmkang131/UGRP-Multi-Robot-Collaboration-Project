"""Own-only public transport; extra same-kind metrics stay in private files."""
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, '/home/ugrp/ugrp-sim/src/0362037280c6cbc4677f70366db43b9892b23690/scripts')
from warp_act_rpc import Client


class EvaluationClient(Client):
    def reset(self, plans, indices=None):
        if self.training or self.audit_state:
            raise ValueError('evaluation client has no privileged/training lane')
        if self.proc is not None:
            raise ValueError('one fresh evaluation generation per owner')
        if indices not in (None, list(range(self.nworld))) or len(plans) != self.nworld:
            raise ValueError('initialize all evaluation worlds')
        path = self.out / 'initial-plans.json'
        path.write_text(json.dumps(dict(episodes=plans), indent=2)+'\n')
        argv = [self.python, '-u', str(Path(__file__).with_name('act16w_eval_owner.py')),
                '--enabled', '--plans', str(path), '--out', str(self.out/'owner')]
        for key, value in self.options.items():
            argv += ['--'+key.replace('_', '-'), str(value)]
        self.stderr = (self.out/'owner.stderr.log').open('x')
        self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=self.stderr, text=True, bufsize=1)
        result = self.receive()
        if self.on_reset is not None:
            self.on_reset(tuple(range(self.nworld)))
        return result
