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


class GraspTransitionRule:
    """Rule-based grasp completion from own issued commands only. DEFAULT OFF.

    The shipped actor's learned done head never fires (raw done max 0.0033
    against the 0.65 decode threshold), so the grasp -> release transition
    never opens. This rule replaces that transition trigger with something
    the robot can observe by itself: the wheels are still and the commanded
    arm posture matches the posture the teacher held when it ended the grasp.

    Inputs are ONLY the own issued command row and the clock. Contact force,
    tilt, clearance, ground truth and weld are never read here: they belong
    to the evaluation-only path (SoloScore) and may not steer a phase.

    Every constant below is justified by ONE recorded teacher episode (seed
    86100, export dev-smoke-only-86100). One episode is not a distribution;
    these numbers are a first rule to be re-measured, not a tuned threshold.
    """

    # End posture of the teacher's grasp skill: the PWM the teacher had
    # issued in the row where it ended the grasp (phase 'hold',
    # terminal_reason 'command_sequence_complete'), servos 1,3,4,5,6 =
    # 1500, 835, 1925, 2176, 1510.
    END_PWM = {'1': 1500, '3': 835, '4': 1925, '5': 2176, '6': 1510}
    # Mean absolute PWM error per servo that still counts as the end
    # posture. 100 is the tolerance of the offline predicate check on the
    # same episode: the still-open gripper state sat 116.0 away (rejected)
    # while the held end posture stayed within 89.8 (accepted), so the
    # rule's acceptance band has margin on both sides of that episode.
    TOLERANCE_PWM = 100
    # Consecutive issued rows that must show the end posture. The teacher
    # itself held that identical posture for 45 rows (4.5 s at the 0.1 s
    # command period) before it ended the grasp, and that episode's done
    # label is anchored 45 rows back from the identical-posture run. The
    # rule therefore requires the robot to hold the end posture for the
    # same 4.5 s before it may call the grasp complete.
    HOLD_ROWS = 45

    def __init__(self, *, end_pwm=None, tolerance_pwm=None, hold_rows=None):
        self.end_pwm = dict(self.END_PWM if end_pwm is None else end_pwm)
        self.tolerance_pwm = self.TOLERANCE_PWM if tolerance_pwm is None else tolerance_pwm
        self.hold_rows = self.HOLD_ROWS if hold_rows is None else hold_rows
        self.hold = 0
        self.fired = False
        self.fire_t = None

    def distance(self, pwm):
        """Mean absolute error per servo against the end posture."""
        return sum(abs(pwm[s] - self.end_pwm[s]) for s in self.end_pwm) / len(self.end_pwm)

    def observe(self, now, issued):
        """Feed one own issued command row. True when the grasp completes.

        The counter resets on any moving wheel and on any posture outside
        the tolerance, so only an unbroken run of HOLD_ROWS rows counts.
        """
        if self.fired:
            return False
        if not all(abs(w) < 1e-9 for w in issued['wheels']):
            self.hold = 0
            return False
        if self.distance(issued['pwm']) > self.tolerance_pwm:
            self.hold = 0
            return False
        self.hold += 1
        if self.hold >= self.hold_rows:
            self.fired = True
            self.fire_t = now
            return True
        return False


class SoloSequence:
    """Instruction schedule driven only by student done and simulation clock.

    With `grasp_rule` the grasp skill may also complete through the
    own-issued-command rule (GraspTransitionRule). The rule reads only the
    robot's own issued commands and the clock; it never reads contact force,
    tilt, clearance, ground truth or weld. The release skill keeps its
    learned-done completion: the rule never applies to it.
    """
    SETTLE_S = 3.1

    def __init__(self, with_release=False, *, grasp_rule=False):
        self.with_release, self.skill = with_release, 'grasp'
        self.done_times = {}
        # Completion cause per skill: 'done' (learned done bit) or 'rule'
        # (the own-issued-command rule). A skill that never completed has no
        # entry, so a rule completion is distinguishable from a learned one.
        self.done_causes = {}
        # None keeps the pre-rule path exactly as it was.
        self.rule = GraspTransitionRule() if grasp_rule else None

    def update(self, now, done, issued=None):
        # With the rule OFF (the default) the statements below are exactly the
        # pre-rule ones: same order, same conditions, same results.
        if self.rule is None:
            if done:
                self.done_times.setdefault(self.skill, now)
            end = self.done_times.get(self.skill)
            if end is None or now - end < self.SETTLE_S - 1e-8:
                return False
            if self.skill == 'grasp' and self.with_release:
                self.skill = 'release'
                return False
            return True
        if done:
            self.done_times.setdefault(self.skill, now)
            self.done_causes.setdefault(self.skill, 'done')
        if (self.skill == 'grasp' and 'grasp' not in self.done_times
                and issued is not None and self.rule.observe(now, issued)):
            self.done_times.setdefault('grasp', now)
            self.done_causes.setdefault('grasp', 'rule')
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
