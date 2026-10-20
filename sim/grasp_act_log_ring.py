"""Opt-in bounded teacher logs for the world-15 log blow-up (pairact P0).

Basis (README-r3 sec. 3.1/4): in world 15 the teacher re-computes and appends a
91-pose ``blocked_goal`` audit to ``goal_set_log`` and ``search22_log`` every
0.1 s tick. r2: 47 search22 rows = 281.5 MB, 46 goal_set rows = 274.9 MB;
r3: raw result 3.2 GB + snapshot 3.0 GB and a stalled batch.

``search26_log_ring_v1`` keeps only the newest ``LOG_RING_ROWS`` rows of those
two logs and counts what was dropped.  It is logging-only:

* no control path reads anything but the newest row (``goal_set_log[-1]`` in
  the r14 align-refresh hook and ``goal_set_log[-1:]`` in the beampair
  adapter); both stay identical because the newest rows are always retained;
* ``diagnostic()['candidate_angle_counts'/'candidate_rejection_counts']`` are
  computed from retained rows only when the mode is on; the ``log_ring``
  summary records the scope so analyses cannot mistake it for full totals.

It does NOT remove the per-tick 91-pose re-computation itself (the r2
``planning_wall_safety_cap`` cost); that remains a separate fix.
Default off; when off the logs are plain lists exactly as before.
"""
from collections import Counter

MODE_KEY = 'search26_log_ring'
MODE = 'search26_log_ring_v1'
# Logging-only bound (not a control, margin, time or cap constant).
LOG_RING_ROWS = 16
RING_LOGS = ('goal_set_log', 'search22_log')


class RingLog(list):
    """A list that keeps only the newest ``cap`` rows; indexing/slicing unchanged."""

    def __init__(self, name, cap=LOG_RING_ROWS, rows=()):
        super().__init__()
        if cap < 1:
            raise ValueError('ring cap must be positive')
        self.name = name
        self.cap = cap
        self.appended_N = 0
        self.dropped_N = 0
        self.dropped_events = Counter()
        for row in rows:
            self.append(row)

    def append(self, row):
        super().append(row)
        self.appended_N += 1
        overflow = len(self) - self.cap
        if overflow > 0:
            for old in self[:overflow]:
                event = old.get('event', 'row') if isinstance(old, dict) else 'row'
                self.dropped_events[str(event)] += 1
            del self[:overflow]
            self.dropped_N += overflow

    def extend(self, rows):
        for row in rows:
            self.append(row)

    def __iadd__(self, rows):
        self.extend(rows)
        return self

    def summary(self):
        return {'name': self.name, 'cap': self.cap, 'appended_N': self.appended_N,
                'retained_N': len(self), 'dropped_N': self.dropped_N,
                'dropped_events': dict(sorted(self.dropped_events.items()))}


def enabled(teacher):
    return teacher.search15_modes.get(MODE_KEY, 'off') != 'off'


def install(teacher):
    """Replace the two heavy logs with ring buffers when the mode is on."""
    if not enabled(teacher):
        return False
    for name in RING_LOGS:
        current = getattr(teacher, name)
        if not isinstance(current, RingLog):
            setattr(teacher, name, RingLog(name, LOG_RING_ROWS, current))
    return True


def summary(teacher):
    if not enabled(teacher):
        return None
    return {'mode': MODE, 'logs': [getattr(teacher, n).summary() for n in RING_LOGS
                                   if isinstance(getattr(teacher, n), RingLog)],
            'counts_scope': 'candidate_*_counts use retained goal_set_log rows only',
            'control_reads': 'newest row only (goal_set_log[-1], adapter goal_set_log[-1:])'}
