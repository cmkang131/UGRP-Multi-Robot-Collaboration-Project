"""Demonstration-only pair release teacher, visible_only, normal physics, weld OFF.

Handoff (docs/act_execution_decisions.md, release section): grasp done -> arm
pose held -> map code carries -> release starts within 0.8 m of the slot.

Visible-only (user 2026-10-14 15:45): each robot knows the destination zone
only from what its own camera shows now (zone edges / zone floor near its own
beam end), else the last seen pose moved by its own issued commands for
``MEMORY_S``, else a static-map prior built from the map code's own-pose
estimate. Partner information is limited to what is visible plus the code's
GO/ACK messages (``PairReleaseCode``). Truth is used by the evaluation owner
only to gate visibility and to compute relative poses of visible things.

Wheels: each wheel 0 or 0.31-0.40 (native), pulse duration <= 0.15 s; fine
motion by duration (docs/decision_log.md 2026-08-29).
"""
from __future__ import annotations
import math
from harness.visual_arm_v3 import solve_grip_site_ik, tool_pose, forward_grip
from sim.visible_belief import VisibleBelief, odometry, relative, MEMORY_S, AXIAL_M_PER_S_AT_035

WHEEL = .35
WHEEL_RANGE = (.31, .40)
PULSE_MAX_S = .15
MARGIN_M = .04            # each landing end at least this far inside the zone edge
GRASP_TO_END_M = .03      # band centre (0.27) -> landing end (0.30)
LOWER_Z_M = .026          # grip z at which the beam bottom reaches the floor (GRASP_Z 0.024)
RAISE_Z_M = .07
BACKOFF_M = .15
MAX_STEP_M = .10
SIGNAL_DELAY_S = .1       # same as harness/e2e_dialogue.py
GO_SETTLE_S = .2          # same as go_ack_settle_s
INSIDE_LB_DEFAULT = .0
OUTSIDE_STEP_M = .08
FOLDED_BACKOFF = {3: 820, 4: 2320, 5: 1320}


def check_wheels(wheels, durations):
    if len(wheels) != 4 or len(durations) != 4:
        raise ValueError('four wheel levels and durations required')
    for w, d in zip(wheels, durations):
        if not (w == 0. or WHEEL_RANGE[0]-1e-9 <= abs(w) <= WHEEL_RANGE[1]+1e-9):
            raise ValueError('wheel level must be 0 or 0.31-0.40')
        if not 0. <= d <= PULSE_MAX_S+1e-9 or (w == 0.) != (d == 0.):
            raise ValueError('pulse duration 0..0.15 s, zero only with zero wheel')
    return [float(w) for w in wheels], [float(d) for d in durations]


class QuantizedWheels:
    """Per-wheel native level for a duration; ticked every physics step."""
    def __init__(self, port):
        self.port = port; self.levels = [0.]*4; self.until = [0.]*4
    def command(self, wheels, durations, now):
        wheels, durations = check_wheels(wheels, durations)
        self.levels = wheels; self.until = [now+d for d in durations]
        self.port._set_motors(tuple(wheels))
    def tick(self, now):
        if any(self.levels):
            changed = False
            for i in range(4):
                if self.levels[i] and now >= self.until[i]-1e-9:
                    self.levels[i] = 0.; changed = True
            if changed:
                self.port._set_motors(tuple(self.levels))
    def stop(self):
        self.levels = [0.]*4; self.port._set_motors((0., 0., 0., 0.))


class PairReleaseCode:
    """Code-side GO/ACK and shared step choice. Reads only posted messages."""
    def __init__(self, robots, margin=MARGIN_M):
        self.robots = tuple(robots); self.margin = margin
        self.outbox = []; self.delivered = {r: None for r in robots}
        self.go = None; self.log = []; self.steps = 0
    def post(self, rid, message, now):
        self.outbox.append((now+SIGNAL_DELAY_S, rid, dict(message, t=now)))
    def deliver(self, now):
        keep = []
        for at, rid, msg in self.outbox:
            if at <= now+1e-9: self.delivered[rid] = msg
            else: keep.append((at, rid, msg))
        self.outbox = keep
    def ready(self, phase, since):
        msgs = [self.delivered[r] for r in self.robots]
        return all(m is not None and m['phase'] == phase and m['t'] >= since-1e-9 for m in msgs)

    def interval(self, msgs):
        """Admissible shift s (+ = toward r2's end) from the two margin reports.

        r1 margin grows with s, r2 margin shrinks. Exact edges and inside lower
        bounds give constraints; 'outside' forces a step; priors only when
        nothing visible. Returns (lo, hi, evidence)."""
        lo, hi = -math.inf, math.inf; evidence = []
        for rid, sign in ((self.robots[0], 1.), (self.robots[1], -1.)):
            m = msgs[rid]; kind = m['kind']; evidence.append(kind)
            if kind in ('edge', 'inside_lb', 'prior', 'remembered'):
                bound = self.margin-m['margin_m']          # sign*s >= margin - m
                if sign > 0: lo = max(lo, bound)
                else: hi = min(hi, -bound)
            elif kind == 'outside':
                bound = self.margin-m['margin_m'] if m.get('margin_m') is not None else self.margin+OUTSIDE_STEP_M
                if sign > 0: lo = max(lo, bound)
                else: hi = min(hi, -bound)
        return lo, hi, evidence

    def decide(self, now):
        msgs = {r: self.delivered[r] for r in self.robots}
        lo, hi, evidence = self.interval(msgs)
        seen = all(k in ('edge', 'inside_lb') for k in evidence)
        exact = {r: msgs[r]['kind'] == 'edge' for r in self.robots}
        if lo <= 0. <= hi and seen:
            choice = {'action': 'lower'}
        else:
            if lo > hi:
                # Contradiction (beam cannot fit by these reports): trust exact edges.
                s = (lo+hi)/2
            elif math.isinf(lo) and math.isinf(hi):
                s = 0.
            elif math.isinf(hi): s = lo+.02
            elif math.isinf(lo): s = hi-.02
            else: s = (lo+hi)/2
            if not seen and abs(s) < .02:
                # Prior-only agreement: creep to obtain visible evidence on the unseen side.
                unseen = [r for r in self.robots if evidence[self.robots.index(r)] not in ('edge', 'inside_lb')]
                # Move away from the side without visible evidence (its end may be outside).
                s = -.05 if unseen and unseen[0] == self.robots[1] else .05
            choice = {'action': 'shift', 'shift_m': max(-MAX_STEP_M, min(MAX_STEP_M, s))}
        choice.update(lo=lo, hi=hi, evidence=evidence, exact=exact, t=now)
        self.log.append(choice); self.steps += choice['action'] == 'shift'
        return choice


class ReleaseTeacher:
    """One robot's release: perceive -> report -> execute code-chosen step."""
    def __init__(self, rid, end, pwm, *, handoff_pose_estimate, zone_rect, memory_s=MEMORY_S, own_pose_source='commands'):
        if own_pose_source not in ('commands', 'truth_comparison'):
            raise ValueError('own pose from own commands; truth only as comparison toggle')
        self.rid, self.end = rid, end
        self.pwm = {int(k): int(v) for k, v in pwm.items()}
        self.belief = VisibleBelief(memory_s); self.own_pose_source = own_pose_source
        self.queue = []; self.phase = 'look'; self.done = False
        self.visible_counts = {}; self.blind_s = 0.; self.max_blind_s = {}
        self.last_report = None
        # Static-map prior through the map code's own-pose estimate (not visible).
        for side, (point, normal) in zone_edges(zone_rect).items():
            rel = relative(handoff_pose_estimate, point, normal)
            self.belief.observe('prior:'+side, rel, 0., source='map_prior')

    # --- own geometry from issued commands only ---
    def landing_end(self):
        x, y, _ = forward_grip(self.pwm)
        return x-GRASP_TO_END_M, y

    def dead_reckon(self, wheels, seconds):
        if seconds > 0 and any(wheels):
            self.belief.propagate(*odometry(wheels, seconds))

    def perceive(self, obs, now):
        """obs: visible-only relative geometry from the evaluation owner.

        {'edges': {side: [x, y, normal_yaw]}, 'interior': [[x, y], ...],
         'own_band_visible': bool, 'partner_visible': bool}"""
        for side, rel in obs['edges'].items():
            self.belief.observe('edge:'+side, rel, now)
        ex, ey = self.landing_end()
        near = [q for q in obs['interior'] if math.hypot(q[0]-ex, q[1]-ey) <= .15]
        if near:
            lb = max(INSIDE_LB_DEFAULT, max(ex-q[0] for q in near))
            self.belief.observe('inside', [ex, ey, 0.], now, lower_bound=lb)
        dest = bool(obs['edges']) or bool(near)
        if obs.get('end_area_visible') and not dest:
            self.outside_seen_t = now          # floor around own end in view, no zone colour
        self.blind_s = 0. if dest else self.blind_s+.1
        self.max_blind_s[self.phase] = max(self.max_blind_s.get(self.phase, 0.), self.blind_s)
        c = self.visible_counts.setdefault(self.phase, {'destination': 0, 'own_band': 0, 'partner': 0, 'N': 0})
        c['N'] += 1; c['destination'] += dest; c['own_band'] += bool(obs.get('own_band_visible'))
        c['partner'] += bool(obs.get('partner_visible'))

    def own_edge(self, now, prefix='edge:'):
        """Zone edge on own side: inward normal most aligned with +x body (toward the beam)."""
        best = None
        for name, item in self.belief.items.items():
            if not name.startswith(prefix): continue
            if prefix == 'edge:' and self.belief.get(name, now) is None: continue
            score = math.cos(item['pose'][2])
            if score > .7 and (best is None or score > best[0]): best = (score, item)
        return None if best is None else best[1]

    def report(self, now):
        ex, ey = self.landing_end()
        edge = self.own_edge(now)
        if edge is not None:
            px, py, a = edge['pose']; m = (ex-px)*math.cos(a)+(ey-py)*math.sin(a)
            kind = 'edge' if edge['source'] == 'visible' and now-edge['seen_t'] <= .15 else 'remembered'
        else:
            inside = self.belief.get('inside', now)
            if inside is not None and now-inside['seen_t'] <= .15:
                kind, m = 'inside_lb', inside['lower_bound']
            else:
                prior = self.own_edge(now, 'prior:'); pm = None
                if prior is not None:
                    px, py, a = prior['pose']; pm = (ex-px)*math.cos(a)+(ey-py)*math.sin(a)
                if self.outside_seen_t is not None and now-self.outside_seen_t <= .15:
                    kind, m = 'outside', (pm if pm is not None and pm < 0 else None)
                elif pm is not None:
                    kind, m = 'prior', pm
                else:
                    kind, m = 'outside', None
        self.last_report = {'phase': 'look', 'kind': kind, 'margin_m': m}
        return self.last_report

    outside_seen_t = None

    # --- primitive generators (executed by the runner at 10 Hz) ---
    def shift_plan(self, s, sign):
        """Body-axial motion of length s*sign with native wheel 0.35 pulses <= 0.15 s."""
        d = s*sign; level = WHEEL if d > 0 else -WHEEL
        remaining = abs(d)/AXIAL_M_PER_S_AT_035; plan = []
        while remaining > 1e-6:
            on = min(.1, remaining); plan.append(([level]*4, [min(PULSE_MAX_S, on)]*4)); remaining -= on
        if plan and plan[-1][1][0] < .04: plan[-1] = (plan[-1][0], [.04]*4)   # minimum effective pulse
        return plan

    def arm_waypoints(self, z_to, steps, pitch=None):
        x, y, z = forward_grip(self.pwm)
        pitch = tool_pose(self.pwm).pitch_deg if pitch is None else pitch
        out = []
        for i in range(1, steps+1):
            pose = solve_grip_site_ik((x, y, z+(z_to-z)*i/steps), preferred_pitch_deg=pitch)
            pose = {k: int(v) for k, v in pose.items() if k in (3, 4, 5, 6)}
            out.append(pose)
        return out

    def diagnostic(self):
        return {'visible_counts_by_phase': self.visible_counts, 'max_destination_blind_s_by_phase': self.max_blind_s,
                'memory_s': self.belief.memory_s, 'own_pose_source': self.own_pose_source,
                'scope': 'visible_only teacher; truth only gates visibility of currently visible targets'}


def zone_edges(rect):
    """Axis-aligned zone rectangle (cx, cy, hx, hy) -> {side: (midpoint, inward normal yaw)}."""
    cx, cy, hx, hy = rect
    return {'south': ((cx, cy-hy), math.pi/2), 'north': ((cx, cy+hy), -math.pi/2),
            'west': ((cx-hx, cy), 0.), 'east': ((cx+hx, cy), math.pi)}
