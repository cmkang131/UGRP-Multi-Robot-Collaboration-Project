"""drive_record_v1: the robot's own pose estimate from the wheel rows it issued. Nothing else is read.

The table gives the mean base motion of one 0.1 s control tick for an issued wheel row, keyed by that
row and the row before it (a pulse keeps rolling into the next tick). It is a frozen motion calibration
measured offline on 20 development scenes, the same kind of constant as the pulse lengths. The estimate
drifts when the robot touches something (wheels slip), which the record cannot see.

Frame: the robot's body frame at the first tick (+x forward, +y left), the frame of the look-around list.
"""
import json
import math
from pathlib import Path

TABLE = Path(__file__).resolve().parent / 'drive_table_v1.json'


def row_key(command):
    wheels, duration = command['wheels'], command['duration_s']
    pattern = ''.join('+' if w > .1 else '-' if w < -.1 else '0' for w in wheels)
    if pattern == '0000':
        return 'still'
    return pattern + '@%.3f' % (round(max(duration) / .025) * .025)


class DriveRecord:
    def __init__(self, table=None):
        self.table = table if table is not None else json.loads(TABLE.read_text())['table']
        self.x = self.y = self.yaw = 0.
        self.previous = 'still'
        self.rows = self.unknown_rows = 0

    def issue(self, command):
        key = row_key(command)
        delta = self.table.get(key + '|' + self.previous) or self.table.get(key + '|any')
        if delta is None:
            delta, self.unknown_rows = (0., 0., 0.), self.unknown_rows + 1
        c, s = math.cos(self.yaw), math.sin(self.yaw)
        self.x += delta[0] * c - delta[1] * s
        self.y += delta[0] * s + delta[1] * c
        self.yaw += delta[2]
        self.previous, self.rows = key, self.rows + 1

    def pose(self):
        return {'x': self.x, 'y': self.y, 'yaw': math.atan2(math.sin(self.yaw), math.cos(self.yaw)),
                'rows': self.rows, 'unknown_rows': self.unknown_rows}
