#!/usr/bin/env python3
"""T03 bench on the Pi: single wheel pulses with the operator typing what they measured.

    # 1) wheels lifted: each sim wheel alone, check it is the expected wheel and turns 'forward'
    python3 scripts/real_pulse_bench.py lifted --wheel-map configs/real_robot/wheel_map_from_drive_map.json --out bench.csv
    # 2) on the floor: one pulse per row, measure dx/dy (mm, robot frame) and dyaw (deg, + = left), return to start
    python3 scripts/real_pulse_bench.py floor --wheel-map ... --out bench.csv --direction forward --speeds 35 40 45 50 --pulse 0.10 --reps 5

Rows are appended to a CSV in the docs/sim2real/tasks/T03_wheel_pulses.md columns plus the measured
write times. Nothing is chained without the operator pressing Enter. Ctrl-C stops all motors.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from real_robot.wheel_map import WHEELS  # noqa: E402

SIM_PATTERNS = {'forward': (1, 1, 1, 1), 'backward': (-1, -1, -1, -1), 'left': (-1, 1, 1, -1), 'right': (1, -1, -1, 1),
                'rotate-left': (-1, 1, -1, 1), 'rotate-right': (1, -1, 1, -1)}
FIELDS = ['trial', 'split', 'direction', 'wheel_values', 'pulse_s', 'dx_mm', 'dy_mm', 'dyaw_rad', 'stop_mm',
          'voltage_v', 'floor', 'load_kg', 'reason', 'board_speed', 't_on', 't_off', 'measured_pulse_s', 'mode', 'check']


def pulse(board, motors_speeds, seconds):
    """Write all motors, busy-wait the pulse on the monotonic clock, write zeros. Returns write times."""
    t_on = time.monotonic()
    for motor, speed in motors_speeds:
        board.write_motor(motor, speed)
    end = t_on + seconds
    while time.monotonic() < end:
        pass
    t_off = time.monotonic()
    for motor, _ in motors_speeds:
        board.write_motor(motor, 0)
    return t_on, t_off


def ask(prompt, cast=float):
    while True:
        text = input(prompt).strip()
        if text == '':
            return None
        try:
            return cast(text)
        except ValueError:
            print('  number please (empty = not measured)')


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('lifted', 'floor'))
    p.add_argument('--wheel-map', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--direction', choices=sorted(SIM_PATTERNS), default='forward')
    p.add_argument('--speeds', type=int, nargs='+', default=[40])
    p.add_argument('--pulse', type=float, default=0.10)
    p.add_argument('--reps', type=int, default=5)
    p.add_argument('--holdout-every', type=int, default=3, help='every Nth rep is a hold-out row (T03: >=2 of 5)')
    p.add_argument('--floor', default='')
    p.add_argument('--load-kg', default='0')
    p.add_argument('--fake', action='store_true', help='fake board (dry run on any computer)')
    a = p.parse_args(argv)
    if not 0 < a.pulse <= 0.15:
        p.error('pulse must be in (0, 0.15] s (sim contract)')
    wmap = json.loads(Path(a.wheel_map).read_text())['wheels']
    if a.fake:
        from real_robot.boards import FakeBoard
        board = FakeBoard()
        voltage = lambda: None  # noqa: E731
    else:
        from real_robot.boards import I2CBoard
        board = I2CBoard()
        mc = board.mc
        def voltage():
            try:
                return mc.probe_hardware()['battery_mv'] / 1000
            except Exception:
                return None
    out = Path(a.out)
    new = not out.exists()
    trial = sum(1 for _ in out.open()) - 1 if out.exists() else 0
    try:
        with out.open('a', newline='') as f:
            w = csv.DictWriter(f, FIELDS)
            if new:
                w.writeheader()
            if a.mode == 'lifted':
                print('Wheels must be OFF the ground. Each step spins ONE wheel forward for 0.3 s at speed 40.')
                for name in WHEELS:
                    m = wmap[name]
                    input(f'[Enter] spin {name} (motor {m["motor"]}) ... ')
                    t_on, t_off = pulse(board, [(m['motor'], m['sign'] * 40)], 0.3)
                    ok = input(f'  did {name} turn, in the robot-forward direction? [y/n] ').strip().lower() == 'y'
                    trial += 1
                    w.writerow({'trial': trial, 'split': 'check', 'direction': f'{name}_forward', 'board_speed': 40,
                                'pulse_s': 0.3, 't_on': t_on, 't_off': t_off, 'measured_pulse_s': round(t_off - t_on, 4),
                                'voltage_v': voltage(), 'mode': 'lifted', 'check': 'pass' if ok else 'fail'})
                    f.flush()
                return 0
            pattern = SIM_PATTERNS[a.direction]
            print(f'FLOOR: {a.direction}, pulse {a.pulse} s. Mark the start pose; measure after the robot stops; return it.')
            for speed in a.speeds:
                if not 35 <= speed <= 100:
                    p.error('board speed must be 35..100 (chassis rule)')
                for rep in range(1, a.reps + 1):
                    input(f'[Enter] speed {speed} rep {rep}/{a.reps} ... ')
                    v = voltage()
                    ms = [(wmap[n]['motor'], wmap[n]['sign'] * pattern[i] * speed) for i, n in enumerate(WHEELS)]
                    t_on, t_off = pulse(board, ms, a.pulse)
                    time.sleep(0.8)
                    dx = ask('  dx forward mm: ')
                    dy = ask('  dy left mm: ')
                    dyaw = ask('  dyaw deg (+left): ')
                    stop = ask('  stop/coast mm after pulse (empty if unknown): ')
                    note = input('  note (empty ok): ').strip()
                    trial += 1
                    w.writerow({'trial': trial, 'split': 'holdout' if rep % a.holdout_every == 0 else 'fit',
                                'direction': a.direction, 'wheel_values': json.dumps([pattern[i] * speed for i in range(4)]),
                                'pulse_s': a.pulse, 'dx_mm': dx, 'dy_mm': dy,
                                'dyaw_rad': None if dyaw is None else round(dyaw * 3.141592653589793 / 180, 5),
                                'stop_mm': stop, 'voltage_v': v, 'floor': a.floor, 'load_kg': a.load_kg, 'reason': note,
                                'board_speed': speed, 't_on': t_on, 't_off': t_off,
                                'measured_pulse_s': round(t_off - t_on, 4), 'mode': 'floor'})
                    f.flush()
    except KeyboardInterrupt:
        print('\nstopped')
    finally:
        for motor in (1, 2, 3, 4):
            board.write_motor(motor, 0)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
