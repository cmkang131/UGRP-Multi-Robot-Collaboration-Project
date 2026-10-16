"""Own-RGB JSON client, usable in the ACT torch environment without MuJoCo."""
import base64
from copy import deepcopy
import json
from pathlib import Path
import subprocess


class Client:
    def __init__(self, *, python, qualified_source, teacher_source, qualification,
                 references, compiled_reference, compiled_geometry, out, nworld,
                 enabled=False, training=False, audit_state=False, on_reset=None,
                 training_truth_factory=None, require_visible_centre=False):
        if not enabled: raise ValueError('MJWarp client is default OFF')
        if require_visible_centre: raise NotImplementedError('visible instance-mask centroid is not available; centre heuristic not admitted')
        self.python, self.nworld, self.training = str(python), nworld, training
        self.audit_state = audit_state
        self.on_reset, self.truth_factory = on_reset, training_truth_factory
        self.options = dict(qualified_source=qualified_source, teacher_source=teacher_source,
                            qualification=qualification, references=references,
                            compiled_reference=compiled_reference, compiled_geometry=compiled_geometry)
        self.out = Path(out); self.out.mkdir(parents=True, exist_ok=False)
        self.proc, self.current, self.terminal = None, None, [True]*nworld

    def receive(self):
        line = self.proc.stdout.readline()
        if not line: raise RuntimeError('owner exited; inspect '+str(self.out/'owner.stderr.log'))
        result = json.loads(line)
        if 'error' in result: raise ValueError(result['error_type']+': '+result['error'])
        if set(result) == {'training'}:
            if not self.training: raise ValueError('privileged response in evaluation client')
            return result['training']
        if set(result) != {'frames', 'terminal'} or len(result['frames']) != self.nworld:
            raise ValueError('owner response whitelist mismatch')
        self.current = []
        for item in result['frames']:
            if set(item) != {'observation', 'jpegs'}: raise ValueError('actor lane whitelist mismatch')
            jpgs = tuple(base64.b64decode(x, validate=True) for x in item['jpegs'])
            import hashlib
            if len(jpgs) != len(item['observation']['rgb']) or any(hashlib.sha256(j).hexdigest() != r['sha256'] for j, r in zip(jpgs, item['observation']['rgb'])):
                raise ValueError('own RGB transport hash mismatch')
            self.current.append((item['observation'], jpgs))
        self.terminal = result['terminal']
        return self.current

    def exchange(self, value):
        self.proc.stdin.write(json.dumps(value, allow_nan=False)+'\n'); self.proc.stdin.flush()
        return self.receive()

    def reset(self, plans, indices=None):
        indices = list(range(self.nworld)) if indices is None else list(indices)
        if self.proc is None:
            if indices != list(range(self.nworld)) or len(plans) != self.nworld: raise ValueError('first reset initializes all worlds in index order')
            p = self.out/'initial-plans.json'; p.write_text(json.dumps(dict(episodes=plans), indent=2)+'\n')
            argv = [self.python, '-u', str(Path(__file__).with_name('warp_act_owner.py')), '--enabled', '--plans', str(p), '--out', str(self.out/'owner')]
            for key, value in self.options.items(): argv += ['--'+key.replace('_', '-'), str(value)]
            if self.training: argv += ['--training']
            if self.audit_state: argv += ['--audit-state']
            self.stderr = (self.out/'owner.stderr.log').open('x')
            self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr, text=True, bufsize=1)
            result = self.receive()
        else: result = self.exchange(dict(reset=plans, indices=indices))
        # Policy chunks/RNG live outside the physics process. A consumer binds
        # its WORLD-LOCAL reset callback; never reset another world's generator.
        if self.on_reset is not None: self.on_reset(tuple(indices))
        return result

    def read_actor(self, i):
        obs, jpgs = self.current[i]
        return deepcopy(obs), tuple(jpgs)

    def step(self, actions):
        self.exchange(dict(actions=actions)); return list(self.terminal)

    def instruct(self, i, skill):
        return self.exchange(dict(instruct=i, skill=skill))

    def read_training(self, i):
        if not self.training: raise RuntimeError('no privileged lane in student evaluation')
        truth, critic = self.exchange(dict(read_training=i))
        if set(truth) != {'distance_m','alignment_rad','target_xy','stable_lift'}:
            raise ValueError('training truth whitelist mismatch')
        from types import SimpleNamespace
        return (self.truth_factory or SimpleNamespace)(**truth), tuple(critic)

    def close(self, reason='caller_stop'):
        if self.proc is None: return
        try:
            if self.proc.poll() is None:
                self.proc.stdin.write(json.dumps({'close':reason})+'\n'); self.proc.stdin.flush()
                self.proc.wait(timeout=30)
            if self.proc.returncode: raise RuntimeError('owner failed: '+str(self.proc.returncode))
        finally:
            if self.proc.poll() is None: self.proc.terminate(); self.proc.wait(timeout=10)
            self.proc.stdin.close(); self.proc.stdout.close(); self.stderr.close()
