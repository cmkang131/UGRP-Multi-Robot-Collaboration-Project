"""Robot-side code for skill tests B and C: find a wall number sign, stand in front of it, (C) set the box down.

B is the last part of the evaluated carry (harness/carry_nav_v1.py) on its own: the robot is put where
the carry would be just after the door (phase 'pass', own pose = the list-frame origin) and the carry
goes on exactly as in a team run: turn on the spot in 30 deg steps reading the number sign with the own
camera (harness/place_memory_v1.py, harness/robot_tags_v1.py), drive to 0.9 m short of it, look again
(sweep once if missed), drive to the floor point SIGN_BOX_M in front of the sign, lower the arm.
Command rows are built as the team runner builds them (carry_rows / carry_pwm of
scripts/run_grasp_act_student.py, the same pulses and constants).
C then plays the fixed set-down (solo_pipeline/harness/release_code_v1.py), as the team runner does
when the carry has finished.

Not used here (no ceiling camera): the measured pose and the known arena. The own pose is the nominal
pulse estimate, as in a team run without --overhead. The arm holds `hold_pwm` (the grasp posture) the
whole time; with no box in the gripper B still tests looking and driving.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# A grasp posture: median of the last 45 issued ACT rows before the grasp-end rule, sim pick of seed 91421
# (scripts/real_skill_test.py pick). Used only when no grasp happened before (B/C started holding by hand).
SIM_HOLD_PWM = {'1': 1498, '3': 647, '4': 1735, '5': 2263, '6': 1522}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, mod)
    spec.loader.exec_module(mod)
    return mod


def team_kit():
    """The carry rows, planning arithmetic and constants of the team runner, as the runner passes them."""
    r = _load('team_runner_for_kit', ROOT / 'scripts' / 'run_grasp_act_student.py')
    names = ('carry_rows', 'carry_to_plan', 'carry_nominal_pose', 'carry_route', 'carry_legs_spec', 'carry_point_clearance',
             'carry_door_step', 'CARRY_DOOR_STANDOFF_M', 'CARRY_LOOK_S', 'CARRY_PASS_TRIES', 'CARRY_BOX_ROW',
             'CARRY_PASS_BEYOND_M', 'CARRY_UNIT', 'CARRY_SWEEP_M', 'CARRY_BODY_M', 'CARRY_BACK_MAX_M')
    return types.SimpleNamespace(**{n: getattr(r, n) for n in names}), r.carry_pwm


class SignBrain:
    def __init__(self, sign, *, hold_pwm=None, held_kind=None, with_release=False, log=None):
        from harness import grasp_act_contract as c
        self.c, self.log, self.sign = c, log, int(sign)
        self.kit, self.carry_pwm = team_kit()
        _load('ground_projection', ROOT / 'harness' / 'approach_survey_v1_parts' / 'ground_projection.py')
        places = _load('place_memory_v1', ROOT / 'harness' / 'place_memory_v1.py').PlaceMemory(sys.modules['ground_projection'])
        nav_mod = _load('carry_nav_v1', ROOT / 'harness' / 'carry_nav_v1.py')
        self.nav = nav_mod.CarryNav(self.kit, places, {'x': 0., 'y': 0., 'yaw': 0.}, [], 'zone_sign%d' % self.sign,
                                    held_kind=held_kind)
        self.nav.phase = 'pass'              # as just after the door: the next step is the look-around for the sign
        # the carry raises the arm to the look-around posture right after the grasp ('arm:far', CARRY_ARM_ROWS rows) and
        # keeps it up through the door; starting from the hold posture, the same rows come first here
        self.nav._extend('arm:far')
        self.hold = dict(hold_pwm or SIM_HOLD_PWM)
        self.release_on = with_release
        self.release_mod = _load('release_code_v1', ROOT / 'solo_pipeline' / 'harness' / 'release_code_v1.py') if with_release else None
        self.release = None
        self.previous = None
        self.finished = False

    def start(self):
        return dict(self.hold)

    def begin(self, now):
        self.previous = {'t': now, 'wheels': [0.] * 4, 'duration_s': [0.] * 4, 'pwm': dict(self.hold)}

    @property
    def stage(self):
        return 'release' if self.release is not None else 'carry:' + self.nav.phase

    def step(self, jpeg, now):
        c = self.c
        out = None if self.nav.finished else self.nav.step(jpeg, {int(k): int(v) for k, v in self.previous['pwm'].items()})
        if out is not None:
            w, d, level = out
            value = c.command({'t': now, 'wheels': list(w), 'duration_s': [d if x else 0. for x in w],
                               'pwm': self.carry_pwm(self.hold, level)})
            source = 'carry_code'
        elif self.release_on:
            if self.release is None:
                self.release = self.release_mod.ReleaseCodeV1(c, self.previous['pwm'])
            value, done = self.release.step(now)
            source = 'release_code'
            if done:
                self.finished = True
        else:
            value = c.command({'t': now, 'wheels': [0.] * 4, 'duration_s': [0.] * 4, 'pwm': dict(self.previous['pwm'])})
            source = 'done'
            self.finished = True
        self.previous = value
        if self.log is not None:
            self.log({'t': now, 'stage': self.stage, 'source': source, 'command': value})
        return value, source

    def record(self):
        r = self.nav.record()
        return {'sign': self.sign, 'outcome': r['outcome'], 'phase': r['phase'], 'zone_seen': r['zone_seen'],
                'steps': r['steps'], 'pose_estimate': r['pose_estimate'], 'rows_issued': r['rows_issued'],
                'release': self.release.record() if self.release is not None else None, 'finished': self.finished}
