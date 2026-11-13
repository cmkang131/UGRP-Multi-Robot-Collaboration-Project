"""RGB/issued-posture survey and observed-entry baseline adapter.

Coordinates are metres in the stationary survey's initial body frame (+y left).
The caller must hold the wheels still, allow commands to settle, and return pan
to 1500 before approach. No measured pose or world heading is accepted here.
The baseline module and contract are trusted code dependencies, not task data.
Deployment must remove the baseline's unused truth-derived hint helper.
"""
from __future__ import annotations

import math
from statistics import median


ENTRY_FIELDS = frozenset({"kind", "x", "y", "bearing_rad", "distance_m",
                          "observations", "dispersion"})
MIN_RANGE_M = .10
MAX_RANGE_M = 4.0
CENTER_CORRECTION_M = .0185
MERGE_RADIUS_M = .10


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _validate_entry(entry):
    if type(entry) is not dict or set(entry) != ENTRY_FIELDS:
        raise ValueError("entry must contain exactly the observed-entry fields")
    if type(entry["kind"]) is not str or entry["kind"] not in ("red", "cyan"):
        raise ValueError("entry kind must be red or cyan")
    for key in ("x", "y", "bearing_rad", "distance_m", "dispersion"):
        if not _number(entry[key]):
            raise ValueError("entry numeric fields must be finite plain numbers")
    if type(entry["observations"]) is not int or entry["observations"] < 2:
        raise ValueError("entry needs at least two frame observations")
    d = math.hypot(entry["x"], entry["y"])
    b = math.atan2(entry["y"], entry["x"])
    if not MIN_RANGE_M <= entry["distance_m"] <= MAX_RANGE_M:
        raise ValueError("entry distance outside survey range")
    if not -math.pi <= entry["bearing_rad"] <= math.pi or entry["dispersion"] < 0:
        raise ValueError("invalid bearing or dispersion")
    delta = entry["bearing_rad"] - b
    if (not math.isclose(d, entry["distance_m"], rel_tol=1e-9, abs_tol=1e-9)
            or abs(math.atan2(math.sin(delta), math.cos(delta))) > 1e-9):
        raise ValueError("entry polar and Cartesian coordinates disagree")


class Survey:
    """Observe every whole red/cyan component, without target selection.

    Only pan (servo 6) may change during a survey. Posture contains issued PWM
    integers for 3,4,5,6, optionally 1; it is not joint telemetry. This API has
    no wheel input and cannot verify that the caller actually kept the base
    stationary. evidence counts all decoded-frame candidates, including rejects.
    """

    def __init__(self, baseline_module):
        self._baseline = baseline_module
        self._tracks = []
        self._fixed_posture = None
        self.evidence = {key: 0 for key in (
            "frames", "components", "whole", "projection_rejected",
            "range_rejected", "accepted", "merged", "new_tracks")}

    def observe(self, jpeg: bytes, posture: dict[int, int]):
        if type(jpeg) is not bytes or not jpeg:
            raise ValueError("jpeg must be nonempty bytes")
        if (type(posture) is not dict or not {3, 4, 5, 6} <= set(posture)
                or not set(posture) <= {1, 3, 4, 5, 6}
                or any(type(k) is not int or type(v) is not int or not 500 <= v <= 2500
                       for k, v in posture.items())):
            raise ValueError("posture must contain only issued servo PWM integers")
        fixed = {k: v for k, v in posture.items() if k != 6}
        if self._fixed_posture is not None and fixed != self._fixed_posture:
            raise ValueError("stationary survey permits pan changes only")

        # Lazy imports keep the boundary self-test independent of vision packages.
        import cv2
        import numpy as np
        if __package__:
            from .ground_projection import measure_contact
        else:
            from ground_projection import measure_contact

        frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if frame is None or frame.shape[:2] != (480, 640):
            raise ValueError("own RGB frame must decode to 640x480")
        self._fixed_posture = fixed
        self.evidence["frames"] += 1
        base = self._baseline
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        lens = (frame.max(axis=2) < base.LENS_BLACK_MAX).astype(np.uint8)
        k = 2 * base.CLIP_DILATE_PX + 1
        rim = cv2.dilate(lens, np.ones((k, k), np.uint8)) > 0
        detections = []
        for kind in ("red", "cyan"):
            mask = base._HSV_RANGES[kind](hsv[..., 0], hsv[..., 1], hsv[..., 2]).astype(np.uint8)
            n, labels, stats, cents = cv2.connectedComponentsWithStats(mask, connectivity=8)
            for label in range(1, n):
                area = int(stats[label, cv2.CC_STAT_AREA])
                if area < base.MIN_COMPONENT_PX:
                    continue
                self.evidence["components"] += 1
                x, y, w, h = map(int, stats[label, :4])
                component = labels == label
                blob = {"A": area, "cx": float(cents[label, 0]), "cy": float(cents[label, 1]),
                        "w": w, "x0": x, "y0": y, "x1": x+w-1, "y1": y+h-1,
                        "clipped": bool(rim[component].any())}
                if not base._is_whole(blob):
                    continue
                self.evidence["whole"] += 1
                rows, cols = np.nonzero(component)
                # One lowest occupied pixel per column, in increasing x order.
                bottom = np.full(640, -1, dtype=int)
                np.maximum.at(bottom, cols, rows)
                occupied = np.flatnonzero(bottom >= 0)
                blob["bottom_pixels"] = np.column_stack((occupied, bottom[occupied]))
                contact = measure_contact(blob, posture)
                if contact is None or not all(_number(v) for v in contact):
                    self.evidence["projection_rejected"] += 1
                    continue
                cx, cy = contact
                radial = math.hypot(cx, cy)
                distance = radial + CENTER_CORRECTION_M
                if radial <= 0 or not MIN_RANGE_M <= distance <= MAX_RANGE_M:
                    self.evidence["range_rejected"] += 1
                    continue
                scale = distance / radial
                detections.append({"kind": kind, "x": cx*scale, "y": cy*scale})
        self._merge(detections)

    def _merge(self, detections):
        """Validate atomically, then greedily match old tracks once per frame."""
        if type(detections) is not list:
            raise ValueError("detections must be a plain list")
        for item in detections:
            if (type(item) is not dict or set(item) != {"kind", "x", "y"}
                    or type(item["kind"]) is not str or item["kind"] not in ("red", "cyan")
                    or not _number(item["x"]) or not _number(item["y"])
                    or not MIN_RANGE_M <= math.hypot(item["x"], item["y"]) <= MAX_RANGE_M):
                raise ValueError("invalid projected detection")
        pairs = []
        for i, track in enumerate(self._tracks):
            x = median(p[0] for p in track["points"])
            y = median(p[1] for p in track["points"])
            for j, item in enumerate(detections):
                d = math.hypot(item["x"]-x, item["y"]-y)
                if item["kind"] == track["kind"] and d <= MERGE_RADIUS_M:
                    pairs.append((d, i, j))
        used_tracks, used_detections = set(), set()
        for _, i, j in sorted(pairs):
            if i in used_tracks or j in used_detections:
                continue
            item = detections[j]
            self._tracks[i]["points"].append((item["x"], item["y"]))
            used_tracks.add(i)
            used_detections.add(j)
        for j, item in enumerate(detections):
            if j not in used_detections:
                self._tracks.append({"kind": item["kind"], "points": [(item["x"], item["y"])]})
        self.evidence["accepted"] += len(detections)
        self.evidence["merged"] += len(used_detections)
        self.evidence["new_tracks"] += len(detections)-len(used_detections)

    def entries(self) -> list[dict]:
        """Fresh plain-data snapshot in first-observed track order.

        observations counts matched frames (not pixels); dispersion is the median
        Euclidean residual in metres about the coordinate-wise median position.
        Snapshot once after survey; later observations can change list indices.
        """
        result = []
        for track in self._tracks:
            points = track["points"]
            if len(points) < 2:
                continue
            x, y = median(p[0] for p in points), median(p[1] for p in points)
            distance = math.hypot(x, y)
            if not MIN_RANGE_M <= distance <= MAX_RANGE_M:
                continue
            result.append({"kind": track["kind"], "x": x, "y": y,
                           "bearing_rad": math.atan2(y, x), "distance_m": distance,
                           "observations": len(points),
                           "dispersion": median(math.hypot(px-x, py-y) for px, py in points)})
        return result


S_POSTURES = ((740, 2320), (740, 2380), (700, 2440), (640, 2440), (500, 2500))
SETTLE_TICKS = 5
VISIBILITY_CX_PX = 80.0
CONTROL_LIMIT = 700
# Five poses (original, three alternatives, original), then a fresh final check.
TERMINAL_RESERVE = 5 * SETTLE_TICKS + 1


def _down_pitch(posture):
    """Command-only review-v3 optical pitch, including joint and PWM clamps."""
    p = {k: min(2500, max(500, posture[k])) for k in (3, 4, 5)}
    shoulder = min(2.80, max(-.15, math.pi/2-(p[5]-1589)*math.pi/2000))
    elbow = min(1.80, max(-1.80, -(p[4]-1553)*math.pi/2000))
    wrist = min(1.80, max(-1.80, (p[3]-1554)*math.pi/2000))
    return -(shoulder + elbow + wrist + math.radians(10))


def _variant_servo(base, variant):
    """Instance-local interception; never patch the trusted baseline's globals."""
    class VariantServo(base.ApproachServo):
        def __init__(self, *args):
            self.s_index = 0
            self._s_active = False
            self._s_left = 0
            self._s_veto = False
            self._terminal = None
            self._finished = False
            self._fresh_prev = None
            self.terminal_ready = False
            self.v_attempts = []
            self.s_transitions = []
            self._variant = variant
            super().__init__(*args)

        def __setattr__(self, name, value):
            if name == 'posture':
                # Retain the uncapped request for ACT, even when S changes output.
                object.__setattr__(self, '_intended_posture', dict(value))
                if self._s_active and self._terminal is None:
                    value = self._cap(value)
            object.__setattr__(self, name, value)

        def _cap(self, posture):
            requested = _down_pitch(posture)
            candidates = [dict(posture) for _ in S_POSTURES]
            for p, (p3, p4) in zip(candidates, S_POSTURES):
                p.update({3: p3, 4: p4})
            # Closest schedule pose at least as downward; deepest pose is the
            # camera upper clamp. The index can never decrease while S is active.
            index = next((i for i in range(self.s_index, len(candidates))
                          if _down_pitch(candidates[i]) >= requested - 1e-12), 4)
            self.s_index = index
            return candidates[index]

        def _hold(self, now, posture):
            if self._s_active and self._terminal is None:
                posture = self._cap(posture)
                object.__setattr__(self, 'posture', posture)
            return super()._hold(now, posture)

        def _pulse_row(self, now, kind, sgn, secs):
            if self._s_veto:
                return self._hold(now, self.posture)
            return super()._pulse_row(now, kind, sgn, secs)

        def _observe(self, jpeg):
            d, bearing, _ = self._est()
            raw = base.components(jpeg, self.object_kind)
            gated = [b for b in raw if base._identity_dev(b, d, bearing) <= base.POS_GATE_M]
            prev = self._fresh_prev
            if prev is None and self.tracker.last_accept == self.ticks - 1:
                prev = self.tracker.track
            if prev is not None:
                gated = [b for b in gated if math.hypot(b['cx']-prev['cx'], b['cy']-prev['cy'])
                         <= base.TRACK_GATE_PX]
                blob = min(gated, key=lambda b: math.hypot(b['cx']-prev['cx'], b['cy']-prev['cy']),
                           default=None)
            else:
                blob = min(gated, key=lambda b: base._identity_dev(b, d, bearing), default=None)
            # No held/stale blob can count as a current-frame observation.
            self._fresh_prev = None if blob is None else dict(blob)
            return blob, len(raw), len(gated)

        def _visible(self, blob):
            return (blob is not None and base._is_whole(blob)
                    and abs(blob['cx'] - base.CX_REF_PX) <= VISIBILITY_CX_PX)

        def _stop_tick(self, now, source, observation=None, counted=False):
            tick = self.ticks - 1 if counted else self.ticks
            if not counted:
                self.ticks += 1
            blob, n_raw, n_gated = observation or (None, 0, 0)
            row = {'tick': tick, 't': round(now, 3), 'stage': self.stage,
                   'state': source, 'cmd_src': source, 'pulse': None,
                   'posture': {str(k): self.posture[k] for k in (3, 4)},
                   'odo': [round(self.pos[0], 4), round(self.pos[1], 4), round(self.yaw, 4)],
                   'n_blobs': n_raw, 'n_gated': n_gated,
                   'A': None if blob is None else blob['A'],
                   'cx': None if blob is None else blob['cx'],
                   'cy': None if blob is None else blob['cy'],
                   'whole': None if blob is None else base._is_whole(blob),
                   'clipped': None if blob is None else bool(blob.get('clipped')),
                   's_index': self.s_index, 'terminal_ready': self.terminal_ready}
            if counted:
                row['baseline_terminal'] = dict(self.trace[-1])
                self.trace[-1] = row
            else:
                self.trace.append(row)
            return self._hold(now, self.posture)

        def _begin_terminal(self, now, counted=False):
            self._terminal = {'reason': self.reason, 'arrival': self.arrival,
                              'posture': dict(self._intended_posture), 'phase': 0,
                              'left': SETTLE_TICKS - 1}
            self.arrived = False
            self.reason = None
            self.arrival = None
            self._s_veto = False
            self.posture = dict(self._terminal['posture'])
            return self._stop_tick(now, 'terminal_settle', counted=counted)

        def _terminal_step(self, jpeg, now):
            term = self._terminal
            if term['left']:
                term['left'] -= 1
                return self._stop_tick(now, 'terminal_settle')
            observation = self._observe(jpeg)
            visible = self._visible(observation[0])
            phase = term['phase']
            self.v_attempts.append({'tick': self.ticks, 'phase': phase,
                                    'posture': dict(self.posture), 'visible': visible,
                                    'compatible': phase in (0, 4)})
            if 'V' not in variant or phase == 4 or (phase == 0 and visible):
                self.terminal_ready = visible if 'V' in variant else True
                self.reason = term['reason'] if self.terminal_ready else 'visibility_exhausted'
                self.arrival = dict(term['arrival'] or {}, tick=self.ticks, t=now)
                self.arrived = self._finished = True
                return self._stop_tick(now, 'terminal_checked', observation)
            term['phase'] += 1
            phase = term['phase']
            self.posture = (base.posture_for((.25, .20, .30)[phase-1]) if phase < 4
                            else dict(term['posture']))
            term['left'] = SETTLE_TICKS - 1
            return self._stop_tick(now, 'visibility_relook', observation)

        def step(self, jpeg, now):
            if self._finished:
                raise RuntimeError('approach servo stepped after terminal decision')
            if self._terminal is not None:
                return self._terminal_step(jpeg, now)
            # Reserve restoration/relook ticks inside, not after, the 700 cap.
            if self.ticks >= CONTROL_LIMIT - TERMINAL_RESERVE:
                self.reason, self.arrival = 'timeout', {'tick': self.ticks, 't': now, 'A': None}
                return self._begin_terminal(now)
            observation = self._observe(jpeg)
            blob = observation[0]
            if 'S' in variant and not self._s_left and blob is not None and blob['y1'] >= 425:
                if self.s_index < 4:
                    self.s_index += 1
                    self._s_active = True
                    self.s_transitions.append({'tick': self.ticks, 'index': self.s_index})
                    # Set the scheduled pose directly, without changing the
                    # baseline's most recent intended posture.
                    p = dict(self.posture)
                    p.update(zip((3, 4), S_POSTURES[self.s_index]))
                    object.__setattr__(self, 'posture', self._cap(p))
                    self._s_left = SETTLE_TICKS
            self._s_veto = self._s_left > 0
            if self._s_veto:
                self._s_left -= 1
                return self._stop_tick(now, 's_settle', observation)
            result = super().step(jpeg, now)
            if self.arrived:
                return self._begin_terminal(now, counted=True)
            return result

        def record(self):
            result = super().record()
            result.update(variant=variant, terminal_ready=self.terminal_ready,
                          s_index=self.s_index, s_transitions=list(self.s_transitions),
                          v_attempts=list(self.v_attempts), visibility_center_tolerance_px=VISIBILITY_CX_PX,
                          intended_terminal=None if self._terminal is None else dict(self._terminal))
            if not self.terminal_ready:
                result['arrived'] = False
            return result

    return VariantServo


class Approach:
    """RGB/commands only; variants baseline, S, V, SV (no side tactic).

    Baseline is an unmodified proxy. Variants reserve 26 of the 700 control ticks
    for terminal restoration/visibility. V accepts whole identity-gated blobs
    within +/-80 px of CX_REF_PX, only after five stopped posture ticks.
    arrived means processing ended; terminal_ready must also be true before ACT.
    A failed V ends with reason visibility_exhausted, never an ACT handover.
    """

    __slots__ = ("_servo",)

    def __init__(self, baseline_module, contract, entries: list, index: int, variant="baseline"):
        if type(variant) is not str or variant not in ("baseline", "S", "V", "SV"):
            raise ValueError("unknown variant (expected baseline, S, V, SV)")
        if type(entries) is not list:
            raise ValueError("entries must be a plain list")
        for entry in entries:
            _validate_entry(entry)
        if type(index) is not int or not 0 <= index < len(entries):
            raise ValueError("index must select an observed entry")
        entry = entries[index]
        hint = {"bearing_rad": entry["bearing_rad"], "distance_m": entry["distance_m"],
                "facing_rad": entry["bearing_rad"]}
        servo_type = (baseline_module.ApproachServo if variant == "baseline"
                      else _variant_servo(baseline_module, variant))
        object.__setattr__(self, "_servo", servo_type(entry["kind"], contract, hint))

    def __getattr__(self, name):
        return getattr(self._servo, name)

    def __setattr__(self, name, value):
        setattr(self._servo, name, value)

    def step(self, jpeg, now):
        if type(jpeg) is not bytes or not _number(now):
            raise ValueError("step accepts only JPEG bytes and a finite command clock")
        return self._servo.step(jpeg, now)

    def record(self):
        return self._servo.record()


def boundary_tests():
    """Dependency-free contract tests; no camera, model, or simulator execution."""
    from types import SimpleNamespace

    class FakeServo:
        def __init__(self, kind, contract, hint):
            self.object_kind, self.hint = kind, hint
            self.ticks = 0

        def step(self, jpeg, now):
            self.ticks += 1
            return {"t": now}

        def record(self):
            return {"ticks_code": self.ticks}

    checks = 0

    def rejects(call):
        nonlocal checks
        try:
            call()
        except ValueError:
            checks += 1
        else:
            raise AssertionError("invalid boundary input accepted")

    baseline = SimpleNamespace(ApproachServo=FakeServo)
    survey = Survey(baseline)
    red = {"kind": "red", "x": 1., "y": 0.}
    survey._merge([red, dict(red, x=1.08)])
    assert survey.entries() == []
    survey._merge([dict(red, x=1.01), dict(red, x=1.07)])
    entries = survey.entries()
    assert len(entries) == 2 and all(e["observations"] == 2 for e in entries)
    assert all(set(e) == ENTRY_FIELDS for e in entries)
    assert survey.evidence["accepted"] == 4 and survey.evidence["merged"] == 2
    checks += 4
    before = survey.entries(), dict(survey.evidence)
    for bad in (dict(red, x=float("nan")), dict(red, y=True), dict(red, x=5.),
                dict(red, kind="green"), dict(red, truth=1), dict(red, x=0.)):
        rejects(lambda bad=bad: survey._merge([red, bad]))
        assert (survey.entries(), survey.evidence) == before
    rejects(lambda: survey._merge((red,)))
    survey._merge([dict(red, kind="cyan")])
    assert survey.entries() == entries
    checks += 1
    for key in ("truth", "gt", "target", "seed", "plan", "cargo_pose_m", "spawns"):
        rejects(lambda key=key: Approach(baseline, None, [dict(entries[0], **{key: 1})], 0))
    for index in (-1, 2, True, 0., "0", None):
        rejects(lambda index=index: Approach(baseline, None, entries, index))
    for patch in ({"observations": 1}, {"observations": True}, {"distance_m": float("inf")},
                  {"distance_m": .5}, {"bearing_rad": 1.}, {"dispersion": -1.}, {"x": False}):
        rejects(lambda patch=patch: Approach(baseline, None, [dict(entries[0], **patch)], 0))
    rejects(lambda: Approach(baseline, None, [entries[0], dict(entries[1], truth=1)], 0))
    rejects(lambda: Approach(baseline, None, tuple(entries), 0))
    for variant in ("unknown", "s", "S+V"):
        rejects(lambda variant=variant: Approach(baseline, None, entries, 0, variant))
    approach = Approach(baseline, None, entries, 1)
    assert set(approach.hint) == {"bearing_rad", "distance_m", "facing_rad"}
    assert approach.hint["facing_rad"] == entries[1]["bearing_rad"]
    assert approach.hint["distance_m"] == entries[1]["distance_m"]
    entries[1]["distance_m"] = 3.
    assert approach.hint["distance_m"] != 3.
    approach.ticks = 4
    assert approach.step(b"fake-jpeg", 0.) == {"t": 0.}
    assert approach.record() == {"ticks_code": 5}
    rejects(lambda: approach.step({"truth": 1}, 0.))
    checks += 6
    return {"status": "PASS", "checks": checks}


def variant_tests():
    """Execute the sanitized controller with mocked RGB components, stdlib only.

    No image libraries or simulator are loaded. JPEG decoding/segmentation is
    replaced at components(), not at the controller or command/odometry path.
    Byte-identical repeated camera images cannot prove sensor freshness; callers
    must supply a new capture after each issued command has run for one tick.
    """
    import copy
    import importlib.util
    import json
    from pathlib import Path
    import sys
    from types import ModuleType, SimpleNamespace
    from unittest.mock import patch

    path = Path(__file__).with_name('approach_core.py')
    spec = importlib.util.spec_from_file_location('_test_approach_core', path)
    base = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'cv2': ModuleType('cv2'), 'numpy': ModuleType('numpy')}):
        spec.loader.exec_module(base)
    contract = SimpleNamespace(command=lambda row: copy.deepcopy(row))
    checks = 0
    frames = {}
    base.components = lambda jpeg, kind: copy.deepcopy(frames.get(jpeg, []))

    def entry(distance=.2):
        return {'kind': 'red', 'x': distance, 'y': 0., 'bearing_rad': 0.,
                'distance_m': distance, 'observations': 2, 'dispersion': 0.}

    def blob(**kwargs):
        return dict({'A': base.A_REF_PX, 'cx': base.CX_REF_PX, 'cy': 327.,
                     'w': 150, 'x0': 210, 'x1': 360, 'y0': 250, 'y1': 400,
                     'clipped': False}, **kwargs)

    frames[b'whole'] = [blob()]
    frames[b'lower'] = [blob(y1=450, clipped=True)]
    frames[b'clipped'] = [blob(clipped=True)]
    frames[b'offcenter'] = [blob(cx=base.CX_REF_PX+81)]
    frames[b'wrong'] = [blob(A=100)]
    frames[b'two'] = [blob(cx=base.CX_REF_PX+20), blob(A=100)]

    # Exact JSON bytes, command rows, full record and trace: baseline proxy does
    # not instantiate the subclass, pre-observe, add keys or change termination.
    for distance, jpeg in ((.2, b'whole'), (.8, b'lower'), (.8, b'missing')):
        observed = entry(distance)
        proxy = Approach(base, contract, [observed], 0)
        direct = base.ApproachServo('red', contract, dict(proxy.hint))
        assert type(proxy._servo) is base.ApproachServo
        for tick in range(701):
            a, b = proxy.step(jpeg, tick*.1), direct.step(jpeg, tick*.1)
            assert json.dumps(a).encode() == json.dumps(b).encode()
            assert proxy.trace == direct.trace
            assert json.dumps(proxy.record()).encode() == json.dumps(direct.record()).encode()
            checks += 1
            if direct.arrived:
                break
        assert direct.arrived

    s = Approach(base, contract, [entry(.8)], 0, 'S')
    original = (copy.deepcopy(s.pos), s.yaw, list(s.nav_steps))
    pitches = []
    for tick in range(20):
        cmd = s.step(b'lower', tick*.1)
        assert cmd['wheels'] == [0.]*4
        assert (s.pos, s.yaw, s.nav_steps) == original
        assert s.ticks == tick+1 and len(s.trace) == tick+1
        pitches.append(_down_pitch(s.posture))
        assert (s.posture[3], s.posture[4]) == S_POSTURES[tick//5+1]
        checks += 1
    assert pitches == sorted(pitches)
    assert [r['tick'] for r in s.s_transitions] == [0, 5, 10, 15]
    for distance in (.2, .35, 1.):
        s.posture = base.posture_for(distance)
        assert (s.posture[3], s.posture[4]) == S_POSTURES[-1]
    # Direct defense-in-depth veto exercises the actual baseline _odo boundary.
    s._s_veto = True
    cmd = s._pulse_row(2., 'fwd', 1., .1)
    assert cmd['wheels'] == [0.]*4 and (s.pos, s.yaw, s.nav_steps) == original
    checks += 5
    # After the finite S dwell the original nav pulse is still available.
    s.step(b'missing', 2.1)
    assert len(s.nav_steps) == len(original[2])-1
    assert s.pos != original[0] or s.yaw != original[1]
    assert s.trace[-1]['pulse'] is not None
    checks += 1

    v = Approach(base, contract, [entry()], 0, 'V')
    assert v._observe(b'wrong')[0] is None
    assert v._observe(b'two')[0]['cx'] == base.CX_REF_PX+20
    assert v._observe(b'missing')[0] is None
    assert v._observe(b'whole')[0] is not None
    for jpeg in (b'clipped', b'offcenter'):
        assert not v._visible(v._observe(jpeg)[0])
    checks += 6

    def terminal(variant, reason='handover_near_no_blob', ticks=0):
        v = Approach(base, contract, [entry()], 0, variant)
        v.stage = 'approach'
        v.posture = base.posture_for(.3)
        intended = dict(v.posture)
        if variant == 'SV':
            v._s_active = True
            v.s_index = 4
            v.posture = intended
            assert v.posture != intended
        v.reason = reason
        v.arrival = {'tick': ticks, 'A': None}
        v.ticks = ticks
        v._begin_terminal(ticks*.1)
        assert v.posture == intended and not v.arrived
        return v, intended

    for variant in ('V', 'SV', 'S'):
        for jpeg in (b'whole', b'missing', b'clipped', b'offcenter', b'wrong'):
            v, intended = terminal(variant)
            # A stale tracker entry is not visibility evidence on an empty frame.
            v.tracker.track = blob()
            v.tracker.last_accept = v.ticks-1
            odo = (list(v.pos), v.yaw)
            for tick in range(1, 27):
                cmd = v.step(jpeg, tick*.1)
                assert cmd['wheels'] == [0.]*4 and (v.pos, v.yaw) == odo
                assert len(v.trace) == v.ticks
                if tick < 5:
                    assert not v.arrived and not v.v_attempts
                if v.arrived:
                    break
            assert v.arrived and v.posture == intended
            success = jpeg == b'whole' or variant == 'S'
            assert v.terminal_ready == success
            assert v.reason == ('handover_near_no_blob' if success else 'visibility_exhausted')
            assert len(v.v_attempts) == (1 if success else 5)
            assert v.ticks == (6 if success else 26)
            if not success:
                assert not v.record()['arrived']
                assert [a['tick'] for a in v.v_attempts] == [5, 10, 15, 20, 25]
            checks += 1

    # Seeing the target at an alternative posture never authorizes ACT there.
    v, intended = terminal('SV')
    for tick in range(1, 26):
        jpeg = b'whole' if tick in (10, 15, 20) else b'missing'
        v.step(jpeg, tick*.1)
    assert not v.terminal_ready and v.posture == intended
    assert [a['visible'] for a in v.v_attempts] == [False, True, True, True, False]
    checks += 1

    # All baseline termination paths are intercepted, with intended posture
    # restored and an actual post-settle capture required before arrived=True.
    for reason in ('arrived', 'settled', 'handover_near_clipped', 'handover_near_no_blob',
                   'search_exhausted'):
        v = Approach(base, contract, [entry()], 0, 'SV')
        intended = base.posture_for(.3)
        def finish(self, jpeg, now):
            self.ticks += 1
            self.posture = dict(intended)
            self.trace.append({'tick': self.ticks-1, 'pulse': None})
            self.arrived, self.reason = True, reason
            self.arrival = {'tick': self.ticks-1}
            return self._hold(now, self.posture)
        with patch.object(base.ApproachServo, 'step', finish):
            v.step(b'whole', 0.)
            assert not v.arrived and v.posture == intended
            for tick in range(1, 6):
                v.step(b'whole', tick*.1)
        assert v.arrived and v.terminal_ready and v.reason == reason
        assert v.ticks == len(v.trace) == 6
        checks += 1

    for variant in ('S', 'V', 'SV'):
        v = Approach(base, contract, [entry(.8)], 0, variant)
        # An indefinitely running baseline still leaves a finite terminal budget.
        def forever(self, jpeg, now):
            self.ticks += 1
            self.trace.append({'tick': self.ticks-1, 'pulse': None})
            return self._hold(now, self.posture)
        with patch.object(base.ApproachServo, 'step', forever):
            for tick in range(CONTROL_LIMIT):
                v.step(b'missing', tick*.1)
                if v.arrived:
                    break
        assert v.arrived and v.ticks <= CONTROL_LIMIT and len(v.trace) == v.ticks
        assert v.reason == ('timeout' if variant == 'S' else 'visibility_exhausted')
        assert v.ticks == (680 if variant == 'S' else 700)
        checks += 1
    return {'status': 'PASS', 'checks': checks, 'vision': 'mocked components; no CV or simulation'}


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if not args.self_test:
        parser.error("only --self-test is supported")
    print(json.dumps({'boundary': boundary_tests(), 'variants': variant_tests()}, sort_keys=True))
