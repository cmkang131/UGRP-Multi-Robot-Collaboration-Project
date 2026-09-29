"""Opt-in front-ultrasonic INPUT for a run (harness side, no simulator import).

2026-09-29 user request: wire the front ultrasonic range into the harness as an
input the run bundle can switch on. The sensor itself (``sim.ultrasonic_range``,
``harness.ultrasonic_model``, ``harness.range_provider``) already existed and
was connected to nothing; this module is the connection point.

* The switch is ``sensors.ultrasonic_front`` in the run configuration
  (``off`` | ``on_v1``). Absent or ``off`` is the default and adds NOTHING: no
  bundle key, no output file, no extra source in the run's source closure
  (``tests/test_ultrasonic_input.py``).
* ``on_v1`` = ``harness.ultrasonic_model.DEFAULT_SPEC`` (sensor model
  ``masterpi_ultrasonic_v2``), crosstalk OFF. A run that turns it on records the
  profile, the sensor model id and the spec hash in its bundle and is NOT
  comparable to a sensors-off baseline (``docs/execution_versioning.md``).
* Each robot gets ONLY its own readings (``OwnRangeInput``). A reading is
  ``{t, range_m, valid, status}``: time, distance and status. It never says what
  was hit. There is no path from one robot's sensor to another robot's provider,
  so the four communication conditions get the same input by construction: the
  sensor sits BELOW the communication layer, in the physics owner's per-robot
  self-sensing path, and never reads the condition.
* Nothing here makes a controller use the value. ``range_report(executor, now)``
  is a receiving channel only; using it is a separate decision.
* The pinned executor/host/runner sources are NOT edited: the adapter
  ``scripts/run_zone_study_sensors.py`` composes them, so a sensors-off run is
  byte-identical, sources included.

The MuJoCo half is ``sim.ultrasonic_input`` (imported by the physics owner only
when the sensor is on).
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from harness import range_provider as rp
from harness import ultrasonic_model as usm

SENSOR_KEY = 'ultrasonic_front'
PROFILE_OFF, PROFILE_ON_V1 = 'off', 'on_v1'
PROFILES = (PROFILE_OFF, PROFILE_ON_V1)
SCHEMA = 'ugrp.sensors_config.v1'
#: what the robot receives per reading (the ``RangeReading`` fields, nothing else)
OBSERVATION_FIELDS = ('t', 'range_m', 'valid', 'status')
#: source modules a run must add to its pinned source closure when the sensor is on
RUNTIME_MODULES = ('harness.ultrasonic_input', 'harness.range_provider', 'harness.ultrasonic_model',
                   'sim.ultrasonic_input', 'sim.ultrasonic_range')
HISTORY_FILE = 'range.jsonl'


class SensorConfigError(ValueError):
    """An unknown sensor key or profile; never mapped to a default."""


def spec_for(profile: str) -> usm.UltrasonicSpec:
    if profile == PROFILE_ON_V1:
        return usm.DEFAULT_SPEC
    raise SensorConfigError(f'profile {profile!r} has no sensor spec')


def normalize_sensors(value: Mapping | None) -> dict:
    """``{'ultrasonic_front': 'on_v1'}`` or ``{}`` (off). Unknown keys/profiles are refused."""
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise SensorConfigError('sensors must be an object')
    unknown = sorted(set(value) - {SENSOR_KEY})
    if unknown:
        raise SensorConfigError(f'unknown sensor keys {unknown}; known: {[SENSOR_KEY]}')
    profile = value.get(SENSOR_KEY, PROFILE_OFF)
    if profile not in PROFILES:
        raise SensorConfigError(f'{SENSOR_KEY} must be one of {PROFILES}, got {profile!r}')
    return {} if profile == PROFILE_OFF else {SENSOR_KEY: profile}


def is_on(sensors: Mapping | None) -> bool:
    return bool(normalize_sensors(sensors))


def runtime_modules(sensors: Mapping | None) -> tuple[str, ...]:
    """Extra modules for the run's source closure (empty when off, so off hashes do not move)."""
    return RUNTIME_MODULES if is_on(sensors) else ()


def bundle_record(sensors: Mapping | None) -> dict | None:
    """The block a run bundle stores under ``sensors`` (``None`` when off: the key is then omitted)."""
    normalized = normalize_sensors(sensors)
    if not normalized:
        return None
    profile = normalized[SENSOR_KEY]
    spec = spec_for(profile)
    record = usm.spec_record(spec)
    block = {'schema': SCHEMA, SENSOR_KEY: {
        'profile': profile, 'enabled': True, 'input_profile_id': rp.PROFILE_ID,
        'sensor_model_id': usm.SENSOR_MODEL_ID, 'spec_sha256': record['sha256'],
        'source': rp.source_label(spec), 'crosstalk': bool(spec.crosstalk),
        'observation_fields': list(OBSERVATION_FIELDS), 'observation_scope': 'own sensor only',
        'noise_seed_rule': rp.NOISE_SEED_RULE, 'noise_index_rule': rp.NOISE_INDEX_RULE,
        'history_file': f'robots/<robot>/inputs/{HISTORY_FILE}',
        'controller_use': 'none wired: receiving channel and recording only',
        'baseline_comparable': False,
        'comparison_note': 'sensors-on run: compare only with sensors-on runs of the same profile'}}
    block['sha256'] = hashlib.sha256(json.dumps(block, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return block


def result_record(sensors: Mapping | None, rows: Mapping[str, int] | None = None) -> dict | None:
    """Small block for a run's result summary (``None`` when off)."""
    block = bundle_record(sensors)
    if block is None:
        return None
    out = {SENSOR_KEY: block[SENSOR_KEY]['profile'], 'sensors_sha256': block['sha256'],
           'baseline_comparable': False}
    if rows is not None:
        out['history_rows'] = dict(rows)
    return out


def range_report(executor, now: float):
    """An executor's own latest range report (receiving channel), or ``None`` when the sensor is off."""
    provider = getattr(executor, 'range_provider', None)
    return None if provider is None else provider.report(float(now))


class OwnRangeInput:
    """Per-robot own-reading providers plus history files for one run (no simulator import).

    ``feed(rid, reading)`` is called by the physics owner with that robot's own
    reading; ``provider(rid)`` hands the robot's controller-side receiving object.
    A robot can only ever be given its own provider.
    """

    def __init__(self, robots: Sequence[str], profile: str, *, noise_seeds: Mapping[str, int],
                 out_dir: str | Path | None = None, run_meta: Mapping | None = None):
        spec = spec_for(profile)
        self.profile, self.spec, self.robots = profile, spec, tuple(robots)
        if set(noise_seeds) != set(self.robots):
            raise SensorConfigError('one noise seed per robot is required')
        self._providers = {rid: rp.OwnUltrasonicRangeProvider(spec) for rid in self.robots}
        self._writers: dict[str, rp.RangeHistoryWriter] = {}
        if out_dir is not None:
            for rid in self.robots:
                self._writers[rid] = rp.RangeHistoryWriter(
                    Path(out_dir) / 'robots' / rid / 'inputs' / HISTORY_FILE, rid, spec,
                    noise_seed=noise_seeds[rid], run_meta={'profile': profile, **dict(run_meta or {})})

    def provider(self, rid: str) -> rp.OwnUltrasonicRangeProvider:
        return self._providers[rid]

    def feed(self, rid: str, reading: usm.RangeReading) -> None:
        self._providers[rid].on_reading(reading)
        if rid in self._writers:
            self._writers[rid].append(reading)

    def rows(self) -> dict[str, int]:
        return {rid: w.rows for rid, w in self._writers.items()}

    def close(self) -> None:
        for writer in self._writers.values():
            writer.close()
