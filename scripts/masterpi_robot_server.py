#!/usr/bin/env python3
"""Run the Pi-side command server for one MasterPi (see real_robot/README.md).

    python3 scripts/masterpi_robot_server.py --calibration configs/real_robot/ugrp1.json --board i2c
    python3 scripts/masterpi_robot_server.py --calibration <test file> --board fake   # no hardware
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from real_robot import calibration as cal_mod  # noqa: E402
from real_robot.boards import FakeBoard, I2CBoard  # noqa: E402
from real_robot.executor import Executor  # noqa: E402
from real_robot.server import Server  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--calibration', required=True)
    p.add_argument('--board', choices=('fake', 'i2c'), required=True)
    p.add_argument('--host', default='0.0.0.0')
    p.add_argument('--port', type=int, default=8765)
    p.add_argument('--log', default=None, help='JSONL event log (default: stdout)')
    args = p.parse_args(argv)

    cal = cal_mod.load(args.calibration)
    if args.board == 'i2c' and not cal.measured:
        p.error('calibration is not marked measured; the real board needs measured values (T03/T04)')
    board = I2CBoard() if args.board == 'i2c' else FakeBoard()
    out = open(args.log, 'a', buffering=1) if args.log else sys.stdout

    def log(event):
        event.setdefault('t_log', time.monotonic())
        out.write(json.dumps(event) + '\n')

    server = Server(Executor(board, cal, log), args.host, args.port)
    log({'event': 'start', 'robot_id': cal.robot_id, 'board': args.board,
         'calibration': args.calibration, 'measured': cal.measured, 'address': list(server.address)})
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if isinstance(board, I2CBoard):
            board.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
