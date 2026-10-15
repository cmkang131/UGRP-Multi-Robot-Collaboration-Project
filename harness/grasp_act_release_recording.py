"""Observation-only release adapter for the ACT12 native JPEG/command writer.

The prefix is never recorded. No sampler, control callback or wall deadline is
installed. The existing 0.1 SIM-second loop owns sampling and command timing.
"""
from __future__ import annotations

import hashlib
import io
import json
import pickle
import random
from pathlib import Path

import numpy as np
from PIL import Image

from harness.grasp_act_contract import PERIOD_S, SERVOS
from harness.grasp_act_solo_recording import SoloRecorder

MODE = 'act12_observer_v1'
MODES = ('off', MODE)


def validate(mode, enabled, options):
    if mode not in MODES or bool(enabled) != (mode == MODE):
        raise ValueError('release training RGB requires act12_observer_v1 and record_training together')
    if enabled and (options.get('release21') != 'release21_v1'
                    or options.get('release_profile') != 'release19_v1'
                    or options.get('review_top') != 'off'
                    or options.get('render_dr') != 'off'):
        raise ValueError('release recording requires gated release21 B, top off and render DR off')


def issued(now, teacher, wheels):
    """Read issued scheduler values only; never measured servos or motor state."""
    durations = [max(0., min(.15, float(u-now))) if level else 0.
                 for level, u in zip(wheels.levels, wheels.until)]
    return dict(t=now, wheels=[float(v) if d else 0. for v, d in zip(wheels.levels, durations)],
                duration_s=durations, pwm={str(s): int(teacher.pwm[s]) for s in SERVOS})


class RenderAudit:
    """Exact integration-state and available RNG equality around every added render.

    mjSTATE_INTEGRATION includes time, controls and solver warm-start state.
    Equality is byte-exact, not a new physical acceptance tolerance. The guard
    raises instead of restoring state, so it cannot hide a renderer mutation.
    """
    def __init__(self):
        self.calls = 0

    def state(self, world):
        import mujoco
        spec = mujoco.mjtState.mjSTATE_INTEGRATION
        values = np.empty(mujoco.mj_stateSize(world.model, spec))
        mujoco.mj_getState(world.model, world.data, values, spec)
        rngs = [random.getstate(), np.random.get_state()]
        for obj in (world, *world.controllers.values()):
            rng = getattr(obj, 'rng', None)
            if isinstance(rng, np.random.Generator):
                rngs.append(rng.bit_generator.state)
        return hashlib.sha256(values.tobytes()+pickle.dumps(rngs)).hexdigest()

    def capture(self, world, rid):
        before = self.state(world)
        jpeg = bytes(world.render_jpeg(robot_id=rid, camera='robot_cam'))
        if self.state(world) != before:
            raise RuntimeError('training_render_mutated_integration_or_rng')
        self.calls += 1
        return jpeg

    def record(self):
        return dict(calls=self.calls, integration_or_rng_changes=0,
                    comparison='mjSTATE_INTEGRATION + Python/NumPy/world/controller RNG, exact SHA256')


class ReleaseRecorder:
    def __init__(self, root, plan, teachers, wheels, now):
        self.root, self.writers = Path(root), {}
        self.audit = RenderAudit()
        for rid, teacher in teachers.items():
            p = dict(robot_id=rid, kind='long_beam', role=plan['roles'][rid],
                     episode_id=f"release-{plan['seed']}")
            writer = SoloRecorder(root, p, issued(now, teacher, wheels[rid]),
                                  destination_zone=plan['destination_region'].removeprefix('zone_'))
            # A release instruction starts with the beam already held. This is
            # task segmentation only; no truth/vision handoff heuristic is run.
            writer.local_started = True
            self.writers[rid] = writer

    def capture(self, world):
        return {rid: self.audit.capture(world, rid) for rid in self.writers}

    def target(self, now, images, *, phase, phase_after, teachers, wheels, complete=False):
        for rid, writer in self.writers.items():
            jpeg = images[rid]
            with Image.open(io.BytesIO(jpeg)) as im:
                frame = np.asarray(im.convert('RGB'))
            writer.observe(now, jpeg, frame, skill='release', phase=phase,
                           previous=writer.history[-1])
            writer.target(issued(now, teachers[rid], wheels[rid]), skill_after='release',
                          phase_after=phase_after, complete=complete)

    def close(self):
        for writer in self.writers.values():
            writer.close()

    def record(self):
        return dict(mode=MODE, actors={r: w.record() for r, w in self.writers.items()},
                    render_audit=self.audit.record(), period_s=PERIOD_S,
                    prefix_recorded=False, training_include=False,
                    timing='unchanged SIM clock; additional rendering and I/O increase wall time')
