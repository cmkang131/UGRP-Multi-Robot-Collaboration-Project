"""Exact v5b predicates for regression only; see manifest source hashes."""
from harness.zone_own_contract import finite_number, POSE_TIME_ROUNDING_S
from harness.zone_pair_align import relook_reason

def pose_report_fresh(report, now, *, max_age_s=.3):
    """Same bounded report-time contract for pair admission and command guards."""
    return (report is not None and finite_number(now) and finite_number(report.t_est)
            and -POSE_TIME_ROUNDING_S <= now - report.t_est <= max_age_s + 1e-9)

def _align_fix_ready(self, now):
    from harness.zone_pair_grasp import FIX_STD_XY_M, FIX_STD_YAW_RAD

    own, start = self.port.own, self.align_look_started_at
    r = own.last_report
    return bool(self.driver.loc is own.pose.loc and pose_report_fresh(r, now)
                and r.initialized and own.gate.ok
                and all(finite_number(v) for v in (r.x_m, r.y_m, r.yaw_rad))
                and 0 <= r.std_xy_m <= FIX_STD_XY_M and 0 <= r.std_yaw_rad <= FIX_STD_YAW_RAD
                and relook_reason(r, now) is None
                and finite_number(r.since_tag_s) and r.since_tag_s >= 0
                and start < r.t_est - r.since_tag_s <= now
                and own.pose.loc.last_tag_t is not None
                and start < own.pose.loc.last_tag_t <= r.t_est)
