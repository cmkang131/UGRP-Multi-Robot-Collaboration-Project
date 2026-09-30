"""Explicit T03 color-box kinds; no can/tile/crate shape or identity support."""
import math
from dataclasses import dataclass

from harness.wrist_zone_skill_v5 import CoarseOrderSheet

BOX_KINDS = ('cyan', 'red', 'green')


def require_box_kind(kind):
    if not isinstance(kind, str) or kind not in BOX_KINDS:
        raise ValueError('M1 color boxes support only cyan, red, green')
    return kind


def validate_box_profile(profile, kind, order_kind):
    require_box_kind(kind)
    if profile not in ('legacy_cyan_v1', 'm1_color_boxes_v1'):
        raise ValueError('unknown M1 box profile')
    if profile == 'legacy_cyan_v1' and kind != 'cyan':
        raise ValueError('legacy M1 supports cyan only; select m1_color_boxes_v1')
    if profile == 'm1_color_boxes_v1' and order_kind != 'own_rgb_bay':
        raise ValueError('color boxes require the coarse own-RGB bay contract')
    return profile


@dataclass(frozen=True)
class ColorBoxOrder(CoarseOrderSheet):
    """Same public coarse-bay contract; explicit kind replaces the legacy cyan gate."""

    def __post_init__(self):
        require_box_kind(self.kind)
        for name in ('pickup_bay_center_m', 'pickup_bay_half_m', 'slot_xy_m'):
            value = getattr(self, name)
            if len(value) != 2 or not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                          and math.isfinite(v) for v in value):
                raise ValueError(f'{name} must be two finite numbers')
        if min(self.pickup_bay_half_m) < .15:
            raise ValueError('a pickup bay is coarse (half extent >= 0.15 m), not a box position')
