"""Active M1 state/leg adapter with explicit legacy/color profile selection.

The constructor mirrors frozen controller fields, but selects the final provider
before initialization. No temporary provider is constructed for an injected one.
"""
from collections.abc import Mapping, Sequence
from harness.m1_owncam_delivery import M1OwnCamDelivery, ORDER_KINDS, DOOR_EXIT_M
from harness.m1_color_contract import validate_box_profile
from harness.m1_color_delivery import ColorBoxDeliveryMixin
from harness.owncam_drive import CARRY_POSTURE
from harness.owncam_drive_v2 import OwnCamDriverV2
from harness.owncam_drive_shared import SharedPoseDriver
from harness.owncam_pose_source import OwnCamPoseSource


class SharedLegDriver(OwnCamDriverV2, SharedPoseDriver):
    def __init__(self, shared_loc, *args, **kwargs):
        self.loc = shared_loc
        super().__init__(*args, **kwargs)

    def on_command(self, row):
        kind = row['kind']
        if kind == 'initial_servo_command':
            self.servo = {int(k): int(v) for k, v in row['pulses'].items()}
        elif kind == 'arm':
            self.servo[int(row['servo_id'])] = int(row['pulse'])
        elif kind == 'look':
            self.servo[6] = int(row['pan_pulse'])

    def observe(self, now, rgb):
        raise RuntimeError('feed frames through the owning pose provider exactly once')


class SharedPoseDelivery(ColorBoxDeliveryMixin, M1OwnCamDelivery):
    def __init__(self, static_map: Mapping, params: Mapping, *, box_kind: str, slot_id: str,
                 slot_xy: Sequence[float], skill_factory, pose_estimate_cls, search_rows_y: Sequence[float],
                 robot_id: str = 'r1', seed: int = 0, order_kind: str = 'own_rgb_bay', pose_source=None,
                 box_profile: str = 'legacy_cyan_v1'):
        if pose_source is not None:
            from harness.pose_provider import is_own_pose_provider
            from harness.m1_owncam_contract import require_m1_source
            require_m1_source(getattr(pose_source, 'source', None))
            if not is_own_pose_provider(pose_source):
                raise ValueError('M1 requires a registered own-camera provider')
        self.box_profile = validate_box_profile(box_profile, box_kind, order_kind)
        if order_kind not in ORDER_KINDS:
            raise ValueError(f'order_kind must be one of {ORDER_KINDS}')
        self.order_kind = order_kind
        self.order_record = None
        self.probe: dict | None = None
        self.manipulated = False
        self.motion_profile = None
        self.map = static_map
        self.static_keepouts = []
        self.params = params
        self.box_kind = box_kind
        self.slot_id = slot_id
        self.slot_xy = (float(slot_xy[0]), float(slot_xy[1]))
        self.skill_factory = skill_factory
        self.pose_estimate_cls = pose_estimate_cls
        self.robot_id = robot_id
        self.seed = seed
        self.pose = pose_source if pose_source is not None else OwnCamPoseSource(static_map, params, seed=seed)
        door = next(p for p in static_map['passages'] if p['kind'] == 'door')
        self.door_xy = (float(door['center_m'][0]), float(door['center_m'][1]))
        self.exit_xy = (self.door_xy[0] + DOOR_EXIT_M, self.door_xy[1])
        self.search_rows_y = sorted(float(y) for y in search_rows_y)
        self.viewpoints: list[tuple[float, float]] = []
        self.phase = 'init'
        self.view_index = 0
        self.leg: SharedLegDriver | None = None
        self.sweep: dict | None = None
        self.cyan: list[dict] = []
        self.seen: list[dict] = []           # every box seen (any colour), map frame, for keep-outs
        self.last_skill_frame: int | None = None
        self.target_xy: tuple[float, float] | None = None
        self.pickup_source: str | None = None
        self.skill = None
        self.servo: dict[int, int] = {}
        self.last_obs: Mapping | None = None
        self.last_frame_id: int | None = None
        self.last_look_t: float | None = None
        self.look_count = 0
        self.gate_looks = 0
        self.preplace_look_done = False
        self.reanchor_needed = False
        self.lookback_gates: list[dict] = []      # one per own-RGB confirmation frame (Codex pre-review #3)
        self.approach_choice: dict | None = None
        self.outcome: str | None = None
        self.events: list[dict] = []
        self.pose_sources: set[str] = set()
        self.face_fallback_used = False
        self.carry_leg_done = False
        self.init_looks = 0

    def _start_leg(self, goal, *, loaded):
        self.leg = SharedLegDriver(self.pose.loc, self.map, self.params, loaded=loaded, goal_xy=goal,
                              door_xy=self.door_xy, keepouts=self._keepouts(), initial_servo=dict(self.servo),
                              seed=self.seed)
        if loaded:
            self.leg.drive_pose = dict(CARRY_POSTURE)
        self.leg_goal = tuple(goal)
