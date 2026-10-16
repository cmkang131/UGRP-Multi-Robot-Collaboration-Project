"""Opt-in color delivery state; sealed M1 and shared adapters never import this module."""
import math
from collections.abc import Mapping, Sequence

from harness.m1_color_contract import ColorBoxOrder, validate_box_profile
from harness.m1_color_perception import detect_own
from harness.m1_owncam_delivery import BAY_HALF_M, ORDER_KINDS, DOOR_EXIT_M
from harness.owncam_delivery_shared import SharedPoseDelivery, SharedLegDriver
from harness.owncam_pose_source import OwnCamPoseSource


class ColorBoxDeliveryMixin:
    box_profile = 'legacy_cyan_v1'

    @property
    def target_detections(self):
        # Preserve the inherited storage name used by clustering and memory adapters.
        return self.cyan

    def _search_detect(self, obs, report):
        if self.box_profile != 'm1_color_boxes_v1':
            return super()._search_detect(obs, report)
        if not report.initialized:
            return
        result = detect_own(obs['image'], obs['actuator_state']['servo_pulses'])
        c, s = math.cos(report.yaw_rad), math.sin(report.yaw_rad)
        for d in result['detections']:
            bx, by = d['estimated_box_center_base_m'][:2]
            row = {'t': report.t_est, 'kind': d['kind'], 'range_class': d['range_class'],
                   'map_xy': [report.x_m + c*bx - s*by, report.y_m + s*bx + c*by],
                   'base_xy': [bx, by], 'iou': d['floor_hypothesis_projection_iou'], 'std_xy_m': report.std_xy_m}
            if d['range_class'] == 'near':
                self.seen.append(row)
            if d['kind'] == self.box_kind:
                self.target_detections.append(row)

    def _make_order(self):
        if self.box_profile != 'm1_color_boxes_v1':
            return super()._make_order()
        tx, ty = (round(float(v), 4) for v in self.target_xy)
        order = ColorBoxOrder(self.box_kind, 'own_rgb_search_bay', (tx, ty), BAY_HALF_M, self.slot_id, self.slot_xy)
        self.order_record = {**order.record(), 'bay_source': 'own RGB search cluster centre (this run)'}
        return order

    def summary(self):
        result = super().summary()
        if self.box_profile == 'legacy_cyan_v1':
            return result
        result.update(box_kind=self.box_kind, box_profile=self.box_profile,
                      target_detections=len(self.target_detections),
                      cyan_detections=len(self.target_detections) if self.box_kind == 'cyan' else 0)
        return result


class ColorSharedPoseDelivery(ColorBoxDeliveryMixin, SharedPoseDelivery):
    """Versioned color constructor; inherited navigation keeps its sealed bytes.

    Mirror the shared state initialization here because its cyan-only admission
    is frozen. Validate the real kind before constructing a provider; never
    temporarily lie about the kind or patch a shared module/class.
    """
    def __init__(self, static_map: Mapping, params: Mapping, *, box_kind: str, slot_id: str,
                 slot_xy: Sequence[float], skill_factory, pose_estimate_cls, search_rows_y: Sequence[float],
                 robot_id: str = 'r1', seed: int = 0, order_kind: str = 'own_rgb_bay', pose_source=None,
                 box_profile: str = 'm1_color_boxes_v1'):
        if pose_source is not None:
            from harness.pose_provider import is_own_pose_provider
            from harness.m1_owncam_contract import require_m1_source
            require_m1_source(getattr(pose_source, 'source', None))
            if not is_own_pose_provider(pose_source):
                raise ValueError('M1 requires a registered own-camera provider')
        validate_box_profile(box_profile, box_kind, order_kind)
        if box_profile != 'legacy_cyan_v1':
            self.box_profile = box_profile
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
