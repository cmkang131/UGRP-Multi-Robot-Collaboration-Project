"""Opt-in wall-time monitor for synchronous SIM runs (DEV diagnostic sidecar, default off).

What it records. Per SIM-time window (default 10 SIM s) one JSON line with the wall and CPU
seconds per SIM second of the host loop phases, the process CPU utilisation, load average,
swap, memory level, RSS and thread count:

    physics      backend.advance_to (port ticks + drive arithmetic + mj_step); mj_step separately
    render_gl    MuJoCo GL render on the render owner thread (update_scene + mjr_render + readback)
    render_wait  main-thread wait for that render (executor hop + locks + GL)
    capture      backend.capture total (render_wait + JPEG encode + base64/sha256 + decode + file/JSONL writes)
    controller   runtime.on_frames + step + arm_step + on_command (vision, PF, guards, status channel)
    eval_log     backend.eval_sample (eval-only contacts/trajectory JSONL)
    issue        backend.issue (command validation + command JSONL)
    progress     runner stage_progress (stage probes)
    jsonl        BaseBackend._append (all JSONL rows, nested inside the phases above)
    other        window wall minus the top-level phases (loop overhead, GC, unattributed)

Why it cannot change research output bytes. The wrappers only read ``time.perf_counter`` /
``time.thread_time`` around the original call: same arguments, same return value, same
exceptions, same call order. Nothing is written into the run's case directory; the sidecar
goes next to it (``<run root>/walltime_profile.jsonl``) and the case manifest
(``artifacts.sha256.json``) only hashes the case directory. Reentrant calls (a subclass method
calling ``super()``) are timed once at the outermost call. ``uninstall()`` restores every
patched attribute. Equivalence check: experiments/2026-10-05-sim-walltime-monitor/README.md.

Wall seconds are informational (AGENTS.md: wall comparisons need the agent lock). Use the
sidecar to see where a run's time goes and how host contention moves it, not as evidence.
"""
from __future__ import annotations

import ctypes
import json
import os
import resource
import subprocess
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path

SCHEMA = 'ugrp.sim_walltime_monitor.v1'
SIDECAR = 'walltime_profile.jsonl'
TOP_LEVEL = ('physics', 'capture', 'controller', 'eval_log', 'issue', 'progress')


class _TaskInfo(ctypes.Structure):
    _fields_ = [('virtual_size', ctypes.c_uint64), ('resident_size', ctypes.c_uint64),
                ('total_user', ctypes.c_uint64), ('total_system', ctypes.c_uint64),
                ('threads_user', ctypes.c_uint64), ('threads_system', ctypes.c_uint64),
                ('policy', ctypes.c_int32), ('faults', ctypes.c_int32), ('pageins', ctypes.c_int32),
                ('cow_faults', ctypes.c_int32), ('messages_sent', ctypes.c_int32),
                ('messages_received', ctypes.c_int32), ('syscalls_mach', ctypes.c_int32),
                ('syscalls_unix', ctypes.c_int32), ('csw', ctypes.c_int32), ('threadnum', ctypes.c_int32),
                ('numrunning', ctypes.c_int32), ('priority', ctypes.c_int32)]


def _task_info():
    """RSS / thread count of this process (macOS libproc PROC_PIDTASKINFO; None elsewhere)."""
    if sys.platform != 'darwin':
        return None
    try:
        lib = ctypes.CDLL('/usr/lib/libproc.dylib')
        ti = _TaskInfo()
        if lib.proc_pidinfo(os.getpid(), 4, ctypes.c_uint64(0), ctypes.byref(ti), ctypes.sizeof(ti)) != ctypes.sizeof(ti):
            return None
        return {'rss_mib': round(ti.resident_size / 2**20, 1), 'threads': ti.threadnum,
                'context_switches': ti.csw, 'pageins': ti.pageins}
    except OSError:
        return None


def _host_memory():
    """Swap use and the kernel memory level (macOS sysctl; Linux /proc/meminfo)."""
    try:
        if sys.platform == 'darwin':
            out = subprocess.run(['sysctl', '-n', 'vm.swapusage', 'kern.memorystatus_level'], capture_output=True,
                                 text=True, timeout=5).stdout.split('\n')
            parts = out[0].split()
            return {'swap_used_mib': float(parts[5].rstrip('M')), 'swap_total_mib': float(parts[2].rstrip('M')),
                    'memory_level_pct': int(out[1])}
        info = {}
        for line in Path('/proc/meminfo').read_text().splitlines():
            key, _, value = line.partition(':')
            info[key] = int(value.split()[0])
        return {'swap_used_mib': round((info['SwapTotal'] - info['SwapFree']) / 1024, 1),
                'swap_total_mib': round(info['SwapTotal'] / 1024, 1),
                'memory_level_pct': round(100 * info['MemAvailable'] / info['MemTotal'])}
    except Exception as exc:  # noqa: BLE001 - diagnostics only
        return {'error': f'{type(exc).__name__}: {exc}'[:120]}


def _process_cpu_s():
    r = resource.getrusage(resource.RUSAGE_SELF)
    return r.ru_utime + r.ru_stime


class WalltimeMonitor:
    def __init__(self, path, *, window_sim_s=10.):
        if not window_sim_s > 0:
            raise ValueError('window_sim_s must be positive')
        self.path, self.window = Path(path), float(window_sim_s)
        self.wall = defaultdict(float)
        self.cpu = defaultdict(float)
        self.calls = defaultdict(int)
        self._patched = []
        self._depth = threading.local()
        self._main = threading.get_ident()
        self._stream = None
        self._prev = None
        self._next = None
        self.rows = 0
        self._last_sim = None

    # ---------------------------------------------------------------- patching
    def wrap(self, owner, name, key, *, cpu=True):
        """Time ``owner.name`` under ``key`` (outermost call only). Only attributes defined on owner are patched."""
        if name not in vars(owner):
            return False
        orig = vars(owner)[name]
        if isinstance(orig, (staticmethod, classmethod)):
            raise TypeError(f'{owner!r}.{name}: static/class methods are not supported')
        wall, cpus, calls, depth, main = self.wall, self.cpu, self.calls, self._depth, self._main
        pc, tt = time.perf_counter, time.thread_time

        def timed(*args, **kwargs):
            k = key if threading.get_ident() == main else key + '@render_thread'
            active = getattr(depth, 'keys', None)
            if active is None:
                active = depth.keys = set()
            if k in active:
                return orig(*args, **kwargs)
            active.add(k)
            w0 = pc()
            c0 = tt() if cpu else 0.
            try:
                return orig(*args, **kwargs)
            finally:
                wall[k] += pc() - w0
                if cpu:
                    cpus[k] += tt() - c0
                calls[k] += 1
                active.discard(k)
        timed.__wrapped__ = orig
        for attr in ('__name__', '__qualname__', '__doc__'):
            try:
                setattr(timed, attr, getattr(orig, attr))
            except (AttributeError, TypeError):
                pass
        self._patched.append((owner, name, orig))
        setattr(owner, name, timed)
        return True

    def wrap_family(self, classes, name, key):
        """Patch ``name`` on every class (MRO included) that defines it; reentrancy keeps one timing per call."""
        seen = []
        for cls in classes:
            for base in getattr(cls, '__mro__', (cls,)):
                if base is object or base in seen:
                    continue
                seen.append(base)
                self.wrap(base, name, key)

    def install_v98(self, runner=None):
        """Hooks for the v98 pair HIGH-carry host (scripts/run_pair_highpose.py)."""
        import mujoco
        from sim import camera_robot_port, final_environment_checks, final_pair_v3
        from sim.multi_masterpi_production import MultiMasterPiProductionV2
        backends = [final_pair_v3.PhysicsBackend]
        runtimes = []
        for module, names in (('sim.final_pair_highpose_clock', ('PhysicsBackend',)),
                              ('sim.final_pair_highpose_staged', ('StagedBackend',))):
            try:
                mod = __import__(module, fromlist=list(names))
                backends += [getattr(mod, n) for n in names if hasattr(mod, n)]
            except ImportError:
                pass
        for module, name in (('harness.zone_pair_highpose_runtime', 'Runtime'),
                             ('harness.zone_pair_highpose_staging', 'StagedRuntime')):
            try:
                runtimes.append(getattr(__import__(module, fromlist=[name]), name))
            except (ImportError, AttributeError):
                pass
        self.wrap_family(backends, 'advance_to', 'physics')
        self.wrap(mujoco, 'mj_step', 'mj_step', cpu=False)
        self.wrap(MultiMasterPiProductionV2, '_render_rgb_for', 'render_wait')
        self.wrap(MultiMasterPiProductionV2, '_render_rgb_direct', 'render_gl')
        self.wrap(camera_robot_port.CameraRobotPort, 'capture', 'port_capture')
        self.wrap_family(backends, 'capture', 'capture')
        self.wrap_family(backends, 'eval_sample', 'eval_log')
        self.wrap_family(backends, 'issue', 'issue')
        self.wrap(final_environment_checks.PhysicsBackend, '_append', 'jsonl')
        for method in ('on_frames', 'step', 'arm_step', 'on_command'):
            self.wrap_family(runtimes, method, 'controller')
        if runner is not None:
            self.wrap(runner, 'stage_progress', 'progress')
        self.wrap_family(backends, 'reset', 'reset')
        mro = []
        for cls in backends:
            mro += [b for b in cls.__mro__ if b is not object and b not in mro]
        self.attach_marks(mro)
        return self

    def uninstall(self):
        for owner, name, orig in reversed(self._patched):
            setattr(owner, name, orig)
        self._patched.clear()

    # ---------------------------------------------------------------- windows
    def _snapshot(self):
        keys = set(self.wall) | set(self.calls)
        return {k: (self.wall[k], self.cpu[k], self.calls[k]) for k in keys}

    def mark(self, sim_t, *, force=False):
        """Call after each SIM advance; writes one row per completed window."""
        sim_t = float(sim_t)
        self._last_sim = sim_t
        now = (sim_t, time.perf_counter(), _process_cpu_s(), self._snapshot(), time.time())
        if self._prev is None:
            self._prev, self._next = now, sim_t + self.window
            return
        if sim_t + 1e-9 < self._next and not force:
            return
        t0, w0, c0, s0, u0 = self._prev
        _, w1, c1, s1, u1 = now
        dsim = sim_t - t0
        if dsim <= 0:
            return
        phases = {}
        for k, (w, c, n) in sorted(s1.items()):
            pw, pc_, pn = s0.get(k, (0., 0., 0))
            if n - pn:
                phases[k] = {'wall_per_sim_s': round((w - pw) / dsim, 4), 'cpu_per_sim_s': round((c - pc_) / dsim, 4),
                             'calls_per_sim_s': round((n - pn) / dsim, 2)}
        dwall = w1 - w0
        top = sum(phases.get(k, {}).get('wall_per_sim_s', 0.) for k in TOP_LEVEL)
        row = {'schema': SCHEMA, 'sim_t0': round(t0, 4), 'sim_t1': round(sim_t, 4), 'wall_s': round(dwall, 3),
               # perf_counter (mach_absolute_time) stops while macOS sleeps; the host clock does not
               'clock_wall_s': round(u1 - u0, 3),
               'wall_per_sim_s': round(dwall / dsim, 4), 'process_cpu_per_sim_s': round((c1 - c0) / dsim, 4),
               'cpu_util_pct': round(100 * (c1 - c0) / dwall, 1) if dwall > 0 else None,
               'other_wall_per_sim_s': round(dwall / dsim - top, 4), 'phases': phases,
               'loadavg': [round(x, 2) for x in os.getloadavg()], 'cpu_count': os.cpu_count(),
               'process': _task_info(), 'memory': _host_memory(), 'unix_time': round(time.time(), 3)}
        if self._stream is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._stream = self.path.open('a', buffering=1)
        self._stream.write(json.dumps(row) + '\n')
        self.rows += 1
        self._prev, self._next = now, sim_t + self.window

    def attach_marks(self, backends):
        """After every advance_to (outermost), mark the window at the backend's SIM clock."""
        monitor = self
        for cls in backends:
            if 'advance_to' not in vars(cls):
                continue
            orig = vars(cls)['advance_to']

            def advance_to(backend, t, _orig=orig):
                depth = monitor._depth
                level = getattr(depth, 'advance', 0)
                if level == 0 and monitor._prev is None:
                    monitor.mark(backend.now)
                depth.advance = level + 1
                try:
                    out = _orig(backend, t)
                finally:
                    depth.advance = level
                if level == 0:
                    monitor.mark(backend.now)
                return out
            advance_to.__wrapped__ = orig
            self._patched.append((cls, 'advance_to', orig))
            setattr(cls, 'advance_to', advance_to)

    def close(self, sim_t=None):
        """Flush the last (partial) window at sim_t or the last marked SIM time, close the sidecar, unpatch."""
        sim_t = self._last_sim if sim_t is None else sim_t
        if sim_t is not None and self._prev is not None:
            self.mark(sim_t, force=True)
        if self._stream is not None:
            self._stream.close()
            self._stream = None
        self.uninstall()


def summarize(path):
    """Whole-run totals from a sidecar: SIM-weighted phase wall per SIM s, plus load/swap ranges."""
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    sim = sum(r['sim_t1'] - r['sim_t0'] for r in rows)
    if not rows or sim <= 0:
        return {'rows': len(rows), 'sim_s': sim}
    phases = defaultdict(float)
    for r in rows:
        d = r['sim_t1'] - r['sim_t0']
        for k, v in r['phases'].items():
            phases[k] += v['wall_per_sim_s'] * d
    wall = sum(r['wall_s'] for r in rows)
    return {'rows': len(rows), 'sim_s': round(sim, 3), 'wall_s': round(wall, 1),
            'wall_per_sim_s': round(wall / sim, 3),
            'phase_wall_per_sim_s': {k: round(v / sim, 4) for k, v in sorted(phases.items())},
            'loadavg1_range': [min(r['loadavg'][0] for r in rows), max(r['loadavg'][0] for r in rows)],
            'cpu_util_pct_mean': round(sum(r['cpu_util_pct'] or 0 for r in rows) / len(rows), 1),
            'swap_used_mib_max': max((r['memory'] or {}).get('swap_used_mib', 0) for r in rows)}


if __name__ == '__main__':
    print(json.dumps(summarize(sys.argv[1]), indent=1))
