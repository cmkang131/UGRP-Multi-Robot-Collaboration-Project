"""Opt-in, colour-specific in-hand visual evidence during the existing lift.

Visual grasp verification observes the hand, not disappearance from a clipped
floor ROI (Nair et al. 2020; Amargant et al. 2025). Their learned classifiers
are NOT reproduced: S2 forbids model calls. This explicit DEV adaptation uses
the existing cyan segmentation and a two-pose persistence test. It reports only
PROBABLE_HELD; issued motion does not prove motion, contact, or holding force.
"""
import copy
import numpy as np
from harness.zone_solo_cyan_real_site import Runtime as Previous
from harness.zone_solo_cyan_scene_runtime import SceneCheck as BaseCheck
from harness.zone_solo_cyan_scene_change import decode, cyan, lens_valid
from harness import zone_solo_cyan_v106 as old

OPTION = 'inhand_rgb_v1'
PROBABLE = 'probable_held_inhand_rgb'
CONFIG = dict(frames_per_pose=9, min_hits=8, min_cyan_px=90,
              settle_s=.45, min_mask_iou=.90, max_centroid_shift_px=12.)
VIEWS = {'via110': old.high.VIA_110, 'high': old.high.HIGH}


class Evidence:
    """Only RGB and own issued commands enter this accumulator."""
    def __init__(self):
        self.samples = {k: [] for k in VIEWS}
        self.masks = {k: [] for k in VIEWS}
        self.seen = set()
        self.view = None
        self.since = None
        self.disarmed = None

    def command(self, action):
        if action['kind'] == 'mecanum' and any(action.get(k, 0) != 0 for k in ('forward','left','turn')):
            self.disarmed = 'base_motion_during_check'
        if action['kind'] == 'arm' and action['servo_id'] == 1 and action['pulse'] != 1500:
            self.disarmed = 'gripper_command_changed'

    def add(self, obs, servo, now, robot_id):
        view = next((k for k,p in VIEWS.items() if all(servo.get(s)==v for s,v in p.items())), None)
        if servo.get(1) != 1500:
            self.disarmed = 'gripper_not_commanded_closed'
        if view != self.view:
            self.view, self.since = view, now
        if (view is None or self.disarmed or now-self.since < CONFIG['settle_s']
                or len(self.samples[view]) >= CONFIG['frames_per_pose']):
            return
        key = (obs['frame_id'], obs['sim_time'])
        if key in self.seen or obs['frame_id'] in {x[0] for x in self.seen}:
            return
        # No stale, malformed, foreign-camera, or digest-mismatched observation.
        verdict, quality = old.frame_gate.gate().assess(obs, robot_id, now, ob=False)
        if (verdict not in (old.frame_gate.VALID, old.frame_gate.CONTENT_ONLY)
                or quality is None or quality['dark_fraction'] >= .25
                or obs['sim_time'] < self.since+CONFIG['settle_s']-1e-8):
            return
        try:
            mask = cyan(decode(obs)) & lens_valid()
        except (ValueError, KeyError):
            return
        self.seen.add(key)
        ys,xs = np.nonzero(mask)
        row = dict(frame_id=obs['frame_id'],t=obs['sim_time'],sha256=obs['sha256'],
                   area_px=int(mask.sum()),hit=int(mask.sum())>=CONFIG['min_cyan_px'],
                   centroid_xy=[float(xs.mean()),float(ys.mean())] if len(xs) else None,
                   bbox_xyxy=[int(xs.min()),int(ys.min()),int(xs.max()),int(ys.max())] if len(xs) else None,
                   frame_gate=verdict,commanded_servo=dict(servo))
        self.samples[view].append(row)
        self.masks[view].append(mask)

    def result(self):
        hits={k:sum(s['hit'] for s in rows) for k,rows in self.samples.items()}
        complete=all(len(rows)==CONFIG['frames_per_pose'] for rows in self.samples.values())
        iou=shift=None
        if complete and all(hits[k]>=CONFIG['min_hits'] for k in VIEWS):
            masks=[np.sum(self.masks[k],axis=0)>=CONFIG['min_hits'] for k in VIEWS]
            a,b=masks;union=int((a|b).sum())
            if min(int(a.sum()),int(b.sum()))>=CONFIG['min_cyan_px']:
                iou=float((a&b).sum()/union)
                shift=float(np.linalg.norm(np.array(np.nonzero(a)).mean(1)-np.array(np.nonzero(b)).mean(1)))
        supported=(not self.disarmed and iou is not None and iou>=CONFIG['min_mask_iou']
                   and shift<=CONFIG['max_centroid_shift_px'])
        return dict(option=OPTION,status=PROBABLE if supported else 'unknown',
            reason='persistent_cyan_across_commanded_lift_views' if supported else
                self.disarmed or 'inhand_cyan_not_observable_or_not_persistent',
            samples=copy.deepcopy(self.samples),hits=hits,complete=complete,
            mask_iou=iou,centroid_shift_px=shift,config=dict(CONFIG),
            physical_success=None,claim='PROBABLE_HELD visual evidence only; not force/contact proof',
            limits='partial visibility allowed; command motion unmeasured; no negative hold inference from missing cyan')


class InhandCheck(BaseCheck):
    def __init__(self):
        super().__init__()
        self.evidence=Evidence()
        self.pregrasp=None

    def remember(self,r,now):
        # Keep the original-site failure visible; never label it as a comparison.
        self.pregrasp=dict(t=now,frame_id=r.last_obs['frame_id'],sha256=r.last_obs['sha256'],
            cyan_area_px=int(cyan(decode(r.last_obs)).sum()),source='own pregrasp RGB')
        r.event('cyan_inhand_reference',now,**{k:v for k,v in self.pregrasp.items() if k!='t'})

    def observe_carry(self,r,now):
        if r.state=='lift' and not self.checks:
            self.evidence.add(r.last_obs,r.servo,now,r.robot_id)

    def control(self,r,now,idle,base):
        if (r.state!='lift' or not idle or r.terminal
                or now-r.started_at>=old.CAP_S or r.pose.provider.failure):
            return base(now,idle)
        if not self.checks:
            report=self.evidence.result()
            if self.pregrasp is None or not r.receipt:
                report.update(status='unknown',reason='missing_pregrasp_or_close_command')
            self.visual_status=report['status']
            report.update(before=copy.deepcopy(self.pregrasp),attempt=1,
                          pickup_site_status='not_evaluated_inhand_selected')
            self.checks.append(report)
            r.event('cyan_inhand_grasp_check',now,**report)
            if self.visual_status!='probable_held_inhand_rgb':
                r.soft('GRASP_INHAND_UNCONFIRMED',now)
                self.notify(r,now,'GRASP_INHAND_UNCONFIRMED','손 안의 cyan 시각 근거가 부족합니다.',report)
        # DEV conservative unknown is logged; independent probe gate stays false.
        return base(now,idle)

    def record(self):
        return {**super().record(),'profile':OPTION,'hold_check':OPTION,
                'pickup_site_status':'not_evaluated_inhand_selected',
                'config':dict(CONFIG),'evidence':self.evidence.result()}


class Runtime(Previous):
    def __init__(self,*args,hold_check='off',**kwargs):
        if hold_check not in ('off',OPTION):raise ValueError('unsupported hold_check')
        if hold_check!='off' and kwargs.get('grasp_check')!='pickup_site_v1':
            raise ValueError('inhand check requires explicit pickup_site_v1 extension')
        super().__init__(*args,**kwargs)
        self.hold_check=hold_check
        if hold_check!='off':self.scene_check=InhandCheck()

    def on_command(self,rid,now,action):
        if self.hold_check!='off' and self.state=='lift':
            self.scene_check.evidence.command(action)
        return super().on_command(rid,now,action)

    def record(self):
        out=super().record()
        if self.hold_check!='off':
            out['hold_check']=dict(option=OPTION,claim='PROBABLE_HELD only',
                effective_verifier=OPTION,pickup_site_comparison=False)
        return out
