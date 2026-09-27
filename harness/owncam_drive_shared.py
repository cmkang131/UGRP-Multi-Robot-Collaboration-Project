"""Controller state initialization for an already injected own-pose localizer.

Inserted before OwnCamDriver in the cooperative MRO: pair approach constructors
still initialize their heading/pursuit fields, but the frozen base constructor
never runs. GuardedDriver binds ``self.loc`` before entering this chain.
The controller fields/defaults mirror the frozen base; no provider is created.
"""
from collections.abc import Mapping, Sequence

from harness.map_goto import UNLOADED_ENVELOPE
from harness.owncam_drive import CARRY_POSTURE, LOADED_ENVELOPE, SEARCH_POSE, OwnCamDriver


class SharedPoseDriver(OwnCamDriver):
    def __init__(self, static_map: Mapping, params: Mapping, *, loaded: bool, goal_xy: Sequence[float],
                 door_xy: Sequence[float], keepouts: Sequence[Mapping] = (), initial_servo: Mapping | None = None,
                 seed: int = 0, width: int = 640, height: int = 480):
        self.map = static_map
        self.loaded = bool(loaded)
        self.goal = [float(goal_xy[0]), float(goal_xy[1])]
        self.door = [float(door_xy[0]), float(door_xy[1])]
        self.keepouts = [dict(k) for k in keepouts]
        self.envelope = LOADED_ENVELOPE if loaded else UNLOADED_ENVELOPE
        self.drive_pose = dict(CARRY_POSTURE) if loaded else dict(SEARCH_POSE)
        self.servo = {int(k): int(v) for k, v in (initial_servo or {}).items()}
        self.state, self.state_since = 'posture', None
        self.arm_target: dict[int, int] = {}
        self.look_queue: list[int] = []
        self.look_reason = None
        self.looks, self.looks_without_fix = 0, 0
        self.checkpoints_done: set[float] = set()
        self.path, self.plan_at, self.plan_fails = None, -1., 0
        self.outcome = None
        self.log: list[dict] = []
        self.last_estimate = self.loc.estimate()
        self.frames_seen = 0
        self.arrival_checked = False
        self.last_look_xy = None
