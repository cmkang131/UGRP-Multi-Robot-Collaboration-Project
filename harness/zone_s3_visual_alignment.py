"""DEV own-RGB alignment continuation; never invent an aligned receipt.

The old conservative PF relook may veto every tick before the RGB servo.
Log that veto and execute the unchanged calibrated pixel alignment handler.
Measured image alignment still precedes the existing hover/blind descent.
"""
import copy
from harness.zone_s3_dev_light import finite_pose
from harness.zone_pair_align import PairAlignRelook

OPTION = 'own_rgb_align_v1'
REASONS = frozenset(('align_entry', 'fix_gap', 'sigma_reserve', 'pose_missing',
                     'global_safety', 'global_safety_reserve'))


def attach_endpoint(ep, audit):
    ctl = ep.controller
    driver = ctl.driver
    tick = driver.tick
    def approach_tick(now):
        # Use the EXISTING calibrated silhouette/prestation check early,
        # without first requiring the possibly biased PF goal to be reached.
        # Its own posture, command-settling and fresh-frame gates stay intact.
        if ctl.state == 'approach' and driver.state == 'drive' and not driver.outcome:
            frame = driver._av_settled_frame(now)
            if frame is not None and driver.arrival_view.check(frame)['ok']:
                ctl.log(ctl.rid, 's3_early_rgb_handoff', now,
                        source='own settled RGB; original calibrated arrival bands')
                return driver._arrive(now)
        return tick(now)
    driver.tick = approach_tick
    original = ctl._begin_align_relook
    def begin(now, reason):
        if reason not in REASONS or not finite_pose(ep.own.last_report):
            return original(now, reason)
        audit.note(ep.own, now, 'POSE_UNCERTAIN', 'align.rgb_continue', trigger=reason)
        if reason == 'align_entry':
            # _align_start already queued the calibrated own beam view.
            # No additional PF pan may replace it before the local servo.
            return ctl._light_setter().set('align', now)
        if ctl.state == 'align':
            # Keep status/partner abort, frame, arm-idle and the instance-bound
            # measured RGB _align handler; bypass only this relook trampoline.
            return super(PairAlignRelook, ctl).tick(now)
        return original(now, reason)
    ctl._begin_align_relook = begin
    ctl.s3_visual_alignment = dict(option=OPTION, error_source='own calibrated RGB beam',
        pf_used_for_local_error=False, aligned_receipt_thresholds_changed=False,
        sequence=['visible RGB alignment', 'fixed hover', 'blind final descent', 'mutual close'])


def attach(pair, *, visual_alignment='off', submit=None):
    if visual_alignment == 'off': return pair
    if visual_alignment != OPTION or not hasattr(pair, 's3_dev_light_audit'):
        raise ValueError('own RGB continuation requires explicit S3 dev_light')
    start = submit or pair.team.start
    def submit(*args, **kwargs):
        result = start(*args, **kwargs)
        for session in pair.team.sessions:
            for ep in session['endpoints'].values():
                if not hasattr(ep.controller, 's3_visual_alignment'):
                    attach_endpoint(ep, pair.s3_dev_light_audit)
        return result
    # S3 captured the real submit callback in OwnLink before substituting its
    # claim dispatcher. The caller must wrap that captured boundary explicitly.
    pair.s3_visual_submit = submit
    record = pair.record
    pair.record = lambda: {**record(), 'visual_alignment': {ep.own.robot_id:
        copy.deepcopy(ep.controller.s3_visual_alignment) for s in pair.team.sessions
        for ep in s['endpoints'].values()}}
    return pair
