"""Versioned, evaluation-only exclusion of previously observed kinematics.

Absolute world poses are compared; only the clock origin may differ. Extra
JSON fields never enter identity. No image, residual, score or control code is
read. A match needs >= window_s of consecutive, common-grid samples, including
both endpoints. The default 0.2 s is B's shortest horizon. Coarser historical
logs use their native common lattice (no interpolation or invented samples).

Tolerance (policy v1): 1e-6 m per position component, 1e-6 per rotation-matrix
element and 1e-6 s relative clock. This is ~1e5 times below the >=0.4 m start
offsets that make a trajectory new, but far above JSON float64 round-trip (exact)
and cross-build MuJoCo drift over a 0.2 s window, so a re-run of an already seen
trajectory cannot slip through on last-bit float noise (the v91 failure mode was
exact equality; an earlier 1e-9 draft would miss a 1e-8 m reproduction).
Rigid re-placements of the same relative motion are NOT detected (by design: the
held-out set reuses training command levels from different world poses).
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import numpy as np

POLICY = {'schema': 'ugrp.kinematic_overlap.v1', 'window_s': .2,
          'position_atol_m': 1e-6, 'rotation_element_atol': 1e-6,
          'time_atol_s': 1e-6, 'rtol': 0., 'clock_origin': 'free_constant_shift',
          'sampling': 'consecutive common lattice; integer-multiple periods; no interpolation',
          'short_prior': 'also exclude an entire shorter trace with at least two common samples',
          'identity_fields': ['t', 'base_position_m', 'base_rotation']}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


@dataclass
class Trace:
    source: str
    t: np.ndarray
    states: np.ndarray  # xyz, then row-major 3x3 rotation
    dt: float
    sha256: str


def trace(rows, source='<memory>'):
    # Project immediately. Never retain unrelated evaluation fields.
    projected = [{k: row[k] for k in POLICY['identity_fields']} for row in rows]
    t = np.asarray([r['t'] for r in projected], float)
    xyz = np.asarray([r['base_position_m'] for r in projected], float)
    rotation = np.asarray([r['base_rotation'] for r in projected], float)
    if (len(t) < 2 or xyz.shape != (len(t), 3) or rotation.shape != (len(t), 3, 3)
            or not all(np.isfinite(a).all() for a in (t, xyz, rotation))):
        raise ValueError('invalid kinematic shape/non-finite or too few samples: '+str(source))
    dt = float(np.median(np.diff(t)))
    if dt <= 0 or not np.allclose(np.diff(t), dt, atol=POLICY['time_atol_s'], rtol=0):
        raise ValueError('nonmonotonic/missing/irregular kinematic samples: '+str(source))
    if (not np.allclose(rotation.transpose(0, 2, 1) @ rotation, np.eye(3), atol=1e-5, rtol=0)
            or not np.allclose(np.linalg.det(rotation), 1., atol=1e-5, rtol=0)):
        raise ValueError('invalid base rotation: '+str(source))
    return Trace(str(source), t, np.column_stack((xyz, rotation.reshape(len(t), 9))),
                 dt, digest(projected))


def read_trace(path):
    path = Path(path)
    # The v91 raw access boundary is also enforced in this shared reader.
    if any(part.startswith('final-pair-v91-heldout-') for part in path.resolve().parts):
        if path.parts[-3:] not in (('eval_only', 'r1', 'pose.jsonl'),
                                   ('eval_only', 'r2', 'pose.jsonl')):
            raise ValueError('v91 access restricted to r1/r2 pose kinematics')
    with path.open() as stream:
        return trace((json.loads(line) for line in stream if line.strip()), str(path.resolve()))


def overlap(a, b, *, window_s=POLICY['window_s']):
    """Return the first witness, including time shift; None means disjoint.

    Search *every* possible start pair, including interior partial segments.
    Sorted-coordinate candidate lookup is exact (not rounded hash buckets).
    """
    if not np.isfinite(window_s) or window_s <= 0:
        raise ValueError('positive declared overlap window required')
    atol = np.array([POLICY['position_atol_m']]*3+[POLICY['rotation_element_atol']]*9)
    clock_tol = POLICY['time_atol_s']
    period = max(a.dt, b.dt)
    sa, sb = round(period/a.dt), round(period/b.dt)
    if abs(sa*a.dt-period) > clock_tol or abs(sb*b.dt-period) > clock_tol:
        raise ValueError('incommensurate sample periods; cannot certify disjointness')
    intervals = min(max(1, int(np.ceil((window_s-clock_tol)/period))),
                    (len(a.t)-1)//sa, (len(b.t)-1)//sb)
    if intervals < 1:
        raise ValueError('no two common samples; cannot certify disjointness')
    count = intervals+1
    na, nb = len(a.t)-intervals*sa, len(b.t)-intervals*sb
    if na <= 0 or nb <= 0:
        raise ValueError('trace shorter than declared overlap window')
    if np.any((a.states.min(0) > b.states.max(0)+atol) |
              (b.states.min(0) > a.states.max(0)+atol)):
        return None
    coord = int(np.argmax(np.ptp(b.states[:nb], axis=0)/atol))
    order = np.argsort(b.states[:nb, coord], kind='stable')
    sorted_values = b.states[order, coord]
    offsets = np.arange(count)
    for i in range(na):
        value = a.states[i, coord]
        lo, hi = np.searchsorted(sorted_values, [value-atol[coord], value+atol[coord]],
                                  side='left')
        hi = np.searchsorted(sorted_values, value+atol[coord], side='right')
        candidates = order[lo:hi]
        candidates = candidates[np.all(np.abs(b.states[candidates]-a.states[i]) <= atol, axis=1)]
        ia = i+offsets*sa
        for j in candidates:
            ib = int(j)+offsets*sb
            if (np.all(np.abs((a.t[ia]-a.t[i])-(b.t[ib]-b.t[j])) <= clock_tol)
                    and np.all(np.abs(a.states[ia]-b.states[ib]) <= atol)):
                return {'status': 'PREVIOUSLY_SEEN', 'candidate': a.source, 'prior': b.source,
                        'candidate_indices': [i, int(ia[-1])],
                        'prior_indices': [int(j), int(ib[-1])], 'samples': count,
                        'matched_duration_s': float(min(a.t[ia[-1]]-a.t[i], b.t[ib[-1]]-b.t[j])),
                        'clock_shift_s': float(a.t[i]-b.t[j]),
                        'max_position_difference_m': float(np.max(np.abs(a.states[ia, :3]-b.states[ib, :3]))),
                        'max_rotation_element_difference': float(np.max(np.abs(a.states[ia, 3:]-b.states[ib, 3:])))}
    return None


def audit(candidates, prior):
    if not candidates or not prior:
        raise ValueError('nonempty candidates and exclusion corpus required')
    pairs, witnesses = [], []
    for candidate in candidates:
        for previous in prior:
            match = overlap(candidate, previous)
            pairs.append({'candidate': candidate.source, 'prior': previous.source,
                          'status': 'PREVIOUSLY_SEEN' if match else 'DISJOINT'})
            if match:
                witnesses.append(match)
    return {'policy': dict(POLICY), 'status': 'PREVIOUSLY_SEEN' if witnesses else 'DISJOINT',
            'comparisons': pairs, 'witnesses': witnesses,
            'inputs': [{'path': t.source, 'kinematic_sha256': t.sha256,
                        'samples': len(t.t), 'period_s': t.dt} for t in candidates+prior]}
