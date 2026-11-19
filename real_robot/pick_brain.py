"""Robot-side part of the evaluated solo pick, as one object: (own JPEG, own clock) -> command row.

Copied branch by branch from solo_pipeline/scripts/run_grasp_act_student.py with the options of
the evaluated solo runs: approach_survey_v1 on, grasp_transition_rule on, release_code_v1 optional;
gaze, approach_code_v1 and carry_test_v1 off. Everything that reads the simulator (scoring, contact
forces, the evaluation-side box matching) is left out, so the same object can drive the simulator
and the real robot (scripts/real_skill_test.py).

One change, needed outside the simulator: which observed box to pick. The simulator runner matches
the designated box against the true scene (evaluation side). Here `select` is a rule over the
robot's own observed list only (default: the nearest entry of the wanted colour), and the sim
test uses the same rule, so both sides pick the same way.
"""
from __future__ import annotations

import base64
import importlib.util
import json
import math
import selectors
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INITIAL_PWM = {'1': 2000, '3': 740, '4': 2320, '5': 1320, '6': 1500}   # runner: fixed far posture before the survey


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def nearest_of_kind(kind):
    """Pick rule over the robot's own observed list: the nearest entry of `kind`, or None."""
    def select(entries):
        own = [(math.hypot(e['x'], e['y']), i) for i, e in enumerate(entries) if e.get('kind') == kind]
        return min(own)[1] if own else None
    return select


class Worker:
    """ACT in its own process (scripts/grasp_act_student_worker.py), as the runner does."""

    def __init__(self, actor_python, model, threads=1, timeout_s=120.):
        self.p = subprocess.Popen([actor_python, '-m', 'scripts.grasp_act_student_worker', '--model', str(model),
                                   '--threads', str(threads)], cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  text=True, bufsize=1)
        self.timeout_s = timeout_s
        if self._read() != {'ready': True}:
            raise RuntimeError('student worker did not load')
        self.latencies = []

    def _read(self):
        with selectors.DefaultSelector() as sel:
            sel.register(self.p.stdout, selectors.EVENT_READ)
            if not sel.select(self.timeout_s):
                raise TimeoutError('student inference timeout')
        line = self.p.stdout.readline()
        if not line:
            raise RuntimeError('student worker exited')
        return json.loads(line)

    def predict(self, observation, jpegs):
        t = time.monotonic()
        self.p.stdin.write(json.dumps({'observation': observation, 'jpegs': [base64.b64encode(x).decode() for x in jpegs]},
                                      allow_nan=False) + '\n')
        self.p.stdin.flush()
        out = self._read()
        self.latencies.append(time.monotonic() - t)
        if set(out) != {'chunk'}:
            raise ValueError('student response whitelist mismatch')
        return out['chunk']

    def close(self):
        if self.p.poll() is None:
            self.p.kill()
            self.p.wait()


class PickBrain:
    def __init__(self, predict, *, kind, role='west', with_release=False, select=None, log=None):
        from harness import grasp_act_contract as c
        from harness.grasp_act_policy import ChunkExecutor
        from harness.grasp_act_rollout import OwnHistory, SoloSequence, GraspTransitionRule
        self.c, self.GraspTransitionRule, self._OwnHistory = c, GraspTransitionRule, OwnHistory
        self.kind, self.role, self.log = kind, role, log
        surv = _load('approach_survey_v1', ROOT / 'solo_pipeline' / 'harness' / 'approach_survey_v1.py')
        self.select_rule = select or nearest_of_kind(kind)
        self.selected = {}
        def _select(entries):
            i = self.select_rule(entries)
            self.selected = {'entries': entries, 'selected_index': i}
            return i
        self.approach = surv.SurveyApproach(c, _select)
        self.D_STOP_M = self.approach.D_STOP_M
        self.executor = ChunkExecutor(predict, n_action_steps=c.CHUNK, temporal_ensemble_coeff=None)
        self.sequence = SoloSequence(with_release, grasp_rule=False)
        self.release_on, self.release_mod, self.release_code = with_release, None, None
        if with_release:
            self.release_mod = _load('release_code_v1', ROOT / 'solo_pipeline' / 'harness' / 'release_code_v1.py')
        self.issued_hist, self.hold_pwm = [], None
        self.rule_state = {'wanted': True, 'armed_at_handover': False, 'note': 'pending handover'}
        self.previous = None
        self.history = None
        self.finished = False
        self.ignored_done = 0

    def start(self):
        """The fixed initial posture. The caller applies it, waits 1 s (as the runner does), then calls begin()."""
        return dict(INITIAL_PWM)

    def begin(self, now):
        self.previous = {'t': now, 'wheels': [0.] * 4, 'duration_s': [0.] * 4, 'pwm': dict(INITIAL_PWM)}
        self.history = self._OwnHistory('r1', 'skill-test', self.previous)

    @property
    def stage(self):
        if not self.approach.arrived:
            return 'approach:' + str(self.approach.stage)
        return self.sequence.skill

    def step(self, jpeg, now):
        """One 0.1 s tick. Returns (command row, source) or None once the sequence has finished."""
        c, seq, approach = self.c, self.sequence, self.approach
        obs, jpegs, _rel = self.history.observe(now, jpeg, skill=seq.skill, object_kind=self.kind, role=self.role,
                                                destination_zone='pickup_site' if seq.skill == 'release' else 'none')
        c.validate_observation(obs)
        code = approach.step(jpeg, now) if not approach.arrived else None
        if approach.arrived and 'act_clock' not in self.rule_state:
            clock = c.IssuedClock()
            clock.skill = (seq.skill, self.kind, self.role, 'none')
            clock.started = now + c.PERIOD_S - approach.approach_seconds()
            self.history.clock = clock
            self.rule_state['act_clock'] = {'rebased_at_s': now, 'approach_s': approach.approach_seconds()}
        if code is not None:
            value, done, source = code, False, 'code'
        elif self.release_on and seq.skill == 'release':
            if self.release_code is None:
                self.release_code = self.release_mod.ReleaseCodeV1(c, self.previous['pwm'])
            value, done = self.release_code.step(now)
            source = 'release_code'
        elif self.release_on and seq.skill == 'grasp' and seq.rule is not None and seq.rule.fired:
            if self.hold_pwm is None:
                self.hold_pwm = self.hold()
            value = c.command({'t': now, 'wheels': [0.0] * 4, 'duration_s': [0.0] * 4, 'pwm': dict(self.hold_pwm)})
            done, source = False, 'release_hold'
        else:
            value, done = self.executor.step(obs, jpegs)
            source = 'act'
        # kept also without release: hold() gives the posture that a following carry holds
        self.issued_hist.append({s: int(value['pwm'][s]) for s in ('1', '3', '4', '5', '6')})
        self.issued_hist = self.issued_hist[-45:]
        self.history.issue(value)
        self.previous = value
        if self.rule_state['wanted'] and seq.rule is None and approach.arrived:
            d_drive = approach.trace[-1]['d_est_m'] if approach.trace else None
            near_stop = d_drive is not None and abs(d_drive - self.D_STOP_M) <= 0.10
            if approach.reason in ('arrived', 'settled') or (approach.reason == 'handover_near_no_blob' and near_stop):
                seq.rule = self.GraspTransitionRule()
                self.rule_state.update(armed_at_handover=True, note='armed: approach %s' % approach.reason)
            else:
                self.rule_state['note'] = 'off: approach %s' % approach.reason
            self.rule_state['wanted'] = False
        if done and seq.skill == 'grasp' and seq.rule is not None:
            self.ignored_done += 1
            done = False
        if self.log is not None:
            self.log({'t': now, 'stage': self.stage, 'source': source, 'command': value, 'done_requested': done})
        if seq.update(now, done, issued=value):
            self.finished = True
        return value, source

    def hold(self):
        """The grasp posture: per servo the median of the last 45 issued rows (as the runner's release_hold)."""
        out = {}
        for s in ('1', '3', '4', '5', '6'):
            vals = sorted(r[s] for r in self.issued_hist) or [self.previous['pwm'][s]]
            m = len(vals)
            out[s] = int(round(vals[m // 2] if m % 2 else 0.5 * (vals[m // 2 - 1] + vals[m // 2])))
        return out

    def record(self):
        return {'approach': self.approach.record(), 'selected': self.selected, 'rule': self.rule_state,
                'learned_done_ignored_rows': self.ignored_done, 'skill': self.sequence.skill,
                'done_times': self.sequence.done_times, 'finished': self.finished,
                'release': self.release_code.record() if self.release_code is not None else None}
