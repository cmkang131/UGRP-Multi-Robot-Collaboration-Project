"""Default-off stopped-base, own-RGB arm alignment (s3fix15 DEV candidate).

Only pixels, issued PWM, fixed calibration and command geometry enter here.
Capture constants are frozen development calibration, not live truth.
"""
import copy
import itertools
import math
from functools import lru_cache
from harness.zone_s3_alignment_ownership import Options, LastVisible, band_vision, install_posture_owner, install_solo_owner, one_step

import numpy as np

from harness import visual_arm_v3 as arm
from harness import visual_arm as sdk
from harness.owncam_pair_beam_v2 import pose_of
from harness.zone_final_pair_vision import GRASP_RADIUS_M, PairVision
from harness.zone_solo_cyan_pulse_cal import action_of
from harness.zone_s3_visual_pose_servo import transform
from harness.zone_s3_settled_servo import SettleGate

OPTION = 'stopped_base_arm_v1'
PARAMS = dict(pair_dx_half_m=.018, cyan_dx_half_m=.0096, yaw_half_rad=.112,
    dy_center_m=-.006, dy_half_m=.003, pan_pwm_min=1300, pan_pwm_max=1700,
    pan_quantum_us=4, pan_move_s=.30, settle_s=.45, fresh_frames=2,
    cyan_radius_m=[.148, .170], cyan_radius_grid_m=.0005,
    radial_filter="IK reachable; vertical path XY deviation <=2mm, descent <=75mm", pair_radius_m=.155,
    camera='fixed v3 mount; commanded yaw composition for local RGB only',
    calibration_source='s3fix14 capture and pulse grid; DEV tuning, not confirmation',
    runtime_gt=False)


def angle(pan):
    return math.radians((pan-sdk.BASE_CENTER)/sdk.PULSE_PER_DEGREE)


def plan(grip, heading, rid):
    x, y = map(float, grip)
    if rid not in ('r1', 'r2', 'r3') or not all(map(math.isfinite, (x, y, heading))):
        raise ValueError('finite own RGB grip and known robot required')
    radius = math.hypot(x-arm.MOUNT_X_M, y)
    if radius <= abs(PARAMS['dy_center_m']):
        raise ValueError('target outside forward arm workspace')
    theta = math.atan2(y, x-arm.MOUNT_X_M)-math.asin(PARAMS['dy_center_m']/radius)
    pan = round((sdk.BASE_CENTER+math.degrees(theta)*sdk.PULSE_PER_DEGREE)/4)*4
    pan = max(1300, min(1700, pan))
    a = angle(pan); c, s = math.cos(a), math.sin(a)
    along, lateral = c*(x-arm.MOUNT_X_M)+s*y, -s*(x-arm.MOUNT_X_M)+c*y
    reach = .155 if rid != 'r3' else min(radial_workspace(), key=lambda r:abs(r-along))
    errors = [along-reach, lateral-PARAMS['dy_center_m'],
              math.atan2(math.sin(heading-a), math.cos(heading-a)) if rid != 'r3' else 0.]
    tol = [PARAMS['pair_dx_half_m'] if rid != 'r3' else PARAMS['cyan_dx_half_m'],
           PARAMS['dy_half_m'], PARAMS['yaw_half_rad']]
    return dict(pan=pan, radius_m=reach, errors=errors, halfwidths=tol,
                ready=all(abs(e) <= t for e, t in zip(errors, tol)))


def postures(p):
    """Public command-space IK only; reject unreachable targets, never clip PWM."""
    from scripts.study_owncam_pair_beam import GRASP_Z_M, HOVER_Z_M
    a = angle(p['pan']); x = arm.MOUNT_X_M+p['radius_m']*math.cos(a)
    y = p['radius_m']*math.sin(a)
    grasp = arm.solve_grip_ik(x, y, GRASP_Z_M, -90.)
    pitch = arm.tool_pose(grasp).pitch_deg
    hover = arm.solve_grip_ik(x, y, HOVER_Z_M, pitch)
    path = [arm.solve_grip_ik(x, y, float(z), pitch)
            for z in np.linspace(HOVER_Z_M, GRASP_Z_M, 8)[1:]]
    for row in [hover, *path]:
        if row[6] != p['pan'] or any(not 500 <= v <= 2500 for v in row.values()):
            raise ValueError('arm command outside registered PWM envelope')
    return hover, path


@lru_cache(maxsize=1)
def radial_workspace():
    """Finite reachable command-space grid; no measured robot/sim state."""
    candidates = []
    for radius in np.arange(.148, .1701, .0005):
        try:
            h, path = postures(dict(pan=1500, radius_m=float(radius)))
        except ValueError:
            continue
        xyz = np.array([arm.forward_grip(p) for p in [h,*path]])
        if (np.max(np.linalg.norm(xyz[:,:2]-xyz[-1,:2],axis=1))<=.002 and
                0 < xyz[0,2]-xyz[-1,2] <= .075):
            candidates.append(float(radius))
    if not candidates:
        raise ValueError('no command-space radial grasp path')
    return tuple(candidates)


def yaw_calibration(calibration, pan):
    """Instance-local kinematic composition about the known arm yaw joint.

    No camera mount fit or live chassis/servo measurement. PF calibration stays
    untouched. Only the inspect posture with a changed commanded pan is added.
    """
    out = copy.deepcopy(calibration)
    inspect = pose_of('inspect')
    key = lambda v: ','.join(str(v[k]) for k in (3, 4, 5, 6))
    source = out['camera_models']['unloaded'][key(inspect)]
    a = angle(pan)-angle(inspect[6]); c, s = math.cos(a), math.sin(a)
    r = np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])
    origin = np.array([arm.MOUNT_X_M, 0., 0.])
    rec = copy.deepcopy(source)
    rec['origin_m'] = (origin+r@(np.asarray(source['origin_m'])-origin)).tolist()
    rec['rotation'] = (r@np.asarray(source['rotation'])).tolist()
    out['camera_models']['unloaded'][key({**inspect, 6: pan})] = rec
    return out


class Servo:
    def __init__(self, rid, profiles, refinements=Options(), planner=None):
        self.refinements = refinements
        self.planner = planner or plan
        self.rid, self.profiles = rid, profiles
        self.gate = SettleGate()
        self.last_frame = None
        self.streak = 0
        self.chosen = None
        self.audit = []
        self.pool = [p for p in profiles.values() if not p['loaded'] and
                     p['axis'] in ('forward', 'turn') and p['duration_s'] == .1
                     and abs(p['u']) == .35]
        if len(self.pool) != 4:
            raise ValueError('four existing 35/100ms base profiles required')

    def proposal(self, grip, heading):
        if self.refinements.coarse_axis_ownership:
            return one_step(self,grip,heading,self.planner)
        p = self.planner(grip, heading, self.rid)
        if p['ready']:
            return None, p
        def score(g, h):
            q = self.planner(g, h, self.rid)
            return sum(max(abs(e)/t-1., 0.)**2 for e, t in zip(q['errors'], q['halfwidths']))
        # Receding three-pulse enumeration resolves coupled yaw/position geometry;
        # issue just the first existing single-axis pulse, then settle/reobserve.
        before = score(grip, heading); candidates = []
        for length in (1, 2, 3):
            for seq in itertools.product(range(4), repeat=length):
                g, h = np.asarray(grip), heading
                for index in seq:
                    g, h = transform(g, h, self.pool[index]['mean_delta'])
                value = score(g, h)
                if value < before-1e-9:
                    candidates.append((value, length, seq))
        if not candidates:
            return None, p
        _, _, seq = min(candidates)
        return self.pool[seq[0]], p

    def observe(self, now, obs, servo, grip, heading):
        if not self.gate.ready(now, obs) or obs['frame_id'] == self.last_frame:
            return 'wait', None
        self.last_frame = obs['frame_id']
        profile, p = self.proposal(grip, heading)
        row = dict(t=now, frame_id=obs['frame_id'], sha256=obs.get('sha256'),
                   grip=list(grip), heading=heading, plan=copy.deepcopy(p))
        self.audit.append(row)
        if not p['ready']:
            self.streak = 0
            row['phase'] = 'coarse' if profile else 'coarse_unresolved'
            if profile:
                self.gate.issued(now, profile, obs)
                row['issued'] = action_of(profile)
                return 'base', row['issued']
            return 'wait', None
        a = angle(servo[6]); c, s = math.cos(a), math.sin(a)
        current = copy.deepcopy(p)
        current['pan'] = servo[6]
        current['errors'] = [c*(grip[0]-arm.MOUNT_X_M)+s*grip[1]-p['radius_m'],
            -s*(grip[0]-arm.MOUNT_X_M)+c*grip[1]-PARAMS['dy_center_m'],
            math.atan2(math.sin(heading-a), math.cos(heading-a)) if self.rid!='r3' else 0.]
        current['ready'] = all(abs(e)<=t for e,t in zip(current['errors'],current['halfwidths']))
        # Actual issued PWM match, then a NEW settled own frame, is mandatory.
        if not current['ready']:
            self.streak = 0
            self.gate.until = now+PARAMS['pan_move_s']+PARAMS['settle_s']
            self.gate.frame_id = obs['frame_id']
            row['phase'] = 'fine_pan'
            return 'pan', p['pan']
        self.streak += 1
        self.chosen = current
        row['plan'] = copy.deepcopy(current)
        row.update(phase='fine_confirm', streak=self.streak)
        return ('ready', current) if self.streak >= 2 else ('wait', None)


def attach_endpoint(ep, option='off', *, refinements=Options(), planner=None):
    if option == 'off':
        return ep
    if option != OPTION:
        raise ValueError('unknown coarse/fine option')
    from harness import zone_pair_highpose_blind_close as blind
    from harness.zone_pair_highpose_frame_gate import controller_gate
    ctl = ep.controller; own = ep.own.pose.localizer
    servo = Servo(ep.own.robot_id, own.pulse_profiles, refinements, planner)
    calibration = ep.vision.calibration
    visions = {}
    def vision(pan):
        if pan not in visions:
            visions[pan] = PairVision(yaw_calibration(calibration, pan))
            if refinements.band_border:band_vision(visions[pan])
        return visions[pan]
    track = ctl.blind_track
    memory = LastVisible(own.pulse_profiles)
    issued = track.command
    def command(row,pulses):
        if refinements.endpoint_memory and ctl.state=='align':memory.command(row,pulses)
        return issued(row,pulses)
    if refinements.endpoint_memory:track.command=command
    # Existing track quality/age estimator, through the command-derived view.
    def standoff(obs, pulses):
        return vision(pulses[6]).beam_track()._standoff(obs, pulses)
    track._standoff = standoff
    original_estimate = track.estimate
    def estimate(now, obs, pulses, segment):
        if (servo.chosen and track.blind_window is not None and
                blind.at_posture(pulses, ctl.grasp_pose)):
            track.advance(now)
            track.blind_code, value = track._blind(now, segment)
            return value
        return original_estimate(now, obs, pulses, segment)
    track.estimate = estimate

    def align(now, idle):
        if not idle or now < ctl.next_look:
            return
        obs = ctl.look(now)
        if not controller_gate(ctl)(obs, ctl.rid, now) or not servo.gate.ready(now, obs):
            return
        pulses = dict(ep.own.servo)
        inspect = {**pose_of('inspect'), 6: pulses[6]}
        if any(pulses[k] != v for k, v in inspect.items()):
            ctl.arm.queue(inspect, now, duration=.4, settle=.45)
            ctl.look_name = 'inspect'
            return
        ctl.next_look = now+.1
        beam = vision(pulses[6]).observe_beam(obs['image'], pulses)
        ctl.log(ctl.rid, 'beam_obs', now, posture='inspect', **{k:v for k,v in beam.items() if k!='provenance'})
        predicted = False
        if refinements.endpoint_memory and beam.get('visible') and beam.get('end_visible'):
            measured=standoff(obs,pulses)
            if measured is not None:
                memory.capture(measured,obs,pulses,ctl.seg)
        if not beam.get('visible') or not beam.get('end_visible'):
            retained=memory.estimate(now,ctl.seg) if refinements.endpoint_memory and beam.get('reason') in ('BAND_CLIPPED','END_CLIPPED') else None
            if retained is None:
                servo.streak = 0
                return ctl.port.hold(now)
            beam={**beam,**retained};predicted=True
            ctl.log(ctl.rid,'last_visible_approach',now,anchor_frame_id=retained['anchor_frame_id'],
                anchor_time_s=retained['anchor_time_s'],pulses=memory.pulses,grip_base_m=retained['grip_base_m'])
        phase, value = servo.observe(now, obs, pulses, beam['grip_base_m'], beam['axis_heading_rad'])
        ctl.log(ctl.rid, 'coarse_fine', now, phase=phase, detail=copy.deepcopy(servo.audit[-1]) if servo.audit else {})
        if phase == 'base':
            return ctl.drive({k:v for k,v in value.items() if k not in ('kind','duration_s')} | {'duration':value['duration_s']}, now)
        if phase == 'pan':
            ctl.port.hold(now)
            return ctl.arm.queue({6:value}, now, duration=.3, settle=.45)
        if phase != 'ready':
            return ctl.port.hold(now)
        # ctl.look may already have accepted this exact RGB into the track.
        # A duplicate read is deliberately refused by observe_standoff; reuse
        # that same validated anchor without renewing time or counting a frame.
        anchored = (track.beam is not None and track.segment == ctl.seg and
            track.beam.get('anchor_frame_id') == obs['frame_id'] and
            track.beam.get('anchor_sha256') == obs['sha256'] and
            track.beam.get('anchor_time_s') == obs['sim_time'])
        if predicted:
            # Keep original visual provenance and uncertainty; no fake new frame.
            track.beam=memory.estimate(now,ctl.seg)
            track.segment=ctl.seg
            track.t=now
            anchored=track.beam is not None
        if not anchored and not track.observe_standoff(obs, pulses, ctl.seg):
            servo.streak = 0
            return ctl.port.hold(now)
        peer_holding = any(v['state'] in ('ready','lift','carry')
            for v in ctl.status[0].partner_view(ctl.rid,now).values())
        if ctl.beam_grasp_confirmed or ep.own.servo.get(1)!=2000 or peer_holding:
            return ctl.fail('PREGRASP_RELOOK_WHILE_CLOSED',now)
        ctl.port.hold(now)
        ctl.vo_pose = None
        ctl.grip_base = list(beam['grip_base_m'])
        ctl.claims['aligned'] = dict(grip_base_m=ctl.grip_base, errors=servo.chosen['errors'],
            sim_time=now, option=OPTION, frame_id=obs['frame_id'])
        if refinements.enabled:
            ctl.claims['aligned'].update(frame_id=track.beam['anchor_frame_id'],
                evidence='predicted_last_visible' if predicted else 'own_rgb')
        # Existing DEV rule: PF budgets log only; the own-RGB reference above
        # remains real. Mutual hover/close/lift GO barriers are not bypassed.
        if not ctl._grasp_pose_ready(now):
            ep.log(ctl.rid, 'dev_light_would_stop', now, code='PREGRASP_POSE_UNCERTAIN', source=OPTION)
        ctl.pregrasp_done = True
        r = ep.own.last_report
        ctl.grasp_estimate = [r.x_m, r.y_m, r.yaw_rad]
        return queue_open(now)

    def queue_open(now):
        if servo.chosen is None or track.beam is None:
            return ctl._light_resume_align(now)
        ctl.high_raising, ctl.high_ready = False, False
        ctl.grip_epoch = getattr(ctl, 'grip_epoch', 0)+1
        ctl.pose_anchors = {}
        ctl.transit = None
        ctl.floor_return_verified = False
        ctl.pregrasp_started_at = now
        ctl.beam_grasp_receipt = None
        ctl.hover, ctl.blind_path = postures(servo.chosen)
        ctl.grasp_pose = ctl.blind_path[-1]
        reference = dict(segment=ctl.seg, visual_confirmed_at_s=track.beam['anchor_time_s'],
            frame_id=track.beam['anchor_frame_id'], sha256=track.beam['anchor_sha256'],
            beam=copy.deepcopy(track.beam), issued_start=dict(ep.own.servo), disarmed=None)
        reference['command_envelope'] = dict(pan=ctl.hover[6], envelope=blind._envelope(
            ctl.hover, [reference['issued_start'], *ctl.blind_path]))
        ctl.s3_pregrasp_reference = reference
        ctl.s3_pregrasp_references.append(reference)
        ctl.arm.queue({**ctl.hover, 1:2000}, now, duration=1.)
        ctl.arm.until += blind.HOVER_SETTLE_S
        ctl.blind_phase, ctl.blind_hover_started = 'hover', None
        ctl.blind_hover_streak, ctl.blind_hover_last_frame = 0, None
        ctl.set('pregrasp_descend', now, blind_phase='hover', profile=OPTION)
        ctl.log(ctl.rid, 'coarse_fine_aligned', now, frame_id=reference['frame_id'])
        ctl.log(ctl.rid, 'coarse_fine_grasp_target', now, plan=copy.deepcopy(servo.chosen),
                hover=ctl.hover, path=ctl.blind_path, source='own RGB + frozen capture offset')
    ctl._align, ctl._queue_open_descent = align, queue_open
    ctl.s3_coarse_fine = servo
    if refinements.enabled:
        previous_set=ctl.set
        def set_state(state,now,**detail):
            if state=='align' and ctl.state!='align':
                memory.anchor=None
                servo.streak=0;servo.chosen=None;servo.gate=SettleGate()
            return previous_set(state,now,**detail)
        ctl.set=set_state
    if refinements.posture_ownership:install_posture_owner(ctl)
    return ep


def attach_solo(own, option='off', *, refinements=Options()):
    if option == 'off':
        return own
    if option != OPTION:
        raise ValueError('unknown coarse/fine option')
    from harness import zone_pair_highpose_blind_close as blind
    from harness.zone_solo_cyan_vision_v106 import CyanVision
    from harness.zone_pair_highpose_frame_gate import gate
    servo = Servo('r3', own.pulse_profiles, refinements)
    control, record = own._control, own.record
    if refinements.coarse_axis_ownership:
        install_solo_owner(own,servo)
    calibration = own.vision.calibration
    visions = {}
    stage = dict(postures=None, anchor=None)
    def control_fine(now, idle):
        if own.state not in ('align','hover','blind_descent','grasp') or own.terminal:
            return control(now, idle)
        if not idle:
            return []
        obs = own.last_obs
        if not gate().valid_frame(obs, own.robot_id, now):
            return []
        if own.state == 'align':
            if not servo.gate.ready(now, obs):
                return []
            inspect = {**pose_of('inspect'), 6:own.servo[6]}
            if any(own.servo[k] != v for k,v in inspect.items()):
                own.queue(inspect, now, duration=.4, settle=.45)
                return []
            pan = own.servo[6]
            if pan not in visions:
                visions[pan] = CyanVision(yaw_calibration(calibration, pan))
            fits = visions[pan].detect(obs, own.servo)
            if len(fits) != 1:
                servo.streak = 0
                return []
            own.target = fits[0]['estimated_box_center_base_m'][:2]
            phase, value = servo.observe(now, obs, own.servo, own.target, 0.)
            own.event('coarse_fine', now, phase=phase, detail=copy.deepcopy(servo.audit[-1]) if servo.audit else {})
            if phase == 'base':
                return [value]
            if phase == 'pan':
                own.queue({6:value}, now, duration=.3, settle=.45)
                return [{'kind':'hold'}]
            if phase != 'ready':
                return []
            stage['postures'] = postures(value)
            stage['anchor'] = dict(t=now, frame_id=obs['frame_id'], sha256=obs['sha256'])
            own.target_t = now
            # Call ArmSequence directly; the old fixed-posture pregrasp
            # interceptor must not substitute its 3mm gate or reset pan.
            own.arm.queue({**stage['postures'][0],1:2000}, now, duration=1., settle=blind.HOVER_SETTLE_S)
            own.set_state('hover', now)
            own.event('coarse_fine_aligned',now,frame_id=obs['frame_id'])
            return []
        hover, path = stage['postures']
        if own.state == 'hover':
            if now-stage['anchor']['t'] > 30. or not blind.at_posture(own.servo, hover):
                return own.fail('COARSE_FINE_ANCHOR_INVALID', now)
            own.blind.window = dict(confirmed_at_s=now, frame_id=stage['anchor']['frame_id'],
                sha256=stage['anchor']['sha256'], visual_confirmed_at_s=stage['anchor']['t'],
                source=OPTION, pan=hover[6], envelope=blind._envelope(hover,path), limits=blind.limits())
            own.blind.disarmed = None
            for p in path:
                own.arm.queue(p, now, duration=.12, settle=0.)
            own.arm.until += blind.HOVER_SETTLE_S
            own.set_state('blind_descent', now)
            return []
        window = own.blind.window
        if not (window and own.blind.disarmed is None and
                now-window['confirmed_at_s'] <= window['limits']['blind_max_s'] and
                blind.at_posture(own.servo, path[-1])):
            return own.fail('COARSE_FINE_BLIND_INVALID', now)
        if own.state == 'blind_descent':
            own.arm.queue({1:1500}, now, duration=.5, settle=.4)
            own.set_state('grasp', now)
            return []
        if own.servo.get(1) != 1500:
            return own.fail('CLOSE_NOT_ISSUED', now)
        own.receipt = True
        own.event('cyan_close_receipt', now, evidence='own issued close only; contact unverified')
        own.arm.queue({**hover,1:1500}, now, duration=1.2, settle=2.8)
        from harness import zone_pair_highpose as high
        for p, duration, settle in high.raise_path():
            own.arm.queue({**p,1:1500}, now, duration=duration, settle=settle)
        own.set_state('lift', now)
        return []
    own._control = control_fine
    own.s3_coarse_fine = servo
    own.record = lambda: {**record(), 'coarse_fine':dict(option=OPTION, params=PARAMS,
        decisions=copy.deepcopy(servo.audit), runtime_gt=False,
        **({'refinements':__import__('dataclasses').asdict(refinements)} if refinements.enabled else {}))}
    return own
