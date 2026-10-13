"""Default-off request preparation at the existing call-start snapshot boundary."""
import copy

OPTION = 'prepared_v1'
VERSIONS = {f'e2e18-v{v}': v+4 for v in range(365,369)}
PARAMETERS = dict(boundary='transport.submit.snapshot', request='prepare_once_then_consume', future_state='forbidden')


def install(trial, option='off'):
    if option == 'off': return
    if option != OPTION or trial.dialogue_call_policy != 'event_v1':
        raise ValueError('CALL_SNAPSHOT_REQUIRES_EVENT_V1')
    snapshot, prepare = trial.snapshot, trial.prepare_call
    pending = {}
    def capture(call):
        snapshot(call)
        if call.call_id in pending: raise ValueError('DUPLICATE_PREPARED_SNAPSHOT')
        # Includes policy summary, protocol RGB hypotheses, dialogue and memory.
        # Original request builder still validates permitted inputs and hashes.
        pending[call.call_id] = prepare(call)
    def consume(call):
        if call.call_id not in pending: raise ValueError('PREPARED_CALL_SNAPSHOT_REQUIRED')
        return pending.pop(call.call_id)
    trial.snapshot, trial.prepare_call = capture, consume
    trial.provenance['call_snapshot'] = dict(option=option, **PARAMETERS)


def compose(bundle, option='off'):
    if option == 'off': return ()
    parent=bundle['execution_bundle_id']; version=VERSIONS.get(parent)
    if option != OPTION or version is None: raise ValueError('CALL_SNAPSHOT_REQUIRES_REGISTERED_PARENT')
    bundle['call_snapshot_parent']=parent;bundle['e2e_options']['call_snapshot']=option
    bundle['call_snapshot_parameters']=dict(PARAMETERS)
    bundle.update(execution_bundle_id=f'e2e18-v{version}',schema=f'ugrp.e2e_ownmap_live.v{version}',workflow_version=f'7.{version-107}.0')
    return ('harness/e2e_call_snapshot.py',f'configs/simulation_workflows.d/e2e18_v{version}.json')


def parent_for_validation(bundle):
    old=copy.deepcopy(bundle);parent=old.get('call_snapshot_parent')
    if (parent not in VERSIONS or old['execution_bundle_id']!=f'e2e18-v{VERSIONS[parent]}'
        or old['e2e_options'].get('call_snapshot')!=OPTION or old.get('call_snapshot_parameters')!=PARAMETERS):
        raise ValueError('REGISTERED_CALL_SNAPSHOT_REQUIRED')
    old['execution_bundle_id']=old.pop('call_snapshot_parent');old.pop('call_snapshot_parameters');old['e2e_options'].pop('call_snapshot');return old
