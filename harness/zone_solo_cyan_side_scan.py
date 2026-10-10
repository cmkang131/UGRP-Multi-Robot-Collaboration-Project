"""Default-off, own-RGB-only side-scan diagnostic before the first lateral pulse.

Reuses Active Markov's settled arm observation timing and the v106 scan posture.
Orange appearance is a candidate obstacle, not identity, depth or free-space.
"""
import copy
import time
import cv2
import numpy as np

from harness.zone_solo_cyan_active_markov import PARAMS as ACTIVE
from harness.zone_solo_cyan_v106 import LOOK_P20

OPTION = 'side_scan_v1'
PARAMS = dict(arm_settle_s=ACTIVE['arm_settle_s'], observe_s=.75,
              side_pans=[2300,700], wall_cap_s=900., sim_cap_s=45.)
# PR398 orange_columns_v1 constants, unchanged. Components only summarize it.
APPEARANCE = dict(hsv_lower=[5,100,60],hsv_upper=[25,255,255],open_px=3,dilate_px=5)


def orange_candidates(rgb):
    from harness import vision_loc_protocol as vp
    bgr=vp.load_vis3()[0].mp.undistort(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
    hsv=cv2.cvtColor(bgr,cv2.COLOR_BGR2HSV)
    mask=cv2.inRange(hsv,tuple(APPEARANCE['hsv_lower']),tuple(APPEARANCE['hsv_upper']))
    opened=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
    dilated=cv2.dilate(opened,np.ones((5,5),np.uint8))
    n,_,stats,_=cv2.connectedComponentsWithStats(dilated,8)
    return dict(orange_pixels=int(np.count_nonzero(opened)),
        detected=bool(np.any(opened)),components=[dict(bbox=s[:4].tolist(),area=int(s[4])) for s in stats[1:n]],
        semantics='orange appearance candidate only; no identity, depth or free-space claim')


def arm_actions(rid,servo):
    """Same arm/look command encoding used by active_markov_v1.setup."""
    return [(rid,dict(kind='look',pan_pulse=v) if k==6 else dict(kind='arm',servo_id=k,pulse=v))
            for k,v in servo.items()]


def runtime_class(previous):
    class Runtime(previous):
        def __init__(self,*args,side_scan='off',**kw):
            if side_scan not in ('off',OPTION):raise ValueError('unknown side_scan')
            self.side_scan_option=side_scan
            super().__init__(*args,**kw)
            if side_scan=='off':return
            self.side_scan_done=False;self.side_scan_phase=None;self.side_scan_queue=[]
            self.side_scan_after=0.;self.side_scan_wall=time.monotonic()
            self.side_scan_audit=dict(option=OPTION,parameters=copy.deepcopy(PARAMS),
                appearance=copy.deepcopy(APPEARANCE),frames=[],trigger=None,gt_inputs=False,
                cap_s=PARAMS['sim_cap_s'],transport_attempted=False)

        def on_frames(self,now,frames):
            if self.side_scan_option=='off':return super().on_frames(now,frames)
            if time.monotonic()-self.side_scan_wall>PARAMS['wall_cap_s']:raise TimeoutError('side-scan 15 minute wall budget')
            super().on_frames(now,frames)
            if self.side_scan_phase=='observe' and now>=self.side_scan_after-1e-8:
                obs,rgb=frames[self.robot_id]
                self.side_scan_audit['frames'].append(dict(t=now,pan=self.servo[6],
                    frame_id=obs['frame_id'],image_sha256=obs['sha256'],
                    commanded_servo=dict(self.servo),**orange_candidates(rgb)))

        def step(self,now):
            if self.side_scan_option=='off':return super().step(now)
            rid=self.robot_id
            if self.side_scan_done:return [(rid,dict(kind='hold'))]
            if self.side_scan_phase is None:
                actions=super().step(now)
                moving=[a for _,a in actions if a['kind'] in ('drive','mecanum') and a.get('left',0)]
                if not moving:return actions
                self.side_scan_audit['trigger']=dict(t=now,withheld=copy.deepcopy(actions),state=self.state)
                # No proposed lateral command crosses the host boundary.
                self.cal_until=None;self.cal_settled_at=now
                self.side_scan_restore=dict(self.servo)
                sides=PARAMS['side_pans'] if moving[0]['left']>0 else list(reversed(PARAMS['side_pans']))
                self.side_scan_queue=[{**LOOK_P20,6:p} for p in [1500,*sides,1500]]
                self.side_scan_phase='next'
            if self.side_scan_phase=='observe':
                if now<self.side_scan_after+PARAMS['observe_s']-1e-8:return []
                self.side_scan_phase='next'
            if self.side_scan_queue:
                target=self.side_scan_queue.pop(0)
                self.side_scan_phase='observe';self.side_scan_after=now+PARAMS['arm_settle_s']
                return [(rid,dict(kind='hold'))]+arm_actions(rid,target)
            self.side_scan_done=True;self.side_scan_audit['completed_t']=now
            return [(rid,dict(kind='hold'))]

        def record(self):
            value=super().record()
            if self.side_scan_option!='off':value['side_scan']=copy.deepcopy(self.side_scan_audit)
            return value
    return Runtime
