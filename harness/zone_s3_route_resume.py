"""Default-off multi-leg release boundary and calibrated move-settle-look.

Only issued servo commands, own frame metadata and public segment indices are
used. No new camera model, measured joint state or evaluation pose enters here.
"""
from dataclasses import dataclass, asdict
from harness.owncam_pair_beam_v2 import pose_of
from harness.zone_s3_settled_servo import SettleGate


@dataclass(frozen=True)
class Options:
    final_release_only: bool = False
    inspect_before_look: bool = False

    def __post_init__(self):
        if any(type(v) is not bool for v in asdict(self).values()):
            raise ValueError('route resume switches must be bool')


CANDIDATES = dict(baseline=Options(), completion=Options(True, False),
    inspect=Options(False, True), combined=Options(True, True))


def release_completes_probe(ctl, bundle):
    # _cp_open has ALREADY incremented seg. Final normal release instead uses
    # _released (it never increments seg), handled independently below.
    return 'registered_route' not in bundle or ctl.seg >= len(ctl.segments)


def attach(ep, options=Options()):
    if options == Options():
        return ep
    ctl = ep.controller
    audit = []
    ctl.s3_route_resume = dict(options=asdict(options), audit=audit, runtime_gt=False)
    if options.final_release_only:
        released = ctl._released
        def final_release(now, idle):
            final = ctl.seg == len(ctl.segments)-1
            if (idle and final and not ctl.failure and ctl.floor_return_verified
                    and ctl._issued().get(1) == 2000):
                ctl.port.hold(now)
                ctl.s3_first_release_complete = True
                audit.append(dict(t=now, phase='final_release_complete', seg=ctl.seg))
                return
            return released(now, idle)
        ctl._released = final_release
    if options.inspect_before_look:
        align = ctl._align
        gate = SettleGate()
        def restored_align(now, idle):
            if not idle or now < ctl.next_look:
                return
            issued = dict(ep.own.servo)
            inspect = {**pose_of('inspect'), 6: issued[6]}
            if any(issued[k] != v for k, v in inspect.items()):
                ctl.port.hold(now)
                obs = ep.own.last_obs
                ctl.arm.queue(inspect, now, duration=.4, settle=.45)
                ctl.look_name = 'inspect'
                gate.until = ctl.arm.until
                gate.frame_id = (obs or {}).get('frame_id')
                audit.append(dict(t=now, phase='restore_inspect', seg=ctl.seg,
                    issued_before=issued, target=inspect, settled_after_s=gate.until))
                return
            # ctl.look also fits a standoff, so this gate must run BEFORE it.
            # Waiting on last_obs only does not interpret an uncalibrated image.
            if not gate.ready(now, ep.own.last_obs):
                return ctl.port.hold(now)
            return align(now, idle)
        ctl._align = restored_align
    return ep
