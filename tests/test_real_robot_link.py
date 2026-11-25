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


def test_camera_stream_keeps_newest_frame_with_pi_capture_time():
    from real_robot import camera

    class Source:
        n = 0

        def grab(self):
            Source.n += 1
            return time.monotonic(), b'\xff\xd8' + bytes([Source.n % 256]) * 1000 + b'\xff\xd9', 640, 480

    stop, ready, address = threading.Event(), threading.Event(), []
    thread = threading.Thread(target=camera.serve, args=(Source(), '127.0.0.1', 0),
                              kwargs={'period_s': 0.02, 'stop': stop, 'ready': ready, 'address': address}, daemon=True)
    thread.start()
    ready.wait(1)
    link = camera.CameraLink(*address[0])
    time.sleep(0.3)
    header, jpeg = link.newest()
    assert link.received >= 5 and link.error is None
    assert header['bytes'] == len(jpeg) == 1004 and jpeg.startswith(b'\xff\xd8')
    assert header['t_capture'] <= header['t_send'] <= header['t_arrival_laptop']
    assert (header['width'], header['height']) == (640, 480)
    link.close()
    stop.set()
    thread.join(timeout=1)


def test_pi_check_runs_without_hardware():
    import json
    import subprocess
    import sys
    out = subprocess.run([sys.executable, 'real_robot/pi_check.py'], capture_output=True, text=True, timeout=60)
    report = json.loads(out.stdout)
    assert report['battery']['ok'] is False  # no board here; must report, not crash
    assert 'camera' in report and 'busy' in report


def test_fleet_check_table_rows():
    import importlib.util
    spec = importlib.util.spec_from_file_location('fleet', 'scripts/masterpi_fleet_check.py')
    fleet = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fleet)
    assert fleet.row({'host': 'ugrp2', 'reachable': False, 'error': 'timeout'})[:2] == ['ugrp2', 'NO']
    r = {'reachable': True, 'ssh_host': 'ugrp1', 'model': 'Raspberry Pi 4 Model B', 'smbus2': True,
         'battery': {'ok': True, 'mv': 7900}, 'camera': {'frame': {'ok': True, 'shape': [480, 640, 3]}},
         'services': ['masterpi.service'], 'busy': {'/dev/video0': [{'pid': 1, 'cmd': '/usr/bin/python3 rpc_server.py'}]}}
    cells = fleet.row(r)
    assert cells[3] == '7900 mV' and cells[4].startswith('ok 480x640') and 'rpc_server.py' in cells[7]


def test_wheel_map_from_drive_map_matches_config():
    import importlib.util
    import json
    from pathlib import Path
    from real_robot import wheel_map
    spec = importlib.util.spec_from_file_location('mc', 'scripts/masterpi_control.py')
    mc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mc)
    solved = wheel_map.solve({k: mc.DRIVE_MAP[k] for k in ('forward', 'left', 'rotate-left')})
    config = json.loads(Path('configs/real_robot/wheel_map_from_drive_map.json').read_text())['wheels']
    assert solved == config
    # every DRIVE_MAP direction (incl. backward/right/rotate-right) is reproduced by the map
    sim = {'forward': (1, 1, 1, 1), 'backward': (-1, -1, -1, -1), 'left': (-1, 1, 1, -1), 'right': (1, -1, -1, 1),
           'rotate-left': (-1, 1, -1, 1), 'rotate-right': (1, -1, 1, -1)}
    for direction, pattern in sim.items():
        real = [0] * 4
        for w, name in enumerate(wheel_map.WHEELS):
            real[solved[name]['motor'] - 1] = solved[name]['sign'] * pattern[w]
        assert tuple(real) == mc.DRIVE_MAP[direction], direction


def test_fitter_matches_sim_displacement_and_bench_fake_rows(tmp_path):
    import csv
    import importlib.util
    import json
    spec = importlib.util.spec_from_file_location('fitcal', 'scripts/fit_real_robot_calibration.py')
    fitcal = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fitcal)
    sim = [{'direction': 'forward', 'value': v, 'pulse_s': 0.1, 'forward_mm': mm}
           for v, mm in ((0.31, 0.0), (0.32, 0.0), (0.33, 10.0), (0.40, 16.0))]
    # Test-only "measurements": real moves 8 mm at 35, 20 mm at 55 per 0.1 s.
    bench = [{'mode': 'floor', 'direction': 'forward', 'split': 'fit', 'pulse_s': '0.1', 'board_speed': str(b),
              'dx_mm': str(mm), 'dy_mm': ''} for b, mm in ((35, 8.0), (35, 8.0), (55, 20.0))]
    points, skipped, _ = fitcal.fit(bench, sim)
    assert points == [[0.33, 38.3], [0.40, 48.3]]
    assert {s['sim_value'] for s in skipped} == {0.31, 0.32}
    rows = bench + [{'mode': 'lifted', 'check': 'pass', 'direction': n, 'split': 'check', 'pulse_s': '0.3',
                     'board_speed': '40', 'dx_mm': '', 'dy_mm': ''} for n in range(4)]
    path = tmp_path / 'bench.csv'
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, sorted({k for r in rows for k in r}))
        w.writeheader()
        w.writerows(rows)
    simf = tmp_path / 'sim.jsonl'
    simf.write_text('\n'.join(json.dumps(r) for r in sim))
    out = tmp_path / 'cal.json'
    fitcal.main(['--bench', str(path), '--sim-reference', str(simf), '--robot-id', 't',
                 '--wheel-map', 'configs/real_robot/wheel_map_from_drive_map.json',
                 '--servo-min-duration-s', '0.02', '--out', str(out)])
    cal = calibration.load(out)
    assert cal.measured is True and cal.sim_no_motion_max == 0.32
    assert cal.board_speed(0, 0.31) == 0                     # sim dead zone -> wheel off
    assert cal.board_speed(0, 0.33) == 38                     # front_left = motor 3, sign +1
    assert cal.board_speed(1, 0.40) == -48                    # front_right = motor 1, sign -1


def test_bench_fake_lifted_run(tmp_path, monkeypatch):
    import builtins
    import importlib.util
    spec = importlib.util.spec_from_file_location('bench', 'scripts/real_pulse_bench.py')
    bench = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bench)
    answers = iter(['', 'y'] * 4)
    monkeypatch.setattr(builtins, 'input', lambda *_: next(answers))
    out = tmp_path / 'b.csv'
    assert bench.main(['lifted', '--wheel-map', 'configs/real_robot/wheel_map_from_drive_map.json',
                       '--out', str(out), '--fake']) == 0
    text = out.read_text()
    assert text.count('pass') == 4 and 'front_left_forward' in text


def test_real_io_paces_commands_and_uses_newest_frame():
    """Laptop RealIO against the Pi server (fake board) and the camera stream (fake source)."""
    from real_robot import camera
    from real_robot.skill_io import RealIO

    class Source:
        n = 0

        def grab(self):
            Source.n += 1
            return time.monotonic(), b'jpeg%d' % Source.n, 640, 480

    board = FakeBoard()
    ex = Executor(board, calibration.parse(TEST_CAL), lambda e: None)
    server = Server(ex, '127.0.0.1', 0)
    st = threading.Thread(target=server.serve_forever, daemon=True); st.start()
    stop, ready, addr = threading.Event(), threading.Event(), []
    ct = threading.Thread(target=camera.serve, args=(Source(), '127.0.0.1', 0), kwargs=dict(period_s=0.05, stop=stop, ready=ready, address=addr), daemon=True)
    ct.start(); ready.wait(2)
    io = RealIO('127.0.0.1', cmd_port=server.address[1], cam_port=addr[0][1])
    io.start(INIT, settle_s=0.1)
    for k in range(4):
        jpeg = io.frame()
        assert jpeg.startswith(b'jpeg')
        if k == 1:
            time.sleep(0.25)          # a slow brain tick (ACT inference)
        io.send(row(io.now(), (0.31,) * 4, (0.1,) * 4))
    gaps = [b['t_wall'] - a['t_wall'] for a, b in zip(io.ticks, io.ticks[1:])]
    assert min(gaps) >= 0.099 and io.now() == pytest.approx(0.4)
    assert gaps[0] >= 0.25 and gaps[1] < 0.2     # the slow tick delays it; the next is not sent at once to catch up
    io.close()
    stop.set(); server.running = False
    st.join(timeout=1); ct.join(timeout=1)
    assert ex.speeds == [0, 0, 0, 0]


def test_pulse_scale_defaults_to_one_backward_compat():
    cal = calibration.parse(TEST_CAL)
    assert cal.pulse_scale == {'drive': 1.0, 'rotate': 1.0, 'strafe': 1.0}
    clock, board, ex, events = make()
    ev = ex.apply(1, row(0., (0.35,) * 4, (0.10,) * 4), clock())
    assert ev['status'] == 'applied'
    assert ev['pulse_motion'] == 'drive'
    assert ev['pulse_scale'] == pytest.approx(1.0)
    assert ev['effective_duration_s'] == pytest.approx([0.10] * 4)
    assert ex.deadlines == pytest.approx([clock() + 0.10] * 4)


def test_pulse_scale_classifies_motions_scales_deadlines_and_caps_at_contract_max():
    cal_data = dict(TEST_CAL, pulse_scale={'drive': 0.75, 'rotate': 0.45, 'strafe': 1.8})
    clock = Clock()
    board = FakeBoard(clock)
    events = []
    ex = Executor(board, calibration.parse(cal_data), events.append)
    ex.initialize_servos(INIT, 1.0, clock())

    # Drive forward: 0.10 s * 0.75 = 0.075 s
    ev_fwd = ex.apply(1, row(0.0, (0.35, 0.35, 0.35, 0.35), (0.10,) * 4), clock())
    assert ev_fwd['pulse_motion'] == 'drive'
    assert ev_fwd['pulse_scale'] == pytest.approx(0.75)
    assert ev_fwd['effective_duration_s'] == pytest.approx([0.075] * 4)
    assert ex.deadlines == pytest.approx([clock() + 0.075] * 4)

    # Rotate CCW (-, +, -, +): 0.10 s * 0.45 = 0.045 s
    clock.t += 0.1
    ev_rot = ex.apply(2, row(0.1, (-0.35, 0.35, -0.35, 0.35), (0.10,) * 4), clock())
    assert ev_rot['pulse_motion'] == 'rotate'
    assert ev_rot['pulse_scale'] == pytest.approx(0.45)
    assert ev_rot['effective_duration_s'] == pytest.approx([0.045] * 4)
    assert ex.deadlines == pytest.approx([clock() + 0.045] * 4)

    # Rotate CW (+, -, +, -) with slightly unequal ACT-like magnitudes
    clock.t += 0.1
    ev_rot_cw = ex.apply(3, row(0.2, (0.36, -0.35, 0.35, -0.34), (0.05,) * 4), clock())
    assert ev_rot_cw['pulse_motion'] == 'rotate'
    assert ev_rot_cw['effective_duration_s'] == pytest.approx([0.0225] * 4)

    # Strafe left (-, +, +, -): 0.10 s * 1.8 = 0.18 s -> capped at contract max 0.15 s
    clock.t += 0.1
    ev_str = ex.apply(4, row(0.3, (-0.35, 0.35, 0.35, -0.35), (0.10,) * 4), clock())
    assert ev_str['pulse_motion'] == 'strafe'
    assert ev_str['pulse_scale'] == pytest.approx(1.8)
    assert ev_str['effective_duration_s'] == pytest.approx([0.15] * 4)
    assert ex.deadlines == pytest.approx([clock() + 0.15] * 4)

    # Strafe right (+, -, -, +): 0.05 s * 1.8 = 0.09 s (below cap)
    clock.t += 0.1
    ev_str_r = ex.apply(5, row(0.4, (0.35, -0.35, -0.35, 0.35), (0.05,) * 4), clock())
    assert ev_str_r['pulse_motion'] == 'strafe'
    assert ev_str_r['effective_duration_s'] == pytest.approx([0.09] * 4)

    # Partial wheel command falls back to drive and leaves zero wheels with deadline None
    clock.t += 0.1
    ev_part = ex.apply(6, row(0.5, (0.35, 0.0, 0.35, 0.0), (0.10, 0.0, 0.08, 0.0)), clock())
    assert ev_part['pulse_motion'] == 'drive'
    assert ev_part['effective_duration_s'] == pytest.approx([0.075, 0.0, 0.06, 0.0])
    assert ex.deadlines[0] == pytest.approx(clock() + 0.075)
    assert ex.deadlines[1] is None and ex.deadlines[3] is None

    # Stop command
    clock.t += 0.1
    ev_stop = ex.apply(7, row(0.6), clock())
    assert ev_stop['pulse_motion'] == 'stop'
    assert ev_stop['effective_duration_s'] == [0.0, 0.0, 0.0, 0.0]
    assert ex.deadlines == [None, None, None, None]


@pytest.mark.parametrize('bad_scale', [
    'fast',
    [0.5, 0.5, 0.5],
    {'turn': 0.5},
    {'drive': 0.0},
    {'rotate': -0.4},
    {'strafe': float('nan')},
    {'drive': float('inf')},
    {'drive': True},
    {'drive': 3.5},
])
def test_pulse_scale_rejects_invalid_values(bad_scale):
    with pytest.raises(ValueError):
        calibration.parse(dict(TEST_CAL, pulse_scale=bad_scale))


def test_camera_pitch_offset_default_and_sign_matches_ugrp1_diag(monkeypatch):
    import importlib.util
    from pathlib import Path
    cv2 = pytest.importorskip('cv2')
    _ = cv2
    path = Path('solo_pipeline/harness/approach_survey_v1_parts/ground_projection.py')
    spec = importlib.util.spec_from_file_location('test_gp_pitch', path)
    gp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gp)

    far = {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}
    monkeypatch.delenv(gp.PITCH_OFFSET_ENV, raising=False)
    gp.set_camera_pitch_offset_deg(None)

    assert gp.camera_pitch_offset_deg() == 0.0
    hit0_mid = gp.project_pixels([[320.0, 240.0]], far)[0]
    hit0_bot = gp.project_pixels([[320.0, 440.0]], far)[0]
    assert hit0_mid[0] == pytest.approx(0.758, abs=0.002)
    assert hit0_bot[0] == pytest.approx(0.414, abs=0.002)

    # +8.0 deg means camera is pitched steeper downward -> shorter projected range
    monkeypatch.setenv(gp.PITCH_OFFSET_ENV, '8.0')
    assert gp.camera_pitch_offset_deg() == pytest.approx(8.0)
    hit8_mid = gp.project_pixels([[320.0, 240.0]], far)[0]
    hit8_bot = gp.project_pixels([[320.0, 440.0]], far)[0]
    assert hit8_mid[0] == pytest.approx(0.559, abs=0.002)
    assert hit8_bot[0] == pytest.approx(0.344, abs=0.002)
    assert hit8_mid[0] < hit0_mid[0] and hit8_bot[0] < hit0_bot[0]

    # Explicit setter overrides env and validates finite numeric values
    gp.set_camera_pitch_offset_deg(0.0)
    assert gp.project_pixels([[320.0, 240.0]], far)[0][0] == pytest.approx(hit0_mid[0])
    with pytest.raises(ValueError):
        gp.set_camera_pitch_offset_deg(float('nan'))
    with pytest.raises(ValueError):
        gp.set_camera_pitch_offset_deg(True)
    gp.set_camera_pitch_offset_deg(None)


def test_approach_area_scale_default_and_cli_flags(monkeypatch):
    import importlib.util
    from pathlib import Path
    from scripts import real_skill_test as rst

    path = Path('solo_pipeline/harness/approach_survey_v1_parts/approach_core.py')
    spec = importlib.util.spec_from_file_location('test_ac_area', path)
    ac = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ac)

    monkeypatch.delenv(ac.AREA_SCALE_ENV, raising=False)
    ac.set_area_scale(None)
    assert ac.area_scale() == 1.0

    # At scale=1.0, a 7877 px blob (30mm cube at 0.20 m) looks ~0.329 m away (dev ~0.129 m vs 0.20 m)
    blob = {'A': 7877, 'cx': ac.CX_REF_PX, 'cy': 327.0, 'w': 90,
            'x0': 240, 'x1': 330, 'y0': 280, 'y1': 370, 'clipped': False}
    dev_default = ac._identity_dev(blob, 0.20, 0.0)
    assert dev_default == pytest.approx(0.1288, abs=0.005)

    # With opt-in area_scale=0.37, 7877 px matches D_STOP_M=0.20 m closely
    monkeypatch.setenv(ac.AREA_SCALE_ENV, '0.37')
    assert ac.area_scale() == pytest.approx(0.37)
    assert ac._identity_dev(blob, 0.20, 0.0) < 0.002
    tracker = ac.BlobTracker({'bearing_rad': 0.0, 'distance_m': 0.20, 'facing_rad': 0.0})
    assert tracker.expected['A'] == pytest.approx(ac.A_REF_PX * 0.37)

    with pytest.raises(ValueError):
        ac.set_area_scale(0.0)
    with pytest.raises(ValueError):
        ac.set_area_scale(-0.5)
    ac.set_area_scale(None)

    # CLI flags default to 0.0 and 1.0, and accept opt-in values
    parser = rst.build_parser()
    args_def = parser.parse_args(['pick', '--side', 'real', '--host', 'ugrp1', '--out', '/tmp/x'])
    assert args_def.camera_pitch_offset_deg == 0.0
    assert args_def.area_scale == 1.0
    args_opt = parser.parse_args(['pick', '--side', 'real', '--host', 'ugrp1', '--out', '/tmp/x',
                                  '--camera-pitch-offset-deg', '8.0', '--area-scale', '0.37'])
    assert args_opt.camera_pitch_offset_deg == pytest.approx(8.0)
    assert args_opt.area_scale == pytest.approx(0.37)


def test_opencv_source_drains_buffer_and_returns_newest_frame():
    import numpy as np
    cv2 = pytest.importorskip('cv2')
    from real_robot import camera

    class FakeCapture:
        def __init__(self):
            self.n = 0
            self.released = False

        def read(self):
            self.n += 1
            time.sleep(0.005)
            frame = np.full((480, 640, 3), self.n % 256, dtype=np.uint8)
            return True, frame

        def release(self):
            self.released = True

    cap = FakeCapture()
    src = camera.OpenCVSource(capture=cap)
    try:
        assert src.quality == 70
        time.sleep(0.08)  # let background thread drain multiple frames
        t1, jpg1, w1, h1 = src.grab()
        assert (w1, h1) == (640, 480) and jpg1.startswith(b'\xff\xd8')
        img1 = cv2.imdecode(np.frombuffer(jpg1, np.uint8), cv2.IMREAD_COLOR)
        val1 = int(round(float(img1.mean())))
        assert val1 >= 5  # skipped earlier frames rather than popping frame #1 from a stale queue
        time.sleep(0.08)
        t2, jpg2, _, _ = src.grab()
        img2 = cv2.imdecode(np.frombuffer(jpg2, np.uint8), cv2.IMREAD_COLOR)
        val2 = int(round(float(img2.mean())))
        assert t2 > t1 and val2 > val1 + 2
    finally:
        src.close()
    assert cap.released is True


def test_camera_serve_clamps_next_t_after_slow_grab_no_burst():
    from real_robot import camera

    class SlowOnceSource:
        def __init__(self):
            self.calls = []

        def grab(self):
            idx = len(self.calls)
            if idx == 1:
                time.sleep(0.18)  # simulate a 180 ms stall (> 4 * period_s)
            t = time.monotonic()
            self.calls.append(t)
            return t, b'\xff\xd8' + b'x' * 64 + b'\xff\xd9', 640, 480

    src = SlowOnceSource()
    stop, ready, addr = threading.Event(), threading.Event(), []
    thread = threading.Thread(
        target=camera.serve,
        args=(src, '127.0.0.1', 0),
        kwargs={'period_s': 0.04, 'stop': stop, 'ready': ready, 'address': addr},
        daemon=True,
    )
    thread.start()
    ready.wait(1)
    link = camera.CameraLink(*addr[0])
    try:
        deadline = time.monotonic() + 2.0
        while len(src.calls) < 5 and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        link.close()
        stop.set()
        thread.join(timeout=1)

    assert len(src.calls) >= 5
    # After the slow frame (calls[1]), calls[2] runs immediately, then calls[3] and calls[4]
    # must resume normal ~period_s pacing instead of bursting back-to-back.
    post_stall_gap = src.calls[3] - src.calls[2]
    assert post_stall_gap >= 0.03


def test_calibration_continuous_032_to_033_mapping_from_fitter(tmp_path):
    import csv
    import importlib.util
    import json

    spec = importlib.util.spec_from_file_location('fitcal_cont', 'scripts/fit_real_robot_calibration.py')
    fitcal = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fitcal)

    sim = [{'direction': 'forward', 'value': v, 'pulse_s': 0.1, 'forward_mm': mm}
           for v, mm in ((0.31, 0.0), (0.32, 0.0), (0.33, 10.0), (0.40, 16.0))]
    bench = [{'mode': 'floor', 'direction': 'forward', 'split': 'fit', 'pulse_s': '0.1', 'board_speed': str(b),
              'dx_mm': str(mm), 'dy_mm': ''} for b, mm in ((35, 8.0), (55, 20.0))]
    rows = bench + [{'mode': 'lifted', 'check': 'pass', 'direction': n, 'split': 'check', 'pulse_s': '0.3',
                     'board_speed': '40', 'dx_mm': '', 'dy_mm': ''} for n in range(4)]
    bench_p = tmp_path / 'bench.csv'
    with bench_p.open('w', newline='') as f:
        w = csv.DictWriter(f, sorted({k for r in rows for k in r}))
        w.writeheader()
        w.writerows(rows)
    sim_p = tmp_path / 'sim.jsonl'
    sim_p.write_text('\n'.join(json.dumps(r) for r in sim))
    out_p = tmp_path / 'cal.json'
    fitcal.main(['--bench', str(bench_p), '--sim-reference', str(sim_p), '--robot-id', 't',
                 '--wheel-map', 'configs/real_robot/wheel_map_from_drive_map.json',
                 '--servo-min-duration-s', '0.02', '--out', str(out_p)])
    cal = calibration.load(out_p)
    assert cal.board_speed(0, 0.32) == 0
    assert cal.board_speed(0, 0.327287) == 37  # smoothly interpolated in (0.32, 0.33) instead of raising ValueError
    assert cal.board_speed(0, 0.33) == 38
    assert cal.board_speed(0, 0.40) == 48


def test_red_hue_max_rejects_orange_wheels_and_preserves_red_cube(monkeypatch):
    import importlib.util
    from pathlib import Path
    import numpy as np
    cv2 = pytest.importorskip('cv2')
    from scripts import real_skill_test as rst

    ac_spec = importlib.util.spec_from_file_location(
        'test_ac_red_hue', Path('solo_pipeline/harness/approach_survey_v1_parts/approach_core.py'))
    ac = importlib.util.module_from_spec(ac_spec)
    ac_spec.loader.exec_module(ac)

    seg_spec = importlib.util.spec_from_file_location(
        'test_seg_red_hue', Path('solo_pipeline/harness/seg_frontend_v1.py'))
    seg = importlib.util.module_from_spec(seg_spec)
    seg_spec.loader.exec_module(seg)

    # Synthetic 640x480 frame containing BOTH a real-red-cube patch (RGB=(181, 23, 34), H=178)
    # and a real-MasterPi orange-wheel patch (RGB=(191, 54, 40), H=3).
    img_bgr = np.full((480, 640, 3), 220, dtype=np.uint8)
    img_bgr[280:360, 400:480] = (34, 23, 181)  # BGR of real red cube (H=178)
    img_bgr[180:260, 40:120] = (40, 54, 191)   # BGR of real orange mecanum wheel (H=3)
    ok, enc = cv2.imencode('.jpg', img_bgr)
    assert ok
    jpeg = enc.tobytes()

    monkeypatch.delenv(ac.RED_HUE_MAX_ENV, raising=False)
    ac.set_red_hue_max(None)
    seg.set_red_hue_max(None)

    # Default (red_hue_max=8): both red cube and H=3 orange wheel match (100% backward compatible with sim)
    assert ac.red_hue_max() == 8 and seg.red_hue_max() == 8
    comps_def = ac.components(jpeg, 'red')
    assert len(comps_def) == 2

    # Opt-in red_hue_max=0: orange wheel is rejected by approach_core AND mapped to BODY by seg5_v1!
    monkeypatch.setenv(ac.RED_HUE_MAX_ENV, '0')
    assert ac.red_hue_max() == 0 and seg.red_hue_max() == 0
    comps_strict = ac.components(jpeg, 'red')
    assert len(comps_strict) == 1
    assert comps_strict[0]['cx'] == pytest.approx(440.0, abs=3.0)
    assert comps_strict[0]['A'] >= 6000

    rgb_small = cv2.cvtColor(cv2.resize(img_bgr, (320, 240), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
    seg_out = seg.segment(rgb_small.transpose(2, 0, 1), 'red').transpose(1, 2, 0)
    # Red cube patch -> TARGET (255, 0, 0); orange wheel patch -> BODY (255, 255, 255)
    assert tuple(seg_out[160, 220].tolist()) == seg.TARGET
    assert tuple(seg_out[110, 40].tolist()) == seg.BODY

    # Validation
    with pytest.raises(ValueError):
        ac.set_red_hue_max(-1)
    with pytest.raises(ValueError):
        ac.set_red_hue_max(9)
    with pytest.raises(ValueError):
        seg.set_red_hue_max(True)

    # CLI flag default 8, accepts 0
    parser = rst.build_parser()
    assert parser.parse_args(['pick', '--side', 'real', '--host', 'ras2', '--out', '/tmp/x']).red_hue_max == 8
    assert parser.parse_args(['pick', '--side', 'real', '--host', 'ras2', '--out', '/tmp/x',
                              '--red-hue-max', '0']).red_hue_max == 0


def test_sim_camera_warp_pitch_sign_zoom_validation_and_real_io():
    import numpy as np
    cv2 = pytest.importorskip('cv2')
    from real_robot import camera
    from real_robot.camera_warp import SimCameraWarp
    from real_robot.skill_io import RealIO
    from scripts import real_skill_test as rst

    # Create a 640x480 image with a bright red square centered at (320, 240)
    img = np.full((480, 640, 3), 200, dtype=np.uint8)
    img[220:260, 300:340] = (0, 0, 220)  # 40x40 = 1600 px red patch at real optical center
    ok, enc = cv2.imencode('.jpg', img)
    assert ok
    jpeg = enc.tobytes()

    # +14 deg steeper-downward real camera -> warped sim view moves center object DOWN (cy_out > 240)
    # and f_real=515.7 < f_sim~620.8 zooms the patch IN (area_out > 1600).
    warp = SimCameraWarp(f_real=515.7, pitch_offset_deg=14.0)
    out_jpeg = warp(jpeg)
    out_img = cv2.imdecode(np.frombuffer(out_jpeg, np.uint8), cv2.IMREAD_COLOR)
    assert out_img.shape == (480, 640, 3)
    red_mask = (out_img[:, :, 2] > 180) & (out_img[:, :, 0] < 60)
    ys, xs = np.nonzero(red_mask)
    assert len(ys) > 2000  # ~1.45x area boost from f_sim/f_real
    assert float(ys.mean()) > 340.0  # shifted significantly downward from y=240
    assert abs(float(xs.mean()) - 287.7) < 5.0  # real center (320) maps onto sim principal point cx_sim~287.7

    # Validation
    with pytest.raises(ValueError):
        SimCameraWarp(f_real=0.0, pitch_offset_deg=14.0)
    with pytest.raises(ValueError):
        SimCameraWarp(f_real=515.7, pitch_offset_deg=90.0)
    with pytest.raises(ValueError):
        SimCameraWarp(f_real=515.7, pitch_offset_deg=float('nan'))
    with pytest.raises(ValueError):
        warp.warp_image(np.zeros((240, 320, 3), dtype=np.uint8))

    # RealIO frame_transform hook
    class Source:
        def grab(self):
            return time.monotonic(), jpeg, 640, 480

    board = FakeBoard()
    ex = Executor(board, calibration.parse(TEST_CAL), lambda e: None)
    server = Server(ex, '127.0.0.1', 0)
    st = threading.Thread(target=server.serve_forever, daemon=True); st.start()
    stop, ready, addr = threading.Event(), threading.Event(), []
    ct = threading.Thread(target=camera.serve, args=(Source(), '127.0.0.1', 0),
                          kwargs=dict(period_s=0.05, stop=stop, ready=ready, address=addr), daemon=True)
    ct.start(); ready.wait(2)
    io = RealIO('127.0.0.1', cmd_port=server.address[1], cam_port=addr[0][1], frame_transform=warp)
    try:
        io.start(INIT, settle_s=0.05)
        got = io.frame()
        got_img = cv2.imdecode(np.frombuffer(got, np.uint8), cv2.IMREAD_COLOR)
        ys_io, _ = np.nonzero((got_img[:, :, 2] > 180) & (got_img[:, :, 0] < 60))
        assert float(ys_io.mean()) > 340.0
    finally:
        io.close()
        stop.set(); server.running = False
        st.join(timeout=1); ct.join(timeout=1)

    # CLI flags default off, accept warp parameters
    parser = rst.build_parser()
    a_def = parser.parse_args(['pick', '--side', 'real', '--host', 'ras2', '--out', '/tmp/x'])
    assert a_def.sim_camera_warp is False
    a_on = parser.parse_args(['pick', '--side', 'real', '--host', 'ras2', '--out', '/tmp/x',
                              '--sim-camera-warp', '--camera-f-real', '450.0', '--camera-warp-pitch-deg', '14.0'])
    assert a_on.sim_camera_warp is True
    assert a_on.camera_f_real == pytest.approx(450.0)
    assert a_on.camera_warp_pitch_deg == pytest.approx(14.0)


def test_unified_calibration_servos_camera_vision_and_adapter(tmp_path, monkeypatch):
    import json
    import numpy as np
    cv2 = pytest.importorskip('cv2')
    from real_robot.adapter import Sim2RealAdapter
    from real_robot.camera_warp import SimCameraWarp
    from scripts import real_skill_test as rst

    full_cal = dict(
        TEST_CAL,
        servos={
            '1': {'offset_pwm': -25, 'min_pwm': 600, 'max_pwm': 2400},
            '4': {'offset_pwm': 40, 'min_pwm': 500, 'max_pwm': 2500},
        },
        camera={
            'enabled': True,
            'f_real': 450.0,
            'pitch_offset_deg': 14.0,
            'yaw_offset_deg': 5.0,
            'roll_offset_deg': -3.0,
            'cx_real': 320.0,
            'cy_real': 240.0,
            'd_real': None,
            'jpeg_quality': 88,
        },
        vision={
            'red_hue_max': 0,
            'red_sat_min': 185,
            'area_scale': 1.0,
            'camera_pitch_offset_deg': 0.0,
        },
    )
    cal = calibration.parse(full_cal)

    # Servo offset & safe clamp (never crashes at boundary 2500 + 40 -> 2500 with clamped=True)
    assert cal.servo_pwm(1, 2000) == (1975, False)
    assert cal.servo_pwm(1, 610) == (600, True)
    assert cal.servo_pwm(4, 2500) == (2500, True)
    assert cal.servo_pwm(5, 1320) == (1320, False)

    # Executor writes physical PWM while tracking sim PWM for slew delta
    clock = Clock()
    board = FakeBoard(clock)
    events = []
    ex = Executor(board, cal, events.append)
    ex.initialize_servos(INIT, 1.0, clock())
    init_servos = {w[1]: w[2] for w in board.writes if w[0] == 'servo'}
    assert init_servos[1] == 1975 and init_servos[4] == 2360 and init_servos[5] == 1320
    assert ex.pwm[1] == 2000 and ex.pwm[4] == 2320
    board.writes.clear()
    ev = ex.apply(1, row(0.1, pwm=dict(INIT, **{'4': 2500})), clock())
    assert ev['status'] == 'applied'
    assert [w for w in board.writes if w[0] == 'servo'] == [('servo', 4, 2500, 90, clock())]
    assert ev['servos'][0]['sim_pwm'] == 2500 and ev['servos'][0]['pwm'] == 2500 and ev['servos'][0]['clamped'] is True

    # Camera yaw/roll sign: +yaw means real camera pointed right -> center object shifts right (+x) in warped sim view
    img = np.full((480, 640, 3), 200, dtype=np.uint8)
    img[220:260, 300:340] = (0, 0, 220)
    ok, enc = cv2.imencode('.jpg', img)
    assert ok
    w0 = SimCameraWarp(f_real=515.7, pitch_offset_deg=0.0, yaw_offset_deg=0.0)
    wy = SimCameraWarp(f_real=515.7, pitch_offset_deg=0.0, yaw_offset_deg=8.0)
    i0 = cv2.imdecode(np.frombuffer(w0(enc.tobytes()), np.uint8), cv2.IMREAD_COLOR)
    iy = cv2.imdecode(np.frombuffer(wy(enc.tobytes()), np.uint8), cv2.IMREAD_COLOR)
    x0 = float(np.nonzero((i0[:, :, 2] > 180) & (i0[:, :, 0] < 60))[1].mean())
    xy = float(np.nonzero((iy[:, :, 2] > 180) & (iy[:, :, 0] < 60))[1].mean())
    assert xy > x0 + 50.0

    # Sim2RealAdapter from file + CLI --calibration loading and overrides
    cal_file = tmp_path / 'ras2_test.json'
    cal_file.write_text(json.dumps(full_cal))
    adapter = Sim2RealAdapter.from_file(cal_file)
    assert adapter.frame_transform is not None
    assert adapter.vision_env() == {'UGRP_RED_HUE_MAX': '0', 'UGRP_RED_SAT_MIN': '185'}

    import os
    monkeypatch.delenv('UGRP_RED_HUE_MAX', raising=False)
    monkeypatch.delenv('UGRP_RED_SAT_MIN', raising=False)
    with adapter.vision_context():
        assert os.environ['UGRP_RED_HUE_MAX'] == '0'
        assert os.environ['UGRP_RED_SAT_MIN'] == '185'
    assert 'UGRP_RED_HUE_MAX' not in os.environ and 'UGRP_RED_SAT_MIN' not in os.environ

    parser = rst.build_parser()
    a_cal = parser.parse_args(['pick', '--side', 'real', '--host', 'ras2', '--calibration', str(cal_file), '--out', '/tmp/x'])
    ad_cal = rst._build_adapter(a_cal)
    assert ad_cal.frame_transform is not None and ad_cal.camera.f_real == pytest.approx(450.0)
    assert ad_cal.vision.red_hue_max == 0 and ad_cal.vision.red_sat_min == 185

    # Explicit CLI overrides win over --calibration
    a_ovr = parser.parse_args([
        'pick', '--side', 'real', '--host', 'ras2', '--calibration', str(cal_file),
        '--no-sim-camera-warp', '--red-sat-min', '200', '--out', '/tmp/x',
    ])
    ad_ovr = rst._build_adapter(a_ovr)
    assert ad_ovr.frame_transform is None and ad_ovr.vision.red_sat_min == 200 and ad_ovr.vision.red_hue_max == 0


def test_red_sat_min_rejects_skin_and_keeps_red_cube(monkeypatch):
    import importlib.util
    from pathlib import Path
    import numpy as np
    cv2 = pytest.importorskip('cv2')

    ac_spec = importlib.util.spec_from_file_location(
        'test_ac_red_sat', Path('solo_pipeline/harness/approach_survey_v1_parts/approach_core.py'))
    ac = importlib.util.module_from_spec(ac_spec)
    ac_spec.loader.exec_module(ac)

    seg_spec = importlib.util.spec_from_file_location(
        'test_seg_red_sat', Path('solo_pipeline/harness/seg_frontend_v1.py'))
    seg = importlib.util.module_from_spec(seg_spec)
    seg_spec.loader.exec_module(seg)

    # Synthetic 640x480 with a bright red cube (S~223) and a lower-saturation skin-like patch (S~165, H=178)
    img_bgr = np.full((480, 640, 3), 220, dtype=np.uint8)
    img_bgr[280:360, 400:480] = (34, 23, 181)  # cube: H=178, S~223, V=181
    img_bgr[180:260, 100:180] = (50, 46, 130)  # skin-like: H=178, S~165, V=130
    ok, enc = cv2.imencode('.jpg', img_bgr)
    assert ok
    jpeg = enc.tobytes()

    monkeypatch.delenv(ac.RED_SAT_MIN_ENV, raising=False)
    ac.set_red_sat_min(None)
    seg.set_red_sat_min(None)
    assert len(ac.components(jpeg, 'red')) == 2  # default S > 150 matches both

    monkeypatch.setenv(ac.RED_SAT_MIN_ENV, '185')
    comps = ac.components(jpeg, 'red')
    assert len(comps) == 1 and comps[0]['cx'] == pytest.approx(440.0, abs=3.0)

    rgb_small = cv2.cvtColor(cv2.resize(img_bgr, (320, 240), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
    seg_out = seg.segment(rgb_small.transpose(2, 0, 1), 'red').transpose(1, 2, 0)
    assert tuple(seg_out[160, 220].tolist()) == seg.TARGET
    assert tuple(seg_out[110, 70].tolist()) == seg.FLOOR


def test_calibrate_real_robot_diagonal_trim_and_root_solver():
    import importlib.util
    spec = importlib.util.spec_from_file_location('cal_helper', 'scripts/calibrate_real_robot.py')
    ch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ch)

    # Idempotent diagonal trim
    t1 = ch.apply_diagonal_trim(TEST_CAL, 6.0)
    assert t1['wheels']['front_left']['points'] == [[0.31, 40.0], [0.40, 60.0]]
    assert t1['wheels']['front_right']['points'] == [[0.31, 46.0], [0.40, 66.0]]
    assert t1['wheels']['rear_left']['points'] == [[0.31, 46.0], [0.40, 66.0]]
    assert t1['wheels']['rear_right']['points'] == [[0.31, 40.0], [0.40, 60.0]]
    # Applying again with 4.0 replaces (not adds to) previous 6.0
    t2 = ch.apply_diagonal_trim(t1, 4.0)
    assert t2['wheels']['front_right']['points'] == [[0.31, 44.0], [0.40, 64.0]]

    # Root solver interpolates zero-crossing cleanly
    root = ch.solve_zero_drift_delta([(0.0, -30.0), (4.0, -10.0), (8.0, 10.0)])
    assert root == pytest.approx(6.0)

    # Real robot configs ras2.json and ugrp1.json both parse cleanly with unified sections
    ras2 = calibration.load('configs/real_robot/ras2.json')
    ugrp1 = calibration.load('configs/real_robot/ugrp1.json')
    assert ras2.camera.enabled is True and ras2.camera.pitch_offset_deg == 14.0 and ras2.vision.red_sat_min == 185
    assert ugrp1.camera.enabled is True and ugrp1.camera.pitch_offset_deg == 8.0 and ugrp1.vision.red_hue_max == 0
