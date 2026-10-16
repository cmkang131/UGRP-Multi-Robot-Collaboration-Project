"""Allowed history construction and evaluation-only score; no simulator imports."""
from collections import deque
import hashlib

from harness import grasp_act_contract as c


def evaluation_gates(row, *, stable_lift):
    """Evaluation evidence, never an instruction/phase input.

    The teacher's .08m/.008m/.04rad nominal pose is descriptive. Students can
    grasp successfully from another feasible pose: the unchanged bilateral
    .5N criterion proves functional alignment, and stable lift proves contact.
    This logical implication adds no acceptance tolerance or policy correction.
    """
    grasp = min(row['forces']) >= LiftScore.CRITERIA['finger_each_n'] or stable_lift
    alignment = grasp or (row['station_error_m'] <= .008 and row['yaw_error_rad'] <= .04)
    return {'approach': alignment or row['station_error_m'] <= .08,
            'alignment': alignment, 'grasp': grasp, 'lift_confirmation': stable_lift}


class InputAudit:
    def __init__(self):
        self.record = {'forbidden_input_fields': 0, 'teacher_input_fields': 0, 'requests': 0,
                       'invisible_measurements': 0, 'held_world_reads': 0, 'top': 0,
                       'mechanism': 'isolated JSON worker; strict own RGB/issued/instruction allowlist; no simulator capability'}

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


class SoloSequence:
    """Instruction schedule driven only by student done and simulation clock."""
    SETTLE_S = 3.1

    def __init__(self, with_release=False):
        self.with_release, self.skill = with_release, 'grasp'
        self.done_times = {}

    def update(self, now, done):
        if done:
            self.done_times.setdefault(self.skill, now)
        end = self.done_times.get(self.skill)
        if end is None or now - end < self.SETTLE_S - 1e-8:
            return False
        if self.skill == 'grasp' and self.with_release:
            self.skill = 'release'
            return False
        return True


class SoloScore:
    """Evaluation only. Never used to select a skill or stop the rollout.

    Setdown is at pickup_site: grounded, upright, stationary, no finger load
    for three seconds after the release instruction, following a stable lift.
    """
    RELEASE_CRITERIA = {'clearance_m': [-.005, .006], 'tilt_deg': 10.,
                        'finger_max_n': .1, 'linear_speed_m_s': .02, 'hold_s': 3.,
                        'airborne_unloaded_drop_clearance_m': .012}

    def __init__(self):
        self.lift = LiftScore()
        self.previous_t, self.previous_good = None, False
        self.stable_s = self.max_stable_s = 0.
        self.drop_detected = False

    def add(self, now, *, skill, linear_speed, **evaluation):
        if evaluation['weld']:
            raise ValueError('WELD_ACTIVE')
        if skill == 'grasp':
            self.lift.add(now, **evaluation)
        dt = 0. if self.previous_t is None else now - self.previous_t
        if not 0 <= dt <= .15 + 1e-8:
            raise ValueError('evaluation clock gap')
        self.drop_detected |= (self.lift.record()['lift_success']
                               and evaluation['clearance'] > .012 and max(evaluation['forces']) < .1)
        good = (not self.drop_detected and skill == 'release' and self.lift.record()['lift_success']
                and -.005 <= evaluation['clearance'] <= .006
                and evaluation['tilt'] <= 10. and max(evaluation['forces']) < .1
                and linear_speed <= .02)
        self.stable_s = self.stable_s + dt if good and self.previous_good else 0.
        self.max_stable_s = max(self.max_stable_s, self.stable_s)
        self.previous_t, self.previous_good = now, good

    def record(self, done_times, *, with_release):
        lift = self.lift.record()
        release = self.max_stable_s >= 3. - 1e-8
        success = not self.drop_detected and lift['lift_success'] and (release if with_release else True)
        failure = (None if success else 'drop_detected' if self.drop_detected
                   else 'grasp_done_not_requested' if 'grasp' not in done_times
                   else 'lift_not_stable' if not lift['lift_success']
                   else 'release_done_not_requested' if 'release' not in done_times
                   else 'release_not_stable')
        return {**lift, 'release_success': release if with_release else None,
                'max_stable_release_s': self.max_stable_s,
                'drop_detected': self.drop_detected,
                'release_criteria': self.RELEASE_CRITERIA if with_release else None,
                'physical_success': success, 'failure_reason': failure}
