"""S2 DEV solo controller: v98 OpenCV/PF, v3 command geometry and own RGB only.

No world, ports, measured joints, contacts, seeded placement or judge inputs.
The provider is the pair partial-fix stack with an explicit solo motion proxy:
30 g loaded motion uses the measured UNLOADED single-robot model, unqualified.
No pair motion plan or beam yaw correction is supplied. Formal use is refused.
"""
from __future__ import annotations

import copy
import math
from types import SimpleNamespace

import numpy as np

from harness import zone_pair_highpose as high
from harness import zone_pair_highpose_blind_close as blind
from harness import zone_pair_highpose_frame_gate as frame_gate
from harness import zone_pair_highpose_own_load_occlusion as occlusion
from harness import zone_pair_highpose_partial_fix as partial
from harness import zone_pair_highpose_contract as hp
from harness.owncam_drive import LOOK_P20
from harness.owncam_pair_beam_v2 import pose_of
from harness.zone_final_pair_vision import GRASP_RADIUS_M, grasp_postures
from harness.zone_final_pair_skill import motor_command
from harness.zone_own_contract import pickup_slots
from harness.zone_own_guards import OwnPose
from harness.zone_own_guards_v3 import SweepGuardV3
from harness.zone_solo_cyan_vision_v106 import CyanVision, BlindCyan
from harness.visual_arm_v3 import CONTROLLER_GEOMETRY_ID

PROFILE = 'solo-cyan-v106-v98-stack-dev'
MOTION_PROXY = 'cyan30g_loaded_uses_v101_unloaded_single_robot_UNQUALIFIED'
CONTROL_S = .1
CAP_S = 900.
ENVELOPE = {'x_m': [-.18, .28], 'y_m': [-.18, .18]}
LOOK_PANS = (1500, 1230, 970, 1770, 2030, 1500)


def build_provider(static_map, calibration, calibration_sha256, seed=0, *, model_runtime=None, worker=None):
    """Reuse the actual partial-fix provider; no tag detector or private pose seed."""
    from harness.zone_study_pose_delay_p03 import DelayedPoseSource
    source = partial.build_source_class()(static_map, calibration, calibration_sha256, seed, worker=worker)
    try:
        pf = source.loc._pf
        # Do NOT inherit the 300 g two-carrier gain/deadband/partner model.
        # Loaded camera geometry and command-based load state remain v98's.
        pf.params['motion_loaded'] = copy.deepcopy(pf.params['motion'])
        source.carry_yaw_fallback = None
        source.runtime_contract['solo_motion_proxy'] = MOTION_PROXY
        source.runtime_contract['pair_plan'] = None
        source.identity_sha256 = hp.base.digest(source.runtime_contract)
        source.source = 'owncam_pf_'+PROFILE+':'+source.identity_sha256[:8]
        return DelayedPoseSource(source)
    except Exception:
        source.close()
        raise


build_provider.controller_geometry_id = CONTROLLER_GEOMETRY_ID
build_provider.uses_landmark_tags = False


def passage_route(static, passage_id, zone):
    passages = [p for p in static['passages'] if p['id'] == passage_id]
    if len(passages) != 1 or passages[0]['kind'] != 'door':
        raise ValueError('solo v106 requires a named door; corridor/two-door qualification pending')
    p = passages[0]
    x, y = p['center_m']
    # Authored destination region, never a live object/robot pose.
    dest = static['regions']['zone_'+zone]['center_m']
    return [(x-.55, y), (x+.55, y), (dest[0]-GRASP_RADIUS_M, dest[1])]


class CommandSink:
    """ArmSequence writes proposals here; only the host can issue them."""
    def __init__(self):
        self.rows = []

    def apply(self, action, now):
        self.rows.append(dict(action))


class Runtime:
    def __init__(self, static, calibration, calibration_sha, *, seed=911, robot_id='r3',
                 pickup_slot='P1-2', destination='B', passage_id='door_1', dev_light=True,
                 provider_factory=build_provider, vision_factory=CyanVision, model_runtime=None):
        if dev_light is not True:
            raise ValueError('SOLO_CYAN_DEV_ONLY: loaded motion/camera and grasp qualification pending')
        if robot_id not in ('r1', 'r2', 'r3') or static['map_id'] != 'zone_wide_door_geometry_v3':
            raise ValueError('solo v106 robot/map outside DEV scope')
        self.route = passage_route(static, passage_id, destination)
        self.slot = pickup_slots(static)[pickup_slot]
        self.map, self.robot_id, self.pickup_slot, self.destination = static, robot_id, pickup_slot, destination
        self.pose = provider_factory(static, calibration, calibration_sha, seed, model_runtime=model_runtime)
        try:
            from sim.zone_model_conventions import spawn_layout
            dock = spawn_layout(static)
            rows = dock['spawn_rows_y']
            self.pose.init_prior((dock['spawn_x'], sum(rows)/len(rows), 0.),
                (.15, max(.15, max(rows)-min(rows)), .174533),
                source='public arena start region; seeded robot-row assignment unknown')
            self.vision = vision_factory(self.pose.provider.calibration)
            self.guard = SweepGuardV3(static)
        except Exception:
            self.pose.close()
            raise
        self.servo, self.last_obs, self.last_report = {}, None, None
        self.state, self.state_t, self.started_at = 'init', 0., None
        self.events, self.pose_log, self.commands = [], [], []
        self.failure, self.receipt = None, False
        self.sink, self.arm = CommandSink(), None
        self.blind = BlindCyan()
        self.target = None
        self.target_t = None
        self.next_control = 0.
        self.path, self.path_goal = [], None
        self.route_i, self.search_i = 0, 0
        self.scan_queue, self.scan_after = [], None
        self.align_streak, self.last_align_frame = 0, None
        self.last_visual_state = None
        self.soft_counts = {}
        self.controller = self.own = self
        self.policy = SimpleNamespace(own_image_ob=False)
        self.own_load_occlusion = occlusion.OwnLoadOcclusion(self)

    @property
    def terminal(self):
        return self.state in ('done', 'failed')

    @property
    def beam_grasp_confirmed(self):
        # Protocol adapter name only: it represents cyan OWN ISSUED CLOSE, not contact.
        return self.receipt and self.servo.get(1, 2000) < 2000

    def log(self, rid, event, now, **fields):
        self.events.append({'robot_id': rid, 'event': event, 't': now, **fields})

    def event(self, name, now, **fields):
        self.log(self.robot_id, name, now, **fields)

    def set_state(self, state, now):
        self.state, self.state_t = state, now
        self.event('state', now, state=state)

    def soft(self, code, now):
        n = self.soft_counts.get(code, 0)
        self.soft_counts[code] = n+1
        if n % 50 == 0:
            self.event('dev_light_would_stop', now, code=code, occurrence=n+1)

    def fail(self, code, now):
        self.failure = code
        self.arm.events.clear()
        self.arm.until = now
        self.sink.rows.clear()
        self.set_state('failed', now)
        return [{'kind': 'hold'}]

    def initial_commands(self, now, commands):
        from scripts.zone_teacher import ArmSequence
        self.servo = copy.deepcopy(commands[self.robot_id])
        self.arm = ArmSequence(self.sink, self.servo)
        self.on_command(self.robot_id, now, {'kind': 'initial_servo_command', 'pulses': self.servo})
        self.started_at = now

    def on_command(self, rid, now, action):
        if rid != self.robot_id:
            raise ValueError('foreign robot command')
        row = {'t': now, **copy.deepcopy(action)}
        self.blind.command(row, self.servo)
        self.pose.on_command(row)
        self.commands.append(row)
        if action['kind'] == 'arm':
            self.servo[action['servo_id']] = action['pulse']
            if action['servo_id'] == 1 and action['pulse'] >= 2000:
                self.receipt = False
        elif action['kind'] == 'look':
            self.servo[6] = action['pan_pulse']

    def on_frames(self, now, frames):
        # The backend may own three robots; only this robot's frame is exposed.
        obs, rgb = frames[self.robot_id]
        self.last_obs = obs
        verdict, _ = frame_gate.gate().assess(obs, self.robot_id, now, ob=False)
        allowed_occlusion = self.own_load_occlusion.accepts(now)
        bounded_blind = (self.state in ('blind_descent', 'grasp') and self.blind.window
            and not self.blind.disarmed and 0 <= now-self.blind.window['confirmed_at_s'] <= blind.limits()['blind_max_s'])
        if verdict == frame_gate.INVALID or (verdict == frame_gate.CONTENT_ONLY and not (allowed_occlusion or bounded_blind)):
            self.fail('INVALID_OWN_IMAGE', now)
        # Occlusion ALWAYS means predict only. Never supply a fabricated frame/fix.
        self.last_report = self.pose.on_frame(now, rgb if verdict == frame_gate.VALID else None)
        if verdict == frame_gate.CONTENT_ONLY and bounded_blind:
            self.event('bounded_blind_no_observation', now, frame_id=obs['frame_id'])
        rep = self.last_report
        self.pose_log.append({'t': now, 't_est': rep.t_est, 'x': rep.x_m, 'y': rep.y_m, 'yaw': rep.yaw_rad,
            'std_xy_m': rep.std_xy_m, 'std_yaw_rad': rep.std_yaw_rad, 'last_fix_t': rep.last_fix_t,
            'observation_quality': rep.observation_quality})

    def queue(self, target, now, *, duration=1., settle=.6):
        # Log the SAME v3 static arm sweep veto, then continue in DEV light.
        if not self.guard.transition_clear(self.servo, target, OwnPose.from_report(self.last_report),
                                            loaded=self.beam_grasp_confirmed):
            self.soft('ARM_COLLISION_GUARD', now)
        self.arm.queue(target, now, duration=duration, settle=settle)

    def scan(self, now, after):
        self.scan_queue = [{**LOOK_P20, 6: p} for p in LOOK_PANS]
        self.scan_after = after
        self.set_state('scan', now)

    def detections(self):
        out = self.vision.detect(self.last_obs, self.servo)
        rep = self.last_report
        c, s = math.cos(rep.yaw_rad), math.sin(rep.yaw_rad)
        valid = []
        for d in out:
            x, y = d['estimated_box_center_base_m'][:2]
            mx, my = rep.x_m+c*x-s*y, rep.y_m+s*x+c*y
            if (self.slot['x_range_m'][0]-.15 <= mx <= self.slot['x_range_m'][1]+.15
                and self.slot['y_range_m'][0]-.15 <= my <= self.slot['y_range_m'][1]+.15):
                valid.append(d)
        return valid

    def drive(self, xy, now, *, tolerance=.03):
        """Static A* plus east-facing mecanum pursuit on the released PF estimate."""
        from harness.map_goto import plan_path
        r = self.last_report
        if not r.initialized or not all(math.isfinite(v) for v in (r.x_m, r.y_m, r.yaw_rad)):
            return self.fail('POSE_NOT_INITIALIZED', now), False
        if r.std_xy_m > .05 or r.std_yaw_rad > math.radians(5) or r.last_fix_t is None:
            self.soft('POSE_UNCERTAIN', now)
        here = (r.x_m, r.y_m)
        yaw = (r.yaw_rad+math.pi) % (2*math.pi)-math.pi
        if math.dist(here, xy) <= tolerance and abs(yaw) <= .025:
            self.path, self.path_goal = [], None
            return [{'kind': 'hold'}], True
        if self.path_goal != tuple(xy):
            plan = plan_path(self.map, here, xy, ENVELOPE, escape_start_m=.10)
            if plan is None:
                # DEV collision veto is log-only; keep a direct candidate and record it.
                self.soft('PATH_COLLISION_GUARD', now)
                self.path = [list(xy)]
            else:
                # A same-cell route may contain only the start while yaw still
                # needs correcting. Keep a valid target for that final turn.
                self.path = plan['waypoints_m'][1:] or [list(xy)]
                self.event('path', now, plan=plan)
            self.path_goal = tuple(xy)
        while len(self.path) > 1 and math.dist(here, self.path[0]) < .035:
            self.path.pop(0)
        dx, dy = np.asarray(self.path[0])-np.asarray(here)
        c, s = math.cos(yaw), math.sin(yaw)
        v = np.array([c*dx+s*dy, -s*dx+c*dy, -yaw])
        v[:2] *= min(.8, .10/max(float(np.linalg.norm(v[:2])), 1e-9))
        v[2] = np.clip(v[2], -.12, .12)
        return self.motion(v, now), False

    def motion(self, velocity, now):
        profile = self.pose.provider.loc._pf.params['motion']
        u = (motor_command(profile, velocity) if 'deadband' in profile
             else np.linalg.solve(np.asarray(profile['gain'], float), velocity))
        u = np.clip(u, [-.05, -.10, -.15], [.15, .10, .15])  # CameraRobotPort raw limits
        return [{'kind': 'mecanum', 'forward': float(u[0]), 'left': float(u[1]),
                 'turn': float(u[2]), 'duration_s': CONTROL_S}]

    def _control(self, now, idle):
        if self.terminal:
            return [{'kind': 'hold'}]
        if now-self.started_at >= CAP_S:
            return self.fail('LOCAL_TIMEOUT', now)
        if self.pose.provider.failure:
            return self.fail('POSE_PROVIDER_ERROR', now)
        if not idle:
            return [{'kind': 'hold'}]
        r = self.last_report
        if self.state == 'init':
            self.scan(now, 'search_move')
        elif self.state == 'scan':
            if self.scan_queue:
                self.queue(self.scan_queue.pop(0), now, duration=.65, settle=.8)
            else:
                if r.last_fix_t is None:
                    self.soft('REOBSERVATION_NO_FIX', now)
                self.queue({**pose_of('search'), 1: 2000}, now)
                self.set_state(self.scan_after, now)
        elif self.state == 'search_move':
            x0, x1 = self.slot['x_range_m']
            cy = self.slot['center_m'][1]
            views = [(max(-.47, x0-.40), cy), (max(-.47, (x0+x1)/2-.40), cy)]
            commands, arrived = self.drive(views[min(self.search_i, len(views)-1)], now)
            if arrived:
                self.search_poses = [pose_of(k) for k in ('search', 'p45', 'inspect')]
                self.set_state('search', now)
            return commands
        elif self.state == 'search':
            fits = self.detections()
            if len(fits) == 1:
                self.target = fits[0]['estimated_box_center_base_m'][:2]
                self.set_state('align', now)
            elif self.search_poses:
                self.queue(self.search_poses.pop(0), now)
            elif self.search_i == 0:
                self.search_i += 1
                self.queue(pose_of('search'), now)
                self.set_state('search_move', now)
            else:
                return self.fail('CYAN_NOT_UNIQUELY_VISIBLE', now)
        elif self.state == 'align':
            fits = self.detections()
            if len(fits) != 1:
                self.align_streak = 0
                if now-self.state_t > 4.:
                    return self.fail('CYAN_ALIGN_VIEW_LOST', now)
                return [{'kind': 'hold'}]
            self.target = fits[0]['estimated_box_center_base_m'][:2]
            x, y = self.target
            # Same finite calibrated view changes as the pair approach.
            look_name = 'search' if x >= .34 else 'p45' if x >= .255 else 'inspect'
            target_pose = pose_of(look_name)
            if any(self.servo.get(k) != v for k, v in target_pose.items()):
                self.queue(target_pose, now)
                return [{'kind': 'hold'}]
            ex, ey = x-GRASP_RADIUS_M, y
            if abs(ex) <= .003 and abs(ey) <= .003:
                if self.last_obs['frame_id'] != self.last_align_frame:
                    self.align_streak += 1
                self.last_align_frame = self.last_obs['frame_id']
                if self.align_streak >= 2:
                    self.target_t = now
                    self.queue({**grasp_postures()[0], 1: 2000}, now, settle=blind.HOVER_SETTLE_S)
                    self.set_state('hover', now)
                return [{'kind': 'hold'}]
            self.align_streak = 0
            self.state_t = now
            return self.motion(np.array([np.clip(ex*.6, -.035, .035), np.clip(ey*.6, -.025, .025), 0.]), now)
        elif self.state == 'hover':
            if now-self.target_t > 30.:
                return self.fail('HOVER_ANCHOR_EXPIRED', now)
            support = self.vision.hover_support(self.last_obs, self.servo, self.target)
            ready = self.blind.confirm(now, self.last_obs, self.servo, self.target, support)
            self.event('cyan_hover_check', now, support=support, ready=ready,
                       frame_id=self.last_obs['frame_id'], streak=self.blind.streak)
            if ready:
                for p in grasp_postures()[1]:
                    self.queue(p, now, duration=blind.DESCENT_STEP_S, settle=0.)
                self.arm.until += blind.HOVER_SETTLE_S
                self.set_state('blind_descent', now)
            elif now-self.arm.until > blind.HOVER_CONFIRM_MAX_S:
                return self.fail('CYAN_HOVER_UNCONFIRMED', now)
        elif self.state == 'blind_descent':
            if not self.blind.ready(now, self.servo):
                return self.fail('BLIND_WINDOW_INVALID', now)
            self.queue({1: 1500}, now, duration=.5, settle=.4)
            self.set_state('grasp', now)
        elif self.state == 'grasp':
            if not self.blind.ready(now, self.servo) or self.servo.get(1) != 1500:
                return self.fail('CLOSE_NOT_ISSUED', now)
            self.receipt = True
            self.event('cyan_close_receipt', now, evidence='own issued close only; contact unverified')
            # Low lift before the exact v98 HIGH trajectory.
            self.queue({**grasp_postures()[0], 1: 1500}, now, duration=1.2, settle=2.8)
            for p, duration, settle in high.raise_path():
                self.queue({**p, 1: 1500}, now, duration=duration, settle=settle)
            self.set_state('lift', now)
        elif self.state == 'lift':
            self.event('high_carry_pose', now, held_by='own command history')
            self.set_state('carry', now)
        elif self.state == 'carry':
            if not self.beam_grasp_confirmed or not high.at_high(self.servo):
                return self.fail('LOADED_COMMAND_STATE_LOST', now)
            commands, arrived = self.drive(self.route[self.route_i], now)
            if arrived:
                self.event('carry_checkpoint', now, index=self.route_i, last_fix_t=r.last_fix_t)
                self.route_i += 1
                if self.route_i == len(self.route):
                    for p, duration, settle in high.lower_path():
                        self.queue({**p, 1: 1500}, now, duration=duration, settle=settle)
                    self.set_state('lower', now)
                else:
                    # Stationary HIGH observation; no false fresh receipt if cyan blocks walls.
                    self.arm.until = now+high.HIGH_SETTLE_S
            return commands
        elif self.state == 'lower':
            self.queue({1: 2000}, now, duration=.5, settle=.5)
            self.queue({**grasp_postures()[0], 1: 2000}, now, duration=1.2, settle=1.)
            self.queue({**pose_of('search'), 1: 2000}, now)
            self.set_state('released', now)
        elif self.state == 'released':
            self.event('place_sequence_complete', now, physical_success=None)
            self.set_state('done', now)
        return [{'kind': 'hold'}]

    def step(self, now):
        if self.terminal:
            return [(self.robot_id, {'kind': 'hold'})]
        idle = self.arm.tick(now)
        commands = self._control(now, idle) if now >= self.next_control-1e-8 else []
        if now >= self.next_control-1e-8:
            self.next_control = now+CONTROL_S
        # Failed control cancels all queued arm proposals in this same tick.
        arm_rows, self.sink.rows = self.sink.rows, []
        if self.terminal:
            return [(self.robot_id, {'kind': 'hold'})]
        return [(self.robot_id, c) for c in [*commands, *arm_rows]]

    def record(self):
        return {'profile': PROFILE, 'motion_proxy': MOTION_PROXY, 'state': self.state, 'failure': self.failure,
            'robot_id': self.robot_id, 'events': self.events, 'poses': self.pose_log,
            'commands': self.commands, 'provider': self.pose.record(), 'dev_light_would_stop': self.soft_counts,
            'occlusion': self.own_load_occlusion.export(), 'blind_window': self.blind.window,
            'physical_success': None, 'in_run_drop_tilt_contact_detection': False,
            'controller_inputs': ['own_rgb', 'static_map', 'own_command_history']}

    def close(self):
        self.pose.close()
