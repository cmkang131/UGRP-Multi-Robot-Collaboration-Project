"""Default-off stage cadence and stale own-target retirement."""
MAPPING='0p6_v1'
STALE='expire12_v1'
WORKFLOW='configs/simulation_workflows.d/e2e18_v237.json'
PROFILE=dict(mapping_s=.6,other_s=.4,max_mapping_pair_gap_s=.65)


def period(option,phase,baseline=.4):
    if option=='off':return baseline
    if option!=MAPPING:raise ValueError('UNKNOWN_MAPPING_CADENCE')
    return .6 if phase=='mapping' else .4


def expire(tr,rid,now,state,fresh):
    if getattr(tr,'stale_station','off')=='off':return False
    if tr.stale_station!=STALE:raise ValueError('UNKNOWN_STALE_STATION')
    if fresh or 'station' not in state or now-state.get('last_seen',now)<=12.:return False
    tr.event(now,'own_stale_station_retired',robot_id=rid,last_seen_age_s=now-state['last_seen'],
             station_own_m=list(state['station']),source='own_rgb_target_expiry')
    keep={k:state[k] for k in ('frame','fine') if k in state}
    state.clear();state.update(keep)
    return True


def compose(bundle,cadence,stale):
    if cadence=='off' and stale=='off':return ()
    if cadence!=MAPPING or stale!=STALE or bundle['execution_bundle_id']!='e2e18-v236':
        raise ValueError('MAPPING_CADENCE_REQUIRES_V236')
    bundle['e2e_options'].update(mapping_cadence=cadence,stale_station=stale)
    bundle['mapping_cadence_profile']=dict(PROFILE)
    bundle.update(schema='ugrp.e2e_ownmap_live.v237',execution_bundle_id='e2e18-v237',workflow_version='7.130.0')
    return (WORKFLOW,)
