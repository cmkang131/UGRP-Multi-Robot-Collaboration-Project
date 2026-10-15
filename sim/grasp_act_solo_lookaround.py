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
                 localizer_factory=None, runner_factory=None, truth_free_v1=False, command_pose=None):
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
            return
        self.loc = self.make_localizer(self.static, [float(v) for v in estimate],
                                       odometry_profile=self.profile)

    def issue(self, command, dt):
        """Move the pose estimate by the previously issued wheel pulses only."""
        if self.command_pose is not None or self.loc is None or dt <= 0:
            return
        levels = [w*min(dt, d)/dt for w, d in zip(command['wheels'], command['duration_s'])]
        self.loc.propagate(levels, dt)

    def start(self, now, pan_pulse):
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
        plan = self.loc.make_plan(int(pan_pulse))
        self.runner = self.make_runner(self.loc.script(), now)
        self.events.append({'t': now, 'event': 'start', 'views': len(plan['views']),
                            'rotated': plan['rotated']})

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
            rec = self.loc.observe(at, own_rgb(), dict(servo))
            if rec.get('status') == 'measured':
                self.measured_views += 1
            if self.command_pose is not None and rec.get('grid'):
                self.command_pose.last_fix = float(at)
                self.command_pose.fixes += 1
            self.events.append({'t': at, 'event': 'view', 'status': rec.get('status'),
                                'wall_points': rec.get('wall_points'), 'floor_lines': rec.get('floor_lines'),
                                'doors': rec.get('doors'), 'seen_groups': rec.get('seen_groups')})

        self.runner.tick(now, set_servo=set_servo, set_wheels=set_wheels,
                         wheels_idle=lambda: not self.pulses, capture=capture)
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
        return {'armed': True, 'truth_free_v1': self.truth_free_v1,
                'self_pose_source': 'task_start_issued_commands' if self.command_pose is not None else 'caller_estimate',
                'localization_verified': False, 'events': self.events, 'measured_views': self.measured_views,
                'localizer': self.loc.record(),
                'predictions_are_observations': False,
                'pose_error': 'evaluation output only; unknown here'}
