"""Solve which board motor (and sign) drives each sim wheel from known drive patterns.

Real patterns: scripts/masterpi_control.py DRIVE_MAP (values at the MotorTransport API, i.e. before
the legacy motor 1/3 I2C flip, which real_robot.boards applies in the same place).
Sim patterns: sim/camera_robot_port.py (_FORWARD_PATTERN, _LEFT_PATTERN, _YAW_LEFT_PATTERN), wheel
order front-left, front-right, rear-left, rear-right.
"""
from __future__ import annotations

SIM = {'forward': (1, 1, 1, 1), 'left': (-1, 1, 1, -1), 'rotate-left': (-1, 1, -1, 1)}
WHEELS = ('front_left', 'front_right', 'rear_left', 'rear_right')


def solve(real: dict) -> dict:
    out = {}
    for w, name in enumerate(WHEELS):
        found = [(m + 1, s) for m in range(4) for s in (1, -1)
                 if all(real[k][m] == s * SIM[k][w] for k in SIM)]
        if len(found) != 1:
            raise ValueError(f'{name}: {len(found)} motor/sign solutions, need exactly one')
        out[name] = {'motor': found[0][0], 'sign': found[0][1]}
    if len({v['motor'] for v in out.values()}) != 4:
        raise ValueError('motors are not a permutation')
    return out
