"""Visible-only teacher memory (user 2026-10-14 15:45, adopted).

User: "그 교사도.. 눈으로 보고 있는 것에 대한 위치만 알게 하는 게 어때".
A teacher knows a target's pose only while it is visible in its own camera.
Otherwise it keeps the last seen pose in its own body frame and moves it only
by its own issued commands (dead reckoning). Memory expires after the
student's history length. Map priors (static map + the map code's own-pose
estimate) are kept separately and are never called "visible".

No simulator import. Callers supply relative poses computed from truth only
for currently visible targets (evaluation owner does the gating).
"""
from __future__ import annotations
import math

# Provisional: planned student command history 16 x 0.1 s (Codex contract v5
# plan, PR #484 comment 2026-10-14). Re-bind when v5 lands.
MEMORY_S = 1.6
# Nominal own-command odometry (provisional, evaluated against truth per run):
# S3 calibration 12.9 mm per 0.10 s pulse at u=0.35 (harness/zone_s3_synchronized_carry.py).
AXIAL_M_PER_S_AT_035 = .129
LATERAL_M_PER_S_AT_035 = .08      # unmeasured at 0.35; low-power strafe is weak on v7
YAW_CAL_RAD_PER_LEVEL_S = 3.0      # yaw_cal_v1 magnitude per (wheel level * s); see ODOMETRY_PROFILES
YAW_RAD_PER_S_AT_035 = .35        # replaced by the yaw probe measurement when available
# Pair-carry profile (toggle, default off): GCP gcp1 probes at 5d6e8291, two robots holding one beam with
# shared-scale 0.35 duty pulses <= 0.15 s, seeds 75000-75002. Realized/commanded: yaw 24.1-25.6 deg vs
# 14.7-14.9 deg (x1.68, 72 increments), lateral 219-225 mm vs 144 mm (x1.54, 6 legs), axial 196-205 mm vs
# 194-203 mm (x1.0, 12 legs). Not measured for a single free robot or other loads.
ODOMETRY_PROFILES = {
    'off': (AXIAL_M_PER_S_AT_035, LATERAL_M_PER_S_AT_035, YAW_RAD_PER_S_AT_035),
    'gcp_probe_v1': (AXIAL_M_PER_S_AT_035, .123, .588),
    # Native v7 wheel order: (-,+,-,+) turns clockwise in the map's
    # counterclockwise-positive SE(2) frame. release8 verifies this in all
    # 36 rotated captures of the three stored unloaded panoramas. Correct
    # the coordinate convention only; do NOT fit a speed to these failures.
    # Legacy reduced-wrench and pair-carry calibration profiles stay frozen.
    'native_yaw_v1': (AXIAL_M_PER_S_AT_035, LATERAL_M_PER_S_AT_035, -YAW_RAD_PER_S_AT_035),
    # release17 yaw_cal_v1 (default off; native_yaw_v1 above is kept byte-for-byte for replay).
    # Evidence in experiments/2026-10-14-e2e18-grasp-rootcause/release17.md: Y>0 is counter-clockwise
    # (the M1 sign, GT 11/11, own image 9/9, release7/8 rotation trains 9/9 unwrapped) and the
    # magnitude is ~3.0 rad/(level*s) (rotation trains 3.07-3.08, 0.2 s pulses median 2.79 n=11).
    # The tuple holds rad/s AT WHEEL LEVEL 0.35, i.e. 3.0*0.35 = 1.05, not 3.0.
    # The release8 comment above (sign "verified") is superseded by that unwrapped re-reading.
    'yaw_cal_v1': (AXIAL_M_PER_S_AT_035, LATERAL_M_PER_S_AT_035, YAW_CAL_RAD_PER_LEVEL_S*.35),
    # release23: R05 audit .08*1.515=.1212 and independent pair probe .123.
    # Lateral only; retain yaw_cal_v1 sign and 1.05 rad/s magnitude.
    'lateral_rate_cal_v1': (AXIAL_M_PER_S_AT_035, .122, YAW_CAL_RAD_PER_LEVEL_S*.35),
}


def rates(profile='off'):
    """(axial m/s, lateral m/s, yaw rad/s) at wheel level 0.35 for an odometry profile."""
    return ODOMETRY_PROFILES[profile]


def wheel_to_body(wheels):
    """Inverse of harness.grasp_act_contract.wheel_mix: (f-l-t, f+l+t, f+l-t, f-l+t)."""
    w0, w1, w2, w3 = wheels
    return (w0+w1+w2+w3)/4, (-w0+w1+w2-w3)/4, (-w0+w1-w2+w3)/4


def odometry(wheels, seconds, profile='off'):
    """Body-frame displacement (dx, dy, dyaw) from issued wheel levels only."""
    f, l, t = wheel_to_body(wheels)
    k = 1/.35; ax, lat, yaw = rates(profile)
    return (f*k*ax*seconds, l*k*lat*seconds, t*k*yaw*seconds)


def relative(robot_pose, xy, yaw=0.):
    """World (x, y, yaw) -> robot body frame. Only for visible targets."""
    dx, dy = xy[0]-robot_pose[0], xy[1]-robot_pose[1]
    c, s = math.cos(robot_pose[2]), math.sin(robot_pose[2])
    return [c*dx+s*dy, -s*dx+c*dy, math.atan2(math.sin(yaw-robot_pose[2]), math.cos(yaw-robot_pose[2]))]


class VisibleBelief:
    def __init__(self, memory_s=MEMORY_S):
        self.memory_s = memory_s
        self.items = {}

    def observe(self, name, rel_pose, now, *, source='visible', **extra):
        if source not in ('visible', 'map_prior', 'own_command'):
            raise ValueError('only visible observations, own-command knowledge or explicit map priors')
        self.items[name] = {'pose': list(rel_pose), 'seen_t': now, 'source': source, **extra}

    def propagate(self, dx, dy, dyaw):
        """Own motion (dx, dy, dyaw) in the previous body frame."""
        c, s = math.cos(dyaw), math.sin(dyaw)
        for item in self.items.values():
            x, y, a = item['pose']
            x, y = x-dx, y-dy
            item['pose'] = [c*x+s*y, -s*x+c*y, a-dyaw]
            if item['source'] == 'visible':
                item['source'] = 'dead_reckoned'

    def get(self, name, now):
        item = self.items.get(name)
        if item is None:
            return None
        if item['source'] not in ('map_prior', 'own_command') and now-item['seen_t'] > self.memory_s:
            return None
        return item

    def forget_expired(self, now):
        for name in [k for k, v in self.items.items() if v['source'] not in ('map_prior', 'own_command') and now-v['seen_t'] > self.memory_s]:
            del self.items[name]
