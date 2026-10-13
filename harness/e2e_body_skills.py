"""Opt-in bounded feedback skills; Jev chooses a skill, code closes its loop.

The immutable v335-v337 pulse policy remains available. These new bundles use
the same own-input, agreement and candidate safety gates, with a new decision
after skill completion, a changed phase, lost visual target, or a safety stop.
No simulator prediction or hidden command chooser is added.
"""
import copy
import math

from harness.e2e_body_controller import BodyGate, stop_like
from harness import e2e_body_semantics as sem

OPTION = 'bounded_v1'
PARAMS = dict(mapping_s=3., approach_s=3., fine_s=2., max_translation_m=.15,
              max_rotation_deg=35., fresh_rgb_s=1., recovery_cooldown_s=20.)


def compose(bundle, option='off'):
    if option == 'off':
        return ()
    if option != OPTION or bundle['execution_bundle_id'] not in ('e2e18-v335','e2e18-v336'):
        raise ValueError('BODY_SKILLS_REQUIRE_V335_OR_V336')
    parent=bundle['execution_bundle_id']
    version=344 if parent=='e2e18-v336' else 345
    bundle.update(body_skills_parent=parent, body_skill_parameters=copy.deepcopy(PARAMS),
                  execution_bundle_id=f'e2e18-v{version}', workflow_version=f'7.{version-107}.0',
                  schema=f'ugrp.e2e_ownmap_live.v{version}')
    bundle['e2e_options']['body_skills']=option
    return ('harness/e2e_body_skills.py',f'configs/simulation_workflows.d/e2e18_v{version}.json')


def parent_for_validation(bundle):
    expected={'e2e18-v344':'e2e18-v336','e2e18-v345':'e2e18-v335'}
    if (bundle.get('body_skills_parent')!=expected.get(bundle['execution_bundle_id'])
            or bundle['e2e_options'].get('body_skills')!=OPTION
            or bundle.get('body_skill_parameters')!=PARAMS):
        raise ValueError('REGISTERED_BODY_SKILLS_REQUIRED')
    parent=copy.deepcopy(bundle)
    parent['execution_bundle_id']=parent.pop('body_skills_parent')
    parent.pop('body_skill_parameters');parent['e2e_options'].pop('body_skills')
    return parent


class SkillsBodyGate(BodyGate):
    def context(self,rid,now):
        facts=super().context(rid,now)
        robot=self.robots[rid];cache=getattr(self,'skill_peer_cache',{})
        self.skill_peer_cache=cache
        frame=(getattr(robot,'beam_observation',None) or {}).get('rgb') or {}
        key=(frame.get('sha256'),tuple(sorted(robot.servo.items())))
        if rid not in cache or cache[rid][0]!=key:
            cache[rid]=(key,sem.peer_appearance_v2(self.image(rid),robot.servo))
        facts['peer_in_own_rgb']=sem.peer_for_path(cache[rid][1],getattr(robot,'nav_command',{}))
        facts['own_pose_estimate']=list(map(float,robot.goal.explorer.local_pose))
        from harness.visual_arm import camera_extrinsics
        try:
            _,axes=camera_extrinsics(robot.servo)
            yaw=math.degrees(math.atan2(axes[2][1],axes[2][0]))
        except (KeyError,ValueError,TypeError):yaw=None
        facts['camera_commanded_posture']=dict(servo=dict(robot.servo),optical_axis_bearing_deg=yaw,
            source='fixed camera calibration plus own issued commands; not measured joints',
            convention='Image centre follows the commanded camera optical axis; it need not equal body heading when panned.')
        peer=facts['peer_in_own_rgb']
        facts['blocking_observation']=(f"Own RGB orange robot-like region: {peer['direction']}, {peer['distance']}; "
            f"planned path {peer['path_direction']}; overlap {peer['in_path']}. Appearance is not peer identity or metric range.")
        rows=[r for r in self.rows if r['robot_id']==rid and r['phase']==self.tr.state][-3:]
        waits={'stop_and_look','hold_and_reobserve','wait_and_reobserve','hold_and_wait','wait'}
        repeated=len(rows)==3 and len({r['choice'] for r in rows})==1 and rows[0]['choice'] in waits
        def unchanged(row):
            old=row['facts'];a=old.get('target_distance_m');b=facts.get('target_distance_m')
            distance=(a is None and b is None) or (a is not None and b is not None and abs(a-b)<.01)
            poses=old.get('own_pose_estimate'),facts['own_pose_estimate']
            pose_same=poses[0] is None or (math.dist(poses[0][:2],poses[1][:2])<.02 and abs((poses[0][2]-poses[1][2]+math.pi)%(2*math.pi)-math.pi)<math.radians(3))
            return old.get('visual_category')==facts['visual_category'] and distance and pose_same
        facts['blocked_persistently']=bool(repeated and all(unchanged(r) for r in rows))
        if facts['blocked_persistently']:
            facts['blocking_observation']+=' Blockage persists: the same wait choice three times changed neither the visual category nor the estimated target/pose. Select an available detour or back-off strategy.'
        return facts

    def motion_safe(self,command,facts):
        current=dict(facts,peer_in_own_rgb=sem.peer_for_path(facts['peer_in_own_rgb'],command))
        if not super().motion_safe(command,current):return False
        peer=current['peer_in_own_rgb']
        return not (command.get('kind')=='mecanum' and (command.get('forward') or command.get('left'))
                    and peer.get('visible') and peer.get('distance')=='near' and peer.get('in_path'))

    def decide(self,rid,now,kind,menu,proposal_label=None,facts=None):
        facts=facts if facts is not None else self.facts(rid,now)[0]
        self.memory[rid].finish_pending(now,facts['visual_category'],facts['target_distance_m'],'observed_before_next_skill')
        facts.update(self.memory[rid].context(now))
        if proposal_label not in menu:
            proposal_label=next((k for k in menu if k.startswith(('detour_','back_off','recover_'))),next(iter(menu)))
        return super().decide(rid,now,kind,menu,proposal_label,facts)

    def menu_direct(self,rid,now,proposal):
        if self.tr.state not in ('mapping','align') or any(c.get('kind') in ('arm','look') for c in proposal):
            facts,_,_=self.facts(rid,now)
            script=[(0.,copy.deepcopy(c)) for c in proposal]
            duration=max([c.get('duration_s',0.) for c in proposal]+[.6])
            menu={'re_observe':('Execute the planned own-camera observation/positioning skill, then inspect a fresh image. '+
                                '; '.join(sem.effect_of(c) for c in proposal),('script',duration,script)),
                  'wait_and_reobserve':('Hold still briefly to inspect a fresh own image before repositioning.',('script',1.,[]))}
            safe=self.safe_menu(rid,now,menu,facts)
            if facts['blocked_persistently'] and 're_observe' in safe:safe.pop('wait_and_reobserve',None)
            return safe,'re_observe' if 're_observe' in safe else next(iter(safe)),facts
        facts,_,_=self.facts(rid,now)
        visual=facts['visual_category']
        fine=bool(self.tr.approach.get(rid,{}).get('fine'))
        menu={}
        if self.tr.state=='mapping':
            label='follow_own_path'
            description='Follow the current own-RGB map exploration goal with feedback for up to 3 SIM seconds; stop at a new camera view, blockage or phase change. Expected effect: cover a new viewpoint and build own map; no beam alignment yet.'
            mode='skill_mapping';duration=PARAMS['mapping_s']
        elif fine and visual not in ('not_visible','unknown'):
            label='align_visible_end'
            description='Use fresh own-RGB visual servo feedback to reduce the grasp distance, side and angle errors for up to 2 SIM seconds; stop immediately if the end is lost or ready. Expected effect: the same banded end moves into grasp tolerance.'
            mode='skill_fine';duration=PARAMS['fine_s']
        else:
            label='approach_own_standoff'
            description='Follow the current own-map approach to the remembered standoff with own camera feedback for up to 3 SIM seconds; stop at standoff, new view, blockage or phase change. Expected effect: reduce standoff distance while preserving a wide view.'
            mode='skill_approach';duration=PARAMS['approach_s']
        # Executability is evaluated on the current proposed first action; every
        # later feedback command is rechecked against own RGB/range/map below.
        if proposal and (self.tr.state=='mapping' or facts['own_map']['standoff'] is not None or fine):
            menu[label]=(description,(mode,duration,[(0.,copy.deepcopy(c)) for c in proposal]))
        for side in ('left','right'):
            menu['detour_'+side]=(f'Sidestep {side} away from an overlapping partner/obstacle with four calibrated short pulses, then replan from the new own RGB and own map; stop if blocked. Expected effect: create lateral clearance; no forward approach toward the obstacle.',
                                  ('script',1.,[(i*.2,sem.pulse('strafe_'+side+'_small')) for i in range(4)]))
        menu['back_off_and_replan']=('Back up about 8 cm using six short pulses, then re-observe the whole beam and replan the own-map path; no claim that the motion succeeded.',
                                    ('script',1.6,[(i*.25,sem.pulse('back_short')) for i in range(6)]))
        last=facts['last_seen_bearing_deg']
        for sign,name in ((1,'left'),(-1,'right')):
            if last is not None and sign*last<0:continue
            menu['scan_'+name]=(f'Rotate {name} about 25 degrees toward the last seen end / a new map view, then observe.',
                               ('script',1.,[(i*.2,sem.pulse('turn_'+name+'_small')) for i in range(5)]))
        menu['hold_and_reobserve']=('Hold still for a fresh own image before choosing a skill.',('script',1.,[]))
        facts['decision_unit']='Select one bounded feedback skill, not individual motor pulses. Candidate durations and effects below are authoritative. A safety event ends the skill.'
        safe=self.safe_menu(rid,now,menu,facts)
        if facts['blocked_persistently'] and any(item[1][2] for item in safe.values()):
            safe={k:v for k,v in safe.items() if v[1][2]}
        # Six executable skills at most. Keep both feasible detours and hold;
        # drop redundant scan directions first.
        while len(safe)>6:
            key=next((k for k in reversed(safe) if k.startswith('scan_')),next(reversed(safe)))
            safe.pop(key)
        label=label if label in safe else next((k for k in safe if k.startswith(('detour_','back_off','recover_'))),next(iter(safe)))
        return safe,label,facts

    def filter(self,now,commands):
        for rid,c in commands:
            if id(c) in self.approved and c.get('kind') in ('arm','look'):
                self.units.pop(rid,None);self.pending.pop(rid,None)
        return super().filter(now,commands)

    def _robot(self,rid,now,moves):
        pending=self.pending.get(rid)
        if pending is not None and now+1e-8>=pending['ready_at'] and pending['executor'][0].startswith('skill_'):
            mode,duration,_=pending['executor']
            self.pending.pop(rid)
            robot=self.robots[rid]
            self.units[rid]=dict(mode=mode,start=now,until=now+duration,script=[],sent=set(),label=pending['label'],
                                start_pose=tuple(float(x) for x in robot.goal.explorer.local_pose),
                                fine=bool(self.tr.approach.get(rid,{}).get('fine')))
        unit=self.units.get(rid)
        if unit is None or not unit['mode'].startswith('skill_'):
            return super()._robot(rid,now,moves)
        robot=self.robots[rid]
        facts=self.context(rid,now)
        pose=robot.goal.explorer.local_pose;old=unit['start_pose']
        rotated=abs(math.degrees(math.atan2(math.sin(pose[2]-old[2]),math.cos(pose[2]-old[2]))))
        visual_lost=(unit['mode']=='skill_fine' and facts['visual_category'] in ('not_visible','unknown'))
        stale=facts['visual_age_s'] is None or facts['visual_age_s']>PARAMS['fresh_rgb_s']
        changed=unit['fine']!=bool(self.tr.approach.get(rid,{}).get('fine'))
        unsafe=any(not self.motion_safe(c,facts) or not self.map_safe(rid,c) for c in moves)
        stop=(now>=unit['until']-1e-8 or visual_lost or stale or changed or unsafe
              or math.dist(pose[:2],old[:2])>=PARAMS['max_translation_m'] or rotated>=PARAMS['max_rotation_deg'])
        # Arm/camera positioning is its own model-selected batch, never an
        # accidental side effect of a navigation skill.
        if any(c.get('kind') in ('arm','look') for c in moves):stop=True
        if stop:
            self.units.pop(rid,None)
            self.memory[rid].finish_pending(now,facts['visual_category'],facts['target_distance_m'],
                'interrupted' if visual_lost or stale or changed or unsafe else 'bounded_skill_finished')
            return [dict(kind='hold')]
        return [copy.deepcopy(c) for c in moves if c.get('kind')=='mecanum' and not stop_like(c)]
