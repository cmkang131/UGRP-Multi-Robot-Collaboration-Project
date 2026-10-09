"""Optional REAL repeat-pose whole-frame floor check, not a verified hold.

physical_state_machine_reference.py:4643-4793: stopped reference pose, .45 s
settle, <=1 floor hit in 9 fresh snapshots. The existing calibrated fisheye
floor-cuboid detector replaces the REAL SDK pinhole floor-ray implementation;
no apparent-size fallback, extra ROI padding, ECC, GT, or camera changes.
"""
import copy
import cv2
import numpy as np
from harness.zone_solo_cyan_real_hover import Runtime as Previous
from harness import zone_solo_cyan_scene_runtime as scene
from harness.zone_solo_cyan_scene_change import decode, cyan, lens_valid
from harness.zone_final_pair_binding import bind

OPTION = 'real_floor_v1'
CONFIG = {**scene.CONFIG, 'frames': 9, 'settle_s': .45}
PROBABLE = 'probable_held_floor_clear'


class FloorMemory:
    def __init__(self, obs, bbox, center, servo, vision):
        self.before = decode(obs)
        self.vision = vision
        self.servo = {k: servo[k] for k in (3,4,5,6)}
        self.bbox = tuple(map(int,bbox))
        x,y,w,h = self.bbox
        if min(w,h)<=0 or x<1 or y<1 or x+w>=639 or y+h>=479:
            raise ValueError('real floor reference must be a complete target')
        mask=cyan(self.before)
        support=np.zeros(mask.shape,bool);support[y:y+h,x:x+w]=mask[y:y+h,x:x+w]
        edge=~cv2.erode(lens_valid().astype(np.uint8),np.ones((3,3),np.uint8)).astype(bool)
        if np.any(support&edge) or int(support.sum())<scene.CONFIG['min_cyan_px']:
            raise ValueError('real floor reference is clipped or unsupported')
        self.record=dict(profile=OPTION,before_sha256=obs['sha256'],before_frame_id=obs['frame_id'],
            before_t=obs['sim_time'],before_cyan_area_px=int(support.sum()),
            before_full_cyan_area_px=int(mask.sum()),pixel_bbox=list(bbox),
            center_base_m_from_own_rgb=list(center),view_commands=dict(self.servo),
            comparison='whole_frame_floor_cuboid; no expanded ROI/ECC',
            claim='PROBABLE_HELD only; not positive grasp proof',physical_success=None)

    def compare(self, obs):
        image=decode(obs);mask=cyan(image);x,y,w,h=self.bbox
        row={**self.record,'after_sha256':obs['sha256'],'after_frame_id':obs['frame_id'],
            'after_t':obs['sim_time'],'after_full_cyan_area_px':int(mask.sum()),
            'after_cyan_area_px':int(mask[y:y+h,x:x+w].sum()),
            'decision':'unknown','physical_success':None}
        # Preserve a basic image-availability guard (the old comparator used
        # gray>30 and >=800 background pixels); a black/lost frame is not clear.
        gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
        if int(((gray>30)&lens_valid()).sum())<800:
            return {**row,'reason':'image_not_observable'}
        fits=[f for f in self.vision.detect(obs,self.servo) if f.get('range_class')=='near']
        row.update(floor_detections=copy.deepcopy(fits),floor_hits=int(bool(fits)),
                   floor_cyan_area_px=sum(float(f['area_px']) for f in fits))
        if fits:
            return {**row,'decision':'present','reason':'floor_compatible_cyan_in_whole_frame'}
        return {**row,'decision':'absent','reason':'no_floor_compatible_cyan_probable_only'}


class SceneCheck(scene.SceneCheck):
    def remember(self,r,now):
        factory=lambda obs,bbox,center,servo:FloorMemory(obs,bbox,center,servo,r.vision)
        return bind(scene.SceneCheck.remember,SiteMemory=factory)(self,r,now)

    def control(self,r,now,idle,base):
        if (self.phase=='observe' and r.state=='lift' and idle and not r.terminal
                and now-r.started_at<scene.old.CAP_S and not r.pose.provider.failure):
            obs=r.last_obs
            if (obs and obs['frame_id'] not in self.seen_frames
                    and obs['sim_time']>max(self.capture_after,self.last_sample_t)):
                self.seen_frames.add(obs['frame_id']);self.last_sample_t=obs['sim_time']
                verdict,quality=scene.old.frame_gate.gate().assess(obs,r.robot_id,now,ob=False)
                moved=any(c['kind']=='mecanum' and any(c.get(k,0)!=0 for k in ('forward','left','turn'))
                    for c in r.commands[self.reference_command_i:])
                same=all(r.servo.get(k)==v for k,v in self.memory.servo.items())
                # A textureless but bright floor is valid colour evidence. Do
                # not use this CONTENT_ONLY exception for localization/control.
                readable=(verdict in (scene.old.frame_gate.VALID,scene.old.frame_gate.CONTENT_ONLY)
                    and quality is not None and quality['dark_fraction']<.25)
                if readable and same and not moved:
                    try:row=self.memory.compare(obs)
                    except ValueError as exc:row=dict(decision='unknown',reason=str(exc))
                else:row=dict(decision='unknown',reason='invalid_image_or_changed_base_or_view')
                row.update(frame_gate=verdict,frame_quality=quality,after_sha256=obs['sha256'])
                self.samples.append(row)
            if len(self.samples)>=CONFIG['frames'] or now-self.capture_after>=30.:
                return self.finish_check(r,now)
            return [{'kind':'hold'}]
        before=self.phase
        out=bind(scene.SceneCheck.control,CONFIG=CONFIG)(self,r,now,idle,base)
        if before=='position_view' and self.phase=='observe':
            self.capture_after=now+CONFIG['settle_s']
        return out

    def finish_check(self,r,now):
        hits=sum(s['decision']=='present' for s in self.samples)
        complete=len(self.samples)==CONFIG['frames'] and all(s['decision'] in ('present','absent') for s in self.samples)
        self.visual_status='failed' if hits>CONFIG['max_present_for_absent'] else PROBABLE if complete else 'unknown'
        report=dict(status=self.visual_status,attempt=self.retries+1,
            before=None if self.memory is None else self.memory.record,
            samples=copy.deepcopy(self.samples),physical_success=None,claim='PROBABLE_HELD only')
        self.checks.append(report);r.event('cyan_scene_grasp_check',now,**report)
        if self.visual_status=='failed':
            if self.retries>=CONFIG['max_retries']:
                return r.fail('CYAN_SCENE_RETRY_EXHAUSTED',now)
            self.retries+=1
            for p,duration,settle in scene.old.high.lower_path():
                r.queue({**p,1:1500},now,duration=duration,settle=settle)
            self.phase='retry_lower'
        else:
            if self.visual_status=='unknown':
                r.soft('GRASP_SCENE_UNCONFIRMED',now)
                self.notify(r,now,'GRASP_SCENE_UNCONFIRMED','원래 관찰 자세의 바닥 확인은 미확인입니다.',report)
            self.restore_high(r,now)
        return [{'kind':'hold'}]

    def record(self):
        return {**super().record(),'site_check':OPTION,'config':dict(CONFIG),
            'claim':'PROBABLE_HELD only; no positive grasp proof'}


class Runtime(Previous):
    def __init__(self,*args,site_check='off',**kwargs):
        if site_check not in ('off',OPTION):raise ValueError('unsupported site_check')
        if site_check!= 'off' and kwargs.get('grasp_check')!='pickup_site_v1':
            raise ValueError('real floor check requires pickup_site_v1')
        super().__init__(*args,**kwargs)
        self.site_check=site_check
        if site_check!='off':self.scene_check=SceneCheck()

    def record(self):
        out=super().record()
        if self.site_check!='off':out['site_check']=dict(option=OPTION,claim='PROBABLE_HELD only')
        return out
