"""Scripted DEV memory-return diagnostic; inputs are only own observations.

This is not the LLM's task/partner/cargo decision layer. The user explicitly
requested this diagnostic sequence: look, remember any observed zone, depart,
turn toward memory, visually reacquire. It never declares delivery/arrival.
"""
import math
import numpy as np
from harness.egocentric_landmark_memory import wrap, language_context


class MemoryReturn:
    def __init__(self, *, sweep_steps, footprint_diameter_m, horizontal_half_fov_rad, strict_return=False, translated_return=False):
        self.sweep_steps=sweep_steps;self.diameter=footprint_diameter_m;self.half_fov=horizontal_half_fov_rad
        self.stage='look';self.steps=0;self.turn=0.;self.away_path=0.;self.goal=None;self.goal_range=None
        self.departed=False;self.done=False;self.events=[]
        self.strict_return=strict_return;self.goal_hue=None;self.visual_exit=False
        self.translated_return=translated_return;self.return_path=0.;self.return_moving=False

    def step(self,t,increment,memories,observations,*,colour_pixels=None):
        self.steps+=1
        def event(reason,**extra):
            self.events.append(dict(t=t,stage=self.stage,category='memory_return',reason=reason,
                blocked_object='not_observed',minimum_gap_m=None,gap_status='not_measured',**extra))
        # Whole-body scan uses actual new self RGB each control tick. The
        # finite cap comes from prior own-LK positive yaw P05, not wall time.
        if self.stage=='look':
            self.turn+=max(0.,increment[2])
            if self.turn>=2*math.pi or self.steps>=self.sweep_steps:
                choices=[m for m in memories if m['kind']=='zone_boundary']
                if not choices:
                    event('cap_end_no_visual_zone');self.done=True;return [0.,0.,0.]
                chosen=min(choices,key=lambda m:m['age_s'])
                self.goal=chosen['id'];self.goal_range=max(self.diameter,chosen['range_m'])
                self.goal_hue=chosen.get('appearance_hue')
                if self.strict_return:
                    rho=chosen['measurement_state'][0]
                    # Oriented normal points INTO the observed colored side.
                    # If inside, cross its measured boundary plus one robot
                    # envelope radius. No map boundary/zone center is supplied.
                    self.goal_range=max(self.diameter,max(0.,-rho)+self.diameter/2)
                event('visual_zone_remembered',memory_id=self.goal,signature=chosen['signature'],
                      departure_distance_m=self.goal_range,scan_own_yaw_rad=self.turn)
                self.stage='depart_turn';self.steps=0
            else:return [0.,0.,.35]
        target=next((m for m in memories if m['id']==self.goal),None)
        if target is None:
            event('memory_deleted');self.done=True;return [0.,0.,0.]
        if self.steps>=self.sweep_steps:
            event('cap_end_phase_compute_budget');self.done=True;return [0.,0.,0.]
        angle=target['bearing_rad']
        if self.stage=='depart_turn':
            error=wrap((target['measurement_state'][1] if self.strict_return else angle)+math.pi)
            # Only the positive folded rotation has an exact own-RGB command
            # calibration. Do not invent a mirrored negative response model.
            if abs(error)>self.half_fov:return [0.,0.,.35]
            self.stage='depart';self.steps=0;event('departure_heading_observed_history')
        if self.stage=='depart':
            self.away_path+=float(np.linalg.norm(increment[:2]))
            if self.strict_return and colour_pixels==0:self.visual_exit=True
            if self.away_path<self.goal_range or (self.strict_return and not self.visual_exit):return [.35,0.,0.]
            self.departed=True;self.stage='return';self.steps=0;event('departure_command_distance_reached',own_path_m=self.away_path)
        if self.stage=='return':
            if self.return_moving:self.return_path+=float(np.linalg.norm(increment[:2]))
            self.return_moving=False
            matching=[o for o in observations if o['kind']=='zone_boundary' and o['signature']==target['signature']]
            # Existing robot envelope diameter is the geometric evidence of a
            # translated return, rather than just turning back to see the color.
            translated=(not self.translated_return or self.return_path>=self.diameter)
            if matching and translated and (not self.strict_return or (self.visual_exit and colour_pixels and abs(angle)<=self.half_fov)):
                event('rgb_signature_reacquired',memory_id=self.goal,signature=target['signature'],
                      evaluation_required=True,arrival_verified=False,own_return_path_m=self.return_path)
                self.done=True;return [0.,0.,0.]
            if abs(angle)>self.half_fov:return [0.,0.,.35]
            self.return_moving=True
            return [.35,0.,0.]
        return [0.,0.,0.]

    def context(self,memories):
        target=next((m for m in memories if m['id']==self.goal),None)
        return language_context(memories,goal_signature=target['signature'] if target else None)
