"""Explicit color behavior for the active adapter; frozen M1 stays byte-identical."""
import math

from harness.m1_color_contract import ColorBoxOrder
from harness.m1_color_perception import detect_own
from harness.m1_owncam_delivery import BAY_HALF_M


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
