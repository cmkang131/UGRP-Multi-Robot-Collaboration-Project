"""Pi-side executor and command server, with a fake board (no hardware)."""
import threading
import time

import pytest

from real_robot import calibration
from real_robot.boards import FakeBoard
from real_robot.executor import Executor
from real_robot.server import RobotLink, Server

# Test-only mapping. NOT measured: real files come from T03/T04 bench measurements.
TEST_CAL = {
    'robot_id': 'test', 'measured': False, 'source': 'unit test, not measured',
    'wheels': {
        'front_left': {'motor': 1, 'sign': 1, 'points': [[0.31, 40], [0.40, 60]]},
        'front_right': {'motor': 2, 'sign': 1, 'points': [[0.31, 40], [0.40, 60]]},
        'rear_left': {'motor': 3, 'sign': -1, 'points': [[0.31, 40], [0.40, 60]]},
        'rear_right': {'motor': 4, 'sign': 1, 'points': [[0.31, 40], [0.40, 60]]},
    },
    'servo_min_duration_s': 0.02,
}
INIT = {'1': 2000, '3': 740, '4': 2320, '5': 1320, '6': 1500}


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def row(t, wheels=(0., 0., 0., 0.), dur=(0., 0., 0., 0.), pwm=None):
    return {'t': t, 'wheels': list(wheels), 'duration_s': list(dur), 'pwm': dict(pwm or INIT)}


def make():
    clock = Clock()
    board = FakeBoard(clock)
    events = []
    ex = Executor(board, calibration.parse(TEST_CAL), events.append)
    ex.initialize_servos(INIT, 2.0, clock())
    board.writes.clear()
    return clock, board, ex, events


def motor_writes(board):
    return [w for w in board.writes if w[0] == 'motor']


def test_mapping_interpolates_and_applies_sign():
    cal = calibration.parse(TEST_CAL)
    assert cal.board_speed(0, 0.31) == 40
    assert cal.board_speed(0, -0.40) == -60
    assert cal.board_speed(0, 0.355) == 50
    assert cal.board_speed(2, 0.31) == -40
    with pytest.raises(ValueError):
        cal.board_speed(0, 0.45)


def test_template_is_not_usable_until_filled():
    import json
    from pathlib import Path
    data = json.loads(Path('configs/real_robot/calibration_template.json').read_text())
    with pytest.raises(ValueError):
        calibration.parse(data)


def test_pulse_stops_by_itself_at_deadline():
    clock, board, ex, _ = make()
    ex.apply(1, row(0., (0.31,) * 4, (0.1, 0.1, 0.05, 0.)[:3] + (0.1,)), clock())
    assert [w[2] for w in motor_writes(board)] == [40, 40, -40, 40]
    clock.t += 0.06
    stops = ex.poll(clock())
    assert [s['motor'] for s in stops] == [3]
    clock.t += 0.05
    stops = ex.poll(clock())
    assert sorted(s['motor'] for s in stops) == [1, 2, 4]
    assert ex.next_deadline() is None


def test_new_command_overwrites_running_pulse_like_sim():
    clock, board, ex, _ = make()
    ex.apply(1, row(0., (0.31,) * 4, (0.15,) * 4), clock())
    clock.t += 0.1
    ex.apply(2, row(0.1, (0.40, 0., 0., 0.), (0.05, 0., 0., 0.)), clock())
    # wheels 2-4 stopped immediately by the new command (sim writes all four at once)
    assert [w[2] for w in motor_writes(board)[-4:]] == [60, 0, 0, 0]
    assert ex.deadlines[0] == pytest.approx(clock() + 0.05)


def test_matches_sim_wheel_timeline():
    """Wheel i is on at time t iff t < t_last + dur_i of the latest command (sim rule)."""
    clock, board, ex, _ = make()
    plan = [(0.31, 0.15), (0.31, 0.05), (0.0, 0.0), (0.40, 0.12), (0.35, 0.15)]
    cmds = [(i * 0.1, w, d) for i, (w, d) in enumerate(plan)]

    def sim_on(t):
        last = [c for c in cmds if c[0] <= t + 1e-12][-1]
        return last[1] != 0 and t < last[0] + last[2] - 1e-12

    timeline = []
    step = 0.001
    t = 0.0
    k = 0
    while t < 0.7:
        clock.t = 100.0 + t
        if k < len(cmds) and t >= cmds[k][0] - 1e-12:
            ex.apply(k + 1, row(cmds[k][0], (cmds[k][1],) * 4, (cmds[k][2],) * 4), clock())
            k += 1
        ex.poll(clock())
        timeline.append((t, ex.speeds[0] != 0, sim_on(t)))
        t = round(t + step, 6)
    # Exact boundary instants differ only by float rounding of the 100 s clock offset.
    edges = [c[0] + c[2] for c in cmds] + [c[0] for c in cmds]
    mismatches = [x for x in timeline if x[1] != x[2] and min(abs(x[0] - e) for e in edges) > 1e-6]
    assert not mismatches, mismatches[:5]


def test_servo_moves_only_on_change_at_sim_slew():
    clock, board, ex, events = make()
    pwm = dict(INIT, **{'1': 2400, '5': 1330})
    ex.apply(1, row(0., pwm=pwm), clock())
    servos = [w for w in board.writes if w[0] == 'servo']
    assert servos == [('servo', 1, 2400, 200, clock()), ('servo', 5, 1330, 20, clock())]
    moves = events[-1]['servos']
    assert moves[1]['sim_duration_s'] == pytest.approx(0.005)
    assert moves[1]['duration_raised'] is True
    board.writes.clear()
    ex.apply(2, row(0.1, pwm=pwm), clock())
    assert [w for w in board.writes if w[0] == 'servo'] == []


@pytest.mark.parametrize('bad', [
    row(0., (0.2, 0., 0., 0.), (0.1, 0., 0., 0.)),     # below contract range
    row(0., (0.31, 0., 0., 0.), (0.2, 0., 0., 0.)),    # pulse too long
    row(0., (0.31, 0., 0., 0.), (0.0, 0., 0., 0.)),    # moving wheel without pulse
    row(0., pwm=dict(INIT, **{'1': 2600})),            # PWM out of range
])
def test_invalid_command_rejected_whole_nothing_written(bad):
    clock, board, ex, events = make()
    event = ex.apply(1, bad, clock())
    assert event['status'] == 'rejected'
    assert board.writes == []


def test_stale_sequence_rejected():
    clock, board, ex, _ = make()
    assert ex.apply(5, row(0.), clock())['status'] == 'applied'
    assert ex.apply(5, row(0.1), clock())['status'] == 'rejected'
    assert ex.apply(4, row(0.2), clock())['status'] == 'rejected'


def test_server_loopback_and_stop_on_disconnect():
    board = FakeBoard()
    events = []
    ex = Executor(board, calibration.parse(TEST_CAL), events.append)
    server = Server(ex, '127.0.0.1', 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    link = RobotLink(*server.address)
    assert link.init_servos(INIT, 1.0)['status'] == 'initialized'
    reply = link.send(row(0., (0.31,) * 4, (0.1,) * 4))
    assert reply['status'] == 'applied'
    time.sleep(0.2)
    stops = [e for e in events if e['event'] == 'pulse_end']
    assert stops and max(s['late_s'] for e in stops for s in e['stops']) < 0.02
    assert link.send(row(0.1, (0.9,) * 4, (0.1,) * 4))['status'] == 'rejected'
    link.send(row(0.2, (0.31,) * 4, (0.15,) * 4))
    link.close()
    time.sleep(0.1)
    assert any(e['event'] == 'stop_all' and e['reason'] == 'client disconnected' for e in events)
    assert ex.speeds == [0, 0, 0, 0]
    server.running = False
    thread.join(timeout=1)


def test_i2c_frames_match_existing_cli(monkeypatch):
    """Persistent-bus writes carry the same bytes as scripts/masterpi_control.py's i2ctransfer frames."""
    import sys
    import types
    from real_robot import boards

    calls = []

    class Bus:
        def __init__(self, n):
            pass

        def write_byte_data(self, addr, reg, val):
            calls.append([addr, reg, val])

        def write_i2c_block_data(self, addr, reg, data):
            calls.append([addr, reg] + list(data))

        def close(self):
            pass

    monkeypatch.setitem(sys.modules, 'smbus2', types.SimpleNamespace(SMBus=Bus))
    board = boards.I2CBoard()
    mc = board.mc

    def frame(argv):
        addr = int(argv[4].split('@')[1], 16)
        return [addr] + [int(x, 16) for x in argv[5:]]

    for motor, speed in ((1, 40), (2, -60), (3, 0), (4, 100)):
        board.write_motor(motor, speed)
        assert calls[-1] == frame(mc.i2c_argv(motor, speed))
    board.write_servo(5, 1330, 0.2)
    assert calls[-1] == frame(mc.servo_i2c_argv(5, 1330, 0.2))
    with pytest.raises(ValueError):
        board.write_motor(1, 20)
