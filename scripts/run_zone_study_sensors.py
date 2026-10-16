"""Zone study runner with the opt-in own front-ultrasonic input (adapter, 2026-09-29).

Entry point for a prereg that carries ``"sensors": {"ultrasonic_front": "on_v1"}``.
Everything else is ``scripts/run_zone_study_integration.py`` unchanged:

* sensors absent or ``off`` -> ``runner.main`` runs UNPATCHED. The pinned runner,
  executor and host sources are not edited by this adapter, so a sensors-off run
  has byte-identical sources, bundle, hashes and outputs (their pins, e.g. the
  v6d DRAFT source receipt, stay valid);
* ``on_v1`` -> for the duration of the run the adapter (1) swaps in a host
  subclass that reads each robot's own front ultrasonic after every physics
  step and hands it to that robot's own provider (``executor.range_provider``),
  (2) adds a ``sensors`` block and the sensor sources to the run bundle, so the
  bundle hash differs from every sensors-off baseline, and (3) writes
  ``robots/<rid>/inputs/range.jsonl`` plus ``sensors.json`` into the run output
  before the manifest hashes it.

No controller reads the value; the executors only hold the receiving provider.
The sensor sits in the physics owner's per-robot self-sensing path, below the
communication layer, and never sees the condition.

Folding this into the main runner (when the coordinator registers a bundle
version) means three small hooks: the ``sensors`` bundle block, the per-step
``rig.tick`` in ``_physics_until``, and closing the rig before ``write_outputs``.
See ``docs/ultrasonic_range_sensor.md`` section 12.

    python scripts/run_zone_study_sensors.py --prereg <prereg with sensors> --episode ... --bundle
    python scripts/run_zone_study_sensors.py --prereg <prereg with sensors> --episode ... --condition no_comm --output ...
"""
from __future__ import annotations

import argparse
import contextlib
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness import ultrasonic_input as hi  # noqa: E402
from scripts import run_zone_study_integration as runner  # noqa: E402

SELF = 'scripts/run_zone_study_sensors.py'
SENSORS_FILE = 'sensors.json'
_RUN: dict = {}                       # per-run context (single trial at a time in this process)


def sensors_of(prereg) -> dict:
    """Normalized sensors of a prereg (``{}`` = off); unknown keys or profiles are refused."""
    return hi.normalize_sensors(prereg.get('sensors'))


class SensorStudyTeamHost(runner.StudyTeamHost):
    """The study host plus the opt-in own ultrasonic: read-only, own readings only."""

    range_rig = None

    def __init__(self, spec, student, *, frames_dir=None, **kwargs):
        super().__init__(spec, student, frames_dir=frames_dir, **kwargs)
        try:
            self._attach(frames_dir)
        except Exception:
            self.close()
            raise

    def _attach(self, frames_dir):
        si = importlib.import_module('sim.ultrasonic_input')
        sensors, episode = _RUN['sensors'], _RUN['episode']
        out = Path(frames_dir).parent                  # run_trial: frames_dir = <run dir>/own_frames
        if Path(frames_dir).name != 'own_frames':
            raise RuntimeError('sensor adapter expects frames_dir=<run dir>/own_frames')
        seed = episode['trial_seed']
        robots = tuple(self.robots)
        range_input = hi.OwnRangeInput(
            robots, sensors[hi.SENSOR_KEY], noise_seeds={rid: si.sensor_seed(seed, rid) for rid in robots},
            out_dir=out, run_meta={'episode': episode['episode_id'], 'trial_seed': seed})
        self.range_rig = si.OwnUltrasonicRig(self.world.model, self.world.data, robots, episode_seed=seed,
                                             range_input=range_input)
        for rid, slot in self.robots.items():          # receiving channel only: no skill reads it
            slot.executor.range_provider = self.range_rig.provider(rid)

    def _physics_until(self, t_end):
        super()._physics_until(t_end)
        if self.range_rig is not None:                 # advance_to() steps once per call: one read per step
            self.range_rig.tick(float(self.world.data.time))

    def close(self):
        try:
            super().close()
        finally:
            if self.range_rig is not None:
                self.range_rig.close()


def _bundle_with_sensors(original):
    def run_bundle(prereg, episode, **kwargs):
        result = original(prereg, episode, **kwargs)
        result[0]['sensors'] = hi.bundle_record(sensors_of(prereg))
        return result
    return run_bundle


def _runtime_files_with_sensors(original):
    def runtime_files(prereg, provider):
        from harness.python_source_closure import source_closure
        extra = source_closure(ROOT, (SELF,), modules=hi.runtime_modules(sensors_of(prereg)))
        return tuple(sorted(set(original(prereg, provider)) | set(extra)))
    return runtime_files


def _run_trial_with_context(original):
    def run_trial(prereg, episode, condition, out, **kwargs):
        _RUN.clear()
        _RUN.update(sensors=sensors_of(prereg), episode=episode)
        try:
            return original(prereg, episode, condition, out, **kwargs)
        finally:
            _RUN.clear()
    return run_trial


def _write_outputs_with_sensors(original):
    def write_outputs(out, prereg, episode, condition, bundle, bundle_sha, host, trial, result, stop, failure, code,
                      started, load0, dev, *, referee=None):
        rig = getattr(host, 'range_rig', None)
        if rig is not None:
            rig.close()                                # flush the own range histories before the manifest hashes them
            (Path(out) / SENSORS_FILE).write_text(json.dumps(
                {'sensors': hi.result_record(sensors_of(prereg), rig.input.rows()), 'rig': rig.record(),
                 'bundle_block_sha256': bundle['sensors']['sha256'],
                 'note': 'own front ultrasonic recorded only; no controller reads it; not comparable to sensors-off runs'},
                indent=1, ensure_ascii=False) + '\n')
        return original(out, prereg, episode, condition, bundle, bundle_sha, host, trial, result, stop, failure, code,
                        started, load0, dev, referee=referee)
    return write_outputs


@contextlib.contextmanager
def sensors_enabled():
    """Patch the runner module for one run; always restored."""
    saved = {name: getattr(runner, name) for name in ('StudyTeamHost', 'run_bundle', 'runtime_files', 'run_trial',
                                                       'write_outputs')}
    try:
        runner.StudyTeamHost = SensorStudyTeamHost
        runner.run_bundle = _bundle_with_sensors(saved['run_bundle'])
        runner.runtime_files = _runtime_files_with_sensors(saved['runtime_files'])
        runner.run_trial = _run_trial_with_context(saved['run_trial'])
        runner.write_outputs = _write_outputs_with_sensors(saved['write_outputs'])
        yield runner
    finally:
        for name, value in saved.items():
            setattr(runner, name, value)


def main(argv=None):
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument('--prereg')
    known, _ = pre.parse_known_args(argv)
    if known.prereg is None or not sensors_of(runner.load_prereg(known.prereg)):
        return runner.main(argv)                       # sensors off: the unpatched runner, unchanged
    with sensors_enabled():
        return runner.main(argv)


if __name__ == '__main__':
    sys.exit(main())
