"""Default-off E2E18 speed pair: relook dt release + phase/function controller timing.

Both toggles are measurement/physics-step settings. They read only the own
issued gripper command and the execution phase; timing never feeds a controller.
"""
import copy
import time
from contextlib import ExitStack, contextmanager

RELEASE = 'release_dt1_v1'
TIMING = 'phase_v1'
PARENTS = {'e2e18-v273': 290, 'e2e18-v277': 291}
PROFILE = dict(mapping_dt_s=.002, align_dt_s=.001, contact_dt_s=.00025, relook_dt_s=.001,
               release='own_issued_gripper_open_or_relook_phase',
               source='own_execution_phase_and_issued_gripper_command')
PARAMS = dict(timing='phase_v1', file='controller-timing.json', controller_feedback=False,
              flush_period_s=1., nested_timers_not_additive=True)
WORKFLOW = 'configs/simulation_workflows.d/e2e18_v{}.json'


def compose(bundle, stage_physics, controller_timing):
    """Both toggles together: v273 -> v290 and (relook view5_restore) v277 -> v291."""
    if stage_physics != RELEASE and controller_timing == 'off':
        return ()
    if stage_physics != RELEASE or controller_timing != TIMING:
        raise ValueError('SPEED_PHASE_REQUIRES_BOTH_TOGGLES')
    version = PARENTS.get(bundle['execution_bundle_id'])
    if version is None:
        raise ValueError('SPEED_PHASE_REQUIRES_V273_OR_V277')
    bundle['e2e_options'].update(stage_physics=RELEASE, controller_timing=TIMING)
    bundle['stage_physics_profile'] = dict(PROFILE)
    bundle['controller_timing_parameters'] = copy.deepcopy(PARAMS)
    bundle['speed_phase_parent_bundle_id'] = bundle['execution_bundle_id']
    bundle.update(schema=f'ugrp.e2e_ownmap_live.v{version}', execution_bundle_id=f'e2e18-v{version}',
                  workflow_version=f'7.{version - 107}.0')
    return (WORKFLOW.format(version),)


def validate(bundle):
    options = bundle['e2e_options']
    if (options.get('stage_physics') != RELEASE or options.get('controller_timing') != TIMING
            or bundle.get('stage_physics_profile') != PROFILE
            or bundle.get('controller_timing_parameters') != PARAMS
            or PARENTS.get(bundle.get('speed_phase_parent_bundle_id')) is None
            or bundle['execution_bundle_id'] != f"e2e18-v{PARENTS[bundle['speed_phase_parent_bundle_id']]}"):
        raise ValueError('REGISTERED_SPEED_PHASE_REQUIRED')


class Timer:
    """phase -> function -> calls/wall_s; same shape as backend.measure()."""
    def __init__(self, backend=None):
        self.backend = backend
        self.phase = 'mapping'
        self.stats = {}
        self.started = time.perf_counter()
        self._last_flush = 0.

    @contextmanager
    def measure(self, name):
        start = time.perf_counter()
        with ExitStack() as stack:
            if self.backend is not None and hasattr(self.backend, 'measure'):
                stack.enter_context(self.backend.measure('controller.' + name))
            try:
                yield
            finally:
                row = self.stats.setdefault(self.phase, {}).setdefault(name, dict(calls=0, wall_s=0.))
                row['calls'] += 1
                row['wall_s'] += time.perf_counter() - start

    def wrap(self, function, name):
        if getattr(function, '_controller_timed', False):
            return function
        def timed(*args, **kwargs):
            with self.measure(name):
                return function(*args, **kwargs)
        timed._controller_timed = True
        return timed

    def snapshot(self):
        return dict(option=TIMING, phases=self.stats, parameters=PARAMS,
                    total_wall_s=time.perf_counter() - self.started,
                    nested_timers_not_additive=True, controller_feedback=False)

    def flush(self, path, writer, force=False):
        now = time.monotonic()
        if force or now - self._last_flush >= PARAMS['flush_period_s']:
            self._last_flush = now
            writer(path, self.snapshot())


def install(option, robots, transport, host, backend, runner_globals=None):
    """Wrap by instance/module attribute only when on; off installs nothing."""
    if option == 'off':
        return None
    if option != TIMING:
        raise ValueError('UNKNOWN_CONTROLLER_TIMING')
    timer = Timer(backend)
    from harness import e2e_live_mapping, e2e_camera_settle
    e2e_live_mapping.observe = timer.wrap(e2e_live_mapping.observe, 'observe_walls')
    e2e_camera_settle.receive = timer.wrap(e2e_camera_settle.receive, 'settled_receive')
    for robot in robots.values():
        robot._receive = timer.wrap(robot._receive, 'robot._receive')
        robot.goal.receive = timer.wrap(robot.goal.receive, 'goal.receive')
        robot.observe_beam = timer.wrap(robot.observe_beam, 'observe_beam')
    transport.step = timer.wrap(transport.step, 'transport.step')
    host.step_to = timer.wrap(host.step_to, 'host.step_to')
    backend.capture = timer.wrap(backend.capture, 'backend.capture')
    if runner_globals is not None:
        for name in ('ownmap_record', 'health'):
            runner_globals[name] = timer.wrap(runner_globals[name], name)
    return timer
