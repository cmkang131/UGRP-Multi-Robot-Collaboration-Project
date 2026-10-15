"""Heavy-crate set-down teacher: the beam release teacher with crate geometry.

Same visible_only logic (sim/grasp_act_release_teacher.ReleaseTeacher, PairReleaseCode),
only the own-geometry constants differ (sim/cargo_teacher_profile.CRATE):
- while holding, the landing end is the issued-arm forward-kinematics grip point
  moved ``grasp_to_end_m`` (0.02 m; beam 0.03) toward the robot;
- after release, the landing end is the visible lug centre moved ``landing_end_m -
  band_center_m`` (0.03 m) outward;
- a re-grasp aims at the lug grasp point, 0.01 m outward of the lug centre.
No simulator import.
"""
from __future__ import annotations
import math
from harness.visual_arm_v3 import forward_grip
from sim.grasp_act_release_teacher import ReleaseTeacher
from sim.cargo_teacher_profile import CRATE


class CrateReleaseTeacher(ReleaseTeacher):
    def __init__(self, *args, profile=CRATE, input_audit=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.profile = profile
        self.input_audit=input_audit
        self.observation_sources=frozenset()

    def perceive(self, obs, now):
        if self.input_audit is not None:
            from harness.grasp_act_input_audit import Sourced,admit
            if not isinstance(obs,Sourced):raise ValueError('strict release requires sourced observations')
            self.observation_sources=obs.sources
            obs=admit(obs,self.input_audit)
        return super().perceive(obs,now)

    def fixed_message(self, phase, now):
        """Local report -> finite vocabulary; continuous margins never cross."""
        from harness.grasp_act_input_audit import sourced
        if phase not in ('look','observe'):
            return sourced({'phase':phase,'signal':'READY'},'issued_commands')
        report=self.last_report or {}
        m=report.get('margin_m');kind=report.get('kind')
        from sim.grasp_act_release_teacher import MARGIN_M
        # Current own scan only, no stale report or map-prior claim of INSIDE.
        fresh=self.last_scan is not None and bool(self.last_scan[1]) and now-self.last_scan[0]<=.15+1e-9
        signal='UNKNOWN'
        if fresh:
            if kind in ('edge','inside_lb') and m is not None and m>=MARGIN_M:
                signal='INSIDE'
            elif kind=='outside' or (kind=='edge' and m is not None and m<MARGIN_M):
                signal='OUTSIDE'
            # A small *lower bound* is not evidence of insufficient clearance.
        if not self.observation_sources:raise ValueError('release report missing observation provenance')
        return sourced({'phase':phase,'signal':signal},*self.observation_sources,'issued_commands')

    def _outward(self, axis):
        sign = -1. if self.end == 'teal' else 1.
        return sign*math.cos(axis), sign*math.sin(axis)

    def end_and_outward(self, now):
        p = self.profile
        if self.holding:
            x, y, _ = forward_grip(self.pwm)
            return (x-p.grasp_to_end_m, y), (-1., 0.), 'commands_fk'
        band = self.belief.get('band', now)
        if band is None or band['source'] not in ('visible', 'dead_reckoned'):
            band = self.belief.get('released_band', now)
            source = 'own_command_release'
        else:
            source = band['source']
        bx, by, axis = band['pose']
        if source == 'own_command_release':
            # released_band is the grip point (axis 0 = the robot's own facing at release, moved by
            # own odometry since). The robot faces its end, so outward is -facing for both ends; the
            # beam teacher's sign-by-end rule would flip it for 'blue'.
            ox, oy = -math.cos(axis), -math.sin(axis)
            return (bx+p.grasp_to_end_m*ox, by+p.grasp_to_end_m*oy), (ox, oy), source
        ox, oy = self._outward(axis)
        d = p.landing_end_m-p.band_center_m
        return (bx+d*ox, by+d*oy), (ox, oy), source

    def pick_target(self, now):
        band = self.belief.get('band', now) or self.belief.get('released_band', now)
        bx, by, axis = band['pose']
        if band['source'] == 'own_command':   # released_band already is the grip point
            return (bx, by), band['source']
        ox, oy = self._outward(axis)
        d = self.profile.band_to_grasp_m
        return (bx+d*ox, by+d*oy), band['source']
