"""Default-off finite retry clocks for event admission."""
import copy

VERSIONS = {('e2e18-v369','tick_v1'):375, ('e2e18-v371','tick_v1'):376,
            ('e2e18-v369','deadline_v1'):377, ('e2e18-v371','deadline_v1'):378}
PARAMETERS = dict(tick_seconds=0.000001, deadline_tolerance_s=1e-9,
                  boundary='admit_at_deadline', same_timestamp_retry='forbidden')


def pending(now, last, interval, option='off'):
    if option == 'off':
        return now-last < interval, last+interval
    if option == 'tick_v1':
        due_tick=round(last*1_000_000)+round(interval*1_000_000)
        return round(now*1_000_000)<due_tick, due_tick/1_000_000
    if option == 'deadline_v1':
        due=round(last+interval,9)
        return now < due-1e-9, due
    raise ValueError('UNKNOWN_ADMISSION_CLOCK')


def install(trial, option='off'):
    if option == 'off': return
    if option not in ('tick_v1','deadline_v1') or trial.dialogue_call_policy!='event_v1':
        raise ValueError('ADMISSION_CLOCK_REQUIRES_EVENT_V1')
    trial.call_events.interval_clock=option
    trial.provenance['admission_clock']=dict(option=option,**PARAMETERS)


def compose(bundle,option='off'):
    if option == 'off': return ()
    parent=bundle['execution_bundle_id'];version=VERSIONS.get((parent,option))
    if version is None: raise ValueError('ADMISSION_CLOCK_REQUIRES_REGISTERED_PARENT')
    bundle['admission_clock_parent']=parent;bundle['admission_clock_parameters']=dict(PARAMETERS)
    bundle['e2e_options']['admission_clock']=option
    bundle.update(execution_bundle_id=f'e2e18-v{version}',schema=f'ugrp.e2e_ownmap_live.v{version}',workflow_version=f'7.{version-107}.0')
    return ('harness/e2e_admission_clock.py',f'configs/simulation_workflows.d/e2e18_v{version}.json')


def parent_for_validation(bundle):
    old=copy.deepcopy(bundle);parent=old.get('admission_clock_parent');option=old['e2e_options'].get('admission_clock')
    version=VERSIONS.get((parent,option))
    if version is None or old['execution_bundle_id']!=f'e2e18-v{version}' or old.get('admission_clock_parameters')!=PARAMETERS:
        raise ValueError('REGISTERED_ADMISSION_CLOCK_REQUIRED')
    old['execution_bundle_id']=old.pop('admission_clock_parent');old.pop('admission_clock_parameters');old['e2e_options'].pop('admission_clock');return old
