"""Opt-in safe fallback candidates after a rejected recovery; own inputs only."""
import copy

VERSIONS={('e2e18-v376','alternatives_v1'):379,('e2e18-v376','skip_rejected_v1'):380}
PARAMETERS=dict(safety_filters='unchanged',fallback='original_safe_motion_candidates',max_recovery_checks=8,
                rejected_is_executed=False,required_hold='preserved')


def executable(gate,rid,item,facts):
    if not isinstance(item[1],tuple):return False
    script=item[1][2]
    if facts['visual_category']=='not_visible' and facts['last_seen_bearing_deg'] is not None:
        pan=gate.robots[rid].servo.get(6,1500)
        if any(c.get('kind')=='look' and (c['pan_pulse']-pan)*facts['last_seen_bearing_deg']<0 for _,c in script):return False
    return all(gate.motion_safe(c,facts) and gate.map_safe(rid,c) for _,c in script)


def install(gate,option='off'):
    if option=='off':return
    if gate is None or option not in ('alternatives_v1','skip_rejected_v1'):raise ValueError('RECOVERY_MENU_REQUIRES_BODY_GATE')
    recovery,original_safe=gate.recovery,gate.safe_menu
    if option=='skip_rejected_v1':
        def next_safe(rid,now,facts):
            local=copy.deepcopy(facts);seen=[]
            for _ in range(PARAMETERS['max_recovery_checks']):
                candidate=recovery(rid,now,local)
                if candidate is None or candidate[0] in seen:break
                if executable(gate,rid,candidate[1],facts):
                    facts['safety_rejected_recovery_candidates']=seen
                    return candidate
                seen.append(candidate[0]);local['recovery_strategies_tried'].append(candidate[0])
            facts['safety_rejected_recovery_candidates']=seen
            return None
        gate.recovery=next_safe
    def safe_menu(rid,now,menu,facts):
        safe=original_safe(rid,now,menu,facts)
        must_wait=facts['partner_stop'] or 'slipping' in facts['own_grip'] or (facts['holding_command'] and not facts['go_ack_complete'])
        if must_wait:
            return {'hold_and_reobserve':('Required own-grip/partner/agreement safety hold.',('script',1.,[]))}
        if (facts.get('strategy_switch_required') and not must_wait
                and not any(isinstance(v[1],tuple) and v[1][2] for v in safe.values())):
            alternatives={k:v for k,v in menu.items() if isinstance(v[1],tuple) and v[1][2] and executable(gate,rid,v,facts)}
            if alternatives:
                safe.update(alternatives)
                facts.update(strategy_switch_required=False,recovery_menu_fallback=option,
                             recovery_menu_candidates=list(alternatives))
        return safe
    gate.safe_menu=safe_menu


def compose(bundle,option='off'):
    if option=='off':return ()
    parent=bundle['execution_bundle_id'];v=VERSIONS.get((parent,option))
    if v is None:raise ValueError('RECOVERY_MENU_REQUIRES_REGISTERED_PARENT')
    bundle['recovery_menu_parent']=parent;bundle['recovery_menu_parameters']=dict(PARAMETERS)
    bundle['e2e_options']['recovery_menu']=option
    bundle.update(execution_bundle_id=f'e2e18-v{v}',schema=f'ugrp.e2e_ownmap_live.v{v}',workflow_version=f'7.{v-107}.0')
    return ('harness/e2e_recovery_menu.py',f'configs/simulation_workflows.d/e2e18_v{v}.json')


def parent_for_validation(bundle):
    old=copy.deepcopy(bundle);parent=old.get('recovery_menu_parent');option=old['e2e_options'].get('recovery_menu');v=VERSIONS.get((parent,option))
    if v is None or old['execution_bundle_id']!=f'e2e18-v{v}' or old.get('recovery_menu_parameters')!=PARAMETERS:raise ValueError('REGISTERED_RECOVERY_MENU_REQUIRED')
    old['execution_bundle_id']=old.pop('recovery_menu_parent');old.pop('recovery_menu_parameters');old['e2e_options'].pop('recovery_menu');return old
