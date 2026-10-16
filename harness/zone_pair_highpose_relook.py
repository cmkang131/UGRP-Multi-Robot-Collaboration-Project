"""v98 dock look: two wider pans, and a bounded in-place re-look when pair admission refuses ``SELF_UNCERTAIN``.

Problem (offline, #363 r2 accuracy note 2026-10-04). From the dock r2 faces east. The five-pan opening look
(1500, 1230, 970, 1770, 2030) constrains x well but y only through the side walls at the end pans: after the look
sigma_x was 22-29 mm and sigma_y 54-57 mm (recorded replays with roughening), the same 56 mm as noise-free
synthetic observations, so std_xy 58-64 mm stays above the 0.05 m admission gate. The refusal is honest. The
controller then only waited: one ``look_around`` on the first step, then ``team.start`` refused with
``SELF_UNCERTAIN`` every tick and no command (``zone_final_pair_runtime.Runtime.step``), until the admitted partner
timed out after 5 s (``PAIR_RENDEZVOUS_TIMEOUT``).

Two v98-only changes, no shared file modified:

1. Dock look pans ``DOCK_LOOK_PANS`` = the five pans plus 700 and 2300 (the existing PREGRASP_PANS_V2 extremes),
   ordered for the shortest pan travel (one side, then the other). Only the ``look_around`` job uses them; the
   delivery sweep and the approach driver keep ``WIDE_LOOK_PANS``. The shared ``_tick_sweep``/``_sweep_steps`` code
   objects are reused with ``WIDE_LOOK_PANS`` bound to the dock tuple (``zone_final_pair_binding.bind``); the
   look-around guard still clears every pan (dropped pans are logged by the shared sweep). Offline the guard allows
   700-2300 at all three dock rows up to sigma 0.08 m (isotropic) / 0.10 m (anisotropic), the same limit at which
   it already blocks the five-pan look.
2. Look recovery, after the Nav2 recovery behaviour tree (``RecoveryNode`` retries a failed action a fixed number of
   times, running recovery actions in between) and active localization (Fox, Burgard and Thrun 1998: act to reduce
   pose uncertainty before acting on the pose). When ``team.start`` refuses this robot with ``SELF_UNCERTAIN`` after
   a finished look, the robot is idle and unloaded (own ``holding()`` is ``no``), ``RELOOK_GRACE_S`` has passed
   since that look ended (the gate needs a 0.4 s dwell and the reports lag 0.16 s), and the partner's wire status
   (if the partner has submitted) is a non-moving phase, the robot runs the same ``look_around`` again. The guard
   is in ``pans_only`` mode for that job (no base back-off), and any base command a re-look would issue is refused
   (the job fails ``LOOK_RECOVERY_BASE_MOTION``). At most ``MAX_RELOOKS`` re-looks; the next ``SELF_UNCERTAIN``
   refusal ends recovery with ``LOOK_RECOVERY_EXHAUSTED`` and this robot stops submitting. Admission refusals exist
   only before the pair job, so the bound is per pair attempt (segment 0), never at a carry barrier.

Rendezvous. A re-look cannot be announced on the pair wire: ``zone_pair_status.STATES`` (fixed enum, identical in all
four communication conditions, byte-pinned by earlier review records) has no RELOOKING state, and a refused robot
has no endpoint (the session channel is created by the first ADMITTED robot in ``PairTeam.start``). Adding either
changes the shared status protocol, so it is not done here. The fallback is v98-only: the admitted partner's
rendezvous wait is ``RENDEZVOUS_TIMEOUT_S`` instead of 5 s, sized to the bounded recovery (see the constant).

Own inputs only: the own pose report, own gate, own jobs/holding answer, and the partner's published wire status.
No simulator state, peer executor state or ground truth enters.
"""
from __future__ import annotations

import copy
import math

from harness.zone_final_pair_binding import bind
from harness import zone_pair_highpose_lookaround as lookaround

ID = 'v98_dock_look_relook_v1'
DOCK_LOOK_PANS = (1500, 1230, 970, 700, 1770, 2030, 2300, 1500)
MAX_RELOOKS = 2
RELOOK_GRACE_S = 1.0
TRIGGER_REFUSALS = ('SELF_UNCERTAIN',)
EXHAUSTED = 'LOOK_RECOVERY_EXHAUSTED'
BASE_MOTION = 'LOOK_RECOVERY_BASE_MOTION'
RELOOK_COMMANDS = ('hold', 'arm', 'look')
# Partner wire phases in which no pair motion is commanded: not submitted (None), waiting for the rendezvous,
# stopped or finished. Anything else (aligning, ready, lift, carry, put_down, barrier states) defers a re-look.
PARTNER_IDLE_PHASES = (None, 'start_ready', 'abort', 'done')
# Measured in tests/test_highpose_relook.py (synthetic closed loop of the v98 runtime at the 0.05 s pair tick, no
# guard wait): the eight-pan dock look ends at 8.4 s (five pans: 6.2 s). LOOK_S = 9 s bounds one look. Worst case
# seen by an admitted partner: the other robot's opening look ends up to 5 s later (the shared contract's
# allowance), then grace + re-look + grace + re-look + grace: 5 + 3*1 + 2*9 = 26 s. The wait is set to the
# PairTeam constructor's upper bound, 30 s, leaving 4 s for guard waits inside the re-looks.
LOOK_S = 9.
RENDEZVOUS_TIMEOUT_S = 30.


def record() -> dict:
    return {'id': ID, 'dock_look_pans': list(DOCK_LOOK_PANS), 'max_relooks': MAX_RELOOKS,
            'relook_grace_s': RELOOK_GRACE_S, 'trigger_refusals': list(TRIGGER_REFUSALS), 'exhausted_code': EXHAUSTED,
            'relook_commands': list(RELOOK_COMMANDS), 'partner_idle_phases': [p for p in PARTNER_IDLE_PHASES],
            'rendezvous_timeout_s': RENDEZVOUS_TIMEOUT_S, 'relook_status_on_wire': False,
            'shared_sources_modified': False,
            'references': ['Nav2 behavior tree RecoveryNode (navigate_to_pose_w_replanning_and_recovery.xml)',
                           'Fox, Burgard, Thrun, Active Markov localization, Robotics and Autonomous Systems 25, 1998']}


def dock_sweep(tick_sweep, sweep_steps, pans=DOCK_LOOK_PANS):
    """``(_tick_sweep, _sweep_steps)`` that use ``pans`` for the ``look_around`` job, the originals else."""
    pans = tuple(int(p) for p in pans)
    dock_tick = lookaround.tick_sweep(bind(tick_sweep, WIDE_LOOK_PANS=pans))
    dock_steps = lookaround.sweep_steps(bind(sweep_steps, WIDE_LOOK_PANS=pans))
    wide_tick, wide_steps = lookaround.tick_sweep(tick_sweep), lookaround.sweep_steps(sweep_steps)

    def _tick_sweep(self, now, job):
        return (dock_tick if job.kind == 'look_around' else wide_tick)(self, now, job)

    def _sweep_steps(self, now, target, loaded):
        job = self.job
        return (dock_steps if job is not None and job.kind == 'look_around' else wide_steps)(self, now, target, loaded)

    _tick_sweep.v98_look_around = _sweep_steps.v98_look_around = True
    _tick_sweep.v98_dock_pans = _sweep_steps.v98_dock_pans = pans
    return _tick_sweep, _sweep_steps


def sigma(own, now) -> dict:
    """The own estimate's spread (and gate state) for the attempt log."""
    rep = own.pose.report(now)
    out = {'sim_s': round(float(now), 3), 'initialized': bool(rep.initialized), 'gate': own.gate.state,
           'std_xy_m': None, 'std_yaw_rad': None, 'sigma_x_m': None, 'sigma_y_m': None}
    for key, value in (('std_xy_m', rep.std_xy_m), ('std_yaw_rad', rep.std_yaw_rad)):
        if isinstance(value, (int, float)) and math.isfinite(value):
            out[key] = round(float(value), 5)
    cov = getattr(rep, 'cov', None)
    try:
        sx, sy = math.sqrt(float(cov[0][0])), math.sqrt(float(cov[1][1]))
        if math.isfinite(sx) and math.isfinite(sy):
            out.update(sigma_x_m=round(sx, 5), sigma_y_m=round(sy, 5))
    except (TypeError, IndexError, ValueError):
        pass
    return out


def partner_phase(team, rid, now):
    """The partner's latest wire phase on a pending session this robot has not joined (None: not submitted)."""
    for session in reversed(getattr(team, 'sessions', ())):
        if session['closed'] or rid in session['endpoints'] or len(session['endpoints']) != 1:
            continue
        view = session['channel'].partner_view(rid, now)
        for value in view.values():
            return value['state']
    return None


class LookRecovery:
    """Per-runtime bounded re-look state (own inputs and the wire only)."""

    def __init__(self, robots, *, max_relooks=MAX_RELOOKS, grace_s=RELOOK_GRACE_S):
        if type(max_relooks) is not int or not 0 <= max_relooks <= 5:
            raise ValueError('max_relooks must be an int in [0, 5]')
        self.max_relooks, self.grace_s = max_relooks, float(grace_s)
        self.state = {rid: {'attempts': [], 'active': None, 'exhausted': None, 'skipped': []} for rid in robots}

    def exhausted(self, rid):
        return self.state[rid]['exhausted'] is not None

    def failures(self):
        return {rid: EXHAUSTED for rid, s in self.state.items() if s['exhausted'] is not None}

    def _skip(self, rid, now, reason, **detail):
        skipped = self.state[rid]['skipped']
        if not skipped or skipped[-1]['reason'] != reason:          # log a change of reason, not every tick
            skipped.append({'sim_s': round(float(now), 3), 'reason': reason, **detail})

    def on_refusal(self, runtime, rid, ack, now):
        """After one ``team.start`` answer for ``rid``: maybe start a re-look (returns True when started)."""
        st = self.state[rid]
        if ack.get('accepted') or st['exhausted'] is not None or st['active'] is not None:
            return False
        if ack.get('rejected_reason') not in TRIGGER_REFUSALS:
            return False
        own = runtime.actors[rid]
        last = own.jobs_done[-1] if own.jobs_done else None
        if own.job is not None or last is None or last['kind'] != 'look_around':
            return False
        if now - float(last['ended_at_sim_s']) < self.grace_s - 1e-9:
            return False
        if own.holding()['answer'] != 'no':
            self._skip(rid, now, 'not_empty_handed')
            return False
        phase = partner_phase(runtime.team, rid, now)
        if phase not in PARTNER_IDLE_PHASES:
            self._skip(rid, now, 'partner_in_motion_phase', partner_phase=phase)
            return False
        before = sigma(own, now)
        if len(st['attempts']) >= self.max_relooks:
            st['exhausted'] = {'sim_s': round(float(now), 3), 'code': EXHAUSTED, 'attempts': len(st['attempts']),
                               'refusal': ack.get('rejected_reason'), 'last_look_outcome': last['outcome'],
                               'sigma': before}
            return False
        own.guard.pans_only = True
        started = own.look_around()
        if not started['accepted']:
            own.guard.pans_only = False
            self._skip(rid, now, 'look_refused', reason_code=started['rejected_reason'])
            return False
        st['active'] = {'attempt': len(st['attempts']) + 1, 'job_id': started['job_id'], 'trigger': ack['rejected_reason'],
                        'previous_look': {'job_id': last['job_id'], 'outcome': last['outcome']},
                        'partner_phase': phase, 't_start': round(float(now), 3), 'sigma_before': before,
                        'pans': list(DOCK_LOOK_PANS)}
        return True

    def pre_step(self, runtime, now):
        """Close a finished re-look attempt: outcome and sigma after."""
        for rid, st in self.state.items():
            active = st['active']
            if active is None:
                continue
            own = runtime.actors[rid]
            if own.job is not None and own.job.job_id == active['job_id']:
                continue
            done = next((j for j in reversed(own.jobs_done) if j['job_id'] == active['job_id']), None)
            own.guard.pans_only = False
            st['attempts'].append({**active, 't_end': round(float(now), 3),
                                   'outcome': None if done is None else done['outcome'],
                                   'job_ended_at_sim_s': None if done is None else done['ended_at_sim_s'],
                                   'sigma_after': sigma(own, now)})
            st['active'] = None

    def filter(self, runtime, now, issued):
        """Refuse any base command of a robot in a re-look (pans only); its re-look job fails."""
        out, failed = [], set()
        for rid, cmd in issued:
            active = self.state[rid]['active'] if rid in self.state else None
            own = runtime.actors[rid]
            if (active is not None and own.job is not None and own.job.job_id == active['job_id']
                    and cmd.get('kind') not in RELOOK_COMMANDS):
                if rid not in failed:
                    failed.add(rid)
                    active['refused_command'] = copy.deepcopy(cmd)
                    own._fail(now, BASE_MOTION, command_kind=cmd.get('kind'))
                continue
            out.append((rid, cmd))
        return out

    def record(self):
        return {**record(), 'robots': copy.deepcopy(self.state)}


def install(runtime, recovery):
    """Wrap ``runtime.team.start``: an exhausted robot stops submitting; a refusal may start a re-look."""
    inner = runtime.team.start

    def start(rid, item_ref=None, target_zone=None, partner_id=None, *, now):
        if recovery.exhausted(rid):
            return {'robot_id': rid, 'api': 'pair_carry', 'accepted': False, 'rejected_reason': EXHAUSTED}
        ack = inner(rid, item_ref, target_zone, partner_id, now=now)
        recovery.on_refusal(runtime, rid, ack, now)
        return ack

    runtime.team.start = start
    return recovery
