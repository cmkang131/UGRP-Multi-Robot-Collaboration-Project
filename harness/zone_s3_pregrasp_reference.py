"""Own-RGB standoff reference, then commanded hover and bounded blind close.

The S2 REAL pre-grasp pattern: a hidden target at hover is not a new visual
measurement. Keep the original RGB anchor/time, fixed path/age bounds and
mutual close GO. No global pose is substituted for the beam-relative fit.
"""
import copy
import math
from harness import zone_pair_highpose_blind_close as blind
from harness import zone_pair_beam_track as resting
from harness.zone_pair_highpose_frame_gate import controller_gate


def attach(ctl,audit):
    track=ctl.blind_track
    queue,descend,command,old_blind=ctl._queue_open_descent,ctl._pregrasp_descend,track.command,track._blind
    references=[]
    ctl.s3_pregrasp_references=references

    def reacquire(now,reason,obs=None):
        h=getattr(ctl,'refix_hover',None)
        if h and h.get('go_s') is not None:
            return ctl.fail('PREGRASP_REFERENCE_INVALID_AFTER_GO',now)
        if obs is not None:
            withdraw=getattr(ctl,'hover_barrier_withdraw',None)
            if withdraw is not None:withdraw(now,obs,reason)
        audit.note(ctl.port.own,now,'PREGRASP_REFERENCE_UNAVAILABLE','pair.pregrasp',reason=reason)
        # Missing evidence never becomes a successful visual receipt. Revisit
        # the existing visible alignment view without ending the DEV mission.
        return ctl._light_resume_align(now)

    def queue_open(now):
        b=track.beam
        if (b is None or track.segment!=ctl.seg
                or not 0<=now-b['anchor_time_s']<=resting.MAX_AGE_S
                or b.get('anchor_frame_id') is None or not b.get('anchor_sha256')):
            return reacquire(now,'missing_or_expired_standoff')
        reference=dict(segment=ctl.seg,visual_confirmed_at_s=b['anchor_time_s'],
            frame_id=b['anchor_frame_id'],sha256=b['anchor_sha256'],
            beam=copy.deepcopy(b),issued_start=dict(ctl.port.own.servo),disarmed=None)
        result=queue(now)
        if ctl.state=='pregrasp_descend' and ctl.blind_phase=='hover':
            reference['command_envelope']=dict(pan=ctl.hover[6],
                envelope=blind._envelope(ctl.hover,[reference['issued_start'],*ctl.blind_path]))
            ctl.s3_pregrasp_reference=reference
            references.append(reference)
            ctl.log(ctl.rid,'s3_pregrasp_reference',now,
                visual_confirmed_at_s=reference['visual_confirmed_at_s'],
                frame_id=reference['frame_id'],sha256=reference['sha256'],
                hover_visual_confirmation=False,source='existing own RGB standoff fit')
        return result

    def issued(row,servo):
        ref=getattr(ctl,'s3_pregrasp_reference',None)
        if ref is not None and ref['disarmed'] is None and ctl.state=='pregrasp_descend':
            code=blind.off_window(row,servo,ref['command_envelope'])
            if code is not None:ref['disarmed']=dict(code=code,t=row['t'])
        return command(row,servo)

    def at_hover(now,idle):
        if getattr(ctl,'blind_phase',None)!='hover':return descend(now,idle)
        if not idle:return
        ref=getattr(ctl,'s3_pregrasp_reference',None)
        obs=ctl.look(now);servo=dict(ctl.port.own.servo)
        valid=(ref is not None and ref['disarmed'] is None and ref['segment']==ctl.seg
            and 0<=now-ref['visual_confirmed_at_s']<=resting.MAX_AGE_S
            and blind.at_posture(servo,ctl.hover) and servo.get(1)==blind.OPEN_PWM
            and controller_gate(ctl)(obs,ctl.rid,now))
        if not valid:
            return reacquire(now,'standoff_or_command_window_invalid',obs)
        if obs['frame_id']!=ctl.blind_hover_last_frame:ctl.blind_hover_streak+=1
        ctl.blind_hover_last_frame=obs['frame_id']
        if ctl.blind_hover_streak<blind.HOVER_CONFIRM_FRAMES:return
        gate=getattr(ctl,'hover_barrier_gate',None)
        if gate is not None and not gate(now,obs):return
        h,g=blind._tool(ctl.hover),blind._tool(ctl.blind_path[-1])
        track.blind_window=dict(profile='own_rgb_pregrasp_reference_v1',segment=ctl.seg,
            confirmed_at_s=float(now),confirm_tick_s=now,frame_id=ref['frame_id'],sha256=ref['sha256'],
            visual_confirmed_at_s=ref['visual_confirmed_at_s'],hover_visual_confirmation=False,
            hover={k:ctl.hover[k] for k in blind.JOINTS},
            grasp={k:ctl.blind_path[-1][k] for k in blind.JOINTS},
            envelope=blind._envelope(ctl.hover,ctl.blind_path),pan=ctl.hover[6],
            drop_m=h.z_m-g.z_m,xy_m=math.hypot(h.x_m-g.x_m,h.y_m-g.y_m),
            lateral_m=ref['beam']['grip_base_m'][1],beam_at_confirm=copy.deepcopy(ref['beam']),
            limits=blind.limits(),disarmed=None)
        ref['command_window_started_s']=now
        for pose in ctl.blind_path:ctl.arm.queue(pose,now,duration=blind.DESCENT_STEP_S,settle=0.)
        ctl.arm.until+=blind.FINAL_DESCENT_SETTLE_S
        ctl.blind_phase='descend'
        ctl.log(ctl.rid,'s3_blind_descent_queued',now,steps=len(ctl.blind_path),
            until_s=ctl.arm.until,visual_frame_id=ref['frame_id'],
            visual_confirmed_at_s=ref['visual_confirmed_at_s'],hover_visual_confirmation=False)

    def predicted(now,segment):
        code,value=old_blind(now,segment)
        if value is not None and track.blind_window.get('profile')=='own_rgb_pregrasp_reference_v1':
            value={**value,'evidence':'blind_after_pregrasp_reference',
                'visual_confirmed_at_s':track.blind_window['visual_confirmed_at_s'],
                'hover_visual_confirmation':False}
        return code,value
    ctl._queue_open_descent,ctl._pregrasp_descend=queue_open,at_hover
    track.command,track._blind=issued,predicted
