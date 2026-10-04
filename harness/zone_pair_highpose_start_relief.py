"""v98-only start-state relief for the base-motion sweep guard: a robot that STARTS inside the margin may move on
if it does not get worse.

Probe 3358372e (raise_high, 8.7 s): both robots stand at the authored dock x = -0.8982 m. ``PairSweepGuard.motion_clear``
tests the zero-displacement start sample too, so every body-point/wall pair that is already inside the margin
(40-60 mm: base 20 + residual 15 + pad 5 + sigma terms) fails sample 0 for ANY command, including one that moves away
from the wall. r1 (-55.3 mm, rear-left chassis corner against ``wall_west``) was vetoed first; r2 (-42.6 mm) would have
been. The recorded commands moved away: r1 -55 -> -28 mm. The real clearance was 34 mm (offline evaluation only), no contact.
Cause: dock pose + authored chassis rear extent (-0.15 m, a conservative authored envelope; the sim robot reaches
-0.093 m) + margin, with a start-sample test that has no way out. Not an isotropic-sigma problem (sigma = 0 still fails).

The rule (coordinator ruling, option 2; the user allowed guard relaxation on 9/29). It only ever runs AFTER the frozen
guard said "not clear" and only when some pair is already negative at the unmoved start sample:

* a pair that starts clear must stay >= 0 at every swept sample, exactly as today;
* a pair that starts inside the margin must not get worse than its floor at any swept sample (floor below);
* a pair whose point starts inside the wall box (``start_inside_raw``: ``_rect_distance`` clamps to 0 there) must also
  not get deeper (its signed distance must not drop), because the clamp cannot show depth;
* a pair whose point starts OUTSIDE the box (raw signed distance >= 0) must stay outside (signed >= 0) at every swept
  sample, with no slack: relief never admits a new entry into an obstacle box (review 5 finding 1, coordinator
  2026-10-04; without it the group floor let r2's command forward .2 / left .2 / turn -.3 enter to -25 mm);
* nothing else changes: arm and transition checks, the margin, the pad, the gain and every answer for a start with no
  negative pair are the frozen guard's (tests compare bit for bit). Mirror disagreement fails closed.

Two readings of "pair" (``SCOPE``). ``'group'`` (default): the floor of a start-negative pair is the worst clearance of
its (part, wall) group at the start, minus ``EPS_M``. ``'pair'``: the floor is the pair's own start clearance minus
``EPS_M`` (the literal "never worse"). Both give the same answer for r1. They differ for r2: its estimated rear
corners start 9.6-14 mm BEYOND the 50 mm wall's far face and drive into the wall box as the robot moves forward (clamped
clearance -33 -> -42.6 mm) while the points already in the box leave it. 'pair' vetoes r2 (7 pairs worsen by up to
14.2 mm), 'group' admits it (the group's worst stays -42.6 -> -42.7 mm, 0.09 mm from the yaw-lever term, hence
``EPS_M`` = 1 mm instead of a bare numeric epsilon). The estimated rigid body straddling a wall is impossible; it only
exists because the estimate is wrong (below).

Known localization-consistency issue, NOT fixed here (coordinator schedules it): at 8.7 s of probe 3358372e the position
estimates were far outside their own covariance (offline evaluation against the simulator pose, never an input):
r2 (-0.9370, -0.8786) against truth (-0.8981, -0.8500), error 48 mm at sigma_x 1.5 mm / sigma_y 2.0 mm, NEES (2 dof)
741; r1 error 32 mm (28 mm along x), NEES 221 (sigma_x 19 mm but a correlated, elongated ellipse). The chi-square 99.9 %
bound for 2 dof is 13.8: both filters were overconfident, r2 by a wide margin. A radial comparison (error / std_xy)
understates it. A filter whose NEES sits far above its chi-square bound is overconfident (Bar-Shalom, Li, Kirubarajan:
NEES/ANEES consistency tests); the usual remedies are covariance inflation or extra process noise when the NEES test
fails, an adaptive noise estimate, split covariance intersection for correlated measurements and, for particle
filters, random-particle injection (Thrun, Burgard, Fox). This relief neither trusts nor corrects the estimate: a
confident 39 mm error toward a wall would defeat any margin.

Probe af2f7c2a (raise_high, 10.9 s, r2), offline evaluation against the simulator pose: the estimate was 16.7 mm off the
truth (13.8 mm of it toward ``wall_west``, NEES 0.42 with the honest sigma), the real chassis stood 34.6 mm from the wall's
inner face, and the authored rear corner (-0.15 m) is inside the 50 mm wall box at the TRUE pose already (23.0 mm past the
inner face, 27.0 mm from the outer one, 2.0 mm east of the wall's mid-plane). The estimate error put the corner on the
OUTER side of the mid-plane (36.7 mm past the inner face, 13.3 mm from the outer one), so ``_signed``'s depth ("distance
to the NEAREST face") flipped to the outer face and the first approach command, which drives east, away from the wall and
toward the inner face, was refused as ``inside_pair_deeper`` (-13.3 -> -22.9 mm): depth to the nearest face grows until
the mid-plane. Under the nearest-face depth no command at the controller's operating speed was admitted at that pose, and
a reverse move toward the outer face was (it "reduces the depth"). Depth to the nearest face is discontinuous on the wall's
medial axis (the jump set of a signed-distance gradient), so inside a thick wall it names the wrong exit whenever the
estimate is a few millimetres off the mid-plane. ``DEPTH == 'exit_face'`` (v2) measures an inside pair's depth to the face
of its wall that faces the robot's own estimated reference point (the side the body is on), fixed at the start sample:
"deeper" is then "deeper along the way back to the free side", moving toward the free side never counts as deeper, and
moving toward the far face does (the old rule admitted it). Where the nearest face already is that face the numbers are
the old ones. ``'nearest_face'`` keeps the v1 rule for replays and the mutation tests. The no-entry rule and the floors
are untouched.

Shared ``zone_pair_geometry``, ``zone_own_guards`` and ``zone_final_pair_guards`` stay byte-identical. Only the robot's
own pose estimate, own issued command and the static map enter the rule: no peer pose, no measured joint, no world state.
"""
from __future__ import annotations

import math
from dataclasses import replace

from harness import zone_own_guards as g
from harness import zone_pair_highpose_guardlog as log
from harness.zone_final_pair_guards import PairGeometry
from harness.zone_own_guards import BACKOFF_GAIN_MAX, body_spheres
from harness.zone_pair_geometry import MOTION_SAMPLE_S

ID = 'v98_start_state_relief_v2'
EVENT = 'pair_collision_guard_start_relief'
SCOPE = 'group'
DEPTH = 'exit_face'                            # 'nearest_face' = the v1 rule (kept for replays and mutation tests)
EPS_M = 1e-3                                  # numeric slack of "never worse"; the group form needs 0.09 mm here
SHOWN_PAIRS = 8


def record() -> dict:
    return {'id': ID, 'event': EVENT, 'scope': SCOPE, 'depth': DEPTH, 'eps_m': EPS_M,
            'applies_to': 'PairSweepGuard.motion_clear (base motion)',
            'arm_and_transition_checks_changed': False, 'shared_sources_modified': False,
            'rule': 'after a frozen veto, admit when start-clear pairs stay >= 0 and start-negative pairs do not fall '
                    'below their (group) start worst - eps; pairs starting inside the wall box also do not get deeper '
                    '(depth to the wall face that faces the robot\'s own estimate, fixed at the start); '
                    'pairs starting outside the wall box never enter it (signed distance stays >= 0)',
            'known_issue': 'estimate over-confidence (r2 15 sigma at 8.7 s of probe 3358372e) is not addressed here'}


def sample_plan(cmd):
    """Gain-scaled command and sample count of ``PairSweepGuard.motion_clear``; None when it rejects the command
    outright (duration or gain not finite, duration outside 0..1 s). ``_poses`` then yields its samples."""
    duration = cmd.get('duration_s')
    if not isinstance(duration, (int, float)) or not math.isfinite(duration) or not 0 <= duration <= 1.:
        return None
    f, l, w = (cmd.get(k, 0.) * BACKOFF_GAIN_MAX for k in ('forward', 'left', 'turn'))
    if not all(math.isfinite(v) for v in (f, l, w)):
        return None
    n = max(1, math.ceil(duration / MOTION_SAMPLE_S))
    return (f, l, w, duration, n)


def _poses(pose, plan):
    f, l, w, duration, n = plan
    for omega in sorted({-abs(w), 0., abs(w)}):
        for i in range(n + 1):
            t = duration * i / n
            a = omega * t
            if omega:
                dx = (f * math.sin(a) + l * (math.cos(a) - 1.)) / omega
                dy = (f * (1. - math.cos(a)) + l * math.sin(a)) / omega
            else:
                dx, dy = f * t, l * t
            yield i, omega, replace(pose.moved(dx, dy), yaw=pose.yaw + a)


def _plain(value):
    """JSON-plain copy (numpy floats from the chassis point grid become floats)."""
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return float(value) if isinstance(value, float) else value


def _pair_key(p):
    return (p.kind, p.index, p.wall)


def _all_pairs(geo, servo, moved, loaded):
    chassis, arm = log.chassis_pairs(geo, moved), log.arm_pairs(geo, servo, moved, loaded)
    # The mirror must be the guard: the minima are what ``chassis_clearance``/``arm_clearance`` return.
    if (min((p.clearance for p in chassis), default=math.inf) != PairGeometry.chassis_clearance(geo, moved)[0]
            or min((p.clearance for p in arm), default=math.inf)
            != PairGeometry.arm_clearance(geo, servo, moved, loaded=loaded)[0]):
        raise ValueError('pair mirror disagrees with the frozen clearance')
    return chassis + arm


def floors(start, scope=SCOPE, eps=EPS_M):
    """Floor per pair key: 0 for a pair that starts clear, the (group) start worst - eps for one that starts negative."""
    group_worst = {}
    for p in start.values():
        if p.clearance < 0.:
            gkey = (p.kind, p.wall)
            group_worst[gkey] = min(group_worst.get(gkey, math.inf), p.clearance)
    out = {}
    for key, p in start.items():
        if not p.clearance < 0.:
            out[key] = 0.
        else:
            out[key] = (group_worst[(p.kind, p.wall)] if scope == 'group' else p.clearance) - eps
    return out


def enters(start_pair, pair) -> bool:
    """True when a pair that starts outside the obstacle box (raw signed distance >= 0) is inside it at this sample.

    Relief never admits a new entry: no slack, no floor (review 5 finding 1, coordinator ruling 2026-10-04)."""
    return start_pair.signed >= 0. and pair.signed < 0.


def _local(box, x, y):
    (cx, cy) = box['center']
    dx, dy = x - cx, y - cy
    if not box['yaw']:
        return dx, dy
    c, s = math.cos(box['yaw']), math.sin(box['yaw'])
    return c * dx + s * dy, -s * dx + c * dy


def exit_face(box, x, y):
    """(axis, side) of the face of ``box`` that faces the point (x, y) (the robot's own reference point), or None when
    that point is not outside the box. Axis 0/1 are the box's local x/y. A point outside along both axes (diagonal to a
    corner) takes the face its plane is nearer to."""
    local = _local(box, x, y)
    out = [(abs(v) - h, axis, 1 if v > 0. else -1) for axis, (v, h) in enumerate(zip(local, box['half'])) if abs(v) > h]
    if not out:
        return None
    _, axis, side = min(out)
    return axis, side


def exit_signed(box, pair, face):
    """The pair's signed distance with the depth of a point inside the box measured to ``face``, not to the nearest face.

    A centre outside the box keeps ``pair.signed``. Inside, the depth is the distance to the face plane along its normal
    (>= the nearest-face depth, equal where that face is this one); a sphere keeps its radius term."""
    r = pair.geom[3]
    if pair.raw + r > 0.:
        return pair.signed
    axis, side = face
    local = _local(box, pair.geom[4], pair.geom[5])
    return -max(box['half'][axis] - side * local[axis], 0.) - r


def _face_name(face):
    return None if face is None else ('x', 'y')[face[0]] + ('+' if face[1] > 0 else '-')


def relief(geo, servo, pose, cmd, loaded, *, scope=SCOPE, eps=EPS_M, depth=DEPTH):
    """Evaluate the start-state rule. None: not applicable (frozen answer stands). Else a dict with ``admitted``."""
    plan = sample_plan(cmd)
    if plan is None:
        return None
    f, l, w, duration, n = plan
    spheres = body_spheres(servo, loaded=False, mount_xyz_m=geo.mount)
    if loaded:
        spheres += geo.beam_spheres(servo)
    lever = max(.2, *(math.hypot(x, y) + r for x, y, _, r in spheres))
    pad = (math.hypot(f, l) + abs(w) * lever) * duration / n / 2.
    saved = geo.residual, geo._loaded_motion
    geo.residual += pad
    geo._loaded_motion = bool(loaded)
    try:
        start, worst, deepest, refusal, samples = None, {}, {}, None, 0
        for i, omega, moved in _poses(pose, plan):
            pairs = {_pair_key(p): p for p in _all_pairs(geo, servo, moved, loaded)}
            if start is None:
                start = pairs
                if not any(p.clearance < 0. for p in start.values()):
                    return None                         # nothing starts inside the margin: the frozen answer stands
                limits = floors(start, scope, eps)
                inside = {k for k, p in start.items() if p.clearance < 0. and p.raw <= 0.}
                boxes = {b['id']: b for b in geo.boxes}
                # The exit face of an inside pair is fixed at the start sample: the face of its wall that faces the
                # robot's own estimated reference point (None: the reference point is not outside that wall).
                faces = {k: exit_face(boxes[k[2]], pose.x, pose.y) if depth == 'exit_face' else None for k in inside}
                depth_of = lambda k, p: p.signed if faces[k] is None else exit_signed(boxes[k[2]], p, faces[k])
                begin = {k: depth_of(k, start[k]) for k in inside}
            samples += 1
            for key, p in pairs.items():
                worst[key] = min(worst.get(key, math.inf), p.clearance)
                if key in inside:
                    deepest[key] = min(deepest.get(key, math.inf), depth_of(key, p) - begin[key])
                if refusal is None and p.clearance < limits[key]:
                    refusal = {'why': 'start_clear_pair_negative' if start[key].clearance >= 0. else 'pair_worse_than_floor',
                               'pair': [p.kind, p.index, p.wall], 'sample': i, 'omega': omega,
                               'clearance_mm': p.clearance * 1000., 'floor_mm': limits[key] * 1000.,
                               'start_clearance_mm': start[key].clearance * 1000.}
                if refusal is None and key in inside and depth_of(key, p) < begin[key] - eps:
                    refusal = {'why': 'inside_pair_deeper', 'pair': [p.kind, p.index, p.wall], 'sample': i, 'omega': omega,
                               'signed_mm': depth_of(key, p) * 1000., 'start_signed_mm': begin[key] * 1000.,
                               'depth': depth, 'exit_face': _face_name(faces[key]),
                               'nearest_face_signed_mm': p.signed * 1000., 'nearest_face_start_signed_mm': start[key].signed * 1000.}
                # Review 5 finding 1: relief never admits a NEW entry into an obstacle box. A pair whose raw signed
                # distance is >= 0 at the start must keep it >= 0 at every swept sample (no slack).
                if refusal is None and enters(start[key], p):
                    refusal = {'why': 'start_outside_pair_enters', 'pair': [p.kind, p.index, p.wall], 'sample': i,
                               'omega': omega, 'signed_mm': p.signed * 1000., 'start_signed_mm': start[key].signed * 1000.}
        if start is None:
            return None
        negatives = sorted((k for k, p in start.items() if p.clearance < 0.), key=lambda k: start[k].clearance)
        groups = {}
        for k in negatives:
            gkey = f'{k[0]}:{k[2]}'
            row = groups.setdefault(gkey, {'start_worst_mm': start[k].clearance * 1000., 'swept_worst_mm': math.inf, 'pairs': 0})
            row['swept_worst_mm'] = min(row['swept_worst_mm'], worst[k] * 1000.)
            row['pairs'] += 1
        shown = [{'kind': k[0], 'index': k[1], 'wall_id': k[2], 'start_clearance_mm': start[k].clearance * 1000.,
                  'start_raw_mm': start[k].raw * 1000., 'start_inside_raw': k in inside,
                  **({'exit_face': _face_name(faces[k]), 'start_exit_signed_mm': begin[k] * 1000.} if k in inside else {}),
                  'worst_swept_clearance_mm': worst[k] * 1000., 'floor_mm': limits[k] * 1000.,
                  'worst_change_mm': (worst[k] - start[k].clearance) * 1000.} for k in negatives[:SHOWN_PAIRS]]
        return _plain({'admitted': refusal is None, 'scope': scope, 'depth': depth, 'eps_m': eps, 'samples': samples,
                       'start_negative_pairs': len(negatives), 'start_inside_raw': bool(inside),
                       'groups': groups, 'pairs': shown, 'refusal': refusal, 'motion_pad_mm': pad * 1000.})
    finally:
        geo.residual, geo._loaded_motion = saved


class StartReliefGeometry(log.RecordingGeometry):
    """``PairGeometry`` (recording) whose ``motion_clear`` applies the start-state rule after a frozen veto."""
    scope = SCOPE
    depth = DEPTH
    eps = EPS_M

    def motion_clear(self, servo, pose, cmd, *, loaded):
        mark = self.trace.checkpoint()
        if super().motion_clear(servo, pose, cmd, loaded=loaded):
            return True
        try:
            verdict = relief(self, servo, pose, cmd, loaded, scope=self.scope, eps=self.eps, depth=self.depth)
        except Exception as exc:                       # fail closed: the frozen veto stands
            self.trace.relief_notes.append(repr(exc))
            return False
        if verdict is None:
            return False
        if not verdict['admitted']:
            self.trace.relief_refusal = verdict
            return False
        try:
            verdict['frozen_guard_first_negative'] = (None if self.trace.first is None
                                                       else log._describe(self.trace.first, self.trace.origin))
        except Exception as exc:
            verdict['frozen_guard_first_negative'] = {'error': repr(exc)}
        self.trace.rollback(mark)                      # the frozen guard's negative queries were not a veto
        verdict['command'] = dict(cmd)
        self.trace.reliefs.append(verdict)
        return True


def install(geo, trace):
    return log.recording(geo, trace, StartReliefGeometry)


def log_reliefs(guard, now, trace):
    """One ``pair_collision_guard_start_relief`` event per admitted command. Never raises into the run."""
    if not trace.reliefs:
        return
    own = guard.ep.own
    estimate = None
    try:
        estimate = log._report(own.last_report)
    except Exception as exc:
        estimate = {'error': repr(exc)}
    for verdict in trace.reliefs:
        try:
            guard.ep.log(own.robot_id, EVENT, now, log_id=ID, estimate=estimate, loaded=bool(guard.carrying_beam),
                         servo_pwm={str(k): v for k, v in sorted(own.servo.items())}, **verdict)
        except Exception as exc:
            guard.ep.log(own.robot_id, EVENT, now, log_id=ID, log_error=repr(exc))
