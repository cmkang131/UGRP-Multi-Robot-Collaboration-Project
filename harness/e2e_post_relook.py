"""DEV waypoint continuation without inventing a localization receipt.

The approved route cursor survives a failed observation task, as in Nav2's
waypoint task policy. Fresh pair alignment and current epoch GO/ACK still gate
every new grasp/carry. Final opening still requires the original RGB B gate.
"""
import copy
from harness.e2e_setdown_relook import boundary_reasons

VERSIONS={'retain_route_v1':320,'carry_through_v1':321,'map_fast_v1':322,'carry_nominal_v1':323}
PARAMS={'retain_route_v1':dict(wait_s=60.,remaining_route=True,skip_intermediate=False),
        'carry_through_v1':dict(wait_s=30.,remaining_route=True,skip_intermediate=True),
        'map_fast_v1':dict(wait_s=30.,remaining_route=False,skip_intermediate=False),
        'carry_nominal_v1':dict(wait_s=30.,remaining_route=True,skip_intermediate=True,nominal_final_margin=True)}


def compose(bundle,option):
    if option=='off':return ()
    if option not in VERSIONS or bundle['execution_bundle_id']!='e2e18-v304' or not bundle['e2e_options']['dev_light']:
        raise ValueError('POST_RELOOK_REQUIRES_DEV_V304')
    v=VERSIONS[option];bundle['e2e_options']['post_relook']=option
    bundle['post_relook_parameters']=copy.deepcopy(PARAMS[option])
    bundle.update(schema=f'ugrp.e2e_ownmap_live.v{v}',execution_bundle_id=f'e2e18-v{v}',workflow_version=f'7.{v-107}.0')
    return (f'configs/simulation_workflows.d/e2e18_v{v}.json',)


def parent_for_validation(bundle):
    mode=bundle['e2e_options'].get('post_relook')
    if mode not in VERSIONS or bundle['execution_bundle_id']!=f'e2e18-v{VERSIONS[mode]}' or bundle.get('post_relook_parameters')!=PARAMS[mode] or not bundle['e2e_options'].get('dev_light'):
        raise ValueError('REGISTERED_POST_RELOOK_REQUIRED')
    old=copy.deepcopy(bundle);old['execution_bundle_id']='e2e18-v304'
    old['e2e_options'].pop('post_relook');old.pop('post_relook_parameters')
    return old


def legacy_giveup(tr,now):
    from harness.e2e_relook_giveup import giveup
    tr._post_relook_dispatching=True
    try:return giveup(tr,now)
    finally:tr._post_relook_dispatching=False


def continue_after_task(tr,now):
    marker=getattr(tr,'post_relook_final_permission',None)
    final=tr.plan is not None and tr.seg==len(tr.plan['own_route']['legs'])-1
    if final and marker and marker['key']==list(tr.dialogue.key or ()):
        clear_pending(tr,now)
        tr.event(now,'final_relook_task_skipped',correction_applied=False,
                 permission=copy.deepcopy(marker),success_source='separate_post_run_evaluator')
        tr.done=True;tr.set('done',now)
        return [(r,dict(kind='hold')) for r in ('r1','r2')]
    mode=tr.post_relook_mode;d=tr.dialogue
    if (not PARAMS[mode]['remaining_route'] or final or tr.plan is None or not d.approved
            or d.claims!={'r1','r2'} or d.proposal is None
            or d.proposal['route']['route_hash']!=tr.plan['agreement_route_hash']):
        return legacy_giveup(tr,now)
    old_seg=tr.seg;clear_pending(tr,now)
    d.key=None;d.votes={};tr.permit=None
    tr.seg+=1;tr.first_seg=tr.seg;tr.aligned={};tr.approach={}
    # Keep all installed capture guards; reset only their temporal streak.
    from harness.zone_s3_settled_servo import SettleGate
    for servo in tr.align.values():
        servo.gate=SettleGate();servo.last_frame=None;servo.streak=0;servo.chosen=None
    tr.event(now,'remaining_approved_route_retained',previous_seg=old_seg,next_seg=tr.seg,
             route_hash=tr.plan['agreement_route_hash'],correction_applied=False,
             requires_fresh_alignment=True,requires_new_GO_ACK=True)
    tr.set('align',now)
    return [(r,dict(kind='hold')) for r in ('r1','r2')]


def clear_pending(tr,now):
    for rid in ('r1','r2'):
        rl=tr.robots[rid].goal.e2e_relook
        rl.emit(dict(event='e2e_relook_task_skipped',t=now,seg=tr.seg,epoch=tr.epoch,
                     correction_applied=False,mode=tr.post_relook_mode))
        rl.pending=None;rl.receipt=None
    tr.event(now,'would_stop',reason='OWN_RGB_METRIC_CORRECTION_TIMEOUT',dev_light=True,
             state=tr.state,correction_applied=False)


def install(tr,option='off'):
    if option=='off':return tr
    if option not in VERSIONS or not tr.dev_light:raise ValueError('POST_RELOOK_DEV_ONLY')
    tr.post_relook_mode=option;tr.post_relook_wait_s=PARAMS[option]['wait_s']
    tr.post_relook_handler=continue_after_task
    goal=tr.robots['r1'].goal;ready=goal.setdown_ready
    if option=='carry_nominal_v1':goal.e2e_dev_nominal_setdown=True
    def setdown_checked(*args,**kwargs):
        accepted=ready(*args,**kwargs)
        if accepted and tr.state=='final_lower_go_ack':
            tr.post_relook_rgb_permission=dict(key=list(kwargs['agreement'].key),t=kwargs['now'])
        return accepted
    goal.setdown_ready=setdown_checked
    lower=tr._lower
    def lowered(now):
        rgb=getattr(tr,'post_relook_rgb_permission',None)
        if (tr.state=='final_lower_go_ack' and tr.dialogue.allowed(tr.dialogue.key,now)
                and rgb and rgb['key']==list(tr.dialogue.key) and rgb['t']==now):
            # This internal call follows setdown_ready's RGB polygon and fresh
            # revised agreement checks. No other _lower call can mint this mark.
            tr.post_relook_final_permission=dict(key=list(tr.dialogue.key),t=now,
                source='original_setdown_ready_RGB_and_current_GO_ACK')
        return lower(now)
    tr._lower=lowered
    after=tr._after_carry
    def after_carry(now):
        if PARAMS[option]['skip_intermediate'] and tr.seg<len(tr.plan['own_route']['legs'])-1:
            reasons=boundary_reasons(tr.plan['own_route'],tr.first_seg,tr.seg,tr.robots['r1'].goal.pose_covariance())
            if reasons:tr.event(now,'would_stop',reason='INTERMEDIATE_RELOOK_TASK',reasons=reasons,dev_light=True)
            tr.seg+=1;tr._open_epoch(now)
            return
        return after(now)
    tr._after_carry=after_carry
    return tr
