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
from harness.drive_model import CommandDriveModel, validate_options

# Provisional: planned student command history 16 x 0.1 s (Codex contract v5
# plan, PR #484 comment 2026-10-14). Re-bind when v5 lands.
MEMORY_S = 1.6
# Nominal own-command odometry (provisional, evaluated against truth per run):
# S3 calibration 12.9 mm per 0.10 s pulse at u=0.35 (harness/zone_s3_synchronized_carry.py).
AXIAL_M_PER_S_AT_035 = .129
LATERAL_M_PER_S_AT_035 = .08      # unmeasured at 0.35; low-power strafe is weak on v7
YAW_RAD_PER_S_AT_035 = .35        # replaced by the yaw probe measurement when available
# Pair-carry profile (toggle, default off): GCP gcp1 probes at 5d6e8291, two robots holding one beam with
# shared-scale 0.35 duty pulses <= 0.15 s, seeds 75000-75002. Realized/commanded: yaw 24.1-25.6 deg vs
# 14.7-14.9 deg (x1.68, 72 increments), lateral 219-225 mm vs 144 mm (x1.54, 6 legs), axial 196-205 mm vs
# 194-203 mm (x1.0, 12 legs). Not measured for a single free robot or other loads.
ODOMETRY_PROFILES = {
    'off': (AXIAL_M_PER_S_AT_035, LATERAL_M_PER_S_AT_035, YAW_RAD_PER_S_AT_035),
    'gcp_probe_v1': (AXIAL_M_PER_S_AT_035, .123, .588),
}


def rates(profile='off', *, drive_model_deadband_v1=False):
    """Rates per 0.1 s isolated pulse at .35, including the subsequent coast.

    ON axial passes the S3 12.6--13.2 mm acceptance band (12.9 mm measured).
    ON yaw uses the same loss provisionally; yaw/lateral losses are unmeasured.
    These planning rates are not steady velocities or an integration shortcut.
    """
    validate_options(drive_model_deadband_v1,profile=profile)
    if drive_model_deadband_v1:
        def pulse_rate(wheels, axis):
            model=CommandDriveModel()
            active=model.delta(wheels,[.1]*4,.1)[axis]
            # Analytic zero-torque stop time, not a fitted settling timeout.
            p=model.parameters
            stop=max(p.effective_inertia_kg_m2/p.total_damping_nm_s *
                     math.log1p(p.total_damping_nm_s*abs(w)/p.rolling_torque_nm)
                     for w in model.angular_speeds)
            return (active+model.delta([0.]*4,[0.]*4,stop)[axis])/.1
        axial=pulse_rate([.35]*4,0)
        yaw=pulse_rate([-.35,.35,-.35,.35],2)
        return axial,axial,yaw
    return ODOMETRY_PROFILES[profile]


def wheel_to_body(wheels):
    """Inverse of harness.grasp_act_contract.wheel_mix: (f-l-t, f+l+t, f+l-t, f-l+t)."""
    w0, w1, w2, w3 = wheels
    return (w0+w1+w2+w3)/4, (-w0+w1+w2-w3)/4, (-w0+w1-w2+w3)/4


def odometry(wheels, seconds, profile='off', *, drive_model_deadband_v1=False, model=None, durations_s=None):
    """Body-frame displacement (dx, dy, dyaw) from issued wheel levels only."""
    validate_options(drive_model_deadband_v1,profile=profile)
    if drive_model_deadband_v1:
        return (model if model is not None else CommandDriveModel()).delta(
            wheels,[seconds]*4 if durations_s is None else durations_s,seconds)
    if model is not None or durations_s is not None:raise ValueError('drive model state/durations require drive_model_deadband_v1')
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
