"""Optional v106 lift/check/retry adapter; observation memory stays per robot.

No base retreat: repeat the last pre-grasp aligned arm view, closed gripper,
then return HIGH. The loaded PF already skips non-HIGH map updates. No new
loaded inspection calibration is invented for the image-to-image comparison.
"""
from __future__ import annotations

import copy
import cv2
import numpy as np
from harness import zone_solo_cyan_v106 as old
from harness.zone_solo_cyan_scene_change import SiteMemory, CONFIG, PROFILE, decode, cyan, lens_valid
from harness.zone_solo_cyan_vision_v106 import CyanVision, BlindCyan

OPTION = 'pickup_site_v1'


class SceneCheck:
    def __init__(self):
        self.memory = None
        self.reference_command_i = 0
        self.phase = None
        self.retries = 0
        self.samples = []
        self.last_key = None
        self.seen_frames = set()
        self.last_sample_t = float('-inf')
        self.visual_status = 'unconfirmed'
        self.checks = []
        self.notifications = []
        self.pending_notifications = []
        self.drop_frames = []
        self.drop_last_key = None
        self.drop_reported = False
        self.floor_vision = None

    def notify(self, r, now, code, text, evidence):
        notice = {'robot_id': r.robot_id, 't': now, 'code': code, 'text': text,
                  'policy': 'log_only', 'evidence': evidence, 'physical_success': None}
        self.notifications.append(notice)
        self.pending_notifications.append(copy.deepcopy(notice))
        r.event('cyan_visual_notification', now, **{k: v for k, v in notice.items() if k not in ('robot_id', 't')})

    def remember(self, r, now):
        self.memory = None  # never reuse the previous attempt's reference
        self.visual_status = 'unconfirmed'
        try:
            obs = r.last_obs
            verdict, _ = old.frame_gate.gate().assess(obs, r.robot_id, now, ob=False)
            if verdict != old.frame_gate.VALID:
                raise ValueError('invalid pre-grasp image')
            fits = r.vision.detect(obs, r.servo)
            if len(fits) != 1:
                raise ValueError('nonunique pre-grasp target')
            self.memory = SiteMemory(obs, fits[0]['pixel_bbox'], r.target, r.servo)
            self.reference_command_i = len(r.commands)
            r.event('cyan_scene_reference', now, **self.memory.record)
        except (ValueError, KeyError) as exc:
            r.event('cyan_scene_reference_unavailable', now, reason=str(exc), physical_success=None)

    def restore_high(self, r, now):
        for p, duration, settle in old.high.raise_path():
            r.queue({**p, 1: 1500}, now, duration=duration, settle=settle)
        self.phase = 'restore_high'

    def finish_check(self, r, now):
        present = sum(s['decision'] == 'present' for s in self.samples)
        complete = len(self.samples) == CONFIG['frames']
        clear = complete and all(s['decision'] in ('present', 'absent') for s in self.samples)
        if present > CONFIG['max_present_for_absent']:
            self.visual_status = 'failed'
        elif clear:
            self.visual_status = 'confirmed_by_site_disappearance'
        else:
            self.visual_status = 'unknown'
        report = {'status': self.visual_status, 'attempt': self.retries+1,
                  'before': None if self.memory is None else self.memory.record,
                  'samples': copy.deepcopy(self.samples), 'physical_success': None}
        self.checks.append(report)
        r.event('cyan_scene_grasp_check', now, **report)
        if self.visual_status == 'failed':
            if self.retries >= CONFIG['max_retries']:
                return r.fail('CYAN_SCENE_RETRY_EXHAUSTED', now)
            self.retries += 1
            # Empty by visual inference, but still lower before opening. Never
            # open at HIGH; keep the original normal-contact descent path.
            for p, duration, settle in old.high.lower_path():
                r.queue({**p, 1: 1500}, now, duration=duration, settle=settle)
            self.phase = 'retry_lower'
        else:
            if self.visual_status == 'unknown':
                r.soft('GRASP_SCENE_UNCONFIRMED', now)
                self.notify(r, now, 'GRASP_SCENE_UNCONFIRMED',
                            '원래 블록 자리를 확실히 보지 못해 파지 여부는 미확인입니다.', report)
            self.restore_high(r, now)
        return [{'kind': 'hold'}]

    def control(self, r, now, idle, base):
        if r.terminal or now-r.started_at >= old.CAP_S or r.pose.provider.failure or not idle:
            return base(now, idle)
        if r.state != 'lift':
            before = r.state
            commands = base(now, idle)
            if before == 'align' and r.state == 'hover':
                self.remember(r, now)
            if before == 'grasp' and r.state == 'lift':
                self.phase, self.samples, self.last_key = 'pending', [], None
                self.seen_frames, self.last_sample_t = set(), float('-inf')
                self.drop_frames, self.drop_last_key, self.drop_reported = [], None, False
            return commands
        if self.phase == 'pending':
            if self.memory is None:
                return self.finish_check(r, now)
            # Reverse only the raised links, stopping at the remembered view.
            # No floor descent, no chassis command and no gripper-open here.
            for pose in (old.high.VIA_130, old.high.VIA_110, self.memory.servo):
                r.queue({**pose, 1: 1500}, now, duration=old.high.MOVE_S, settle=old.high.VIA_SETTLE_S)
            self.phase = 'position_view'
        elif self.phase == 'position_view':
            self.phase, self.capture_after = 'observe', now
        elif self.phase == 'observe':
            obs = r.last_obs
            key = None if obs is None else (obs['frame_id'], obs['sim_time'])
            if (obs and key != self.last_key and obs['frame_id'] not in self.seen_frames
                    and obs['sim_time'] > max(self.capture_after, self.last_sample_t)):
                self.last_key = key
                self.seen_frames.add(obs['frame_id'])
                self.last_sample_t = obs['sim_time']
                verdict, _ = old.frame_gate.gate().assess(obs, r.robot_id, now, ob=False)
                moved = any(c['kind'] == 'mecanum' and any(c.get(k, 0) != 0 for k in ('forward', 'left', 'turn'))
                            for c in r.commands[self.reference_command_i:])
                same_view = all(r.servo.get(k) == v for k, v in self.memory.servo.items())
                if verdict == old.frame_gate.VALID and same_view and not moved:
                    try:
                        row = self.memory.compare(obs)
                    except ValueError as exc:
                        row = {'decision': 'unknown', 'reason': str(exc), 'after_sha256': obs.get('sha256')}
                else:
                    row = {'decision': 'unknown', 'reason': 'invalid_image_or_changed_base_or_view',
                           'after_sha256': obs.get('sha256')}
                self.samples.append(row)
            if len(self.samples) >= CONFIG['frames'] or now-self.capture_after >= 30.:
                return self.finish_check(r, now)
        elif self.phase == 'retry_lower':
            r.queue({1: 2000}, now, duration=.5, settle=.5)
            r.queue({**old.grasp_postures()[0], 1: 2000}, now, duration=1.2, settle=1.)
            r.queue({**old.pose_of('search'), 1: 2000}, now)
            self.phase = 'retry_open'
        elif self.phase == 'retry_open':
            r.blind = BlindCyan()
            r.target, r.target_t, r.align_view, r.last_align_frame = None, None, None, None
            r.align_streak = 0
            r.search_poses = [old.pose_of(k) for k in old.ALIGN_VIEWS]
            self.memory, self.phase = None, None
            r.set_state('search', now)  # reacquire from RGB; no old coordinate grasp
        elif self.phase == 'restore_high':
            self.phase = None
            return base(now, idle)  # original lift -> carry transition
        else:
            # A loaded runtime without a causal pre-grasp reference cannot
            # silently turn its own close command into visual confirmation.
            self.samples = []
            return self.finish_check(r, now)
        return [{'kind': 'hold'}]

    def observe_carry(self, r, now):
        if r.state != 'carry' or not old.high.at_high(r.servo) or not r.beam_grasp_confirmed:
            self.drop_frames = []
            return
        obs = r.last_obs
        key = (obs['frame_id'], obs['sim_time'])
        if key == self.drop_last_key or self.drop_reported:
            return
        self.drop_last_key = key
        verdict, _ = old.frame_gate.gate().assess(obs, r.robot_id, now, ob=False)
        if verdict != old.frame_gate.VALID:
            self.drop_frames = []
            return
        try:
            image = decode(obs)  # evidence digest must match the actual image bytes
        except ValueError:
            self.drop_frames = []
            return
        if self.floor_vision is None:
            cal = copy.deepcopy(r.pose.provider.calibration)
            # CyanVision's fixed lookup name is unloaded. Here only the
            # existing loaded HIGH table is supplied to this separate detector.
            cal['camera_models']['unloaded'] = copy.deepcopy(cal['camera_models']['loaded'])
            self.floor_vision = CyanVision(cal)
        fits = self.floor_vision.detect(obs, r.servo)
        if len(fits) != 1:
            self.drop_frames = []
            return
        fit = fits[0]
        x, y, w, h = fit['pixel_bbox']
        lens_edge = ~cv2.erode(lens_valid().astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
        if (x <= 0 or y <= 0 or x+w >= 639 or y+h >= 479 or
                np.any((cyan(image) & lens_edge)[y:y+h, x:x+w])):
            self.drop_frames = []  # clipped wrist strip is not a floor block
            return
        self.drop_frames.append({'sha256': obs['sha256'], 'frame_id': obs['frame_id'],
                                 't': obs['sim_time'], 'cyan_area_px': fit['area_px'],
                                 'pixel_bbox': list(fit['pixel_bbox'])})
        self.drop_frames = self.drop_frames[-2:]
        if len(self.drop_frames) == 2:
            self.notify(r, now, 'CYAN_CARRY_DROP_SUSPECTED',
                        '운반 중 자기 영상에서 바닥 cyan이 보여 놓침이 의심됩니다. 주행은 계속합니다.',
                        copy.deepcopy(self.drop_frames))
            self.drop_reported = True

    def record(self):
        return {'profile': PROFILE, 'option': OPTION, 'config': dict(CONFIG),
                'visual_status': self.visual_status, 'checks': self.checks,
                'retry_count': self.retries, 'notifications': self.notifications,
                'drop_policy': 'own RGB positive floor-cyan suspicion; log_only; no gate/stop/regrasp',
                'physical_success': None, 'runtime_admitted': False}
