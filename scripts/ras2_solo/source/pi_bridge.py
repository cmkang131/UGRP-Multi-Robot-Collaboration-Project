"""One SSH-owned Pi hardware session. Wheel timers run independently of camera reads."""
import argparse
import base64
import contextlib
import importlib.util
import json
import math
from pathlib import Path
import select
import signal
import socket
import sys
import threading
import time
import urllib.request

SERVOS = {'1', '3', '4', '5', '6'}


def validate(request):
    if set(request) != {'op', 'motors', 'duration_s', 'pwm'}:
        raise ValueError('Hardware command fields differ')
    motors, durations, pwm = request['motors'], request['duration_s'], request['pwm']
    if len(motors) != 4 or len(durations) != 4 or set(pwm) != SERVOS:
        raise ValueError('Expected four motors and five servo targets')
    for speed, duration in zip(motors, durations):
        if type(speed) is not int or not (speed == 0 or 35 <= abs(speed) <= 40):
            raise ValueError('Driver speed outside zero or 35..40')
        if type(duration) not in (int, float) or not math.isfinite(duration):
            raise ValueError('Invalid motor pulse')
        if not 0 <= duration <= .15 or (speed == 0) != (duration == 0):
            raise ValueError('Inconsistent motor pulse')
    if any(type(value) is not int or not 500 <= value <= 2500 for value in pwm.values()):
        raise ValueError('Servo PWM outside driver bounds')
    return motors, durations, pwm


class Hardware:
    def __init__(self, control):
        self.control = control
        self.motors = control.MotorTransport()
        self.servos = control.ServoTransport()
        self.pose = {str(k): v for k, v in control.load_pose_state().items()}
        self.lock = threading.Lock()
        self.finish = threading.Event()
        self.target = [0] * 4
        self.active = [0] * 4
        self.deadlines = [0.] * 4
        self.heartbeat = time.monotonic()
        self.error = None
        self.thread = threading.Thread(target=self._timers, daemon=True)

    def stop(self):
        with self.lock:
            self.target = [0] * 4
            self.control.stop_all(self.motors, context='')
            self.active = [0] * 4

    def _timers(self):
        try:
            while not self.finish.wait(.002):
                with self.lock:
                    now = time.monotonic()
                    if now - self.heartbeat > 2.5:
                        raise TimeoutError('Host command stream expired')
                    for index in range(4):
                        desired = self.target[index] if now < self.deadlines[index] else 0
                        if desired != self.active[index]:
                            self.motors.write_motor(index + 1, desired)
                            self.active[index] = desired
        except BaseException as exc:
            self.error = str(exc)
            self.finish.set()
            try:
                self.stop()
            except Exception as stop_error:
                self.error += f'; stop failed: {stop_error}'

    def apply(self, request):
        motors, durations, pwm = validate(request)
        self.heartbeat = time.monotonic()
        # Servo writes are individually bounded by the existing driver.
        for servo, target in pwm.items():
            if self.pose.get(servo) != target:
                duration = (1. if servo not in self.pose else
                            max(.1, min(1., abs(target - self.pose[servo]) / 2000.)))
                with self.lock:
                    self.servos.write_servo(int(servo), target, duration)
                self.pose[servo] = target
        with self.lock:
            now = time.monotonic()
            self.target = list(motors)
            self.deadlines = [now + duration for duration in durations]
        return {'accepted_at': now, 'motors': motors, 'duration_s': durations, 'pwm': dict(self.pose)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--control', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--seconds', type=float, default=300)
    args = parser.parse_args()
    if socket.gethostname().split('.')[0] != 'ras2':
        raise RuntimeError('Connected hardware is not ras2')
    spec = importlib.util.spec_from_file_location('masterpi_control', args.control)
    control = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(control)
    lease, hardware = None, None

    def emit(value):
        print(json.dumps(value, allow_nan=False), flush=True)

    def interrupt(signum, _frame):
        raise SystemExit(128 + signum)

    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, interrupt)
    begin = time.monotonic()
    try:
        with contextlib.redirect_stdout(sys.stderr):
            if args.execute:
                lease = control.acquire_actuator_lease(owner='ras2-solo-pipeline')
                hardware = Hardware(control)
                hardware.stop()
                hardware.thread.start()
            probe = control.probe_hardware()
        emit({'ready': True, 'host': socket.gethostname(), 'execute': args.execute, 'probe': probe,
              'pose': {str(k): v for k, v in control.load_pose_state().items()}})
        while time.monotonic() - begin < args.seconds:
            if hardware and hardware.error:
                raise RuntimeError(hardware.error)
            if not select.select([sys.stdin], [], [], .05)[0]:
                continue
            line = sys.stdin.readline()
            if not line:
                break
            request = json.loads(line)
            if hardware:
                hardware.heartbeat = time.monotonic()
            op = request.get('op')
            if op == 'observe':
                with urllib.request.urlopen('http://127.0.0.1:8080/snapshot', timeout=2.) as response:
                    jpeg = response.read(2_000_000)
                if not jpeg.startswith(b'\xff\xd8'):
                    raise ValueError('Camera did not return JPEG')
                emit({'t': time.monotonic(), 'jpeg': base64.b64encode(jpeg).decode('ascii')})
            elif op == 'command' and hardware:
                with contextlib.redirect_stdout(sys.stderr):
                    result = hardware.apply(request)
                emit(result)
            elif op == 'stop':
                if hardware:
                    with contextlib.redirect_stdout(sys.stderr):
                        hardware.stop()
                emit({'stopped': True})
                break
            else:
                raise ValueError('Unknown operation or execute mode is disabled')
    finally:
        with contextlib.redirect_stdout(sys.stderr):
            try:
                if hardware:
                    hardware.finish.set()
                    if hardware.thread.ident is not None:
                        hardware.thread.join(timeout=3.)
                    hardware.stop()
            finally:
                if lease:
                    lease.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'error': str(error)}), flush=True)
        raise SystemExit(1)
