"""Controller-facing own ultrasonic range provider (2026-09-28 user decision, #221).

Consistent with the landmark-agnostic pose provider contract of PR #240
(``harness/pose_provider.py``): every report says WHEN the measurement was
taken (raw SIM capture time ``t_meas``, never delivery or prediction time),
how OLD it is at ``now``, WHERE it comes from (``source`` label bound to the
sensor model and spec hash) and HOW UNCERTAIN it is (``sigma_m``). A valid
reading is not proof of what was hit: the provider never says whether the echo
came from a wall, a peer robot or cargo.

Inputs are only the robot's own sensor readings (``RangeReading``: time, range,
valid). No simulator import (checked by ``tests/test_ultrasonic_range.py``).

The same provider configuration is used in every communication condition:
``provider_config_for_condition`` ignores the condition by construction and
refuses unknown names. It is OFF in every existing registered bundle; a run
opts in by constructing a provider and recording its history.
"""
from __future__ import annotations

import json
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from harness.ultrasonic_model import (DEFAULT_SPEC, READING_SCHEMA, SENSOR_MODEL_ID, RangeReading,
                                      UltrasonicSpec, spec_record)

SOURCE_PREFIX = 'own_ultrasonic_v1'
HISTORY_SCHEMA = 'ugrp.own_ultrasonic_history.v1'
PROFILE_ID = 'own_ultrasonic_input.v1'


@dataclass(frozen=True)
class RangeReport:
    t_meas: float | None            # raw SIM time of the latest reading (None: no reading yet)
    age_s: float | None             # now - t_meas
    valid: bool                     # latest reading had an echo inside [min, max]
    range_m: float = float('nan')
    sigma_m: float = float('inf')
    min_range_m: float = DEFAULT_SPEC.min_range_m
    max_range_m: float = DEFAULT_SPEC.max_range_m
    last_valid_t: float | None = None
    source: str = SOURCE_PREFIX

    def as_dict(self) -> dict:
        return {'t_meas': None if self.t_meas is None else round(self.t_meas, 6),
                'age_s': None if self.age_s is None else round(self.age_s, 6),
                'valid': self.valid, 'range_m': round(self.range_m, 4) if self.valid else None,
                'sigma_m': round(self.sigma_m, 5) if self.valid else None,
                'min_range_m': self.min_range_m, 'max_range_m': self.max_range_m,
                'last_valid_t': self.last_valid_t, 'source': self.source}


@dataclass(frozen=True)
class RangeLimits:
    max_age_s: float = .2
    require_valid: bool = True
    name: str = ''


def check_range_limits(report: RangeReport, now: float, limits: RangeLimits) -> list[str]:
    """Every violated limit (empty list = the reading may be used)."""
    if report.t_meas is None:
        return ['no_reading']
    bad = []
    if now - report.t_meas > limits.max_age_s + 1e-9:
        bad.append('stale')
    if limits.require_valid and not report.valid:
        bad.append('invalid')
    return bad


class RangeProvider(Protocol):
    source: str

    def on_reading(self, reading: RangeReading) -> None: ...
    def report(self, now: float) -> RangeReport: ...
    def history(self, now: float, window_s: float) -> list[RangeReading]: ...


def source_label(spec: UltrasonicSpec = DEFAULT_SPEC) -> str:
    return f"{SOURCE_PREFIX}:{spec_record(spec)['sha256'][:8]}"


@dataclass
class OwnUltrasonicRangeProvider:
    """Buffers the robot's own readings (time ordered) and reports the latest one."""
    spec: UltrasonicSpec = DEFAULT_SPEC
    keep_s: float = 5.
    source: str = field(init=False)

    def __post_init__(self):
        self.source = source_label(self.spec)
        self._buf: deque[RangeReading] = deque()
        self._last_valid_t: float | None = None

    def on_reading(self, reading: RangeReading) -> None:
        if self._buf and reading.t < self._buf[-1].t - 1e-12:
            raise ValueError('range readings must arrive in time order')
        if reading.valid and not (self.spec.min_range_m <= reading.range_m <= self.spec.sdk_clamp_m):
            raise ValueError('valid reading outside the sensor range')
        self._buf.append(reading)
        if reading.valid:
            self._last_valid_t = reading.t
        while self._buf and self._buf[0].t < reading.t - self.keep_s:
            self._buf.popleft()

    def report(self, now: float) -> RangeReport:
        latest = next((r for r in reversed(self._buf) if r.t <= now + 1e-12), None)
        common = dict(min_range_m=self.spec.min_range_m, max_range_m=self.spec.max_range_m, source=self.source,
                      last_valid_t=self._last_valid_t)
        if latest is None:
            return RangeReport(t_meas=None, age_s=None, valid=False, **common)
        age = float(now) - latest.t
        if not latest.valid:
            return RangeReport(t_meas=latest.t, age_s=age, valid=False, **common)
        return RangeReport(t_meas=latest.t, age_s=age, valid=True, range_m=latest.range_m,
                           sigma_m=self.spec.sigma_m(latest.range_m), **common)

    def history(self, now: float, window_s: float) -> list[RangeReading]:
        return [r for r in self._buf if now - window_s - 1e-12 <= r.t <= now + 1e-12]


def provider_config_for_condition(condition_name: str, spec: UltrasonicSpec = DEFAULT_SPEC) -> dict:
    """Identical sensor input for every communication condition (not a manipulated variable)."""
    from harness.zone_study_contract import CONDITIONS
    if condition_name not in CONDITIONS:
        raise ValueError(f'unknown condition: {condition_name!r}')
    record = spec_record(spec)
    return {'profile_id': PROFILE_ID, 'sensor_model_id': SENSOR_MODEL_ID, 'spec_sha256': record['sha256'],
            'source': source_label(spec), 'consumer': 'own executor (controller), not the LLM payload',
            'default_in_existing_bundles': 'off'}


class RangeHistoryWriter:
    """Own-reading history as JSONL in the run output (hashed by the common run record).

    Header row: schema, robot, sensor model, spec hash and source. Rows: the
    ``RangeReading`` fields only (t, range_m, valid).
    """

    def __init__(self, path: str | Path, robot_id: str, spec: UltrasonicSpec = DEFAULT_SPEC, *,
                 run_meta: Mapping | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open('x', encoding='utf-8')
        record = spec_record(spec)
        header = {'schema': HISTORY_SCHEMA, 'reading_schema': READING_SCHEMA, 'robot_id': robot_id,
                  'sensor_model_id': SENSOR_MODEL_ID, 'spec_sha256': record['sha256'], 'spec': record['spec'],
                  'source': source_label(spec), 'run_meta': dict(run_meta or {})}
        self._write(header)
        self.rows = 0

    def _write(self, row: Mapping) -> None:
        self._fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n')

    def append(self, reading: RangeReading) -> None:
        self._write(reading.as_dict())
        self.rows += 1

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.flush()
            self._fh.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def read_history(path: str | Path) -> tuple[dict, list[RangeReading]]:
    lines = Path(path).read_text(encoding='utf-8').splitlines()
    header = json.loads(lines[0])
    if header.get('schema') != HISTORY_SCHEMA:
        raise ValueError('not an own ultrasonic history file')
    rows = []
    for line in lines[1:]:
        row = json.loads(line)
        if set(row) != {'t', 'range_m', 'valid'}:
            raise ValueError('history row carries fields other than t, range_m, valid')
        rows.append(RangeReading(row['t'], float('nan') if row['range_m'] is None else row['range_m'],
                                 bool(row['valid'])))
    return header, rows

