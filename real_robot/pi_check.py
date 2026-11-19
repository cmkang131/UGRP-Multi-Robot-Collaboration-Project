#!/usr/bin/env python3
"""Read-only bring-up check, run ON a MasterPi. Prints one JSON object. Moves nothing.

Self-contained (stdlib only) so the laptop can pipe it over SSH without copying the repo:
    ssh <host> python3 - < real_robot/pi_check.py
The battery read uses the same two I2C transfers as scripts/masterpi_control.py `probe`.
"""
import glob
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time

I2C_TRANSFER = '/usr/sbin/i2ctransfer'
I2C_BUS, I2C_ADDRESS, BATTERY_REGISTER = 1, 0x7A, 0  # scripts/masterpi_control.py


def run(argv, timeout=3.0):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, '', str(exc)


def read_text(path):
    try:
        with open(path) as f:
            return f.read().strip('\x00\n ')
    except OSError:
        return None


def battery():
    if not os.path.exists(I2C_TRANSFER):
        return {'ok': False, 'error': 'i2ctransfer missing'}
    code, _, err = run([I2C_TRANSFER, '-y', '-a', str(I2C_BUS), f'w1@0x{I2C_ADDRESS:02x}', f'0x{BATTERY_REGISTER:02x}'])
    if code != 0:
        return {'ok': False, 'error': err or f'exit {code}'}
    code, out, err = run([I2C_TRANSFER, '-y', '-a', str(I2C_BUS), f'r2@0x{I2C_ADDRESS:02x}'])
    if code != 0:
        return {'ok': False, 'error': err or f'exit {code}'}
    try:
        b = [int(t, 16) for t in out.split()]
        return {'ok': len(b) == 2, 'mv': b[0] | (b[1] << 8) if len(b) == 2 else None, 'raw': out}
    except ValueError:
        return {'ok': False, 'error': f'unparsed {out!r}'}


def camera():
    devices = sorted(glob.glob('/dev/video*'))
    result = {'devices': devices, 'frame': None}
    try:
        import cv2  # optional on the Pi
    except ImportError:
        result['frame'] = {'ok': False, 'error': 'cv2 not installed'}
        return result
    cap = cv2.VideoCapture(0)
    try:
        t0 = time.monotonic()
        ok, frame = cap.read()
        result['frame'] = {'ok': bool(ok), 'shape': list(frame.shape) if ok else None,
                           'first_read_s': round(time.monotonic() - t0, 3)}
    finally:
        cap.release()
    return result


def holders(paths):
    """Processes holding the camera or I2C (a second program would conflict with ours)."""
    if not shutil.which('fuser'):
        return {'error': 'fuser missing'}
    found = {}
    for path in paths:
        code, out, err = run(['fuser', path])
        pids = (out + ' ' + err).split(':')[-1].split() if code == 0 else []
        procs = []
        for pid in pids:
            pid = pid.strip('cefFrm')
            if pid.isdigit():
                procs.append({'pid': int(pid), 'cmd': (read_text(f'/proc/{pid}/cmdline') or '').replace('\x00', ' ')[:200]})
        found[path] = procs
    return found


def services():
    code, out, _ = run(['systemctl', 'list-units', '--type=service', '--state=running', '--no-legend', '--plain'])
    if code != 0:
        return None
    names = [line.split()[0] for line in out.splitlines() if line.strip()]
    keys = ('hiwonder', 'masterpi', 'rpc', 'mjpg', 'camera', 'ugrp', 'ros')
    return [n for n in names if any(k in n.lower() for k in keys)]


def main():
    report = {
        'host': socket.gethostname(),
        'model': read_text('/proc/device-tree/model'),
        'os': read_text('/etc/os-release') and dict(
            line.split('=', 1) for line in read_text('/etc/os-release').splitlines() if '=' in line).get('PRETTY_NAME', '').strip('"'),
        'python': platform.python_version(),
        'smbus2': _has('smbus2'),
        'numpy': _has('numpy'),
        'i2c_device': os.path.exists(f'/dev/i2c-{I2C_BUS}'),
        'battery': battery(),
        'camera': camera(),
        'busy': holders([f'/dev/i2c-{I2C_BUS}'] + sorted(glob.glob('/dev/video*'))[:2]),
        'services': services(),
        'cpu_temp_c': (lambda v: round(int(v) / 1000, 1) if v and v.isdigit() else None)(read_text('/sys/class/thermal/thermal_zone0/temp')),
        'throttled': run(['vcgencmd', 'get_throttled'])[1] or None,
        'disk_free_gb': round(shutil.disk_usage('/').free / 1e9, 1),
        'clock_synced': (lambda r: r[1] if r[0] == 0 else None)(run(['timedatectl', 'show', '-p', 'NTPSynchronized', '--value'])),
        'repo_present': os.path.isdir(os.path.expanduser('~/UGRP-Multi-Robot-Collaboration-Project')),
    }
    json.dump(report, sys.stdout)
    sys.stdout.write('\n')


def _has(module):
    import importlib.util
    return importlib.util.find_spec(module) is not None


if __name__ == '__main__':
    main()
