"""release_code_v1 (EXPERIMENTAL, default OFF): replay the teacher's median release table as the release skill's
commands, instead of letting ACT place the box.

Source: harness/release_table_v1.json, the per-row median of action[:, 0, :] over the 87 skill=='release' rows of the
140 demos in dataset-green2 (every demo has the same scripted release, so the median equals each demo).
Columns: wheels 0-3 (signed 0.35 or 0), pulses 4-7 (duration = pulse * 0.15 s, zero iff the wheel is zero), servos
8-12 for servos 1, 3, 4, 5, 6 (pwm = round(1500 + 1000 * value)), done flag 13 (row 86).

The arm blends from the pose at the handover to the table over the first ARM_BLEND_ROWS rows, so the arm does not
snap. After the table the robot holds (zero wheels, last pose) until the sequence's settle window ends.
Only the robot's own issued commands and the clock are used; no ground truth, no ACT input.
"""
import json
import math
from pathlib import Path

TABLE_PATH = Path(__file__).resolve().parent / 'release_table_v1.json'
SERVOS_ORDER = (1, 3, 4, 5, 6)
WHEEL_SPEED = 0.35
PULSE_UNIT_S = 0.15
ARM_BLEND_ROWS = 10
EXPECTED_ROWS = 87


class ReleaseCodeV1:
    def __init__(self, contract, start_pwm):
        table = json.loads(TABLE_PATH.read_text())
        self.rows = table['rows']
        if len(self.rows) != EXPECTED_ROWS or any(len(r) != 14 for r in self.rows):
            raise ValueError('release table must be 87 rows of 14 columns')
        self.c = contract
        self.start = {str(s): int(start_pwm[str(s)]) for s in SERVOS_ORDER}
        self.last_pwm = dict(self.start)
        self.i = 0
        self.started_t = None
        self.done_t = None
        self.table_done = False

    def step(self, now):
        """Return (validated command row, done) for this tick. done is True on the table's flagged last row."""
        if self.started_t is None:
            self.started_t = now
        done = False
        if self.i < len(self.rows):
            r = self.rows[self.i]
            wheels = [math.copysign(WHEEL_SPEED, w) if w != 0 else 0.0 for w in r[0:4]]
            durations = [p * PULSE_UNIT_S if w != 0 else 0.0 for w, p in zip(r[0:4], r[4:8])]
            pwm = {}
            for servo, value in zip(SERVOS_ORDER, r[8:13]):
                target = int(round(1500 + 1000 * value))
                if self.i < ARM_BLEND_ROWS:
                    alpha = (self.i + 1) / float(ARM_BLEND_ROWS)
                    pwm[str(servo)] = int(round(self.start[str(servo)] + alpha * (target - self.start[str(servo)])))
                else:
                    pwm[str(servo)] = target
            if r[13] >= 0.5:
                done = True
                self.table_done = True
                self.done_t = now
            self.i += 1
            row = {'t': now, 'wheels': wheels, 'duration_s': durations, 'pwm': pwm}
        else:
            row = {'t': now, 'wheels': [0.0] * 4, 'duration_s': [0.0] * 4, 'pwm': dict(self.last_pwm)}
        self.last_pwm = dict(row['pwm'])
        return self.c.command(row), done

    def record(self):
        return {'enabled': True, 'source': 'teacher median table, 140 demos', 'rows': len(self.rows),
                'rows_issued': min(self.i, len(self.rows)), 'table_done': self.table_done,
                'started_sim_s': self.started_t, 'done_sim_s': self.done_t,
                'start_pwm': dict(self.start), 'arm_blend_rows': ARM_BLEND_ROWS,
                'table_file': 'harness/release_table_v1.json'}
