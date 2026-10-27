"""Administrative CPU-init provenance for the sealed pair GPU retry.

No physics/actor/evaluator expressions change. Recorder installation is a
one-way boundary per MjData; GPU initialization is a process-wide boundary.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import functools
import json
from pathlib import Path


def utc():
    return datetime.now(timezone.utc).isoformat()


class CPUInitGuard:
    def __init__(self, output, arm, seeds):
        self.output, self.arm = Path(output), arm
        if self.output.exists():
            raise ValueError('new CPU provenance path required')
        self.scope = None
        self.batch_rollout = False
        self.data = {}  # Keep MjData references alive: Python ids cannot be reused.
        self.rows = {str(i): self.row(i, seed) for i, seed in enumerate(seeds)}
        self.template = self.row(None, None)
        self.transitions = []
        self.denials = []
        self.flush()

    @staticmethod
    def row(index, seed):
        return dict(world=index, seed=seed, phase='INIT_OR_RESET',
                    cpu_init_mj_step_count=0, cpu_init_mj_step_calls=0,
                    phase_transitions=[dict(phase='INIT_OR_RESET', utc=utc())])

    def flush(self):
        record = dict(schema='ugrp.pair.scoped-cpu-init.v1', arm=self.arm,
            cpu_init_mj_step_count=sum(r['cpu_init_mj_step_count'] for r in self.rows.values())
                + self.template['cpu_init_mj_step_count'],
            episodes=list(self.rows.values()), template=self.template,
            batch_phase='ROLLOUT' if self.batch_rollout else 'INIT_OR_RESET',
            phase_transitions=self.transitions, rollout_cpu_denial_events=self.denials,
            updated_utc=utc())
        self.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.output.with_suffix('.tmp')
        temporary.write_text(json.dumps(record, indent=2) + '\n')
        temporary.replace(self.output)

    @contextmanager
    def episode(self, index):
        before = self.scope
        self.scope = str(index)
        try:
            yield
        finally:
            self.scope = before

    def bind(self, data, key):
        identity = id(data)
        if identity in self.data:
            prior = self.data[identity]
            if prior['key'] != key:
                raise RuntimeError('CPU-init guard: MjData episode ownership changed')
            return prior
        row = self.template if key is None else self.rows[key]
        entry = dict(data=data, key=key, row=row, rollout=False)
        self.data[identity] = entry
        return entry

    def step(self, original, model, data, *args, **kwargs):
        entry = self.data.get(id(data))
        row = entry['row'] if entry else (self.template if self.scope is None else self.rows[self.scope])
        if self.batch_rollout or (entry and entry['rollout']) or row['phase'] == 'ROLLOUT':
            event = dict(utc=utc(), world=row['world'], seed=row['seed'],
                phase='ROLLOUT', cpu_init_mj_step_count=row['cpu_init_mj_step_count'],
                arm_cpu_init_mj_step_count=sum(r['cpu_init_mj_step_count'] for r in self.rows.values())
                    + self.template['cpu_init_mj_step_count'])
            self.denials.append(event)
            self.flush()
            raise RuntimeError('CPU_MJ_STEP_DURING_ROLLOUT: ' + json.dumps(event, sort_keys=True))
        entry = entry or self.bind(data, self.scope)
        result = original(model, data, *args, **kwargs)
        # mujoco.mj_step(model, data, nstep=1): count physics steps, not just calls.
        row['cpu_init_mj_step_count'] += int(args[0] if args else kwargs.get('nstep', 1))
        row['cpu_init_mj_step_calls'] += 1
        return result

    def recorder(self, index, data):
        key = str(index)
        entry = self.bind(data, key)
        entry['rollout'] = True
        row = entry['row']
        row['phase'] = 'ROLLOUT'
        event = dict(phase='ROLLOUT', utc=utc(), reason='GPU command recorder installation', world=index)
        row['phase_transitions'].append(event)
        self.transitions.append(event)
        self.flush()

    def begin_batch(self, reason):
        self.batch_rollout = True
        self.transitions.append(dict(phase='ROLLOUT', utc=utc(), reason=reason))
        self.flush()

    @contextmanager
    def installed(self, mujoco, flow, backend):
        """Wrap scheduling boundaries, retaining every original implementation."""
        original_step = mujoco.mj_step
        original_lane = flow.make_lane
        original_invoke = flow.Lane.invoke
        original_recorder = flow.Bridge.install_command_recorder
        original_initialize = backend.WarpTransport.initialize
        original_gpu_step = backend.WarpTransport.step
        guard = self

        @functools.wraps(original_lane)
        def make_lane(*args, **kwargs):
            lane, bridge = original_lane(*args, **kwargs)
            index = bridge.index
            if guard.rows[str(index)]['seed'] != bridge.plan['seed']:
                raise ValueError('CPU-init guard: sealed seed/index mismatch')
            lane._cpu_guard_index = index
            return lane, bridge

        @functools.wraps(original_invoke)
        def invoke(lane, method):
            with guard.episode(lane._cpu_guard_index):
                return original_invoke(lane, method)

        @functools.wraps(original_recorder)
        def recorder(bridge, world):
            guard.recorder(bridge.index, world.data)
            return original_recorder(bridge, world)

        @functools.wraps(original_initialize)
        def initialize(transport, *args, **kwargs):
            guard.begin_batch('MJWarp batch initialize begins')
            return original_initialize(transport, *args, **kwargs)

        @functools.wraps(original_gpu_step)
        def gpu_step(transport, *args, **kwargs):
            if not guard.batch_rollout:
                raise RuntimeError('CPU-init guard: GPU loop before batch boundary')
            return original_gpu_step(transport, *args, **kwargs)

        mujoco.mj_step = lambda model, data, *a, **kw: guard.step(original_step, model, data, *a, **kw)
        flow.make_lane, flow.Lane.invoke = make_lane, invoke
        flow.Bridge.install_command_recorder = recorder
        backend.WarpTransport.initialize, backend.WarpTransport.step = initialize, gpu_step
        try:
            yield self
        finally:
            self.flush()
            mujoco.mj_step = original_step
            flow.make_lane, flow.Lane.invoke = original_lane, original_invoke
            flow.Bridge.install_command_recorder = original_recorder
            backend.WarpTransport.initialize, backend.WarpTransport.step = original_initialize, original_gpu_step
