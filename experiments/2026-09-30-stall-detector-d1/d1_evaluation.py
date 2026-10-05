"""Evaluation-only D1 scoring. Never imported by detect() or a controller.

Labels cover every scheduled one-second GT window, including missing images.
This helper neither generates GT labels nor selects staging replacements.
"""
from dataclasses import dataclass
from typing import Sequence

import numpy as np

STALL_KINDS = ("divider_contact", "beam_end_contact", "one_robot_blocked",
               "lateral_friction", "blocked_at_start")
TIME_EPS = 1e-9


def stall_cohort_status(kinds: Sequence[str]) -> str:
    """Count gate only; independence and manipulation validity need a manifest."""
    if any(kind not in STALL_KINDS for kind in kinds):
        raise ValueError("unknown stall mechanism")
    return ("COMPLETE" if len(kinds) == 30 and all(kinds.count(k) == 6 for k in STALL_KINDS)
            else "INCOMPLETE")


@dataclass(frozen=True)
class EventScore:
    start_s: float
    end_s: float  # exclusive: first non-STALL check, or command end
    alarm_s: float | None
    latency_s: float | None


@dataclass(frozen=True)
class IntervalScore:
    events: tuple[EventScore, ...]
    false_alarm_times_s: tuple[float, ...]
    unmatched_alarm_times_s: tuple[float, ...]
    moving_checks: int
    other_checks: int
    observation_status: str
    all_moving: bool

    @property
    def moving_control_pass(self) -> bool:
        return self.observation_status == "EVALUATED" and self.all_moving \
            and self.moving_checks > 0 and not self.false_alarm_times_s


def score_interval(result, labels: Sequence[str]) -> IntervalScore:
    """Match an alarm only to its own STALL-labeled check in the same event.

    OTHER/MOVING close an event immediately; no joining across recovery or
    command boundaries. Earlier false alarms remain false alarms even if a
    later alarm detects an event. All repeated STALL ticks are retained by the
    detector; each event receives only its first matched tick and latency.
    """
    checks = result.checks
    if len(labels) != len(checks) or any(v not in ("STALL", "MOVING", "OTHER") for v in labels):
        raise ValueError("one STALL/MOVING/OTHER label required for every scheduled check")
    expected = np.arange(result.command.start_s + 1., result.command.end_s - TIME_EPS, .2)
    if len(checks) != len(expected) or any(abs(c.scheduled_s - t) > TIME_EPS
                                           for c, t in zip(checks, expected)):
        raise ValueError("scoring requires the complete scheduled check grid")
    alarms = set(result.alarm_times_s)
    status = result.status
    if status == "EVALUATED" and not result.sufficient_coverage:
        status = "INSUFFICIENT_COVERAGE"
    events, false_alarms, unmatched = [], [], []
    moving_checks = other_checks = 0
    start = alarm = None
    for check, label in zip(checks, labels):
        t = check.scheduled_s
        if label != "STALL" and start is not None:
            events.append(EventScore(start, t, alarm, None if alarm is None else alarm - start))
            start = alarm = None
        if label == "STALL":
            if start is None:
                start = t - 1.
            if t in alarms:
                if status == "EVALUATED" and alarm is None:
                    alarm = t
                elif status != "EVALUATED":
                    unmatched.append(t)
        elif t in alarms:
            unmatched.append(t)
            if label == "MOVING":
                false_alarms.append(t)
        if t > result.command.start_s + 3. + TIME_EPS:
            moving_checks += label == "MOVING"
            other_checks += label == "OTHER"
    if start is not None:
        events.append(EventScore(start, result.command.end_s, alarm, None if alarm is None else alarm - start))
    return IntervalScore(tuple(events), tuple(false_alarms), tuple(unmatched),
                         moving_checks, other_checks, status, all(v == "MOVING" for v in labels))
