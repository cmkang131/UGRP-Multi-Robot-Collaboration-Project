"""Offline D1 reference: own wrist RGB + own issued command intervals only.

No controller integration, simulator, ground truth, file I/O or model client.
The exact draft protocol (including missing-data semantics) is PREREG_DRAFT.md.
Frames are 640x480 RGB in [0,255], or grayscale arrays for arithmetic replay.
Times are seconds in one monotonic clock; command intervals are half-open.
NO_STALL_SUSPECT means no alarm, not verified physical progress or safety.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

LAG_S = 1.0
SHORT_LAG_S = 0.1
CHECK_STRIDE_S = 0.2
FRAME_TOLERANCE_S = 0.11
MIN_COMMAND_S = 5.0
MIN_REFERENCE_CHECKS = 5
REFERENCE_END_S = 3.0
BLOCK_SIZE = 16
TIME_EPS = 1e-9
REFERENCE_EPS = 1e-12  # numerical zero guard; not a learned signal threshold


@dataclass(frozen=True)
class Parameters:
    ratio: float = 0.4
    consecutive: int = 2

    def __post_init__(self):
        if not np.isfinite(self.ratio) or not 0 < self.ratio < 1:
            raise ValueError("ratio must be finite and between 0 and 1")
        if type(self.consecutive) is not int or self.consecutive < 1:
            raise ValueError("consecutive must be a positive integer")


PRIMARY = Parameters(0.4, 2)
SECONDARY = Parameters(0.5, 3)


@dataclass(frozen=True)
class CommandInterval:
    """One own-issued, constant nonzero translation command run, not GT motion.

    Split on direction/speed change, stop or expiry. Slow commands are included.
    Arm/carry eligibility must come from issued commands, never measured joints.
    """
    start_s: float
    end_s: float
    command_id: str = ""

    def __post_init__(self):
        if not np.isfinite([self.start_s, self.end_s]).all() or self.end_s <= self.start_s:
            raise ValueError("command interval must have finite start < end")


@dataclass(frozen=True)
class Measurement:
    long_score: float
    short_score: float
    score: float
    roi_rows: tuple[int, int]


@dataclass(frozen=True)
class Check:
    scheduled_s: float
    frame_s: float | None
    measurement: Measurement | None
    state: str
    consecutive: int = 0


@dataclass(frozen=True)
class IntervalResult:
    command: CommandInterval
    parameters: Parameters
    reference: float | None
    status: str
    checks: tuple[Check, ...]

    @property
    def alarm_times_s(self) -> tuple[float, ...]:
        # Decision is available at scheduled_s (never before the selected frame).
        return tuple(c.scheduled_s for c in self.checks if c.state == "STALL_SUSPECT")


def _gray(frame: np.ndarray) -> np.ndarray:
    a = np.asarray(frame)
    if a.shape not in ((480, 640), (480, 640, 3)):
        raise ValueError("expected 480x640 grayscale or 480x640x3 RGB frame")
    if not np.issubdtype(a.dtype, np.number) or not np.isfinite(a).all():
        raise ValueError("frame values must be finite real numbers in [0,255]")
    if np.iscomplexobj(a) or a.min() < 0 or a.max() > 255:
        raise ValueError("frame values must be finite real numbers in [0,255]")
    if a.ndim == 3:
        # Explicit RGB order, rounded 8-bit luminance; never OpenCV's BGR order.
        a = np.rint(a.astype(np.float32) @ np.array([.299, .587, .114], dtype=np.float32))
    return a


def dark_central_roi(a: np.ndarray, b: np.ndarray) -> tuple[int, int] | None:
    """Research dark_roi rule, unchanged for 640x480 grayscale frames."""
    dark = (a > 3) & (a < 60) & (b > 3) & (b < 60)
    rows = np.flatnonzero(dark[:, 200:440].mean(axis=1) > .9)
    if len(rows) < 40:
        return None
    lo, hi = int(rows[0]) + 10, int(rows[-1]) - 10
    return (lo, hi) if hi - lo >= 32 else None


def block_mean_difference(a: np.ndarray, b: np.ndarray) -> float:
    """Mean absolute globally centered SIGNED block difference (16x16 pixels).

    Subtract before absolute value; otherwise uniform exposure offsets survive.
    Incomplete bottom/right blocks are discarded, matching the research code.
    """
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    if a.ndim != 2 or a.shape != b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("block inputs must be matching finite 2D arrays")
    h, w = (n // BLOCK_SIZE * BLOCK_SIZE for n in a.shape)
    if min(h, w) == 0:
        raise ValueError("block inputs must contain at least one 16x16 block")
    d = b[:h, :w] - a[:h, :w]
    means = d.reshape(h // BLOCK_SIZE, BLOCK_SIZE, w // BLOCK_SIZE, BLOCK_SIZE).mean(axis=(1, 3))
    return float(np.abs(means - means.mean()).mean())


def measure_frames(previous: np.ndarray, current: np.ndarray, short_previous: np.ndarray) -> Measurement | None:
    """f = sqrt(max(f_1s**2 - f_0.1s**2, 0)), same ROI for both pairs."""
    a, b, p = (_gray(f) for f in (previous, current, short_previous))
    roi = dark_central_roi(a, b)
    if roi is None:
        return None
    lo, hi = roi
    long = block_mean_difference(a[lo:hi, 100:540], b[lo:hi, 100:540])
    short = block_mean_difference(p[lo:hi, 100:540], b[lo:hi, 100:540])
    return Measurement(long, short, float(np.sqrt(max(long * long - short * short, 0.))), roi)


def detect(
    frames: Sequence[np.ndarray],
    timestamps_s: Sequence[float],
    commands: Sequence[CommandInterval],
    parameters: Parameters = PRIMARY,
) -> tuple[IntervalResult, ...]:
    """Replay command runs separately, causally, without interpolating frames.

    Select the latest frame at/before each target, within 0.11s. Missing checks
    reset the consecutive count; references never cross command boundaries.
    No command-magnitude cutoff: slow/creeping controls remain in the cohort.
    """
    ts = np.asarray(timestamps_s, dtype=float)
    if ts.ndim != 1 or len(ts) != len(frames) or not np.isfinite(ts).all() or np.any(np.diff(ts) <= 0):
        raise ValueError("timestamps must be finite, strictly increasing and match frames")
    commands = tuple(commands)
    if not isinstance(parameters, Parameters) or any(not isinstance(c, CommandInterval) for c in commands):
        raise ValueError("expected Parameters and CommandInterval objects")
    if any(b.start_s < a.end_s for a, b in zip(commands, commands[1:])):
        raise ValueError("command intervals must be ordered and non-overlapping")

    def index_at(target):
        i = int(np.searchsorted(ts, target + TIME_EPS, side="right")) - 1
        return i if i >= 0 and target - ts[i] <= FRAME_TOLERANCE_S + TIME_EPS else None

    results = []
    for command in commands:
        if command.end_s - command.start_s < MIN_COMMAND_S - TIME_EPS:
            results.append(IntervalResult(command, parameters, None, "UNSUPPORTED_SHORT_COMMAND", ()))
            continue
        samples = []
        # Integer check number avoids floating addition drifting across t_on+3.
        count = int(np.ceil((command.end_s - command.start_s - LAG_S) / CHECK_STRIDE_S))
        for n in range(count):
            t = command.start_s + LAG_S + n * CHECK_STRIDE_S
            if t >= command.end_s - TIME_EPS:
                break
            ia, ib = index_at(t - LAG_S), index_at(t)
            ip = index_at(ts[ib] - SHORT_LAG_S) if ib is not None else None
            if (ia is None or ib is None or ip is None or not ia < ip < ib
                    or ts[ia] < command.start_s - TIME_EPS
                    or abs(ts[ib] - ts[ia] - LAG_S) > FRAME_TOLERANCE_S + TIME_EPS):
                samples.append(Check(t, None, None, "MISSING_FRAME"))
                continue
            measurement = measure_frames(frames[ia], frames[ib], frames[ip])
            samples.append(Check(t, float(ts[ib]), measurement, "VALID" if measurement else "INVALID_ROI"))
        refs = [c.measurement.score for c in samples if c.measurement is not None
                and c.scheduled_s <= command.start_s + REFERENCE_END_S + TIME_EPS]
        reference = float(np.median(refs)) if len(refs) >= MIN_REFERENCE_CHECKS else None
        status = ("INSUFFICIENT_REFERENCE" if reference is None else
                  "INSUFFICIENT_SIGNAL" if reference <= REFERENCE_EPS else "EVALUATED")
        checks, streak = [], 0
        for c in samples:
            if c.measurement is None:
                state, streak = c.state, 0
            elif c.scheduled_s <= command.start_s + REFERENCE_END_S + TIME_EPS:
                state = "REFERENCE"
            elif status != "EVALUATED":
                state, streak = status, 0
            else:
                below = c.measurement.score < parameters.ratio * reference
                streak = streak + 1 if below else 0
                state = "STALL_SUSPECT" if streak >= parameters.consecutive else "NO_STALL_SUSPECT"
            checks.append(Check(c.scheduled_s, c.frame_s, c.measurement, state, streak))
        results.append(IntervalResult(command, parameters, reference, status, tuple(checks)))
    return tuple(results)
