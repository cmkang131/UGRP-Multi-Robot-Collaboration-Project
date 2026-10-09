"""Default-off S3 DEV veto policy; estimates and certificates stay truthful.

Log the original conservative verdict, then use the current finite own
estimate. No global patches, no GT, no modified uncertainty thresholds.
Unknown failures, command/input errors and every pair GO barrier stay hard.
"""
import copy
import math
from types import MethodType

from harness import zone_pair_highpose_runtime as hp
from harness.zone_own_guards import OwnPose
from harness.zone_pair_highpose_frame_gate import gate as frame_gate

OPTION = 'continue_estimate_v1'
SOFT = hp.hp_contract.DEV_LIGHT_SOFT_STOPS | frozenset({
    'LOOK_RECOVERY_EXHAUSTED', 'SELF_UNCERTAIN', 'SWEEP_POSE_UNCERTAIN',
    'SWEEP_GATE_TIMEOUT', 'SWEEP_TRANSITION_BLOCKED', 'ALIGN_RELOOK_LIMIT',
    'ALIGN_RELOOK_NO_SAFE_VIEW', 'ALIGN_RETURN_VIEW_BLOCKED',
    'PREGRASP_RELOOK_TIMEOUT', 'PREGRASP_NO_SAFE_VIEW',
    'PREGRASP_RELATIVE_OR_GLOBAL_UNCERTAIN', 'DOOR_POSE_NOT_LOCALIZED',
    'APPROACH_POSE_UNCERTAIN', 'APPROACH_LOST', 'APPROACH_ARRIVAL_UNCONFIRMED',
    'POSE_NOT_INITIALIZED', 'BEAM_RELATIVE_UNCERTAIN',
})


def finite_pose(report):
    return report is not None and report.initialized and all(math.isfinite(float(v))
        for v in (report.x_m, report.y_m, report.yaw_rad, report.std_xy_m, report.std_yaw_rad))


class Audit:
    def __init__(self):
        self.counts, self.rows = {}, []

    def note(self, own, now, code, site, **detail):
        key = own.robot_id + ':' + site + ':' + code
        n = self.counts.get(key, 0) + 1
        self.counts[key] = n
        if (n-1) % 50 == 0:
            r = own.last_report
            row = dict(event='dev_light_would_stop', robot_id=own.robot_id,
                t=float(now), code=code, site=site, occurrence=n,
                estimate=None if not finite_pose(r) else dict(x=r.x_m, y=r.y_m,
                    yaw=r.yaw_rad, std_xy_m=r.std_xy_m, std_yaw_rad=r.std_yaw_rad),
                continued_with='current own estimate', physical_success=None, **detail)
            self.rows.append(row)
            own.events.append(copy.deepcopy(row))

    def record(self):
        return dict(option=OPTION, thresholds_changed=False, gt_inputs=False,
                    counts=copy.deepcopy(self.counts), rows=copy.deepcopy(self.rows))


class Geometry:
    """Outermost static-geometry veto only; the original diagnostic is retained."""
    def __init__(self, original, own, audit):
        self.original, self.own, self.audit = original, own, audit

    def __getattr__(self, key):
        return getattr(self.original, key)

    @property
    def pans_only(self):
        return getattr(self.original, 'pans_only', False)

    @pans_only.setter
    def pans_only(self, value):
        self.original.pans_only = value

    def transition_clear(self, *args, **kwargs):
        clear = self.original.transition_clear(*args, **kwargs)
        if not clear and finite_pose(self.own.last_report):
            self.audit.note(self.own, self.own.now, 'SWEEP_TRANSITION_BLOCKED', 'sweep.transition')
            return True
        return clear

    def motion_clear(self, *args, **kwargs):
        clear = self.original.motion_clear(*args, **kwargs)
        if not clear and finite_pose(self.own.last_report):
            self.audit.note(self.own, self.own.now, 'PAIR_COLLISION_GUARD', 'sweep.motion')
            return True
        return clear

    def plan(self, current, target, pans, pose, **kwargs):
        result = self.original.plan(current, target, pans, pose, **kwargs)
        if (result.get('reason') != 'clear' or result.get('dropped') or result.get('backoff')) and finite_pose(self.own.last_report):
            self.audit.note(self.own, self.own.now, 'SWEEP_TRANSITION_BLOCKED', 'sweep.plan',
                            original=copy.deepcopy(result))
            return {**result, 'reason': 'clear', 'transition_clear': True,
                    'pans': list(pans), 'dropped': [], 'backoff': None}
        return result


def attach_actor(own, audit):
    original = own.pair_readiness
    def readiness(now, item_ref=None, target_zone=None):
        state = original(now, item_ref, target_zone)
        if state != 'uncertain' or not finite_pose(own.last_report):
            return state
        from harness.zone_pair_admission import readiness_snapshot
        receipt = readiness_snapshot(own, now, item_ref, target_zone)
        # Bypass only the sigma/dwell gate. Fresh input, finite estimate,
        # complete servo history, empty gripper and task checks remain real.
        failed = set(receipt['failed_checks'])
        if (failed <= {'gate_ok'} and frame_gate().valid_frame(own.last_obs, own.robot_id, now)
                and own.holding()['answer'] == 'no'):
            audit.note(own, now, 'SELF_UNCERTAIN', 'pair.admission', failed_checks=sorted(failed))
            return 'available'
        return state
    own.pair_readiness = readiness
    own.guard = Geometry(own.guard, own, audit)


def attach_driver(driver, own, audit):
    class Continuing(type(driver)):
        def _drive_guard(self, now):
            if not finite_pose(own.last_report):
                return super()._drive_guard(now)
            if not own.gate.ok:
                audit.note(own, now, 'POSE_UNCERTAIN', 'approach.drive')
            return None

        def _needs_look(self, est, now):
            reason = super()._needs_look(est, now)
            if reason in ('uncertain', 'no_fix', 'gate_uncertain') and finite_pose(own.last_report):
                audit.note(own, now, 'POSE_UNCERTAIN', 'approach.look', trigger=reason)
                return None
            return reason

        def _should_refix(self, fixed):
            if not fixed and finite_pose(own.last_report):
                audit.note(own, own.now, 'REOBSERVATION_NO_FIX', 'approach.refix')
                return False
            return super()._should_refix(fixed)

        def _finish(self, now, outcome):
            if outcome in ('lost', 'pose_uncertain', 'sweep_transition_blocked',
                           'progress_unconfirmed') and finite_pose(own.last_report):
                audit.note(own, now, 'APPROACH_'+outcome.upper(), 'approach.finish')
                self.outcome = None
                self.looks_without_fix = 0
                self.arm_target = dict(self.drive_pose)
                self._set('posture_back', now)
                return [{'kind': 'hold'}]
            if outcome == 'arrival_unconfirmed' and finite_pose(own.last_report):
                audit.note(own, now, 'APPROACH_ARRIVAL_UNCONFIRMED', 'approach.finish')
                # Estimated arrival is a stage transition, never eval success.
                return super()._finish(now, 'arrived')
            return super()._finish(now, outcome)
    driver.__class__ = Continuing


def attach_endpoint(ep, audit):
    own, ctl, guard = ep.own, ep.controller, ep.command_guard
    attach_driver(ctl.driver, own, audit)
    abort, check = ep.abort, guard.check
    softened = []
    def soft_abort(now, reason):
        if reason in SOFT and finite_pose(own.last_report):
            audit.note(own, now, reason, 'pair.abort')
            softened.append(reason)
            return None
        return abort(now, reason)
    ep.abort = soft_abort
    before = guard.before_control
    def before_control(now):
        if not finite_pose(own.last_report):
            return before(now)
        # Evaluate without initiating the very re-look that DEV must not
        # repeatedly force on a valid but broad estimate.
        if not own.gate.ok or guard._high(OwnPose.from_report(own.last_report)):
            audit.note(own, now, 'POSE_UNCERTAIN', 'pair.before_control')
        if guard.reobserving:
            audit.note(own, now, 'PAIR_REOBSERVE_TIMEOUT', 'pair.before_control')
        return True
    guard.before_control = before_control
    def command_check(now, commands):
        softened.clear()
        out = check(now, commands)
        return commands if softened and not ep.terminal else out
    guard.check = command_check
    preclose = guard.preclose_check
    def preclose_check(now, obs):
        if preclose(now, obs):
            return True
        from harness.zone_own_contract import pose_report_fresh
        # Only localization/geometry can be bypassed. A stale frame, moving
        # arm/base or inconsistent issued posture is an execution/input fault.
        valid = (finite_pose(own.last_report) and pose_report_fresh(own.last_report, now)
                 and now >= guard.motion_until
                 and frame_gate().frame_gate(ep.policy)(obs, own.robot_id, now)
                 and guard._same_camera_commands(obs))
        if valid:
            audit.note(own, now, 'PREGRASP_BEAM_UNSAFE', 'pair.preclose')
        return bool(valid)
    guard.preclose_check = preclose_check
    ctl.preclose_check = preclose_check

    # Keep exact numerical certificates in logs; bypass their veto only for
    # DEV progression. The separate posterior certification is unchanged.
    for name in ('_align_fix_checks', '_grasp_pose_checks'):
        original = getattr(ctl, name)
        def checks(now, original=original, name=name):
            result = original(now)
            if not finite_pose(own.last_report):
                return result
            hard = {'shared_localizer', 'initialized', 'pose_finite', 'report_fresh'}
            failed = [k for k, v in result.items() if not v and k not in hard]
            if failed:
                audit.note(own, now, 'POSE_UNCERTAIN', name, failed_checks=failed)
            return {k: v if k in hard else True for k, v in result.items()}
        setattr(ctl, name, checks)
    for holder, name in ((ctl, 'global_certificate'), (guard, 'global_certificate')):
        original = getattr(holder, name)
        def certificate(now, *args, original=original, **kwargs):
            result = original(now, *args, **kwargs)
            if finite_pose(own.last_report) and (not result['clear'] or result.get('relook_reserve_low')):
                audit.note(own, now, 'GLOBAL_ENVELOPE_BLOCKED', 'pair.certificate', original=copy.deepcopy(result))
                return {**result, 'clear': True, 'relook_reserve_low': False, 'dev_veto_bypassed': True}
            return result
        setattr(holder, name, certificate)
    # v98 elevated a repeated soft stop to a hard failure at occurrence21.
    # DEV must remain log-only for every repetition; formal off is unchanged.
    ctl._light_repeat_exceeded = lambda reason, now: False
    original_fail = ctl.fail
    def fail(reason, now):
        if reason not in SOFT or not finite_pose(own.last_report):
            return original_fail(reason, now)
        audit.note(own, now, reason, 'controller.fail')
        if reason.startswith('ALIGN_RELOOK') or reason in ('PAIR_SCHEDULED_REOBSERVE_LIMIT', 'ALIGN_RETURN_VIEW_BLOCKED'):
            ctl._light_resume_align(now)
        elif reason in ('PREGRASP_RELOOK_TIMEOUT', 'PREGRASP_NO_SAFE_VIEW',
                         'PREGRASP_RELATIVE_OR_GLOBAL_UNCERTAIN', 'DOOR_POSE_NOT_LOCALIZED'):
            ctl.pregrasp_done = True
            r = own.last_report
            ctl.grasp_estimate = [r.x_m, r.y_m, r.yaw_rad]
            ctl._queue_open_descent(now)
        elif reason.startswith('APPROACH_'):
            ctl.driver.outcome = None
            ctl.driver._set('drive', now)
            ctl.set('approach', now)
        elif reason in ('ALIGN_TIMEOUT', 'BEAM_RELATIVE_UNCERTAIN'):
            ctl.state_t = ctl.align_started_at = now
        # Other sigma-budget hooks already keep their queued carry schedule.
        return None
    ctl.fail = fail


def attach(pair, *, s3_dev_light='off'):
    if s3_dev_light == 'off':
        return pair
    if s3_dev_light != OPTION:
        raise ValueError('unknown s3_dev_light')
    audit = Audit()
    for own in pair.actors.values():
        attach_actor(own, audit)
    recovery = pair.look_recovery
    exhausted = recovery.exhausted
    def is_exhausted(rid):
        if exhausted(rid):
            own = pair.actors[rid]
            if finite_pose(own.last_report):
                audit.note(own, own.now, 'LOOK_RECOVERY_EXHAUSTED', 'pair.recovery')
                return False
        return exhausted(rid)
    recovery.exhausted = is_exhausted
    failures = recovery.failures
    recovery.failures = lambda: {r: code for r, code in failures().items() if is_exhausted(r)}
    start = pair.team.start
    def submit(*args, **kwargs):
        result = start(*args, **kwargs)
        for session in pair.team.sessions:
            for ep in session['endpoints'].values():
                if not getattr(ep, 's3_dev_attached', False):
                    attach_endpoint(ep, audit)
                    ep.s3_dev_attached = True
        return result
    pair.team.start = submit
    record = pair.record
    pair.record = lambda: {**record(), 's3_dev_light': audit.record()}
    pair.s3_dev_light_audit = audit
    return pair
