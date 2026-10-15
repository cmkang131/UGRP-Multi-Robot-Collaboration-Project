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
from harness.visual_arm_v3 import solve_grip_site_ik, tool_pose, forward_grip, MOUNT_X_M
from harness.visual_arm import CALIBRATED_GRASP_RADIUS_CM
from sim.visible_belief import VisibleBelief, odometry, relative, MEMORY_S, AXIAL_M_PER_S_AT_035
GRASP_Z_M = .024           # sim/zone_cargo.GRASP_Z_M (catalogue constant, not a measurement)

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
OBSERVE_MODES = ('gaze_v2', 'backoff_v3')
OBSERVE_BACKOFF_M = .15   # backoff_v3: step back before looking so the floor beyond the end enters the view
REACH_MID_M = sum(CALIBRATED_GRASP_RADIUS_CM)/200.
REACH_TOL_M = .01
# reach_v2: pick-feasible window from an IK scan of pick_schedule (hover .095 m + descent to GRASP_Z_M, v3
# physical pad) at 5d6e8291: radius 14.6-15.8 cm solves for |y| <= 3 cm; 16.1 cm fails at |y| >= 2 cm and
# 16.4-17.6 cm always fail ("no safe v3 physical-pad IK solution"). REACH_MID_M (16.25 cm) sits in the gap.
REACH_MODES = ('calibrated_mid_v1', 'pad_window_v2')
PAD_WINDOW_M = (.146, .158)
PAD_MID_M = sum(PAD_WINDOW_M)/2.
PAD_TOL_M = .004


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
    def __init__(self, robots, margin=MARGIN_M, *, channel='legacy', input_audit=None):
        if channel not in ('legacy','fixed_signals_v1'):raise ValueError('unsupported release channel')
        if channel=='fixed_signals_v1' and input_audit is None:raise ValueError('fixed release requires provenance audit')
        self.channel=channel;self.input_audit=input_audit
        self.robots = tuple(robots); self.margin = margin
        self.outbox = []; self.delivered = {r: None for r in robots}
        self.go = None; self.log = []; self.steps = 0
    def post(self, rid, message, now):
        if self.channel=='fixed_signals_v1':
            from harness.grasp_act_input_audit import admit
            message=admit(message,self.input_audit)
            if (rid not in self.robots or set(message)!={'phase','signal'}
                    or message['phase'] not in ('look','observe','lowered')
                    or message['signal'] not in ('INSIDE','OUTSIDE','UNKNOWN','READY')
                    or (message['phase']=='lowered')!=(message['signal']=='READY')):
                raise ValueError('fixed channel forbids relative margins/positions')
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

    def decide(self, now, *, require_seen=True):
        msgs = {r: self.delivered[r] for r in self.robots}
        if self.channel=='fixed_signals_v1':
            signals=[msgs[r]['signal'] for r in self.robots]
            if any(s not in ('INSIDE','OUTSIDE','UNKNOWN') for s in signals):
                raise ValueError('release decision requires fresh observed fixed signals')
            if all(s=='INSIDE' for s in signals):choice={'action':'lower'}
            elif 'UNKNOWN' in signals:choice={'action':'observe'}
            elif all(s=='OUTSIDE' for s in signals):choice={'action':'handoff'}
            else:choice={'action':'shift','shift_m':OUTSIDE_STEP_M*(1 if signals[0]=='OUTSIDE' else -1)}
            choice.update(t=now,channel=self.channel,signals=signals)
            self.log.append(choice);self.steps+=choice['action']=='shift'
            return choice
        lo, hi, evidence = self.interval(msgs)
        seen = all(k in ('edge', 'inside_lb') for k in evidence) or not require_seen
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
    """One robot's release: perceive -> report -> execute code-chosen step.

    Perception input (visible points only, from the evaluation owner) is an
    axial floor scan beside the own beam end: each visible point is classified
    'zone' (destination floor colour) or 'floor'. The teacher turns it into a
    margin of its own landing end using only its own geometry: while holding,
    the end comes from forward kinematics of its issued arm pose; after release,
    from the visible own band, else from where its own commands released it.
    """
    SCAN_EXACT_GAP_M = .03

    def __init__(self, rid, end, pwm, *, handoff_pose_estimate, zone_rect, memory_s=MEMORY_S, own_pose_source='commands',
                 reach_mode='calibrated_mid_v1'):
        if reach_mode not in REACH_MODES:
            raise ValueError(reach_mode)
        self.reach_mode = reach_mode
        if own_pose_source not in ('commands', 'truth_comparison'):
            raise ValueError('own pose from own commands; truth only as comparison toggle')
        self.rid, self.end = rid, end
        self.pwm = {int(k): int(v) for k, v in pwm.items()}
        self.belief = VisibleBelief(memory_s); self.own_pose_source = own_pose_source
        self.holding = True; self.phase = 'look'
        self.visible_counts = {}; self.blind_s = 0.; self.max_blind_s = {}
        self.last_report = None; self.last_scan = None
        if handoff_pose_estimate is not None:
            for side, (point, normal) in zone_edges(zone_rect).items():
                self.belief.observe('prior:'+side, relative(handoff_pose_estimate, point, normal), 0., source='map_prior')

    # --- own geometry ---
    def end_and_outward(self, now):
        """Own landing end (x, y) and outward unit vector in the body frame."""
        if self.holding:
            x, y, _ = forward_grip(self.pwm)
            return (x-GRASP_TO_END_M, y), (-1., 0.), 'commands_fk'
        band = self.belief.get('band', now)
        if band is None or band['source'] not in ('visible', 'dead_reckoned'):
            band = self.belief.get('released_band', now); source = 'own_command_release'
        else:
            source = band['source']
        bx, by, axis = band['pose']
        # Band 0.27 m from the beam centre, landing end 0.30 m; outward = away from centre.
        sign = -1. if self.end == 'teal' else 1.
        ox, oy = sign*math.cos(axis), sign*math.sin(axis)
        return (bx+GRASP_TO_END_M*ox, by+GRASP_TO_END_M*oy), (ox, oy), source

    def released_here(self, now):
        """Remember the band where own commands set it down (forward kinematics)."""
        x, y, _ = forward_grip(self.pwm)
        self.belief.observe('released_band', [x, y, 0.], now, source='own_command')
        self.holding = False

    def dead_reckon(self, wheels, seconds):
        if seconds > 0 and any(wheels):
            self.belief.propagate(*odometry(wheels, seconds))

    def perceive(self, obs, now):
        """obs (visible only): {'scan': [[x, y, 'zone'|'floor'], ...] body frame,
        'band': [x, y, axis_yaw] or None, 'own_band_visible', 'partner_visible'}."""
        if obs.get('band') is not None:
            self.belief.observe('band', obs['band'], now)
        (ex, ey), (ox, oy), _ = self.end_and_outward(now)
        pts = [((x-ex)*ox+(y-ey)*oy, c) for x, y, c in obs['scan']]
        self.last_scan = (now, pts)
        dest = any(c == 'zone' for _, c in pts)
        self.blind_s = 0. if dest else self.blind_s+.1
        self.max_blind_s[self.phase] = max(self.max_blind_s.get(self.phase, 0.), self.blind_s)
        c = self.visible_counts.setdefault(self.phase, {'destination': 0, 'end_area': 0, 'own_band': 0, 'partner': 0, 'N': 0})
        c['N'] += 1; c['destination'] += dest; c['end_area'] += bool(pts)
        c['own_band'] += bool(obs.get('own_band_visible')); c['partner'] += bool(obs.get('partner_visible'))

    @classmethod
    def scan_margin(cls, pts):
        """Visible scan -> (kind, margin). s > 0 is outward from the landing end."""
        zone = sorted(s for s, c in pts if c == 'zone'); floor = sorted(s for s, c in pts if c == 'floor')
        if not pts:
            return None, None
        near = [c for s, c in pts if abs(s) <= .03]
        if 'zone' in near or (zone and min(zone) <= 0. and not any(-.03 <= f <= .0 for f in floor)):
            beyond = [f for f in floor if f > 0.]
            if beyond:
                first = min(beyond); last_zone = max([z for z in zone if z < first], default=0.)
                if first-last_zone <= cls.SCAN_EXACT_GAP_M:
                    return 'edge', (first+last_zone)/2
                return 'inside_lb', last_zone
            return 'inside_lb', max(zone)
        if near and 'floor' in near:
            inward = [z for z in zone if z < 0.]
            if inward:
                nearest = max(inward); floor_in = [f for f in floor if nearest < f <= 0.]
                return 'outside', (nearest+min(floor_in, default=0.))/2
            return 'outside', None
        return None, None

    def report(self, now, phase='look'):
        kind = m = None
        if self.last_scan is not None and now-self.last_scan[0] <= .15:
            kind, m = self.scan_margin(self.last_scan[1])
        if kind is None:
            # No visible evidence: static-map prior through own-pose estimate.
            (ex, ey), (ox, oy), _ = self.end_and_outward(now); best = None
            for name, item in self.belief.items.items():
                if not name.startswith('prior:'): continue
                px, py, a = item['pose']; nx, ny = math.cos(a), math.sin(a)
                score = -(nx*ox+ny*oy)        # inward normal opposite to outward
                if score > .7 and (best is None or score > best[0]): best = (score, (ex-px)*nx+(ey-py)*ny)
            kind, m = ('prior', best[1]) if best else ('outside', None)
        self.last_report = {'phase': phase, 'kind': kind, 'margin_m': m}
        return self.last_report

    # --- primitive generators (executed by the runner) ---
    def shift_plan(self, s, sign):
        """Body-axial motion of length s*sign with native wheel 0.35 pulses <= 0.15 s."""
        d = s*sign; level = WHEEL if d > 0 else -WHEEL
        remaining = abs(d)/AXIAL_M_PER_S_AT_035; plan = []
        while remaining > 1e-6:
            on = min(.1, remaining); plan.append(([level]*4, [min(PULSE_MAX_S, on)]*4)); remaining -= on
        if plan and plan[-1][1][0] < .04: plan[-1] = (plan[-1][0], [.04]*4)   # minimum effective pulse
        return plan

    def arm_waypoints(self, z_to, steps, pitch=None, xy=None):
        x, y, z = forward_grip(self.pwm)
        if xy is not None: x, y = xy
        pitch = tool_pose(self.pwm).pitch_deg if pitch is None else pitch
        out = []
        for i in range(1, steps+1):
            pose = solve_grip_site_ik((x, y, z+(z_to-z)*i/steps), preferred_pitch_deg=pitch)
            out.append({k: int(v) for k, v in pose.items() if k in (3, 4, 5, 6)})
        return out

    def gaze_target(self, now):
        """Observation pose aimed at the own beam end (own geometry, never truth)."""
        from sim.grasp_act_gaze import gaze_pose
        (ex, ey), (ox, oy), _ = self.end_and_outward(now)
        # Look slightly outward of the end so the zone boundary beyond it is in view.
        return {k: int(v) for k, v in gaze_pose((ex+.06*ox, ey+.06*oy, .03), self.pwm).items() if k in (3, 4, 5, 6)}

    def pick_target(self, now):
        band = self.belief.get('band', now) or self.belief.get('released_band', now)
        return band['pose'][:2], band['source']

    def approach_plan(self, now):
        """Own-command axial approach so the re-grasp target sits mid-reach (never a crash on reach)."""
        (x, y), _ = self.pick_target(now)
        radius = math.hypot(x-MOUNT_X_M, y)
        if self.reach_mode == 'pad_window_v2':
            lo, hi, tol = PAD_WINDOW_M[0], PAD_WINDOW_M[1], PAD_TOL_M
        else:
            lo, hi = (v/100. for v in CALIBRATED_GRASP_RADIUS_CM); tol = REACH_TOL_M
        if lo+tol <= radius <= hi-tol:
            return []
        return self.shift_plan(radius-self.reach_mid(), 1.)

    def reach_mid(self):
        return PAD_MID_M if self.reach_mode == 'pad_window_v2' else REACH_MID_M

    def pick_schedule(self, now):
        """Re-grasp the own band (visible band preferred): hover, descent, close, lift."""
        (x, y), _ = self.pick_target(now)
        grip = solve_grip_site_ik((x, y, GRASP_Z_M)); pitch = tool_pose(grip).pitch_deg
        seq = [(0., {**{k: int(v) for k, v in solve_grip_site_ik((x, y, .095), preferred_pitch_deg=pitch).items() if k in (3, 4, 5, 6)}, 1: 2000})]
        t = 1.2
        for i in range(1, 9):
            z = .095+(GRASP_Z_M-.095)*i/8
            seq.append((t, {k: int(v) for k, v in solve_grip_site_ik((x, y, z), preferred_pitch_deg=pitch).items() if k in (3, 4, 5, 6)})); t += .2
        seq.append((t+.3, {1: 1500})); t += 1.6
        seq.append((t, {k: int(v) for k, v in solve_grip_site_ik((x, y, .095), preferred_pitch_deg=pitch).items() if k in (3, 4, 5, 6)}))
        return seq, t+1.5

    def diagnostic(self):
        return {'visible_counts_by_phase': self.visible_counts, 'max_destination_blind_s_by_phase': self.max_blind_s,
                'memory_s': self.belief.memory_s, 'own_pose_source': self.own_pose_source,
                'scope': 'visible_only teacher; truth only gates visibility of currently visible points'}


def zone_edges(rect):
    """Axis-aligned zone rectangle (cx, cy, hx, hy) -> {side: (midpoint, inward normal yaw)}."""
    cx, cy, hx, hy = rect
    return {'south': ((cx, cy-hy), math.pi/2), 'north': ((cx, cy+hy), -math.pi/2),
            'west': ((cx-hx, cy), 0.), 'east': ((cx+hx, cy), math.pi)}
