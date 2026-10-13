"""body_controller=jev_v1: own-body motion chosen by a categorical decider.

Structure (user 2026-10-13): Gemma only talks (messages, route/claim/GO/ACK);
every own-body motion is chosen by a decider (Jev by default, paid Liquid d1 as
the optional backend) from 2-6 executable short-motion candidates built by
code from the robot's own RGB, own map estimate, own issued commands and the
received dialogue state.  Code executes the chosen candidate numerically
through the unchanged ports, authorizations and safety guards.

Decision points (one call per finished motion, never per frame):
* direct controller motions (mapping 1 s units, alignment/approach pulses,
  camera pans) -> menu of calibrated short pulses / pan / hold / plan step;
* queued arm/camera batches (grasp+lift, set-down, relook pose, views) ->
  execute / wait / (grasp only) re-align; pair batches require both robots;
* carry segments -> offered only when the current GO/ACK is complete; both
  robots must choose to carry.
Decider failure or timeout -> hold and re-ask after RETRY_S (never ground truth).
Measured decision latency is charged as SIM time during which the robot holds.
"""
import base64
import copy
import hashlib
import json
import math
import statistics
import time
import urllib.request
from collections import deque
from pathlib import Path

from harness import e2e_body_semantics as sem

OPTION = 'jev_v1'
BACKENDS = ('jev', 'liquid_d1')
PARENT = 'e2e18-v321'
VERSIONS = {'jev': 335, 'liquid_d1': 336}
REMOTE_PORT = 18433
URL = f'http://127.0.0.1:{REMOTE_PORT}/v1/body/decide'
RELAY_SOURCES = ('scripts/body_decider_relay.py', 'harness/body_decider_upstream.py')
PARAMS = dict(mapping_unit_s=sem.MAPPING_UNIT_S, hold_s=sem.HOLD_S, retry_s=1., http_timeout_s=25.,
              batch_execute_valid_s=3., phase_budget_s=60., progress_window_s=20., history_size=10, latency_sim='measured_hold_v1', pan_step_us=sem.PAN_STEP_US,
              min_candidates=2, max_candidates=6, image='own_wrist_rgb_jpeg_latest',
              failure='hold+retry_same_backend_no_free_tier', jev='text state only')
INSTRUCTIONS = ('You choose the next single short body motion for one small mecanum robot with a wrist camera '
                'and gripper. Use the image (this robot\'s own camera) and the state. Pick the candidate whose '
                'predicted effect best advances the current phase safely. Prefer re-observing when the target '
                'is not visible or evidence conflicts; never start joint carrying without completed GO/ACK.')
DT = .05


def compose(bundle, body_controller='off', body_backend='jev', body_visual_check='off'):
    if body_controller == 'off':
        if body_visual_check != 'off':raise ValueError('VISUAL_CHECK_REQUIRES_BODY_CONTROLLER')
        return ()
    if body_controller != OPTION or body_backend not in BACKENDS:
        raise ValueError('UNKNOWN_BODY_CONTROLLER')
    if bundle['execution_bundle_id'] != PARENT or not bundle['e2e_options'].get('dev_light'):
        raise ValueError('BODY_CONTROLLER_REQUIRES_DEV_V321')
    if bundle['e2e_options'].get('decider','off') != 'off':
        raise ValueError('BODY_JEV_REQUIRES_GEMMA_DIALOGUE_ONLY')
    if body_visual_check not in ('off','d1_v1'):raise ValueError('UNKNOWN_VISUAL_CHECK')
    if body_visual_check!='off' and body_backend!='jev':raise ValueError('VISUAL_CHECK_REQUIRES_JEV')
    v = 337 if body_visual_check=='d1_v1' else VERSIONS[body_backend]
    bundle['body_controller_parent'] = PARENT
    bundle['e2e_options'].update(body_controller=body_controller, body_backend=body_backend, body_visual_check=body_visual_check)
    bundle['body_controller_parameters'] = copy.deepcopy(PARAMS)
    bundle.update(schema=f'ugrp.e2e_ownmap_live.v{v}', execution_bundle_id=f'e2e18-v{v}',
                  workflow_version=f'7.{v-107}.0')
    return (f'configs/simulation_workflows.d/e2e18_v{v}.json', 'harness/e2e_body_controller.py',
            'harness/e2e_body_semantics.py', *RELAY_SOURCES)


def parent_for_validation(bundle):
    o = bundle['e2e_options']
    if (o.get('body_controller') != OPTION or o.get('body_backend') not in BACKENDS
            or bundle['execution_bundle_id'] != f"e2e18-v{337 if o.get('body_visual_check')=='d1_v1' else VERSIONS[o['body_backend']]}"
            or bundle.get('body_controller_parent') != PARENT
            or bundle.get('body_controller_parameters') != PARAMS):
        raise ValueError('REGISTERED_BODY_CONTROLLER_REQUIRED')
    old = copy.deepcopy(bundle)
    old['execution_bundle_id'] = PARENT
    for k in ('body_controller_parent', 'body_controller_parameters'):
        old.pop(k)
    for k in ('body_controller', 'body_backend', 'body_visual_check'):
        old['e2e_options'].pop(k)
    return old


def relay_hashes(root):
    return {p: hashlib.sha256((Path(root) / p).read_bytes()).hexdigest() for p in RELAY_SOURCES}


def validate_receipt(receipt, root, backend, now=None):
    now = time.time() if now is None else now
    if (receipt.get('schema') != 'ugrp.body_decider_relay.v1' or receipt.get('remote_url') != URL
            or receipt.get('source_sha256') != relay_hashes(root)
            or backend not in receipt.get('backends', ())
            or not receipt['checked_unix'] <= now <= receipt['checked_unix'] + receipt['valid_for_s']):
        raise ValueError('BODY_RELAY_RECEIPT_INVALID')


class Client:
    """VM-side loopback client; the credential exists only in the Mac relay."""

    def __init__(self, backend, run_key, url=URL, timeout=PARAMS['http_timeout_s'], send=None):
        self.backend, self.run_key, self.url, self.timeout = backend, run_key, url, timeout
        self.count = 0
        self.send = send or self._send

    def _send(self, payload):
        req = urllib.request.Request(self.url, json.dumps(payload).encode(), {
            'Content-Type': 'application/json', 'X-UGRP-Call-ID': payload['call_id']})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read(2_000_000))

    def decide(self, state, candidates, image_jpeg, *, instructions=INSTRUCTIONS):
        self.count += 1
        payload = dict(call_id=f'{self.run_key}:body-{self.count}', backend=self.backend, state=state,
                       instructions=instructions, candidates=candidates,
                       image_jpeg_b64=base64.b64encode(image_jpeg).decode() if image_jpeg else None)
        started = time.monotonic()
        try:
            out = self.send(payload)
        except Exception as exc:  # transport failure: hold and re-ask
            out = dict(status='transport_error', error_type=type(exc).__name__)
        out.setdefault('wall_s', time.monotonic() - started)
        out['call_id'] = payload['call_id']
        out['image_sha256'] = hashlib.sha256(image_jpeg).hexdigest() if image_jpeg else None
        if out.get('status') == 'ok' and out.get('choice') not in candidates:
            out = dict(out, status='invalid_choice')
        return out


def stop_like(c):
    """Hold/wait and zero-speed pulses are safety stops: never gated."""
    return c.get('kind') in ('hold', 'wait') or (
        c.get('kind') == 'mecanum' and not any(c.get(a) for a in ('forward', 'left', 'turn')))


def pan_target(pan, sign):
    return int(min(2100, max(900, pan + sign * PARAMS['pan_step_us'])))


def ceil_dt(x):
    return math.ceil(max(0., x) / DT - 1e-9) * DT


class BodyGate:
    def __init__(self, transport, robots, client, *, profiles, record=None):
        self.tr, self.robots, self.client, self.profiles = transport, robots, client, profiles
        self.record = record or (lambda row: None)
        self.units, self.pending, self.retry_at = {}, {}, {}
        self.approved, self.batches = set(), {}
        self.history = {r: deque(maxlen=16) for r in robots}
        self.poses = {r: deque(maxlen=200) for r in robots}
        self.carry_votes = {}
        self.rows = []
        self.memory = {r: sem.DecisionMemory() for r in robots}
        self.peer_cache = {}
        self.grip_cache = {}
        self.stage_times = {}
        self.dispatch_key = None
        self.visual_check = 'off'
        self.visual_checks = {}
        self.recovery_started = {}
        self.suppressed = 0
        orig = transport._carry

        def carry(now):
            return self._carry(now, orig)
        transport._carry = carry

    # ---------------------------------------------------------------- facts
    def facts(self, rid, now):
        r, tr = self.robots[rid], self.tr
        beam, grip, heading = sem.beam_state(r, now)
        f = {'beam': beam['visibility'] + ', ' + beam['age']}
        if 'bearing' in beam:
            f['beam_direction'] = beam['bearing']
            f['beam_distance'] = beam['distance']
        if grip is not None and rid in sem.PAIR and tr.state in ('align', 'grasp_lift'):
            try:
                f.update(sem.align_words(sem.align_errors(rid, grip, heading)))
            except Exception:
                pass
        f['recent_own_motion'] = sem.oscillation(list(self.history[rid]))
        f['own_progress_last_5s'] = sem.progress(list(self.poses[rid]), now)
        f['gripper'] = sem.grip_command_state(r)
        f['own_route'] = 'route generated or received' if getattr(r, 'packet', None) else 'see delivered dialogue route state'
        f.update({('agreement_' + k): v for k, v in sem.agreement(getattr(tr, 'dialogue', None), now).items()})
        f.update(self.context(rid, now))
        if tr.state=='mapping':
            f['navigation_task']='Build own map and find B/beam by following the proposed own-map path to a new viewpoint. Beam fine-alignment/search rules apply only after mapping; do not spin just because the beam is absent.'
            f['next_own_navigation_motion']=sem.effect_of(getattr(r,'nav_command',{}))
        return f, grip, heading

    def image(self, rid):
        frame = getattr(self.robots[rid], 'frame', None)
        return getattr(frame, 'jpeg', None)

    def context(self, rid, now):
        r, tr = self.robots[rid], self.tr
        self.stage_times.setdefault(tr.state, now)
        self.last_now = now
        approach = getattr(tr, 'approach', {}).get(rid, {})
        geo = sem.geometry(r, approach, now)
        target = geo['grasp'] or geo['standoff'] or {}
        visual = sem.visual_category(r)
        observation = getattr(r, 'beam_observation', None) or {}
        rgb = observation.get('rgb') or {}
        result = observation.get('result') or {}
        grip = result.get('grip_base_m')
        bearing = math.degrees(math.atan2(grip[1], grip[0])) if grip is not None else target.get('bearing_deg')
        distance = target.get('distance_m')
        if distance is None and grip is not None:
            distance = math.hypot(*grip)
        loop = sem.oscillation(list(self.history[rid])) == 'repeated back-and-forth'
        memory = self.memory[rid]
        memory.observe((tr.state, getattr(tr,'epoch',0), getattr(tr,'seg',0)), now, visual,
                       distance, bearing, loop, rgb.get('frame_id'))
        frame_id = rgb.get('sha256')
        if self.peer_cache.get(rid, (None,))[0] != frame_id or rid not in self.peer_cache:
            self.peer_cache[rid] = (frame_id, sem.peer_appearance(self.image(rid)))
        from harness.ultrasonic_input import range_report
        report = range_report(r, now)
        sonar = report.as_dict() if report is not None else {'status':'off', 'range_m':None}
        d = getattr(tr, 'dialogue', None)
        view = d.view(rid, now) if d is not None and hasattr(d,'view') else {}
        inbox = []
        if d is not None and hasattr(d,'trial'):
            inbox = d.trial.channel.inbox(rid, now_sim_s=now)
        messages = [dict(id=e.get('message_id'), sender=e.get('sender'),
                         text=(e.get('body') or {}).get('text','')[:300],
                         delivered_at_sim_s=e.get('delivered_at_sim_s')) for e in inbox[-4:]]
        # Delivered text only, never the other robot's private state.
        stop_words = ('slip','danger','stop','wait','stuck','미끄','위험','멈','기다')
        recent_text = ' '.join(m['text'].lower() for m in messages
                              if isinstance(m['delivered_at_sim_s'],(int,float)) and now-m['delivered_at_sim_s']<10)
        holding = r.servo.get(1)==1500 and tr.state in (
            'grasp_lift','grasp_go_ack','wait_go_ack','carry','final_rgb_wait','final_route_approval','final_lower_go_ack','lower_open')
        visual_grip = self.grip_state(rid, frame_id, holding)
        return dict(visual_category=visual, visual_age_s=None if not rgb else now-rgb['t_sim'],
                    own_map=geo,target_distance_m=distance, target_bearing_deg=bearing,
                    own_grip=visual_grip,
                    holding_command=holding, front_ultrasonic=sonar, peer_in_own_rgb=self.peer_cache[rid][1],
                    dialogue=view, go_ack_complete=bool(view.get('transport_admitted')),
                    joint_operation='both own visual alignment gates passed; closed grippers; current lift GO/ACK received' if tr.state=='grasp_lift' and view.get('transport_admitted') else tr.state,
                    partner_recent_messages=messages, partner_stop=any(w in recent_text for w in stop_words),
                    left_right_loop=loop, **memory.context(now))

    def grip_state(self, rid, frame_id, holding):
        if not holding:
            self.grip_cache.pop(rid, None)
            return 'open command; no holding claim'
        image = self.image(rid)
        if not image:
            return 'unknown; closed command alone is not proof'
        old = self.grip_cache.get(rid)
        if old and old[0]==frame_id:
            return old[2]
        from harness.owncam_pair_beam import held_signature, signature_fraction, signature_iou
        signature = held_signature(image)
        fraction = signature_fraction(signature)
        pose = tuple(sorted(self.robots[rid].servo.items()))
        same_pose = old and old[3]==pose
        slipping = same_pose and signature_fraction(old[1])>.02 and signature_iou(old[1],signature)<.3
        label = 'possible slipping in own RGB' if slipping else 'beam visible at closed gripper; holding hypothesis' if fraction>.02 else 'unknown; beam not visible at closed gripper'
        self.grip_cache[rid]=(frame_id,signature,label,pose)
        return label

    @staticmethod
    def hazard(facts):
        sonar = facts['front_ultrasonic']
        near = (sonar.get('valid') and (sonar.get('age_s') or 0)<=.5
                and sonar.get('range_m') is not None and sonar['range_m']<.15)
        peer = facts['peer_in_own_rgb']
        return near or sonar.get('status')=='blind' or (peer.get('visible') and peer.get('in_path') and peer.get('distance')=='near')

    def motion_safe(self, command, facts):
        if command.get('kind')!='mecanum' or stop_like(command):
            return True
        if facts['holding_command'] and (not facts['go_ack_complete'] or facts['partner_stop'] or self.hazard(facts) or 'slipping' in facts['own_grip']):
            return False
        if self.hazard(facts) and command.get('forward',0)>0:
            return False
        peer=facts['peer_in_own_rgb']
        if peer.get('visible') and peer.get('distance')=='near':
            if (peer.get('direction')=='left' and command.get('left',0)>0
                    or peer.get('direction')=='right' and command.get('left',0)<0):
                return False
        if facts['left_right_loop'] and (command.get('turn',0) or command.get('left',0)):
            return False
        if facts['visual_category']=='not_visible' and facts['last_seen_bearing_deg'] is not None:
            turn = command.get('turn',0)
            if turn and turn*facts['last_seen_bearing_deg']<0:
                return False
        return True

    def map_safe(self, rid, command):
        if command.get('kind')!='mecanum' or stop_like(command):
            return True
        robot = self.robots[rid]
        explorer = robot.goal.explorer
        if not hasattr(explorer,'grid'):
            return True  # no own map available yet; range/RGB filters remain
        from harness.active_wall_mapping import compose
        from harness.public_navigation_unknown import from_observed_grid
        from harness.public_navigation.follower import projected_clear
        from harness.public_navigation_recovery import issued_twist
        pose = compose(explorer.map_to_odom, explorer.local_pose)
        costmap = from_observed_grid(explorer.grid, pose, explorer.latest, set())
        return bool(projected_clear(costmap, pose, issued_twist(command)))

    def recovery(self, rid, now, facts):
        """Executable ordered recovery candidates; no hidden strategy execution."""
        tried = facts['recovery_strategies_tried']
        if 'recover_wide_view' not in tried:
            return 'recover_wide_view', ('back up with six short reverse pulses for a wider view of the whole beam',
                ('script', 1.6, [(i*.25, sem.pulse('back_short')) for i in range(6)]))
        if 'recover_standoff' not in tried and facts['own_map']['standoff'] is not None:
            # One bounded step of the existing own-map follower toward the stored
            # standoff. Reaching it and clearing fine mode requires own odometry.
            from harness.e2e_rpp_path import command
            r = self.robots[rid]
            pose = r.goal.explorer.local_pose
            station = self.tr.approach[rid]['station']
            c,_ = command(dict(coordinate_frame=rid+'/own_odom',path_m=[list(pose[:2]),list(station[:2])],
                               status='goal_approach',heading_rad=float(station[2])),pose,self.profiles,robot_id=rid)
            return 'recover_standoff', ('return toward the remembered own-map standoff; restart approach from there',
                ('standoff', 10., [(0.,c)]))
        if 'recover_camera_pan' not in tried:
            sign = -1 if (facts['last_seen_bearing_deg'] or 0)<0 else 1
            pan = self.robots[rid].servo.get(6,1500)
            c = dict(kind='look',pan_pulse=pan_target(pan,sign))
            return 'recover_camera_pan', ('pan the camera toward the last seen beam direction to reacquire it',
                ('script', .6, [(0.,c)]))
        return None

    def safe_menu(self, rid, now, menu, facts):
        switch = self.tr.state=='align' and (facts['budget_exceeded'] or facts['no_progress_20s'] or facts['left_right_loop'])
        if switch and now-self.recovery_started.get(rid,-math.inf)>=20. and not facts['holding_command']:
            recovery = self.recovery(rid,now,facts)
            menu = {k:v for k,v in menu.items() if not v[1][2]}
            if recovery is not None:
                menu[recovery[0]]=recovery[1]
            facts['strategy_switch_required']=True
            facts['strategies_exhausted']=recovery is None
        safe = {}
        for label,item in menu.items():
            script = item[1][2]
            if facts['visual_category']=='not_visible' and facts['last_seen_bearing_deg'] is not None:
                pan=self.robots[rid].servo.get(6,1500)
                if any(c.get('kind')=='look' and (c['pan_pulse']-pan)*facts['last_seen_bearing_deg']<0 for _,c in script):
                    continue
            if all(self.motion_safe(c,facts) and self.map_safe(rid,c) for _,c in script):
                safe[label]=(item[0]+sem.predict_target(facts['own_map'],script,self.profiles),item[1])
        if not safe:
            safe['hold_and_reobserve']=('stay still; no safe motion available',('script',sem.HOLD_S,[]))
        return safe

    # -------------------------------------------------------------- decide
    def decide(self, rid, now, kind, menu, proposal_label=None, facts=None):
        """menu: label -> (description, executor). Returns label or None on failure."""
        if facts is None:
            facts, _, _ = self.facts(rid, now)
        decision_started=time.monotonic()
        if self.visual_check=='d1_v1' and facts.get('visual_category') in ('clipped','not_visible'):
            self.crosscheck(rid,now,facts)
        state = sem.state_text(rid, self.tr.state, facts)
        candidates = {k: v[0] for k, v in menu.items()}
        out = self.client.decide(state, candidates, self.image(rid))
        latency = max(time.monotonic()-decision_started,float(out.get('wall_s') or out.get('latency_s') or 0.))
        if not math.isfinite(latency) or latency < 0 or latency > PARAMS['http_timeout_s']:
            out['status']='late_or_invalid_latency'; latency=PARAMS['http_timeout_s']
        row = dict(t=now, robot_id=rid, phase=self.tr.state, decision=kind, state=state, facts=facts,
                   candidates=candidates, code_proposal=proposal_label, status=out.get('status'),
                   choice=out.get('choice'), probabilities=out.get('probabilities'), confidence=out.get('confidence'),
                   tier=out.get('tier'), model=out.get('model'), latency_s=latency, wall_s=out.get('wall_s'),
                   usage=out.get('usage'), attempts=out.get('attempts'), call_id=out.get('call_id'),
                   image_sha256=out.get('image_sha256'), sim_hold_s=ceil_dt(latency))
        executor = menu.get(out.get('choice'), (None, None))[1]
        duration = executor[1] if isinstance(executor, tuple) else .6
        self.memory[rid].selected(now, out.get('choice'), facts.get('visual_category'), facts.get('target_distance_m'),
                                  ceil_dt(latency)+duration, out.get('status'))
        self.rows.append(row)
        self.record(row)
        if out.get('status')=='ok' and str(out.get('choice')).startswith('recover_'):
            self.recovery_started[rid]=now+ceil_dt(latency)
        if out.get('status') != 'ok':
            self.retry_at[rid] = now + ceil_dt(latency) + PARAMS['retry_s']
            return None, now
        return out['choice'], round(now + ceil_dt(latency), 8)

    def crosscheck(self, rid, now, facts):
        previous=self.visual_checks.get(rid)
        if previous and now-previous['t']<10.:
            facts['d1_visual_crosscheck']=previous
            return
        client=Client('liquid_d1',self.client.run_key+':visual:'+rid,send=self.client.send)
        client.count=self.client.count
        categories={k:k.replace('_',' ') for k in ('visible','left','right','clipped','too_close','not_visible')}
        out=client.decide('Classify only the banded end of the beam in this robot own wrist image. '
                         'Do not choose motion or infer another robot state.',categories,self.image(rid),
                          instructions='Choose the visible location/category of the banded beam end, based only on this image.')
        self.client.count=client.count
        entry=dict(t=now,category=out.get('choice'),status=out.get('status'),latency_s=out.get('wall_s'),
                   image_sha256=out.get('image_sha256'),usage=out.get('usage'),call_id=out.get('call_id'))
        self.visual_checks[rid]=entry
        facts['d1_visual_crosscheck']=entry
        self.record(dict(decision='visual_crosscheck',robot_id=rid,phase=self.tr.state,**entry))

    # ------------------------------------------------------- direct motions
    def menu_direct(self, rid, now, proposal):
        """Short executable candidates for one controller motion proposal."""
        facts, grip, heading = self.facts(rid, now)
        phase = self.tr.state
        menu, plabel = {}, None
        if phase == 'mapping':
            effect = '; '.join(sorted({sem.effect_of(c) for c in proposal})) or 'stop'
            script = [(0., copy.deepcopy(c)) for c in proposal if not stop_like(c)]
            duration = max([c.get('duration_s', .4) for _,c in script]+[.4])
            menu['follow_own_path'] = (f'execute the next own-map exploration/path-following motion ({effect}); then observe',
                                       ('script', duration, script))
            menu['turn_left_scan'] = ('rotate left in place about 25 degrees to view new area',
                                      ('script', 1., [(i * .2, sem.pulse('turn_left_small')) for i in range(5)]))
            menu['turn_right_scan'] = ('rotate right in place about 25 degrees to view new area',
                                       ('script', 1., [(i * .2, sem.pulse('turn_right_small')) for i in range(5)]))
            menu['back_off'] = ('move backward about 4 cm away from what is ahead',
                                ('script', .6, [(i * .2, sem.pulse('back_short')) for i in range(3)]))
            menu['stop_and_look'] = ('stay still and take a new camera look', ('script', PARAMS['hold_s'], []))
            plabel = 'follow_own_path'
            return self.safe_menu(rid, now, menu, facts), plabel, facts
        moves = [c for c in proposal if c.get('kind') in ('mecanum', 'look', 'arm')]
        pan = self.robots[rid].servo.get(6, 1500)
        before = None
        if grip is not None and rid in sem.PAIR and phase in ('align', 'grasp_lift'):
            try:
                before = sem.align_words(sem.align_errors(rid, grip, heading))
            except Exception:
                before = None
        names = ['forward_short', 'back_short', 'turn_left_small', 'turn_right_small']
        for name in names:
            p = sem.profile_of(name, self.profiles)
            text = {'forward_short': 'drive forward about 1.3 cm', 'back_short': 'drive backward about 1.3 cm',
                    'turn_left_small': 'rotate left about 5 degrees', 'turn_right_small': 'rotate right about 5 degrees'}[name]
            if before is not None and p is not None:
                try:
                    text += sem.describe_prediction(before, sem.predicted(rid, grip, heading, p))
                except Exception:
                    pass
            cmd = sem.pulse(name)
            menu[name] = (text, ('script', cmd['duration_s'], [(0., cmd)]))
            if len(moves) == 1 and moves[0] == cmd:
                plabel = name
        if plabel is None and moves:
            effect = ' then '.join(sem.effect_of(c) for c in moves[:3])
            kind = 'camera' if all(c['kind'] in ('look', 'arm') for c in moves) else 'body'
            dur = max([c.get('duration_s', 0.) for c in moves] + [0.])
            menu['own_plan_step'] = (f'execute own planned {kind} step ({effect}) toward the grasp station / target view',
                                     ('script', dur, [(0., copy.deepcopy(c)) for c in moves]))
            plabel = 'own_plan_step'
        if 'not visible' in facts['beam'] or 'partly' in facts['beam']:
            # Camera search alternatives replace the least useful drive candidates.
            # Keep back-up available for clipped/too-close views.
            menu.pop('forward_short', None) if 'not visible' in facts['beam'] else None
            for side, sign in (('left', 1), ('right', -1)):
                target = pan_target(pan, sign)
                menu[f'pan_camera_{side}'] = (f'pan camera {side} to search for the beam end',
                                              ('script', .5, [(0., dict(kind='look', pan_pulse=target))]))
        menu['hold_and_reobserve'] = ('stay still briefly and take a new camera look', ('script', PARAMS['hold_s'], []))
        # Keep <= max candidates; never drop the plan step or hold.
        keep = [k for k in menu if k in (plabel, 'hold_and_reobserve')]
        rest = [k for k in menu if k not in keep]
        menu = {k: menu[k] for k in (rest[:PARAMS['max_candidates'] - len(keep)] + keep)}
        return self.safe_menu(rid, now, menu, facts), plabel, facts

    def filter(self, now, commands):
        out, grouped = [], {}
        key=(self.tr.state,getattr(self.tr,'epoch',0),getattr(self.tr,'seg',0))
        if key != self.dispatch_key:
            self.pending.clear();self.units.clear();self.dispatch_key=key
        if self.tr.failure or self.tr.done:
            self.pending.clear(); self.units.clear()
            return [(rid,dict(kind='hold')) for rid in self.robots]
        for rid,c in commands:
            if id(c) in self.approved:
                self.approved.discard(id(c))
                out.append((rid,c))
            else:
                grouped.setdefault(rid,[]).append(c)
        for rid,r in self.robots.items():
            pose=getattr(getattr(r.goal,'explorer',None),'local_pose',None)
            if pose is not None:self.poses[rid].append((now,[float(x) for x in pose]))
            self.context(rid,now)
            moves=[c for c in grouped.get(rid,[]) if not stop_like(c)]
            if not moves and rid not in self.units and rid not in self.pending:
                out.extend((rid,c) for c in grouped.get(rid,[]))
            out.extend((rid,c) for c in self._robot(rid,now,moves))
        # Emergency range/appearance and agreement filters also apply to queued
        # pulses at execution, after API delay. Numeric authorization stays below.
        safe=[]
        for rid,c in out:
            f=self.context(rid,now)
            if c.get('kind')=='mecanum' and not self.motion_safe(c,f):
                safe.append((rid,dict(kind='hold')))
                self.tr.event(now,'body_safety_stop',robot_id=rid,reason='latest_own_evidence')
                if self.tr.state=='carry':
                    # A partially interrupted calibrated segment cannot inherit
                    # its completion or be silently replayed from the beginning.
                    return self.tr.fail('BODY_CARRY_INTERRUPTED_REPLAN_REQUIRED',now)
            else:
                safe.append((rid,c))
                if c.get('kind')=='mecanum' and not stop_like(c):self.history[rid].append(dict(c))
        return safe

    def _robot(self, rid, now, moves):
        unit = self.units.get(rid)
        if unit is not None and now >= unit['until'] - 1e-8:
            self.units.pop(rid)
            unit = None
        if unit is not None:
            emitted = [c for t, c in unit['script'] if unit['start'] + t <= now + 1e-8 and id(c) not in unit['sent']]
            for c in emitted:
                unit['sent'].add(id(c))
            if unit['mode']=='standoff':
                if now<unit.get('next_at',now):return []
                unit['next_at']=now+.2
                r=self.robots[rid];station=self.tr.approach.get(rid,{}).get('station')
                if station is None or math.dist(list(r.goal.explorer.local_pose[:2]),list(station[:2]))<.05:
                    self.units.pop(rid,None);return [dict(kind='hold')]
                from harness.e2e_rpp_path import command
                pose=r.goal.explorer.local_pose
                c,_=command(dict(coordinate_frame=rid+'/own_odom',path_m=[list(pose[:2]),list(station[:2])],
                                status='goal_approach',heading_rad=float(station[2])),pose,self.profiles,robot_id=rid)
                return [c] if self.map_safe(rid,c) else [dict(kind='hold')]
            if unit['mode'] == 'follow':
                return emitted + moves
            self.suppressed += len(moves)
            return emitted
        p = self.pending.get(rid)
        if p is not None:
            if now + 1e-8 < p['ready_at']:
                self.suppressed += len(moves)
                return []
            self.pending.pop(rid)
            mode, duration, script = p['executor']
            if mode=='standoff':
                self.tr.approach.get(rid,{}).pop('fine',None)
                self.tr.aligned.pop(rid,None)
            self.units[rid] = dict(mode=mode, start=now, until=now + max(duration, DT), sent=set(),
                                   script=[(t, copy.deepcopy(c)) for t, c in script], label=p['label'])
            return self._robot(rid, now, moves if mode == 'follow' else [])
        if not moves:
            return []
        if now + 1e-8 < self.retry_at.get(rid, -1.):
            self.suppressed += len(moves)
            return [dict(kind='hold')]
        menu, plabel, facts = self.menu_direct(rid, now, moves)
        choice, ready = self.decide(rid, now, 'motion', menu, plabel, facts)
        if choice is None:
            return [dict(kind='hold')]
        self.pending[rid] = dict(ready_at=ready, label=choice, executor=menu[choice][1])
        self.suppressed += len(moves)
        return self._robot(rid, now, []) if ready <= now + 1e-8 else [dict(kind='hold')]

    # ------------------------------------------------------- queued batches
    def batch_kind(self):
        return {'grasp_close': 'grasp_close', 'grasp_lift': 'grasp_lift', 'lower_open': 'set_down', 'relook_camera': 'relook_pose',
                'final_lower_go_ack': 'set_down'}.get(self.tr.state, 'camera_view')

    def batch_menu(self, kind):
        if kind == 'grasp_close':
            return {'grasp_only': ('approach with arm, close the gripper at the visually aligned end; do not lift', 'execute'),
                    'wait_and_reobserve': ('stay still and observe the end before closing', 'wait'),
                    'realign_first': ('return to own-camera alignment before closing', 'realign')}
        if kind == 'grasp_lift':
            return {'grasp_and_lift': ('close gripper on the beam end and lift together with partner', 'execute'),
                    'wait_and_reobserve': ('keep holding still; inspect own RGB and current lift agreement', 'wait')}
        if kind == 'set_down':
            return {'set_down_now': ('lower the beam to the floor together with partner and open gripper', 'execute'),
                    'wait_and_reobserve': ('keep holding the beam still and take a new look', 'wait')}
        return {'move_camera_to_planned_view': ('move arm/camera to the planned viewing pose', 'execute'),
                'wait_and_reobserve': ('keep the current camera pose and take a new look', 'wait')}

    def pre_step(self, now):
        tr = self.tr
        due = {}
        for t, rid, c in tr.queue:
            if id(c) not in self.approved:
                due.setdefault(rid, []).append(t)
        blocked = set()
        extra = []
        for rid, ts in due.items():
            if min(ts) > now + DT + 1e-8:
                continue
            kind = self.batch_kind()
            pair = kind in ('grasp_close', 'grasp_lift', 'set_down')
            group = sem.PAIR if pair else (rid,)
            if pair and rid != group[0]:
                continue
            st = self.batches.get(group)
            if st is None or st['kind'] != kind:
                st = self.batches[group] = dict(kind=kind, votes={}, since=now)
            done = True
            for g in group:
                v = st['votes'].get(g)
                if v and v['action'] == 'execute' and now - v['t'] > PARAMS['batch_execute_valid_s']:
                    v = None
                if v is None or (v['action'] != 'execute' and now + 1e-8 >= v['until']):
                    if now + 1e-8 < self.retry_at.get(g, -1.):
                        done = False
                        continue
                    menu = self.batch_menu(kind)
                    facts, _, _ = self.facts(g, now)
                    if kind == 'grasp_lift' and not facts['go_ack_complete']:
                        menu.pop('grasp_and_lift', None)
                    choice, ready = self.decide(g, now, kind, menu, list(menu)[0], facts)
                    if choice is None:
                        done = False
                        continue
                    action = menu[choice][1]
                    v = st['votes'][g] = dict(action=action, label=choice, t=now, ready=ready,
                                              until=ready + (PARAMS['hold_s'] if action != 'execute' else 0.))
                    if action in ('pan_left', 'pan_right'):
                        pan = self.robots[g].servo.get(6, 1500)
                        sign = 1 if action == 'pan_left' else -1
                        extra.append((g, dict(kind='look', pan_pulse=pan_target(pan, sign))))
                        v['until'] = ready + .5
                    if action == 'realign':
                        self._realign(g, now, group)
                        st['votes'].clear()
                        done = False
                        break
                if v['action'] != 'execute' or now + 1e-8 < v['ready']:
                    done = False
            if done and tr.queue:
                for t, r, c in tr.queue:
                    if r in group:
                        self.approved.add(id(c))
                self.batches.pop(group, None)
            elif tr.queue:
                blocked.update(group)
        if blocked:
            tr.queue = [((round(t + DT, 8) if r in blocked and id(c) not in self.approved else t), r, c)
                        for t, r, c in tr.queue]
            tr.queue.sort(key=lambda row: (row[0], row[1]))
            tr.queue_until = max([tr.queue_until + DT] + [t for t, _, _ in tr.queue])
            for r in blocked:
                tr.robot_queue_until[r] = tr.robot_queue_until.get(r, 0.) + DT
        return extra

    def _realign(self, rid, now, group):
        tr = self.tr
        tr.queue = [(t, r, c) for t, r, c in tr.queue if not (r in group and id(c) not in self.approved)]
        tr.queue_until = max([now] + [t for t, _, _ in tr.queue])
        for r in group:
            tr.robot_queue_until[r] = now
        tr.aligned.pop(rid, None)
        servo = tr.align.get(rid)
        if servo is not None:
            servo.streak = 0
            servo.chosen = None
        tr.event(now, 'body_decider_realign', robot_id=rid)
        tr.set('align', now)

    # ---------------------------------------------------------------- carry
    def _carry(self, now, orig):
        d = self.tr.dialogue
        if not d.allowed(d.key, now):
            return False  # no carry candidate without the current completed GO/ACK
        key = tuple(d.key)
        votes = self.carry_votes.setdefault(key, {})
        ready = True
        for rid in sem.PAIR:
            v = votes.get(rid)
            if v is None or (v['action'] != 'execute' and now + 1e-8 >= v['until']):
                if now + 1e-8 < self.retry_at.get(rid, -1.):
                    ready = False
                    continue
                menu = {'carry_segment': ('carry the beam along the agreed route segment together with partner '
                                          '(current GO/ACK complete)', 'execute'),
                        'hold_and_wait': ('keep holding the beam still and wait', 'wait')}
                facts, _, _ = self.facts(rid, now)
                plan=getattr(self.tr,'plan',None)
                if plan:
                    leg=plan['own_route']['legs'][self.tr.seg]
                    facts['current_agreed_segment']=dict(index=self.tr.seg,distance_m=leg['distance_m'])
                    menu['carry_segment']=(menu['carry_segment'][0]+f"; expected route progress {leg['distance_m']:.3f} m (calibrated estimate)",'execute')
                if self.hazard(facts) or facts['partner_stop'] or 'slipping' in facts['own_grip']:
                    menu.pop('carry_segment')
                choice, at = self.decide(rid, now, 'carry', menu, 'carry_segment', facts)
                if choice is None:
                    ready = False
                    continue
                action = menu[choice][1]
                v = votes[rid] = dict(action=action, label=choice, t=now, ready=at,
                                      until=at + (PARAMS['hold_s'] if action != 'execute' else 0.))
            if v['action'] != 'execute' or now + 1e-8 < v['ready']:
                ready = False
        if not ready or not d.allowed(d.key,now):
            return False
        before = {id(c) for _, _, c in self.tr.queue}
        started = orig(now)
        if started:
            for _, _, c in self.tr.queue:
                if id(c) not in before:
                    self.approved.add(id(c))
            self.carry_votes.pop(key, None)
        return started

    # -------------------------------------------------------------- summary
    def summary(self):
        rows = self.rows
        ok = [r for r in rows if r['status'] == 'ok']
        lat = [r['latency_s'] for r in ok if r['latency_s']]
        cost = sum(float((r.get('usage') or {}).get('cost') or 0.) for r in ok)
        tokens = sum(int((r.get('usage') or {}).get('input_tokens') or 0) for r in ok)
        by = {}
        for r in rows:
            k = f"{r['decision']}:{r['phase']}"
            by.setdefault(k, {}).setdefault(str(r['choice']), 0)
            by[k][str(r['choice'])] += 1
        tiers = {}
        for r in ok:
            tiers[r.get('tier')] = tiers.get(r.get('tier'), 0) + 1
        return dict(stage_times=self.stage_times, memory={r:m.context(getattr(self,'last_now',0.)) for r,m in self.memory.items()}, calls=len(rows), ok=len(ok), failed=len(rows) - len(ok), tiers=tiers,
                    latency_median_s=statistics.median(lat) if lat else None,
                    latency_max_s=max(lat) if lat else None, sim_hold_total_s=sum(r['sim_hold_s'] for r in ok),
                    input_tokens=tokens, cost_usd=cost,
                    agreed_with_code_proposal=sum(1 for r in ok if r['choice'] == r['code_proposal']),
                    choices=by, suppressed_controller_commands=self.suppressed)


def install(transport, robots, bundle, out, receipt_path, root, *, send=None, append=None):
    o = bundle['e2e_options']
    if o.get('body_controller', 'off') == 'off':
        return None
    receipt = json.loads(Path(receipt_path).read_text())
    if send is None:
        validate_receipt(receipt, root, o['body_backend'])
        if o.get('body_visual_check')=='d1_v1':validate_receipt(receipt,root,'liquid_d1')
        with urllib.request.urlopen(URL.replace('/v1/body/decide', '/identity'), timeout=5) as r:
            if json.load(r) != receipt:
                raise ValueError('LIVE_BODY_RELAY_IDENTITY_REQUIRED')
    profiles = json.loads((Path(root) / 'configs/s2_v133_full_template.json').read_text())['pulse_calibration']['profiles']
    client = Client(o['body_backend'], out.parent.name, send=send)
    path = Path(out) / 'body-decisions.jsonl'

    def record(row):
        if append is not None:
            append(row)
            return
        with path.open('a') as f:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
    gate = BodyGate(transport, robots, client, profiles=profiles, record=record)
    gate.visual_check=o.get('body_visual_check','off')
    transport.body_gate = gate
    transport.body_controller = OPTION
    return gate
