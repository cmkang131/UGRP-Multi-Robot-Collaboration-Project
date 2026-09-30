"""P08 DRAFT: fake-check observation contract, NOT a D1 runtime binding.

No detector, controller, host, file reader, random generator or model client.
The upstream D1 interface is unapproved. Only tests construct this prototype.
RGB provenance is supplied by the own-camera producer; IDs cannot authenticate
pixels on their own. A future binding requires a separately reviewed producer.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import math

import numpy as np

SCHEMA = "p08.observation.draft.v1"
STATES = frozenset(("REFERENCE", "MISSING_FRAME", "INVALID_ROI",
                    "INSUFFICIENT_REFERENCE", "INSUFFICIENT_SIGNAL",
                    "INSUFFICIENT_COVERAGE", "UNSUPPORTED_SHORT_COMMAND",
                    "NO_STALL_SUSPECT", "STALL_SUSPECT"))


def packed(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def finite(value):
    return type(value) in (float, int) and math.isfinite(value)


@dataclass(frozen=True, slots=True)
class OwnCommand:
    robot_id: str
    command_id: str
    start_s: float
    end_s: float
    forward_mps: float
    left_mps: float

    def __post_init__(self):
        if (type(self.robot_id) is not str or not self.robot_id
                or type(self.command_id) is not str or not self.command_id
                or not all(finite(v) for v in (self.start_s, self.end_s, self.forward_mps, self.left_mps))
                or not 0 <= self.start_s < self.end_s
                or self.forward_mps == self.left_mps == 0):
            raise ValueError("finite own issued nonzero translation window required")


@dataclass(frozen=True, slots=True)
class OwnFrame:
    robot_id: str
    camera: str
    frame_id: str
    captured_s: float
    rgb: np.ndarray


@dataclass(frozen=True, slots=True)
class FakeCheck:
    """Explicitly synthetic output; no numerical detection rule lives here."""
    scheduled_s: float
    available_s: float
    state: str
    baseline_end_s: float | None = None
    baseline_value: float | None = None
    noise_floor: float | None = None
    # IDs of the long-previous, short-previous and current frame, respectively.
    selected_frame_ids: tuple[str, ...] = ()
    interval_status: str | None = None  # Retrospective qualification, never erase a causal alarm.


class ObservationAdapter:
    """Opt-in private log only. There is deliberately no stop/notify callback."""
    def __init__(self, robot_id: str, *, enabled=False):
        if type(enabled) is not bool:
            raise ValueError("enabled must be bool")
        self.robot_id, self.enabled = robot_id, enabled
        self._rows, self._commands, self._last_checks = [], {}, {}

    @property
    def rows(self):
        return tuple(json.loads(row) for row in self._rows)

    @property
    def command_denominator(self):
        return len(self._commands)

    def register_command(self, command: OwnCommand):
        """At own command issue, including windows that never yield a check."""
        if not self.enabled:
            return None
        if type(command) is not OwnCommand or command.robot_id != self.robot_id:
            raise ValueError("only own issued command accepted")
        encoded = packed(asdict(command))
        old = self._commands.get(command.command_id)
        if old is not None and old != encoded:
            raise ValueError("command ID reused with a different window")
        # Register BEFORE validating images/timestamps: unknowns stay in denominator.
        self._commands[command.command_id] = encoded
        return encoded

    @property
    def command_summary(self):
        result = []
        for key in self._commands:
            rows = [r for r in self.rows if r["command"]["command_id"] == key]
            armed = sum(r["armed"] for r in rows)
            result.append(dict(command_id=key, checks=len(rows), armed_checks=armed,
                               unknown_checks=sum(r["unknown"] for r in rows), unarmed=armed == 0,
                               status="NO_CHECKS" if not rows else "RECORDED"))
        return tuple(result)

    def record(self, command: OwnCommand, frames: tuple[OwnFrame, ...], check: FakeCheck):
        if not self.enabled:
            return None
        encoded = self.register_command(command)
        reason = None
        provenance = []
        try:
            if type(check) is not FakeCheck or type(check.state) is not str or check.state not in STATES:
                raise ValueError("INVALID_CHECK")
            if check.interval_status is not None and check.interval_status not in (
                    "EVALUATED", "INSUFFICIENT_REFERENCE", "INSUFFICIENT_SIGNAL",
                    "INSUFFICIENT_COVERAGE", "UNSUPPORTED_SHORT_COMMAND"):
                raise ValueError("INVALID_INTERVAL_STATUS")
            if (not finite(check.scheduled_s) or not finite(check.available_s)
                    or not command.start_s <= check.scheduled_s < command.end_s
                    or check.available_s < check.scheduled_s):
                raise ValueError("DISCONTINUOUS_TIME")
            if check.scheduled_s <= self._last_checks.get(command.command_id, -1):
                raise ValueError("DISCONTINUOUS_TIME")
            self._last_checks[command.command_id] = check.scheduled_s
            previous = -1.
            ids = set()
            for frame in frames:
                if (type(frame) is not OwnFrame or frame.robot_id != self.robot_id
                        or frame.camera != "wrist_rgb"):
                    raise ValueError("FOREIGN_INPUT")
                if (not finite(frame.captured_s) or not command.start_s <= frame.captured_s <= check.scheduled_s
                        or frame.captured_s <= previous or type(frame.frame_id) is not str
                        or not frame.frame_id or frame.frame_id in ids):
                    raise ValueError("DISCONTINUOUS_TIME")
                if type(frame.rgb) is not np.ndarray or frame.rgb.shape != (480, 640, 3) or frame.rgb.dtype != np.uint8:
                    raise ValueError("INVALID_RGB")
                # Hash a detached copy; do not change flags or bytes of caller's RGB.
                rgb = frame.rgb.copy()
                provenance.append(dict(frame_id=frame.frame_id, captured_s=frame.captured_s,
                                       rgb_sha256=hashlib.sha256(rgb.tobytes()).hexdigest()))
                ids.add(frame.frame_id)
                previous = frame.captured_s
            selected = check.selected_frame_ids
            if type(selected) is not tuple or any(type(fid) is not str for fid in selected):
                raise ValueError("INVALID_FRAME_LINK")
            if selected and (len(selected) != 3 or len(set(selected)) != 3 or not set(selected) <= ids):
                raise ValueError("INVALID_FRAME_LINK")
            if selected:
                times = {f.frame_id: f.captured_s for f in frames}
                if not times[selected[0]] < times[selected[1]] < times[selected[2]]:
                    raise ValueError("INVALID_FRAME_LINK")
            for value in (check.baseline_value, check.noise_floor):
                if value is not None and (not finite(value) or value < 0):
                    raise ValueError("INVALID_MEASUREMENT")
            if check.baseline_end_s is not None and (
                    not finite(check.baseline_end_s)
                    or not command.start_s <= check.baseline_end_s <= check.scheduled_s):
                raise ValueError("INVALID_BASELINE_TIME")
            if check.state in ("STALL_SUSPECT", "NO_STALL_SUSPECT") and (
                    not selected or check.baseline_end_s is None or check.baseline_value is None
                    or check.noise_floor is None):
                raise ValueError("MISSING_CHECK_PROVENANCE")
        except ValueError as error:
            reason = str(error)
        valid = reason is None
        state = check.state if valid else "UNKNOWN_INPUT"
        scheduled = check.scheduled_s if type(check) is FakeCheck and finite(check.scheduled_s) else None
        available = check.available_s if type(check) is FakeCheck and finite(check.available_s) else None
        row = dict(schema=SCHEMA, mode="observation_only_fake", robot_id=self.robot_id,
                   command=asdict(command), command_sha256=hashlib.sha256(encoded).hexdigest(),
                   scheduled_s=scheduled, available_s=available,
                   frames=provenance, frame_id=check.selected_frame_ids[-1] if valid and check.selected_frame_ids else None,
                   selected_frame_ids=list(check.selected_frame_ids) if valid else [],
                   baseline_age_s=scheduled - check.baseline_end_s if valid and check.baseline_end_s is not None else None,
                   baseline_value=check.baseline_value if valid else None,
                   noise_floor=check.noise_floor if valid else None,
                   state=state, alarm_s=scheduled if state == "STALL_SUSPECT" else None,
                   interval_status=check.interval_status if valid else None,
                   armed=state in ("STALL_SUSPECT", "NO_STALL_SUSPECT"),
                   unknown=state not in ("STALL_SUSPECT", "NO_STALL_SUSPECT") or (
                       valid and check.interval_status not in (None, "EVALUATED")),
                   reason=reason, denominator_included=True)
        self._rows.append(packed(row))
        return None  # Never return a control decision.
