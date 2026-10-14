"""Allowed history construction and evaluation-only score; no simulator imports."""
from collections import deque
import hashlib

from harness import grasp_act_contract as c


class InputAudit:
    def __init__(self):
        self.record = {'forbidden_input_fields': 0, 'teacher_input_fields': 0, 'requests': 0}

    def accept(self, observation):
        try:
            c.validate_observation(observation)
        except (ValueError, TypeError, KeyError):
            self.record['forbidden_input_fields'] += 1
            raise
        self.record['requests'] += 1
        return observation


class OwnHistory:
    def __init__(self, robot_id, episode_id, initial_command):
        self.robot_id, self.episode_id = robot_id, episode_id
        self.issued = deque([c.command(initial_command)] * c.HISTORY, maxlen=c.HISTORY)
        self.frames = deque()
        self.clock, self.index = c.IssuedClock(), 0

    def observe(self, now, jpeg, *, skill, object_kind, role, destination_zone='none'):
        path = f'rgb/{self.robot_id}/{self.index:06d}.jpg'
        ref = {'path': path, 'sha256': hashlib.sha256(jpeg).hexdigest(), 't': now, 'robot_id': self.robot_id}
        self.frames.append((ref, jpeg))
        while len(self.frames) > 1 and self.frames[1][0]['t'] < now - c.MEMORY_S - .1:
            self.frames.popleft()
        refs = c.image_history([r for r, _ in self.frames], now)
        pixels = {r['path']: jpg for r, jpg in self.frames}
        instruction = (skill, object_kind, role, destination_zone)
        obs = {'schema': c.SCHEMA, 'robot_id': self.robot_id,
               'sample_id': f'{self.episode_id}:{self.index}:{self.robot_id}', 't': now,
               'skill': skill, 'object_kind': object_kind, 'role': role,
               'destination_zone': destination_zone, 'rgb': refs, 'issued': list(self.issued),
               **self.clock.observe(instruction, now, self.issued[-1]['pwm'])}
        self.index += 1
        c.validate_observation(obs)
        return obs, [pixels[r['path']] for r in refs], path

    def issue(self, value):
        self.issued.append(c.command(value))


class LiftScore:
    """Evaluation-only: never supplies phase, done, or correction to the actor."""
    CRITERIA = {'clearance_m': .012, 'tilt_deg': 10., 'finger_each_n': .5, 'hold_s': 3., 'weld': 'off'}

    def __init__(self):
        self.previous_t, self.previous_good, self.stable_s, self.max_stable_s = None, False, 0., 0.

    def add(self, now, *, clearance, tilt, forces, weld):
        if weld:
            raise ValueError('WELD_ACTIVE')
        dt = 0. if self.previous_t is None else now - self.previous_t
        if not 0 <= dt <= .15 + 1e-8:
            raise ValueError('evaluation clock gap')
        good = clearance >= .012 and tilt <= 10. and min(forces) >= .5
        self.stable_s = self.stable_s + dt if good and self.previous_good else 0.
        self.max_stable_s = max(self.max_stable_s, self.stable_s)
        self.previous_good, self.previous_t = good, now

    def record(self):
        return {'lift_success': self.max_stable_s >= 3. - 1e-8,
                'max_stable_lift_s': self.max_stable_s, 'criteria': self.CRITERIA}
