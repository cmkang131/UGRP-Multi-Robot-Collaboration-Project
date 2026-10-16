"""Opt-in REAL stopped pre-grasp reference, then blind hover/descent.

physical_state_machine_reference.py:250-254,4740-4758,4796-4832:
settle .45 s, >=4 hits among <=9 fresh snapshots before moving the arm;
hover does not need visual support. Existing S2 descent/close limits remain.
No simulator state or evaluation inputs. Default off delegates byte-for-byte.
"""
import copy
from harness.zone_solo_cyan_align_pulse import Runtime as Previous
from harness import zone_solo_cyan_v106 as old
from harness.zone_solo_cyan_scene_change import decode, cyan

OPTION = 'real_pregrasp_v1'
SETTLE_S, SAMPLE_S, MAX_SAMPLES, MIN_HITS, MIN_AREA = .45, .025, 9, 4, 500


class Runtime(Previous):
    def __init__(self, *args, hover_check='off', pregrasp_policy='off', **kwargs):
        if hover_check not in ('off', OPTION):
            raise ValueError('unsupported hover_check')
        if pregrasp_policy not in ('off','log_only_v1') or (pregrasp_policy!='off' and hover_check!=OPTION):
            raise ValueError('pregrasp policy requires explicit real pregrasp path')
        super().__init__(*args, **kwargs)
        self.hover_check = hover_check
        self.pregrasp_policy = pregrasp_policy
        self.pending_hover = None
        self.pregrasp = None
        self.pregrasp_history = []

    def queue(self, target, now, *, duration=1., settle=.6):
        if (self.hover_check != 'off' and self.state == 'align'
                and target == {**old.grasp_postures()[0], 1: 2000}):
            self.pending_hover = (copy.deepcopy(target), duration, settle)
            return
        return super().queue(target, now, duration=duration, settle=settle)

    def set_state(self, state, now):
        if self.hover_check != 'off' and state == 'hover' and self.pending_hover:
            hover = old.grasp_postures()[0]
            self.pregrasp = dict(start_s=now, servo=copy.deepcopy(self.servo), samples=[],
                last_sample_s=-1., last_frame=None, accepted=False, disarmed=None,
                guard=dict(pan=hover[6], envelope=old.blind._envelope(hover,[self.servo])))
            self.pregrasp_history.append(self.pregrasp)
            state = 'real_pregrasp'
        return super().set_state(state, now)

    def on_command(self, rid, now, action):
        if self.hover_check != 'off' and self.pregrasp and self.state in ('real_pregrasp','hover'):
            code = old.blind.off_window(action, self.servo, self.pregrasp['guard'])
            if code:
                self.pregrasp['disarmed'] = code
        return super().on_command(rid, now, action)

    def _control(self, now, idle):
        if (self.hover_check == 'off' or self.state not in ('real_pregrasp','hover')
                or self.terminal or now-self.started_at >= old.CAP_S or self.pose.provider.failure or not idle):
            return super()._control(now,idle)
        ref = self.pregrasp
        if ref is None or ref['disarmed'] or now-self.target_t > 30.:
            return self.fail('REAL_PREGRASP_ANCHOR_INVALID',now)
        if self.state == 'real_pregrasp':
            if self.servo != ref['servo']:
                return self.fail('REAL_PREGRASP_VIEW_CHANGED',now)
            obs = self.last_obs
            after = max(ref['start_s']+SETTLE_S,ref['last_sample_s']+SAMPLE_S)
            if (obs is None or obs['frame_id'] == ref['last_frame'] or obs['sim_time'] < after-1e-8):
                return [{'kind':'hold'}]
            verdict,_ = old.frame_gate.gate().assess(obs,self.robot_id,now,ob=False)
            fits = self.detections() if verdict == old.frame_gate.VALID else []
            area = int(cyan(decode(obs)).sum()) if verdict == old.frame_gate.VALID else 0
            supported = (len(fits)==1 and area >= MIN_AREA and
                abs(fits[0]['estimated_box_center_base_m'][0]-old.GRASP_RADIUS_M) <= .003 and
                abs(fits[0]['estimated_box_center_base_m'][1]) <= .003)
            row=dict(t=obs['sim_time'],frame_id=obs['frame_id'],sha256=obs['sha256'],
                area_px=area,supported=bool(supported))
            ref['samples'].append(row);ref['last_frame']=obs['frame_id'];ref['last_sample_s']=obs['sim_time']
            hits=sum(s['supported'] for s in ref['samples'])
            self.event('cyan_real_pregrasp_sample',now,**{k:v for k,v in row.items() if k!='t'},hits=hits)
            if hits >= MIN_HITS:
                ref['accepted']=True;ref['confirmed_at_s']=now;ref['evidence']=copy.deepcopy(row)
                self.target=list(fits[0]['estimated_box_center_base_m'][:2]);self.target_t=now
                # Preserve the separate pickup-site check and its clipped-ROI refusal.
                if self.scene_check is not None:
                    self.scene_check.remember(self,now)
                target,duration,settle=self.pending_hover;self.pending_hover=None
                self.queue(target,now,duration=duration,settle=settle)
                self.set_state('hover',now)
            elif hits+MAX_SAMPLES-len(ref['samples']) < MIN_HITS:
                if self.pregrasp_policy=='log_only_v1':
                    # User DEV rule: preserve the last approach anchor, not a
                    # fabricated visual success or a renewed observation time.
                    self.soft('REAL_PREGRASP_UNCONFIRMED',now)
                    ref['dev_light_blind']=True;ref['evidence']=copy.deepcopy(row)
                    ref['anchor_observed_at_s']=self.target_t
                    if self.scene_check is not None:self.scene_check.remember(self,now)
                    target,duration,settle=self.pending_hover;self.pending_hover=None
                    self.queue(target,now,duration=duration,settle=settle)
                    self.set_state('hover',now)
                    return [{'kind':'hold'}]
                return self.fail('REAL_PREGRASP_UNCONFIRMED',now)
            return [{'kind':'hold'}]
        hover,path=old.grasp_postures()
        authorized = ref['accepted'] or (self.pregrasp_policy=='log_only_v1' and ref.get('dev_light_blind'))
        if not authorized or not old.blind.at_posture(self.servo,hover) or self.servo.get(1)!=2000:
            return self.fail('REAL_PREGRASP_ANCHOR_INVALID',now)
        # Transfer the earlier RGB anchor to the unchanged command envelope.
        # This timestamp starts command timing; it is NOT a fresh visual receipt.
        evidence=ref['evidence']
        self.blind.window=dict(confirmed_at_s=now,frame_id=evidence['frame_id'],sha256=evidence['sha256'],
            visual_confirmed_at_s=ref.get('confirmed_at_s'),source=OPTION,pan=hover[6],
            envelope=old.blind._envelope(hover,path),limits=old.blind.limits())
        if ref.get('dev_light_blind'):
            self.blind.window.update(source='dev_pregrasp_log_only_v1',visual_confirmed=False,
                anchor_observed_at_s=ref['anchor_observed_at_s'])
        self.blind.disarmed=None
        self.event('cyan_real_hover_transfer',now,visual_frame_id=evidence['frame_id'],
            visual_confirmed_at_s=ref.get('confirmed_at_s'),hover_visual_confirmation=False,physical_success=None)
        for pose in path:
            self.queue(pose,now,duration=old.blind.DESCENT_STEP_S,settle=0.)
        self.arm.until += old.blind.HOVER_SETTLE_S
        self.set_state('blind_descent',now)
        return [{'kind':'hold'}]

    def record(self):
        out=super().record()
        if self.hover_check!='off':
            out['hover_check']=dict(option=self.hover_check,settle_s=SETTLE_S,max_samples=MAX_SAMPLES,
                min_hits=MIN_HITS,min_area_px=MIN_AREA,references=copy.deepcopy(self.pregrasp_history),
                physical_success=None,hover_visual_confirmation=False)
            if self.pregrasp_policy!='off':out['hover_check']['pregrasp_policy']=self.pregrasp_policy
        return out
