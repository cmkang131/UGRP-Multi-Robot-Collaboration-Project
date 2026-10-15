"""Recording-only timing and controller-ingress audit; no simulator imports."""
from contextlib import contextmanager
from functools import wraps
import time


class Metrics:
    """Inclusive and exclusive wall times, including failed calls.

    Wrappers stay on this recording's instances. Nested categories must not be
    summed using inclusive_s. No observation or command is changed by a timer.
    """
    def __init__(self, clock=time.perf_counter):
        self.clock, self.timers, self.stack = clock, {}, []

    @contextmanager
    def measure(self, name):
        frame = [self.clock(), 0.]
        self.stack.append(frame)
        try:
            yield
        finally:
            elapsed = self.clock()-frame[0]
            self.stack.pop()
            if self.stack:
                self.stack[-1][1] += elapsed
            row = self.timers.setdefault(name, dict(calls=0, inclusive_s=0., exclusive_s=0.))
            row['calls'] += 1
            row['inclusive_s'] += elapsed
            row['exclusive_s'] += elapsed-frame[1]

    def wrap(self, obj, method, name):
        original = getattr(obj, method)
        @wraps(original)
        def measured(*args, **kwargs):
            key = name(*args, **kwargs) if callable(name) else name
            with self.measure(key):
                return original(*args, **kwargs)
        setattr(obj, method, measured)

    def install(self, backend):
        # Install after reset, before the first recorded frame. World/ports are
        # never given to controllers; the evaluator retains its own access.
        for method, name in (('advance_to', 'physics_advance'), ('_append', 'jsonl_write'),
                             ('flush', 'log_flush'), ('eval_sample', 'evaluation'),
                             ('issue', 'command_dispatch')):
            self.wrap(backend, method, name)
        world = backend.world
        self.wrap(world, '_physics_step_for', 'physics_step')
        # render_rgb includes renderer executor synchronization. render_jpeg's
        # exclusive time is JPEG encoding (including buffer construction).
        self.wrap(world, 'render_rgb', lambda *a, **kw: 'render_rgb_and_sync_'+str(kw['robot_id']))
        self.wrap(world, 'render_jpeg', lambda *a, **kw: 'jpeg_encode_'+str(kw['robot_id']))
        backend.recording_metrics = self
        for rid, port in backend.ports.items():
            port.recording_metrics = self
            self.wrap(port, 'capture', 'camera_capture_'+rid)

    def snapshot(self):
        return dict(schema='map-amcl-stage-timing/1', timers={k: dict(v) for k, v in self.timers.items()},
                    inclusive_timers_not_additive=True,
                    render_sync='render_rgb includes executor wait; no extra render',
                    controller_feedback=False)


class InputAudit:
    """Count actual controller ingress and denied reads of forbidden fields.

    Scope is the recording's closed input boundary, not every evaluator/world
    read in the process. Evaluation is intentionally outside this boundary.
    """
    allowed = frozenset(('frame_id', 'sim_time', 'sha256', 'image'))
    top = frozenset(('top', 'top_rgb', 'top_camera', 'top_image', 'cctv_top'))

    def __init__(self):
        self.counts = dict(own_rgb_inputs=0, controller_calls=0, top_camera_inputs=0,
                           truth_reads=0, held_world_reads=0, rejected_inputs=0,
                           held_observations=0)

    def denied(self, key, held):
        self.counts['rejected_inputs'] += 1
        if key in self.top:
            self.counts['top_camera_inputs'] += 1
        else:
            self.counts['truth_reads'] += 1
            self.counts['held_world_reads'] += int(held)
        raise ValueError('FORBIDDEN_CONTROLLER_INPUT:'+str(key))

    def receive(self, robot, obs, rgb, now, *, held=False):
        # Validate camera identity before dropping port-only metadata. Never
        # pass actuator measurements or camera/world handles to the actor.
        if obs.get('camera', 'robot_cam') != 'robot_cam':
            self.denied('top_camera', held)
        if obs.get('robot_id', robot.robot_id) != robot.robot_id:
            self.denied('foreign_robot', held)
        payload = AuditedObservation({k: obs[k] for k in self.allowed}, self, held)
        payload['sim_time'] = now
        self.counts['own_rgb_inputs'] += 1
        self.counts['controller_calls'] += 1
        self.counts['held_observations'] += int(held)
        return robot.receive(payload, rgb)

    def snapshot(self):
        return dict(schema='map-amcl-input-audit/1', status='MEASURED_CONTROLLER_BOUNDARY',
                    **self.counts, scope='own RGB ingress and forbidden field access; evaluator excluded',
                    held_scope='drive-only recording, no grasp/held phase; held count is not held-task validation')


class AuditedObservation(dict):
    def __init__(self, value, audit, held):
        super().__init__(value)
        self.audit, self.held = audit, held

    def __getitem__(self, key):
        if key not in InputAudit.allowed:
            self.audit.denied(key, self.held)
        return super().__getitem__(key)

    def get(self, key, default=None):
        if key not in InputAudit.allowed:
            self.audit.denied(key, self.held)
        return super().get(key, default)

    def __deepcopy__(self, memo):
        # Values are immutable scalars/base64 text; retain the live audit on
        # the actor's saved last_obs rather than copying its counters.
        return type(self)(dict(self), self.audit, self.held)
