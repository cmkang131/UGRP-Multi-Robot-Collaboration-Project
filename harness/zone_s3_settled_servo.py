"""Optional quantization-aware, single-axis move-settle-look visual control.

Use only already admitted calibrated pulses. A suppressed command is NOT an
aligned receipt: the caller's original RGB tolerances still authorize grasp.
"""
import copy
import math
from dataclasses import dataclass, asdict
from types import SimpleNamespace, MethodType

from harness.zone_final_pair_binding import bind
from harness.zone_final_pair_vision import ALIGN_TOL_X_M, ALIGN_TOL_Y_M
from harness.owncam_pair_beam import ALIGN_TOL_RAD
from harness.zone_s3_pair_alignment import project as previous
from harness.zone_s3_pair_heading import moving
from harness.zone_solo_cyan_path_heading import command_reason
from harness.zone_solo_cyan_pulse_cal import action_of, profile_key

OPTION = 'quantized_settled_v1'
AXES = ('forward', 'left', 'turn')


@dataclass(frozen=True)
class Options:
    deadband_hysteresis: bool = False
    move_settle_look: bool = False
    proportional_pulse: bool = False
    separate_axes: bool = False

    def __post_init__(self):
        if any(type(v) is not bool for v in asdict(self).values()):
            raise ValueError('servo toggles must be bool')

    @property
    def enabled(self):
        return any(asdict(self).values())


class Selector:
    def __init__(self, options=Options(), *, angle_required=True):
        self.options = options
        self.angle_required = angle_required
        self.tolerances = (ALIGN_TOL_X_M, ALIGN_TOL_Y_M, ALIGN_TOL_RAD)
        self.latched = [False]*3

    def __call__(self, profiles, errors):
        if not self.options.enabled:
            return previous(profiles, errors)
        errors = tuple(map(float, errors))
        if not all(math.isfinite(v) for v in errors):
            raise ValueError('finite own-RGB errors required')
        distance = math.hypot(*errors[:2])
        if distance > .10:
            return previous(profiles, errors)
        active = []
        for i, (error, tol) in enumerate(zip(errors, self.tolerances)):
            if abs(error) <= tol:
                self.latched[i] = True
            elif abs(error) > 1.5*tol:
                self.latched[i] = False
            active.append(abs(error) > tol and not
                          (self.options.deadband_hysteresis and self.latched[i]))
        if not self.angle_required:
            active[2] = False
        info = dict(phase=OPTION, goal_distance_m=distance, control_errors=list(errors),
                    options=asdict(self.options), thresholds_changed=False,
                    control_exit_multiplier=1.5, aligned_receipt=False,
                    suppressed=[], error_source='own RGB fit')
        hold = dict(kind='mecanum', forward=0., left=0., turn=0., duration_s=.1)
        if not any(active):
            return hold, None, dict(info, reason='deadband_hold')
        if self.options.separate_axes:
            # Final object orientation, not bearing of the gripper error.
            axes = [2] if active[2] else sorted(
                [i for i in (0, 1) if active[i]],
                key=lambda i: -abs(errors[i])/self.tolerances[i])
        else:
            legacy, _, _ = previous(profiles, errors)
            axes = [i for i, axis in enumerate(AXES) if legacy.get(axis)]
        for i in axes:
            candidates = []
            pool = [p for p in profiles.values() if not p['loaded']
                    and p['axis'] == AXES[i] and command_reason(action_of(p)) is None
                    and p['mean_delta'][i]*errors[i] > 0]
            for p in pool:
                magnitude = abs(p['mean_delta'][i])
                if magnitude <= 0:
                    continue
                # P duration (gain=1) quantized DOWN to an existing measured
                # duration. Never stretch a profile or invent a shorter pulse.
                requested = abs(errors[i])*p['duration_s']/magnitude
                if self.options.proportional_pulse and p['duration_s'] > requested+1e-12:
                    info['suppressed'].append(dict(axis=AXES[i], requested_s=requested,
                        available_s=p['duration_s'], predicted_step=magnitude))
                    continue
                residual = abs(errors[i]-p['mean_delta'][i])
                if residual < abs(errors[i])-1e-12:
                    candidates.append((residual, p['duration_s'], p, requested))
            if candidates:
                _, _, p, requested = min(candidates, key=lambda x: x[:2])
                return action_of(p), p, dict(info, reason='single_axis_pulse',
                    axis=AXES[i], proportional_requested_s=requested)
        return hold, None, dict(info, reason='below_calibrated_resolution')


class SettleGate:
    """Command timestamps and own frame metadata only; never measured motion."""
    def __init__(self):
        self.until = -math.inf
        self.frame_id = None

    def issued(self, now, profile, obs):
        self.until = now+max(.50, profile['times'][-1])
        self.frame_id = (obs or {}).get('frame_id')

    def ready(self, now, obs):
        if self.until == -math.inf:
            return True
        return (obs is not None and now >= self.until-1e-9
                and float(obs.get('sim_time', -math.inf)) >= self.until-1e-9
                and obs.get('frame_id') != self.frame_id)


def attach_endpoint(ep, options=Options()):
    if not options.enabled:
        return ep
    own = ep.own.pose.localizer
    selector = Selector(options)
    ctl = ep.controller
    original = ctl._align.__func__
    ob = original.__globals__['ob']
    private = SimpleNamespace(**{**vars(ob), 'align_command':
        bind(ob.align_command, project=selector)})
    ctl._align = MethodType(bind(original, ob=private), ctl)
    gate = SettleGate()
    apply, tick = ep.port.apply, ctl.tick

    def issued(action, now):
        result = apply(action, now)
        if options.move_settle_look and ctl.state == 'align' and moving(action):
            gate.issued(now, own.pulse_profiles[profile_key(action, False)], own.last_obs)
        return result

    def settled_tick(now):
        if ctl.state == 'align' and options.move_settle_look and not gate.ready(now, own.last_obs):
            return  # native motor expiry still stops the issued finite pulse
        return tick(now)

    ep.port.apply = issued
    ctl.tick = settled_tick
    ctl.s3_settled_servo = dict(option=OPTION, options=asdict(options), runtime_gt=False)
    return ep


def attach_solo(own, options=Options()):
    if not options.enabled:
        return own
    selector = Selector(options, angle_required=False)
    step, record = own.step, own.record
    gate, audit = SettleGate(), []

    def selected(now):
        if own.state == 'align' and options.move_settle_look and not gate.ready(now, own.last_obs):
            return []
        rows = step(now)
        if (own.state != 'align' or own.target is None or not own.fine_rows
                or own.fine_rows[-1]['t'] != now):
            return rows
        from harness.zone_final_pair_vision import GRASP_RADIUS_M
        errors = [own.target[0]-GRASP_RADIUS_M, own.target[1], 0.]
        if math.hypot(*errors[:2]) > .10:
            return rows
        action, profile, info = selector(own.pulse_profiles, errors)
        own.fine_until = None
        if profile is not None:
            own.heading_align_until = now+profile['duration_s']
            own.heading_align_settled = now+profile['times'][-1]
            own.fine_observe_after = own.heading_align_settled
            if options.move_settle_look:
                gate.issued(now, profile, own.last_obs)
        else:
            # Discard the replaced proposal's wait; no pulse was issued.
            own.heading_align_until = None
            own.heading_align_settled = now
            own.fine_observe_after = now
        audit.append(dict(t=now, frame_id=own.last_obs['frame_id'], issued=copy.deepcopy(action), **info))
        return [(rid, action if a['kind'] in ('mecanum', 'drive', 'hold') else a) for rid,a in rows]

    own.step = selected
    own.record = lambda: {**record(), 's3_settled_servo':
        dict(option=OPTION, options=asdict(options), decisions=audit, runtime_gt=False)}
    return own
