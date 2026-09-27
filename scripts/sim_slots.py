#!/usr/bin/env python3
"""Cooperative reservations for a conservative upper bound on loaded MuJoCo processes.

A mapping of libmujoco is NOT evidence of active stepping: idle imports, notebooks
and pytest count too. Each held slot covers at most one mapped process, matched
through a live owner/start identity, never merely an open slot FD. Extra children
count separately. Launchers MUST reserve their peak process count with --workers;
this is an admission queue, not a sandbox capable of preventing arbitrary forks.

Reservations are closed, never explicitly unlocked, so inherited descriptors keep
them alive. The CLI also waits for its entire work process group (including children
that close inherited FDs). Detached work must retain a reservation FD or acquire its
own slot. No unrelated process is signalled. All participants on a host must use the
same root and cap. --root is for isolated tests/admin configuration, not agent roots.

Census is fail-closed and bounded, not advertised as cheap. A monotonic --timeout
includes lock contention and census; timeout=0 still bounds each census attempt.
"""
from __future__ import annotations

import argparse
import contextlib
import ctypes
import errno
import signal
import fcntl
import functools
import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path

def default_root() -> Path:
    # Fixed per host, independent of cwd, worktree, HOME and agent environment.
    # Keep the established Mac root; Linux administrators provision this shared
    # directory for the participating users (e.g. a common group).
    return (Path('/Users/changmin/projects/ugrp/outputs/sim-slots') if sys.platform == 'darwin'
            else Path('/var/tmp/ugrp-sim-slots'))


DEFAULT_ROOT = default_root()
MACHINE_CAP = 6          # AGENTS/user rule: at most 6 sim processes machine-wide
POLL_S = 5.0
SIM_LIBRARY = 'libmujoco'
ADMISSION = 'admission.lock'
QUEUE = 'queue.lock'
CENSUS_TIMEOUT_S = 5.0
COUNTING_CONTRACT = 'loaded_mujoco_process_upper_bound'
LINUX_HOST_VISIBILITY = Path('/etc/ugrp/sim-slots-host.json')


def positive_int(value, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f'{name} must be a positive integer, got {value!r}')
    try:
        number = int(str(value).strip())
    except ValueError:
        raise ValueError(f'{name} must be a positive integer, got {value!r}') from None
    if number < 1:
        raise ValueError(f'{name} must be a positive integer, got {value!r}')
    return number


def default_slots() -> int:
    env = os.environ.get('UGRP_SIM_SLOTS')
    return MACHINE_CAP if env is None or not env.strip() else positive_int(env, 'UGRP_SIM_SLOTS')


# ------------------------------------------------------------------ census
def _queue_role(path: str, prefix: str) -> str | None:
    """'holder' for a slot file, 'waiter' for the queue/admission files, None outside the slot directory."""
    if not path.startswith(prefix):
        return None
    name = path[len(prefix):]
    return ('holder' if name.startswith('slot-') and name.endswith('.lock') else
            'waiter' if name in (QUEUE, ADMISSION) else None)


def parse_lsof(text: str, root: Path) -> tuple[set[int], set[int], set[int]]:
    """(mapped-library PIDs, slot-file OPENERS, queue-file OPENERS) from ``lsof -F pfn`` (regular descriptors only)."""
    prefix = os.path.realpath(root) + os.sep
    sims, roles, pid, fd = set(), {'holder': set(), 'waiter': set()}, None, ''
    for line in text.splitlines():
        tag, value = line[:1], line[1:]
        if tag == 'p':
            pid, fd = (int(value) if value.isdigit() else None), ''
        elif tag == 'f':
            fd = value
        elif tag == 'n' and pid is not None:
            if fd in ('txt', 'mem') and SIM_LIBRARY in os.path.basename(value):
                sims.add(pid)
            elif fd.isdigit() and (role := _queue_role(value, prefix)):
                roles[role].add(pid)
    return sims, roles['holder'], roles['waiter']


class ProcessTable(dict):
    """Parent PIDs plus kernel start identities from the same census."""
    def __init__(self):
        super().__init__()
        self.starts = {}
        self.groups = {}
        self.states = {}


def _remaining(deadline: float | None) -> float:
    if deadline is None:
        return CENSUS_TIMEOUT_S
    left = deadline - time.monotonic()
    if left <= 0:
        raise TimeoutError('sim admission/census deadline expired')
    return left


def _proc_stat(path: Path):
    fields = path.read_text().rsplit(')', 1)[1].split()
    return int(fields[1]), fields[19], int(fields[2]), fields[0]


class _BSDInfo(ctypes.Structure):
    # sys/proc_info.h: PROC_PIDTBSDINFO, microsecond start identity.
    _fields_ = [(n, ctypes.c_uint32) for n in (
        'flags', 'status', 'xstatus', 'pid', 'ppid', 'uid', 'gid', 'ruid', 'rgid', 'svuid', 'svgid', 'reserved')]
    _fields_ += [('comm', ctypes.c_char * 16), ('name', ctypes.c_char * 32)]
    _fields_ += [(n, ctypes.c_uint32) for n in ('nfiles', 'pgid', 'jobc', 'tdev', 'tpgid', 'nice')]
    _fields_ += [('start_sec', ctypes.c_uint64), ('start_usec', ctypes.c_uint64)]


@functools.cache
def _libproc():
    lib = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
    lib.proc_pidinfo.argtypes = (ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int)
    lib.proc_pidinfo.restype = ctypes.c_int
    lib.proc_listallpids.argtypes = (ctypes.c_void_p, ctypes.c_int)
    lib.proc_listallpids.restype = ctypes.c_int
    lib.proc_listpgrppids.argtypes = (ctypes.c_int, ctypes.c_void_p, ctypes.c_int)
    lib.proc_listpgrppids.restype = ctypes.c_int
    return lib


def _mac_info(pid: int):
    lib = _libproc()
    info = _BSDInfo()
    n = lib.proc_pidinfo(pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info))
    if n != ctypes.sizeof(info):
        error = ctypes.get_errno()
        if error == errno.ESRCH:
            raise ProcessLookupError(pid)
        raise RuntimeError(f'incomplete process identity for PID {pid}: errno {error}')
    return info


def process_identity(pid: int) -> str:
    if sys.platform.startswith('linux'):
        return _proc_stat(Path('/proc')/str(pid)/'stat')[1]
    info = _mac_info(pid)
    return f'{info.start_sec}:{info.start_usec}'


def _mac_table(deadline=None, *, pgid=None) -> ProcessTable:
    _remaining(deadline)
    lib = _libproc()
    def listing(buffer, size):
        return (lib.proc_listallpids(buffer, size) if pgid is None
                else lib.proc_listpgrppids(pgid, buffer, size))

    count = listing(None, 0)
    if count < 0 or (count == 0 and pgid is None):
        raise RuntimeError('cannot enumerate process identities')
    buffer = (ctypes.c_int * (count * 2 + 64))()
    count = listing(buffer, ctypes.sizeof(buffer))
    if count < 0 or count >= len(buffer):
        raise RuntimeError('incomplete process identity listing')
    table = ProcessTable()
    for pid in buffer[:count]:
        _remaining(deadline)
        if pid == 0:
            continue
        try:
            info = _mac_info(pid)
        except ProcessLookupError:
            continue
        table[pid] = info.ppid
        table.starts[pid] = f'{info.start_sec}:{info.start_usec}'
        table.groups[pid] = info.pgid
        table.states[pid] = 'Z' if info.status == 5 else 'live'
    if not table and pgid is None:
        raise RuntimeError('empty process listing')
    return table


def _host_visibility_reference() -> dict:
    """Administrator pin recorded in the HOST PID namespace for this boot.

    A container's /proc/1 is not proof of host visibility. Never auto-enrol the
    namespace we happen to be in, or treat a missing pin as an empty host.
    """
    path = LINUX_HOST_VISIBILITY
    for parent in path.parents:
        st = parent.stat()
        if st.st_uid != 0 or st.st_mode & 0o022:
            raise RuntimeError('host visibility reference directory is not administrator-owned')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as fh:
        st = os.fstat(fh.fileno())
        if st.st_uid != 0 or st.st_mode & 0o022:
            raise RuntimeError('host visibility reference is not administrator-owned')
        return json.load(fh)


def verify_linux_visibility(proc: Path) -> None:
    """Refuse hidden PIDs, filtered proc mounts and unproven PID namespaces."""
    try:
        proc = proc.resolve()
        mounts = []
        for line in (proc/'self/mountinfo').read_text().splitlines():
            left, right = line.split(' - ', 1)
            fields, fs = left.split(), right.split()
            unescape = lambda value: re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), value)
            point = Path(unescape(fields[4]))
            mounts.append((point, unescape(fields[3]), fs[0], fields[5].split(',') + fs[2].split(',')))
        relevant = [m for m in mounts if proc == m[0] or m[0] in proc.parents]
        if not relevant:
            raise RuntimeError('cannot establish the proc mount visibility')
        point, mount_root, kind, options = max(relevant, key=lambda m: len(m[0].parts))
        if point != proc or mount_root != '/' or kind != 'proc':
            raise RuntimeError('filtered or non-root proc mount is not a host census')
        for option in options:
            if option.startswith('hidepid=') and option not in ('hidepid=0', 'hidepid=off'):
                raise RuntimeError(f'incomplete host census: {option}')
        for point, _, _, _ in mounts:
            if proc in point.parents:
                part = point.relative_to(proc).parts[0]
                if part.isdigit() or part in ('self', 'thread-self'):
                    raise RuntimeError('overlaid process directories prevent a complete host census')
        reference = _host_visibility_reference()
        if (reference.get('schema') != 'ugrp.host_proc_visibility.v1'
                or reference.get('boot_id') != (proc/'sys/kernel/random/boot_id').read_text().strip()):
            raise RuntimeError('missing/stale host visibility reference for this boot')
        expected = reference.get('pid_namespace')
        for name in ('self', '1'):
            st = (proc/name/'ns/pid').stat()
            if expected != {'device': st.st_dev, 'inode': st.st_ino}:
                raise RuntimeError('PID namespace is not the pinned host namespace')
    except (OSError, ValueError, IndexError, AttributeError) as exc:
        raise RuntimeError(f'cannot verify complete Linux host census: {exc}') from exc


def scan_proc(root: Path, proc: Path = Path('/proc'), *, deadline=None):
    """Linux mappings census. Only disappeared processes/FDs may be skipped."""
    verify_linux_visibility(proc)
    prefix = os.path.realpath(root) + os.sep
    sims, roles, parents = set(), {'holder': set(), 'waiter': set()}, ProcessTable()
    for entry in proc.iterdir():
        _remaining(deadline)
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        try:
            ppid, start, group, state = _proc_stat(entry/'stat')
            mapped = (entry/'maps').read_text()
            opened = set()
            for fd in (entry/'fd').iterdir():
                _remaining(deadline)
                try:
                    if role := _queue_role(os.readlink(fd), prefix):
                        opened.add(role)
                except FileNotFoundError:  # an FD closed during enumeration
                    continue
            after = _proc_stat(entry/'stat')
        except FileNotFoundError:
            if (entry/'stat').exists():
                raise RuntimeError(f'incomplete /proc census for live PID {pid}')
            continue
        except TimeoutError:
            raise
        except (OSError, IndexError, ValueError) as exc:
            raise RuntimeError(f'incomplete /proc census for PID {pid}: {exc}') from exc
        if after[:3] != (ppid, start, group):
            raise RuntimeError(f'process changed during census: {pid}')
        parents[pid], parents.starts[pid] = ppid, start
        parents.groups[pid], parents.states[pid] = group, state
        if SIM_LIBRARY in mapped:
            sims.add(pid)
        for role in opened:
            roles[role].add(pid)
    # Reject PID reuse between an early maps read and the end of the scan.
    for pid in parents:
        _remaining(deadline)
        try:
            after = _proc_stat(proc/str(pid)/'stat')
        except FileNotFoundError:
            continue  # counting a departed process is conservative
        if after[:2] != (parents[pid], parents.starts[pid]):
            raise RuntimeError(f'process identity changed during census: {pid}')
    verify_linux_visibility(proc)  # do not accept a visibility change during enumeration
    return sims, roles['holder'], roles['waiter'], parents


def _scan(root: Path, *, deadline=None):
    deadline = min(deadline or float('inf'), time.monotonic() + CENSUS_TIMEOUT_S)
    try:
        if sys.platform.startswith('linux'):
            return scan_proc(root, deadline=deadline)
        before = _mac_table(deadline)
        listing = subprocess.run(['lsof', '-n', '-P', '-w', '-F', 'pfn'], capture_output=True, text=True,
                                 timeout=_remaining(deadline))
        if listing.returncode != 0 or not listing.stdout.strip() or listing.stderr.strip():
            raise RuntimeError(f'incomplete lsof census (exit {listing.returncode}): {listing.stderr[:200]}')
        sims, openers, waiters = parse_lsof(listing.stdout, root)
        after = _mac_table(deadline)
        relevant = sims | openers | waiters
        for pid in list(relevant):
            seen = set()
            while pid > 1 and pid not in seen:
                seen.add(pid)
                relevant.add(pid)
                pid = after.get(pid, 0)
        for pid in relevant:
            if (pid not in before or pid not in after or before[pid] != after[pid]
                    or before.starts[pid] != after.starts[pid]):
                raise RuntimeError(f'process identity changed during census: {pid}')
        _remaining(deadline)
        return sims, openers, waiters, after
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError('sim census deadline expired') from exc
    except TimeoutError:
        raise
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f'cannot take complete sim census: {exc}') from exc


def _reservations(root: Path) -> dict:
    records = {}
    for path in sorted(root.glob('slot-*.lock')):
        held, text = _is_held(path)
        if held:
            try:
                record = json.loads(text)
            except ValueError:
                record = {}
            records[path.name] = record if isinstance(record, dict) else {}
    return records


def census(root: Path, *, deadline=None) -> dict:
    deadline = min(deadline or float('inf'), time.monotonic() + CENSUS_TIMEOUT_S)
    before = _reservations(root)
    sims, openers, waiters, parents = _scan(root, deadline=deadline)
    reservations = _reservations(root)
    starts = getattr(parents, 'starts', {})
    holders, covered = set(), set()
    for name, record in reservations.items():
        _remaining(deadline)
        if record != before.get(name):
            continue  # cannot use a reservation that changed across the snapshot
        children = record.get('children', [])
        owners = [record] + (children if isinstance(children, list) else [])
        valid = set()
        for owner in owners:
            if not isinstance(owner, dict):
                continue
            pid, start = owner.get('pid'), owner.get('start_id')
            if start is None or starts.get(pid) != start:
                continue
            try:
                if process_identity(pid) == start:
                    valid.add(pid)
            except (ProcessLookupError, FileNotFoundError):
                pass
        holders.update(valid)
        # A reservation covers ONE mapped process. Never exclude all descendants.
        for candidate in sorted(sims - covered):
            pid, visited = candidate, set()
            while pid > 1 and pid not in visited and pid not in valid:
                visited.add(pid)
                pid = parents.get(pid, 0)
            if pid in valid:
                covered.add(candidate)
                break
    return {'counting_contract': COUNTING_CONTRACT, 'active_sim_count': None,
            'sim_pids': sorted(sims), 'holder_pids': sorted(holders),
            'slot_file_open_pids': sorted(openers), 'waiter_pids': sorted(waiters),
            # An open queue FD is not proof that a process stopped doing work.
            'unslotted_sim_pids': sorted(sims - covered), 'held_slots': len(reservations)}


# ------------------------------------------------------------------ slots
class Slot:
    def __init__(self, path: Path, fd: int, index: int, record: dict):
        self.path, self.fd, self.index, self.record = path, fd, index, record
        self.additional: list[Slot] = []

    def release(self) -> None:
        if self.fd >= 0:
            # LOCK_UN affects inherited copies of this open-file description too.
            # Close only our copy; preserve metadata for any still-live child.
            os.close(self.fd)
            self.fd = -1
        for other in getattr(self, 'additional', []):
            other.release()

    @property
    def fds(self):
        return tuple(s.fd for s in [self, *getattr(self, 'additional', [])] if s.fd >= 0)


def _slot_paths(root: Path, slots: int) -> list[Path]:
    root.mkdir(parents=True, exist_ok=True)
    return [root / f'slot-{i:02d}.lock' for i in range(slots)]


def _is_held(path: Path) -> tuple[bool, str]:
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o664)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            held = False
            fcntl.flock(fd, fcntl.LOCK_UN)
        except BlockingIOError:
            held = True
        return held, os.pread(fd, 65536, 0).decode(errors='replace').strip()
    finally:
        os.close(fd)


def held_count(root: Path) -> int:
    """Held slots over every slot file present (a holder with another N is still counted)."""
    return sum(_is_held(p)[0] for p in sorted(root.glob('slot-*.lock')))


def _try_slot(root: Path, slots: int, record: dict) -> Slot | None:
    for index, path in enumerate(_slot_paths(root, slots)):
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o664)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            continue
        try:
            value = {**record, 'pid': os.getpid(), 'start_id': process_identity(os.getpid()),
                     'slot': index, 'slots': slots, 'acquired_unix': time.time(),
                     'reservation_id': f'{os.getpid()}-{time.time_ns()}',
                     'loadavg_at_acquire': [round(v, 2) for v in os.getloadavg()]}
            _write_record(fd, value)
        except BaseException:
            os.close(fd)
            raise
        return Slot(path, fd, index, value)
    return None


def _write_record(fd: int, record: dict) -> None:
    os.ftruncate(fd, 0)
    os.pwrite(fd, (json.dumps(record, ensure_ascii=False) + '\n').encode(), 0)


@contextlib.contextmanager
def _admission(root: Path, *, deadline=None):
    fd = os.open(root/ADMISSION, os.O_RDWR | os.O_CREAT, 0o664)
    locked = False
    try:
        while not locked:
            _remaining(deadline)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except BlockingIOError:
                time.sleep(min(.025, _remaining(deadline)))
        yield
    finally:
        os.close(fd)


def try_admit(root: Path, slots: int, record: dict, *, workers: int = 1, deadline=None,
              include_current: bool = False):
    """Atomically reserve the declared peak number of loaded work processes."""
    slots, workers = positive_int(slots, 'slots'), positive_int(workers, 'workers')
    if workers > slots:
        raise ValueError('workers must not exceed slots')
    _slot_paths(root, slots)
    with _admission(root, deadline=deadline):
        info = census(root, deadline=deadline)
        held = info['held_slots'] if 'held_slots' in info else held_count(root)
        seen = {'held_slots': held, 'unslotted_sims': len(info['unslotted_sim_pids']),
                'unslotted_sim_pids': info['unslotted_sim_pids'][:20]}
        seen['running'] = held + seen['unslotted_sims']
        # Python's context manager reserves its already-loaded caller. The CLI
        # reserves NEW children instead; it must never receive this credit.
        credit = int(include_current and os.getpid() in info['unslotted_sim_pids'])
        if include_current:
            seen['current_process_credit'] = credit
        _remaining(deadline)
        reserved = []
        try:
            if seen['running'] + workers - credit <= slots:
                for _ in range(workers):
                    slot = _try_slot(root, slots, record)
                    if slot is None:
                        return None, seen
                    reserved.append(slot)
                first = reserved[0]
                first.additional = reserved[1:]
                reserved = []  # transfer ownership
                return first, seen
            return None, seen
        finally:
            for slot in reserved:
                slot.release()


def acquire(root: Path, slots: int, record: dict, *, workers: int = 1, timeout_s: float = 0.,
            poll_s: float = POLL_S, log=None, include_current: bool = False) -> Slot:
    """Wait for reservations; monotonic timeout includes lock and census time."""
    if isinstance(timeout_s, bool) or not math.isfinite(timeout_s) or timeout_s < 0:
        raise ValueError(f'timeout_s must be a finite number >= 0, got {timeout_s!r}')
    if isinstance(poll_s, bool) or not math.isfinite(poll_s) or poll_s <= 0:
        raise ValueError('poll_s must be finite and positive')
    slots, workers = positive_int(slots, 'slots'), positive_int(workers, 'workers')
    if workers > slots:
        raise ValueError('workers must not exceed slots')
    _slot_paths(root, slots)
    started, last = time.monotonic(), float('-inf')
    deadline = started + timeout_s if timeout_s else None
    queue_fd = os.open(root/QUEUE, os.O_RDWR | os.O_CREAT, 0o664)
    try:
        while True:
            slot, seen = try_admit(root, slots, record, workers=workers, deadline=deadline,
                                   include_current=include_current)
            if slot is not None:
                try:
                    _remaining(deadline)
                    for member in [slot, *slot.additional]:
                        member.record.update(waited_s=round(time.monotonic() - started, 1), census_at_acquire=seen)
                        _write_record(member.fd, member.record)
                except BaseException:
                    slot.release()
                    raise
                return slot
            _remaining(deadline)
            if log and time.monotonic() - last >= 60:
                log(f'sim_slots: waiting ({seen["running"]} loaded-process/reservation upper bound, cap {slots})')
                last = time.monotonic()
            time.sleep(min(poll_s, _remaining(deadline)))
    finally:
        os.close(queue_fd)


def _group_alive(pgid: int) -> bool:
    if sys.platform.startswith('linux'):
        proc = Path('/proc')
        verify_linux_visibility(proc)
        for entry in proc.iterdir():
            if entry.name.isdigit():
                try:
                    _, _, group, state = _proc_stat(entry/'stat')
                except FileNotFoundError:
                    continue
                if group == pgid and state != 'Z':
                    return True
        verify_linux_visibility(proc)
        return False
    table = _mac_table(time.monotonic() + CENSUS_TIMEOUT_S, pgid=pgid)
    return any(table.groups[p] == pgid and table.states[p] != 'Z' for p in table)


def run_reserved(slot: Slot, cmd: list[str]) -> int:
    """Keep the reservation until all live members of OUR work group exit."""
    child = None
    interrupted = 0
    previous = {}
    leader_start = None
    can_signal = False
    pending_signal = 0

    def deliver_pending():
        nonlocal pending_signal
        # poll()/waitpid can reap the leader before returning to Python. Clear
        # can_signal BEFORE calling it, not after checking child.returncode.
        # No forwarding after reaping: a numeric PGID is no longer our handle.
        if pending_signal and child is not None and can_signal and child.returncode is None:
            signum, pending_signal = pending_signal, 0
            try:
                if process_identity(child.pid) == leader_start and os.getpgid(child.pid) == child.pid:
                    os.killpg(child.pid, signum)
            except (OSError, RuntimeError):
                pass  # ownership unavailable: do not signal a possibly unrelated group

    def forward(signum, _frame):
        nonlocal interrupted, pending_signal
        interrupted = pending_signal = signum
        deliver_pending()

    # KeyboardInterrupt/SIGTERM must not unwind past a live child and release.
    for sig in (signal.SIGINT, signal.SIGTERM):
        previous[sig] = signal.signal(sig, forward)
    try:
        if signal.getsignal(signal.SIGCHLD) != signal.SIG_DFL:
            raise RuntimeError('run_reserved requires default SIGCHLD ownership (no external reaper)')
        child = subprocess.Popen(cmd, pass_fds=slot.fds, start_new_session=True)
        setup_error = None
        try:
            identity = {'pid': child.pid, 'start_id': process_identity(child.pid)}
            leader_start = identity['start_id']
            can_signal = True  # our unreaped child pins this PID/PGID lifetime
            for member in [slot, *slot.additional]:
                member.record['children'] = [identity]
                _write_record(member.fd, member.record)
        except (FileNotFoundError, ProcessLookupError):
            pass  # short command; still wait for its work group below
        except Exception as exc:
            setup_error = exc  # even failed bookkeeping cannot release live work
        if interrupted:
            deliver_pending()
        while True:
            can_signal = False
            code = child.poll()
            if code is None:
                can_signal = leader_start is not None
                deliver_pending()
            if code is not None:
                try:
                    alive = _group_alive(child.pid)
                except (OSError, RuntimeError, subprocess.SubprocessError):
                    alive = True  # fail closed: keep reservation if liveness is unknown
                if not alive:
                    if setup_error is not None:
                        raise setup_error
                    return 128 + interrupted if interrupted else code
            time.sleep(.05)
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def status(root: Path, slots: int) -> list[dict]:
    rows = []
    for index, path in enumerate(_slot_paths(root, slots)):
        held, text = _is_held(path)
        row = {'slot': index, 'held': held}
        if held and text:
            try:
                row.update(json.loads(text))
            except ValueError:
                row['record'] = text[:200]
            row['slot'] = index
        rows.append(row)
    return rows


@contextlib.contextmanager
def sim_slot(*, owner: str, label: str = '', root: Path = DEFAULT_ROOT, slots: int | None = None,
             timeout_s: float = 0., workers: int = 1):
    slot = acquire(root, default_slots() if slots is None else slots,
                   {'owner': owner, 'label': label, 'pid': os.getpid(), 'command': ' '.join(sys.argv)[:500]},
                   workers=workers, timeout_s=timeout_s, include_current=True,
                   log=lambda m: print(m, file=sys.stderr, flush=True))
    try:
        yield slot
    finally:
        slot.release()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--slots', default=None,
                        help=f'machine-wide sim cap = slot count (default: UGRP_SIM_SLOTS or {MACHINE_CAP})')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('status')
    run = sub.add_parser('run', help='wait for a slot, run the command holding it, return its exit code')
    run.add_argument('--owner', required=True, help='claude, codex or kiro')
    run.add_argument('--label', default='')
    run.add_argument('--workers', default='1', help='peak loaded work processes, reserved atomically')
    run.add_argument('--timeout', type=float, default=0., help='give up after this many seconds (0 = wait forever)')
    run.add_argument('cmd', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        slots = default_slots() if args.slots is None else positive_int(args.slots, '--slots')
    except ValueError as exc:
        parser.error(str(exc))
    if args.command == 'status':
        rows = status(args.root, slots)
        try:
            seen = census(args.root)
        except (RuntimeError, TimeoutError) as exc:
            print(f'sim_slots: {exc}', file=sys.stderr)
            return 70
        mism = sorted({r['slots'] for r in rows if r.get('held') and r.get('slots') not in (None, slots)})
        print(json.dumps({'slots': slots, 'held': held_count(args.root), 'slot_count_mismatch': mism,
                          'counting_contract': COUNTING_CONTRACT, 'active_sim_count': None,
                          'loaded_mujoco_processes': len(seen['sim_pids']),
                          'unslotted_sim_pids': seen['unslotted_sim_pids'],
                          'loadavg': [round(v, 2) for v in os.getloadavg()], 'holders': [r for r in rows if r['held']]},
                         ensure_ascii=False, indent=2))
        return 0
    cmd = args.cmd[1:] if args.cmd[:1] == ['--'] else args.cmd
    if not cmd:
        parser.error('run needs a command after --')
    if not math.isfinite(args.timeout) or args.timeout < 0:
        parser.error(f'--timeout must be a finite number >= 0, got {args.timeout!r}')
    try:
        workers = positive_int(args.workers, '--workers')
        if workers > slots:
            raise ValueError('--workers must not exceed --slots')
    except ValueError as exc:
        parser.error(str(exc))
    record = {'owner': args.owner, 'label': args.label, 'pid': os.getpid(), 'command': ' '.join(cmd)[:500]}
    try:
        slot = acquire(args.root, slots, record, workers=workers, timeout_s=args.timeout,
                       log=lambda m: print(m, file=sys.stderr, flush=True))
    except TimeoutError as exc:
        print(f'sim_slots: {exc}', file=sys.stderr)
        return 75
    except RuntimeError as exc:           # census unavailable: never start unchecked
        print(f'sim_slots: {exc}', file=sys.stderr)
        return 70
    print(f'sim_slots: slot {slot.index}/{slots} after {slot.record["waited_s"]} s '
          f'({slot.record["census_at_acquire"]["running"]} running before)', file=sys.stderr, flush=True)
    try:
        # the child inherits the locked descriptor: the slot is held while either process lives
        return run_reserved(slot, cmd)
    except KeyboardInterrupt:
        return 130
    finally:
        slot.release()


if __name__ == '__main__':
    sys.exit(main())
