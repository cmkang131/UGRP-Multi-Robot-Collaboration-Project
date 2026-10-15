"""Solo set-down look-around (setdown_lookaround_v1) on the shared Opus interface.

Same method and code as the pair release: ``sim.lookaround_localization``
(``LookaroundLocalizer`` + ``ScriptRunner``) picks views from the static map and
the own pose estimate (``sim.active_lookaround.plan_views``), executes them as a
fixed-timing command script (arm to look pose, optional body rotation, pan,
0.8 s dwell) and corrects the pose from the own 640x480 RGB frame with the
existing OpenCV wall / zone-line / door detectors. This module only adapts that
script to the solo teacher's 10 Hz duty-pulse command stream.

Inputs: static map, the map code's own pose estimate (built by the scene owner
outside the teacher), own issued commands, own RGB. Predicted landmarks never
count as detections. Truth pose error is scored by the run evaluator only.
"""
from __future__ import annotations


class SoloLookaround:
    def __init__(self, static, *, ops, odometry_profile='off',
                 localizer_factory=None, runner_factory=None, truth_free_v1=False, command_pose=None, carry5=False,
                 carry5_rank_aware_views_v1=False, carry7_robust_recovery_v1=False,
                 active_relocalization='off'):
        if localizer_factory is None or runner_factory is None:
            from sim.lookaround_localization import LookaroundLocalizer, ScriptRunner
            localizer_factory = localizer_factory or LookaroundLocalizer
            runner_factory = runner_factory or ScriptRunner
        self.static, self.ops, self.profile = static, ops, odometry_profile
        self.make_localizer, self.make_runner = localizer_factory, runner_factory
        self.loc = None
        self.runner = None
        self.pulses = []
        self.events = []
        self.measured_views = 0
        self.truth_free_v1 = bool(truth_free_v1)
        self.scan_armed = False
        if command_pose is not None and not truth_free_v1:
            raise ValueError('command pose requires truth-free own-RGB mode')
        self.command_pose = command_pose
        self.carry5 = bool(carry5)
        self.rank_aware_v1 = carry5_rank_aware_views_v1
        if type(carry7_robust_recovery_v1) is not bool or (carry7_robust_recovery_v1 and not self.rank_aware_v1):
            raise ValueError('carry7 requires rank-aware command-pose recovery')
        self.robust_recovery_v1 = carry7_robust_recovery_v1
        from harness.active_relocalization import validate
        validate(active_relocalization)
        if active_relocalization != 'off' and not self.robust_recovery_v1:
            raise ValueError('RELOC8_REQUIRES_CARRY7_SAFETY')
        self.active_relocalization = active_relocalization
        self.active_replans = 0
        self.accepted_ready = False
        self.deadline = None
        self.rank_retry = 0
        self.partial_replans = 0
        self.replan_pending = False
        self.partial_budget_exhausted = False
        if type(carry5_rank_aware_views_v1) is not bool or (self.rank_aware_v1 and not (carry5 and command_pose is not None)):
            raise ValueError('rank-aware views require carry5 command pose')

    @property
    def armed(self):
        return self.scan_armed if self.truth_free_v1 else self.loc is not None

    def arm(self, estimate=None):
        """Called once by the scene owner when the set-down skill begins.

        ``estimate`` is the map code's own pose estimate (x, y, yaw) in the map
        frame. truth_free_v1 rejects caller estimates. It uses a fixed scan
        unless carry supplies its shared task-start/command belief; that mode
        reuses the existing static landmark look planner and own-RGB correction.
        """
        if self.armed:
            raise ValueError('look-around already armed')
        if self.truth_free_v1:
            if estimate is not None:
                raise ValueError('truth-free scan accepts no pose estimate')
            self.scan_armed = True
            if self.command_pose is not None:
                self.loc = self.make_localizer(self.static, self.command_pose.pose,
                                               odometry_profile=self.profile)
                # One belief, propagated once by carry.issue; never a scene pose.
                self.loc.own = self.command_pose.own
                self.loc.require_fix_acceptance = True
            return
        self.loc = self.make_localizer(self.static, [float(v) for v in estimate],
                                       odometry_profile=self.profile)

    def issue(self, command, dt):
        """Move the pose estimate by the previously issued wheel pulses only."""
        if self.command_pose is not None or self.loc is None or dt <= 0:
            return
        levels = [w*min(dt, d)/dt for w, d in zip(command['wheels'], command['duration_s'])]
        self.loc.propagate(levels, dt)

    def start(self, now, pan_pulse, *, continuation=False):
        if not continuation:
            self.partial_replans = 0
            self.active_replans = 0
            self.partial_budget_exhausted = False
        self.accepted_ready = False
        if self.truth_free_v1 and self.command_pose is None:
            if not self.armed:
                raise ValueError('look-around start before scan was armed')
            from sim.lookaround_localization import look_servo, ARM_MOVE_S, VIEW_SETTLE_S, PAN_DEG_PER_PULSE
            # No global pose prior exists in this runner. Do not invent one or
            # initialise it from setup/truth. Inspect actual own RGB in a fixed
            # command-only sweep; no localisation-success claim is made.
            pans = (500, 1000, 1500, 2000, 2500, 1500)
            script = [{'servo': look_servo((pans[0]-1500)*PAN_DEG_PER_PULSE),
                       'wait': ARM_MOVE_S, 'capture': False, 'label': 'arm_to_look'}]
            script.extend({'servo': look_servo((pan-1500)*PAN_DEG_PER_PULSE),
                           'wait': VIEW_SETTLE_S, 'capture': True, 'label': f'view_{pan}'} for pan in pans)
            self.runner = self.make_runner(script, now)
            self.events.append({'t': now, 'event': 'start', 'views': len(pans), 'rotated': False})
            return
        if self.loc is None:
            raise ValueError('look-around start before the pose estimate was armed')
        if self.carry5:
            import numpy as np
            self.loc.planning_covariance = np.diag(np.square(self.command_pose.sigmas()))
            self.loc.pan_only = False
        if self.rank_aware_v1:
            self.loc.rank_aware_v1 = True
            self.loc.rank_retry = self.rank_retry
        if self.robust_recovery_v1:
            self.loc.robust_recovery_v1 = True
        self.loc.active_relocalization = self.active_relocalization
        plan = self.loc.make_plan(int(pan_pulse))
        self.runner = (Carry5ViewRunner(plan, self.command_pose, self.ops, now) if self.carry5
                       else self.make_runner(self.loc.script(), now))
        if self.robust_recovery_v1:
            import math
            from sim.solo_carry7 import TURN_RATE_FLOOR
            headings = [0., *[v['body_yaw_deg'] for v in plan['views']]]
            angle = sum(abs(math.radians(b-a)) for a,b in zip(headings,headings[1:]))
            # Each plan/continuation has its own finite rotation+slew budget.
            self.deadline = now+angle/TURN_RATE_FLOOR+len(plan['views'])*5.+10.
        self.events.append({'t': now, 'event': 'start', 'views': len(plan['views']),
                            'rotated': plan['rotated'],
                            **({'rank_aware': plan['rank_aware'], 'plan_views': plan['views']}
                               if self.rank_aware_v1 else {})})

    def step(self, now, pwm, own_rgb):
        """One 10 Hz tick. ``own_rgb`` is a zero-argument callable returning the
        current own frame as RGB uint8 (called only when a view is captured)."""
        if self.runner is None:
            raise ValueError('look-around start instruction missing')
        servo = {int(s): int(pwm[s]) for s in (1, 3, 4, 5, 6)}

        def set_servo(pose, at):
            servo.update({int(s): int(v) for s, v in pose.items()})

        def set_wheels(plan, at):
            self.pulses = [(list(w), list(d)) for w, d in plan]

        def capture(at):
            if self.truth_free_v1 and self.command_pose is None:
                import hashlib
                frame = own_rgb()
                if frame.shape != (480, 640, 3):
                    raise ValueError('truth-free scan requires native own RGB')
                self.events.append({'t': at, 'event': 'view', 'status': 'captured_only',
                    'pan_pulse': servo[6], 'rgb_sha256': hashlib.sha256(frame.tobytes()).hexdigest()})
                return
            if self.command_pose is not None:
                import numpy as np
                prior_x, prior_P = self.loc.own.x.copy(), self.loc.own.P.copy()
                # Include the accumulated command-error budget in this update.
                self.loc.own.P = np.diag(np.square(self.command_pose.sigmas()))
            try:
                rec = self.loc.observe(at, own_rgb(), dict(servo))
            except Exception:
                if self.command_pose is not None:
                    self.loc.own.x, self.loc.own.P = prior_x, prior_P
                raise
            if rec.get('status') == 'measured':
                self.measured_views += 1
            if self.command_pose is not None:
                if rec.get('fix_acceptance', {}).get('accepted') is True:
                    self.command_pose.accepted_fix(at)
                    if self.active_relocalization != 'off':
                        self.loc._reloc8_evidence.frames.clear()
                    if self.robust_recovery_v1:
                        import math
                        s = self.command_pose.sigmas()
                        self.accepted_ready = (max(s[:2]) < .4 and s[2] < math.radians(16.))
                elif rec.get('partial_update', {}).get('applied') is True:
                    self.command_pose.partial_fix()
                    if self.partial_replans < 2:
                        self.partial_replans += 1
                        self.replan_pending = True
                    else:
                        # Three partial captures exhaust this attempt's view
                        # budget. finish_recovery schedules the next body turn.
                        self.partial_budget_exhausted = True
                else:
                    self.loc.own.x, self.loc.own.P = prior_x, prior_P
                if self.active_relocalization != 'off' and not self.accepted_ready and self.active_replans < 2:
                    self.active_replans += 1
                    self.replan_pending = True
            self.events.append({'t': at, 'event': 'view', 'status': rec.get('status'),
                                'wall_points': rec.get('wall_points'), 'floor_lines': rec.get('floor_lines'),
                                'doors': rec.get('doors'), 'seen_groups': rec.get('seen_groups'),
                                **({'fix_acceptance': rec.get('fix_acceptance')} if self.command_pose is not None else {}),
                                **({'partial_update': rec['partial_update']} if 'partial_update' in rec else {})})

        self.runner.tick(now, set_servo=set_servo, set_wheels=set_wheels,
                         wheels_idle=lambda: not self.pulses, capture=capture)
        if self.robust_recovery_v1 and (self.accepted_ready or now >= self.deadline):
            self.runner.done = True
            self.pulses.clear()
            self.replan_pending = False
            self.events.append(dict(t=now,event='accepted_ready_stop' if self.accepted_ready else 'scan_budget_exhausted'))
        if self.partial_budget_exhausted:
            self.runner.done = True
        if self.replan_pending:
            self.replan_pending = False
            self.start(now, servo[6], continuation=True)
        wheels, duration = [0.]*4, [0.]*4
        if self.pulses:
            wheels, duration = self.pulses.pop(0)
        value = self.ops.command({'t': now, 'wheels': wheels, 'duration_s': duration,
                                  'pwm': {str(s): servo[s] for s in (1, 3, 4, 5, 6)}})
        return value, bool(self.runner.done and not self.pulses)

    def record(self):
        if self.truth_free_v1 and self.command_pose is None:
            return {'armed': self.armed, 'events': self.events, 'truth_free_v1': True,
                    'self_pose_source': 'none', 'localization_verified': False,
                    'predictions_are_observations': False}
        if self.loc is None:
            return {'armed': False}
        return {'armed': True, 'events': self.events, 'measured_views': self.measured_views,
                **({'truth_free_v1': True, 'self_pose_source': 'task_start_issued_commands',
                    'localization_verified': False} if self.command_pose is not None else {}),
                'localizer': self.loc.record(),
                'predictions_are_observations': False,
                'pose_error': 'evaluation output only; unknown here'}


class Carry5ViewRunner:
    """Map-chosen views; turn completion is issued-command feedback, never nominal M2 rate.

    Camera pan is preferred by plan_views. If it predicts no information, turn
    in place after setdown. No return turn after the last accepted observation.
    """
    def __init__(self, plan, pose, ops, now):
        self.views = plan['views']; self.pose = pose; self.ops = ops
        self.origin_yaw = pose.pose[2]
        self.i = 0; self.stage = 'arm'; self.wait_from = None
        self.done = not self.views
        self.start = now

    def tick(self, now, *, set_servo, set_wheels, wheels_idle, capture):
        import math
        from sim.active_lookaround import wrap
        from sim.lookaround_localization import look_servo
        if self.done:
            return
        view = self.views[self.i]
        if self.stage == 'arm':
            set_servo(view.get('servo', look_servo(view['pan_deg'])), now)
            self.wait_from = now; self.stage = 'arm_wait'; return
        if self.stage == 'arm_wait':
            if now-self.wait_from < 1.:
                return
            self.stage = 'turn'
        if self.stage == 'turn':
            error = wrap(self.origin_yaw+math.radians(view['body_yaw_deg'])-self.pose.pose[2])
            if abs(error) > .025:
                turn = max(-.1, min(.1, .6*error))
                wheels, duration = self.ops.duty([0., 0., .65*turn])
                set_wheels([(wheels, duration)], now)
                return
            set_servo(view.get('servo', look_servo(view['pan_deg'])), now)
            self.wait_from = now; self.stage = 'settle'; return
        if self.stage == 'settle' and now-self.wait_from >= .8-1e-9:
            capture(now)
            self.i += 1
            self.done = self.i == len(self.views)
            self.stage = 'turn'
