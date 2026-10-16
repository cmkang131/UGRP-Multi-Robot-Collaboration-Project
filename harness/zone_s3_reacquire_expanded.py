"""v177 default-off expanded, unloaded own-RGB feature reacquisition at route checkpoints."""
from dataclasses import dataclass, asdict
from harness.owncam_pair_beam_v2 import pose_of
from harness.zone_s3_settled_servo import SettleGate
from harness.zone_solo_cyan_pulse_cal import action_of


@dataclass(frozen=True)
class Options:
    canonical_pan: bool = False
    clipped_backoff: bool = False
    expanded_backoff: bool = False

    def __post_init__(self):
        if any(type(v) is not bool for v in asdict(self).values()):
            raise ValueError('reacquisition switches must be bool')


CANDIDATES = dict(baseline=Options(), pan=Options(True),
                  pan_backoff=Options(True, True))


def attach(ep, options=Options()):
    if options == Options():
        return ep
    ctl = ep.controller
    audit = []
    ctl.s3_reacquire = dict(options=asdict(options), audit=audit, runtime_gt=False)
    old_align, old_log = ctl._align, ctl.log
    gate = SettleGate()
    segment = None
    count = 0
    observed = None

    def log(rid, event, now, **detail):
        nonlocal observed
        if rid == ctl.rid and event == 'beam_obs':
            observed = dict(t=now, **detail)
        return old_log(rid, event, now, **detail)

    def safe(now):
        peer = ctl.status[0].partner_view(ctl.rid, now)
        return (ep.own.servo.get(1) == 2000 and not ctl.beam_grasp_confirmed
                and not any(v['state'] in ('ready', 'lift', 'carry') for v in peer.values()))

    def align(now, idle):
        nonlocal segment, count, observed
        if ctl.seg == 0:
            return old_align(now, idle)
        if not idle or now < ctl.next_look:
            return
        if segment != ctl.seg:
            if options.canonical_pan and not safe(now):
                return ctl.port.hold(now)
            segment, count = ctl.seg, 0
            if options.canonical_pan:
                obs = ep.own.last_obs
                target = {**pose_of('inspect'), 6:1500}
                ctl.port.hold(now)
                ctl.arm.queue(target, now, duration=.4, settle=.45)
                ctl.look_name = 'inspect'
                gate.until, gate.frame_id = ctl.arm.until, (obs or {}).get('frame_id')
                audit.append(dict(t=now, seg=segment, phase='canonical_inspect',
                    target=target, settled_after_s=gate.until))
                return
        if not gate.ready(now, ep.own.last_obs):
            return ctl.port.hold(now)
        observed = None
        value = old_align(now, idle)
        if (not options.clipped_backoff or count >= (6 if options.expanded_backoff else 2) or ctl.state != 'align'
                or observed is None or observed['t'] != now
                or observed.get('end_visible')
                or observed.get('reason') not in ('BAND_CLIPPED','END_CLIPPED')
                or not safe(now)):
            return value
        # Existing admitted unloaded minimum pulse; no new gain or live pose.
        profiles = ep.own.pose.localizer.pulse_profiles
        p = next(p for p in profiles.values() if not p['loaded']
                 and p['axis']=='forward' and p['u']==-.35 and p['duration_s']==.10)
        action = action_of(p)
        obs = ep.own.last_obs
        gate.issued(now, p, obs)
        count += 1
        audit.append(dict(t=now, seg=segment, phase='clipped_backoff', count=count,
            reason=observed['reason'], frame_id=obs['frame_id'], action=action,
            calibrated_delta=p['mean_delta'], settled_after_s=gate.until))
        return ctl.drive({k:v for k,v in action.items() if k not in ('kind','duration_s')}
                         | {'duration':action['duration_s']}, now)

    ctl.log, ctl._align = log, align
    return ep
