"""v98 only: an unloaded approach never re-looks in place on the 3 s fix-recency alone.

Finding (v98 raise_high probe 1f7fb800, r2, offline replay of the real driver on the recorded own frames): the
drive-posture camera yields almost no informative scan near the goal wall (95 of the 101 informative scans after
19 s were taken during arm sweeps, 6 while driving), so ``fix_age_s > LOOK_IF_NO_FIX_S`` (zone_own_driver.py) is true
again within ~3 s of every look. 13 looks took 113 of 141 s; 7 of the 9 ``no_fix`` looks started after <= 0.08 m of
estimated travel since the previous look, i.e. the same viewpoint with the same belief (no new information).

Rule: an observation update/look is only worth its cost after the robot has moved (ROS AMCL ``update_min_d``:
the filter is updated only after a minimum translation; Nav2 BT recovery: a retried action must change something).
The registered unloaded travel distance (``owncam_drive.LOADED_LOOK_EVERY_M``, 0.35 m via ``_travel_look_m``) gates
the ``no_fix`` branch only. ``not_initialized``, ``uncertain`` (sigma), door checkpoints, ``progress_check``,
``gate_uncertain``, ``relocalize``, ``turn_step``, arrival check and the MAX_LOOKS_WITHOUT_FIX / MAX_RELOCALIZE
bounds are untouched, so the loop still ends in ``lost`` instead of holding forever.

Inputs: own estimate (from own RGB + own commands) only. No new threshold. Shared modules are unchanged.
"""
from __future__ import annotations

ID = 'v98_approach_no_fix_travel_gate_v1'
REFERENCES = ('ROS AMCL update_min_d / update_min_a (github.com/ros-planning/navigation, amcl_node.cpp)',
              'Nav2 BT RecoveryNode number_of_retries + RoundRobin (github.com/ros-navigation/navigation2)')


class TravelGatedNoFix:
    """Mixin placed in front of the guarded pair approach driver."""

    def _needs_look(self, est, now):
        if (not self.loaded and est.get('fix_age_s') is not None and self.last_look_xy is not None
                and self._since_look_m(est) <= self._travel_look_m()):
            est = {**est, 'fix_age_s': None}          # recency alone: no look until the robot has moved
        return super()._needs_look(est, now)


_CACHE: dict = {}


def adopt(cls):
    """Driver class with the gate; one class object per base so ``type(driver)`` stays stable."""
    if cls not in _CACHE:
        _CACHE[cls] = type('TravelGated' + cls.__name__, (TravelGatedNoFix, cls), {})
    return _CACHE[cls]


def record() -> dict:
    return {'id': ID, 'scope': 'unloaded approach no_fix look only', 'new_threshold': False,
            'distance_m_source': 'owncam_drive.LOADED_LOOK_EVERY_M via _travel_look_m', 'references': list(REFERENCES)}
