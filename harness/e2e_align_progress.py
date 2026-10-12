"""Default-off DEV timeout continuation and fresh-camera pregrasp recovery."""
from harness.owncam_pair_beam_v2 import pose_of
OPTION='dev_continue_v1'
SEARCH='bounded_search_v1'
WORKFLOW='configs/simulation_workflows.d/e2e18_v229.json'


def lost_search(transport,rid,now,state):
    # A fresh own beam immediately cancels this state in the caller.
    started=state.setdefault('search_started',now)
    sequence=(('search',1500),('p45',1500),('inspect',1500),('search',1250),('search',1750))
    step=int((now-started)//1.2);index=step%len(sequence)
    tag,pan=sequence[index];pose=pose_of(tag);pose[6]=pan
    robot=transport.robots[rid]
    robot.carrier_approach.update(status='reacquire_own_beam',search_index=index,camera=tag,pan_pulse=pan)
    if state.get('search_step')!=step:
        state['search_step']=step
        transport._poses(rid,now,[(pose,.3,.6)])
        transport.event(now,'own_beam_search_view',robot_id=rid,camera=tag,pan_pulse=pan)
    return False,[dict(kind='hold')]


def compose(bundle,option,recovery):
    if option=='off' and recovery=='off':return ()
    if option!=OPTION or recovery!=SEARCH or bundle['execution_bundle_id']!='e2e18-v228' or not bundle['e2e_options'].get('dev_light'):
        raise ValueError('ALIGN_PROGRESS_REQUIRES_DEV_V228')
    bundle['e2e_options'].update(align_progress=option,pregrasp_recovery=recovery)
    bundle.update(schema='ugrp.e2e_ownmap_live.v229',execution_bundle_id='e2e18-v229',workflow_version='7.122.0')
    return (WORKFLOW,)
