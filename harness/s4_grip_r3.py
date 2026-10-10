"""Cyan-only DEV candidates. Beam monitor and its command path stay frozen."""
from collections import deque
import math
import cv2
import numpy as np
from harness.s4_grip_visual import TemporalGrip

MODES = ('existing', 'edge_roi', 'absence_vote', 'active_reobserve')


def cyan_mask(frame):
    if frame.shape != (480,640,3) or frame.dtype != np.uint8:
        raise ValueError('owned 640x480 BGR required')
    hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
    # Remove y14..36 lens/border colour noise, retain the full lower face.
    mask=(hsv[...,0]>=80)&(hsv[...,0]<=105)&(hsv[...,1]>=100)&(hsv[...,2]>=60)
    return mask[40:472:2,24:616:2]


class R3Grip:
    def __init__(self, mode='existing', *, robot_id='r3'):
        if robot_id!='r3' or mode not in MODES:raise ValueError('registered r3 candidate only')
        self.mode=mode
        self.legacy=TemporalGrip('cyan') if mode=='existing' else None
        self.initial=[];self.reference=None;self.last_t=None
        self.unobservable=False;self.lost=False;self.bad=0
        self.unknown_streak=0;self.reobserved=False;self.moving_until=None

    def reset_after_reobserve(self):
        self.initial=[];self.reference=None;self.unobservable=False;self.bad=0
        self.unknown_streak=0;self.moving_until=None

    def observe(self, frame, sim_time):
        if self.legacy is not None:return self.legacy.observe(frame,sim_time)
        if not math.isfinite(sim_time) or (self.last_t is not None and sim_time<=self.last_t):
            self.bad=0;return dict(state='unknown',reason='INVALID_TIME')
        gap=self.last_t is not None and sim_time-self.last_t>.15+1e-8
        self.last_t=sim_time
        if self.moving_until is not None:
            if sim_time<self.moving_until-1e-8:return dict(state='unknown',reason='REOBSERVING_MOVING_CAMERA')
            self.reset_after_reobserve()
        try:mask=cyan_mask(frame)
        except (AttributeError,ValueError):
            self.bad=0;return dict(state='unknown',reason='INVALID_RGB')
        if gap:self.bad=0;return dict(state='unknown',reason='FRAME_GAP')
        if self.unobservable:
            self.unknown_streak+=1;return dict(state='unknown',reason='ANCHOR_UNOBSERVABLE')
        if self.reference is None:
            self.initial.append(mask)
            if len(self.initial)<3:return dict(state='unknown',reason='ANCHOR_ACQUISITION')
            self.reference=np.sum(self.initial,axis=0)>=2
            # 150 grid pixels = 600 native pixels; observed blank bodies have 0.
            if int(self.reference.sum())<150:
                self.unobservable=True;self.unknown_streak=1
                return dict(state='unknown',reason='ANCHOR_UNOBSERVABLE')
        ref=self.reference;overlap=int((ref&mask).sum());seen=int(mask.sum())
        retained=overlap/max(1,int(ref.sum()));iou=overlap/max(1,int((ref|mask).sum()))
        if self.mode=='edge_roi':
            shift=float(np.linalg.norm((np.argwhere(mask).mean(0)-np.argwhere(ref).mean(0))/np.array(mask.shape))) if seen else 1.
            bad=iou<.6 or retained<.6 or shift>.1;needed=3
        else:
            # Full disappearance vote; movement with an object still visible is
            # a warning, not a claim of complete bilateral contact loss.
            bad=seen<max(20,.03*int(ref.sum()));needed=5
        self.bad=self.bad+1 if bad else 0;self.lost|=self.bad>=needed
        return dict(state='grip_lost' if self.lost else 'held',reason='RGB_ABSENCE_VOTE' if self.lost else 'RGB_PRESENT',
                    seen_grid_pixels=seen,retained=retained,iou=iou,bad_frames=self.bad,
                    motion_warning=iou<.6,contact_claim=False)

    def request_reobserve(self, relative_s, sim_time, commanded_servo):
        """One pre-disturbance attempt, driven solely by own RGB/own commands."""
        if (self.mode!='active_reobserve' or self.reobserved or self.lost
                or self.unknown_streak<3 or relative_s>1.+1e-8):return None
        from harness.zone_final_pair_vision import GRASP_RADIUS_M
        from harness import visual_arm_v3 as arm
        from scripts.study_owncam_pair_beam import HOVER_Z_M
        from scripts.zone_teacher import ArmSequence
        pose=arm.solve_grip_ik(GRASP_RADIUS_M,0.,HOVER_Z_M,-55.)
        tape=ArmSequence(None,dict(commanded_servo))
        tape.queue({**pose,1:1500},sim_time,duration=.6,settle=.3)
        self.reobserved=True;self.moving_until=tape.until
        return dict(events=list(tape.events),until=tape.until,pose=pose,
                    reason='OWN_RGB_ANCHOR_UNOBSERVABLE',max_attempts=1,
                    qualification='command-space same grip site; actual retention evaluated separately')
