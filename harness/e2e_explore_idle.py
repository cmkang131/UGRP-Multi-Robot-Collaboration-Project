"""Default-off, per-run retry interval for the existing own-map recovery."""
import copy

PARENT = 'e2e18-v346'
OPTIONS = {'idle5_v1': (347, 5.), 'idle10_v1': (348, 10.)}


def compose(bundle, option='off'):
    if option == 'off':
        return ()
    if (option not in OPTIONS or bundle['execution_bundle_id'] != PARENT
            or bundle['e2e_options'].get('explore_deadlock') != 'replan_v1'
            or bundle['e2e_options'].get('body_controller', 'off') != 'off'
            or bundle['e2e_options'].get('dialogue_decider') != 'code_v1'):
        raise ValueError('CODE_PROTOCOL_V346_REQUIRED_BEFORE_IDLE_COMPARISON')
    version, seconds = OPTIONS[option]
    bundle['explore_idle_parent'] = PARENT
    bundle['e2e_options']['explore_idle'] = option
    bundle['explore_idle_parameters'] = dict(idle_s=seconds, scope='own issued hold; no map or pose reset')
    bundle.update(execution_bundle_id=f'e2e18-v{version}', schema=f'ugrp.e2e_ownmap_live.v{version}',
                  workflow_version=f'7.{version-107}.0')
    return ('harness/e2e_explore_idle.py', 'harness/e2e_explore_deadlock.py',
            f'configs/simulation_workflows.d/e2e18_v{version}.json')


def parent_for_validation(bundle):
    option = bundle['e2e_options'].get('explore_idle')
    if option not in OPTIONS:
        raise ValueError('REGISTERED_EXPLORE_IDLE_REQUIRED')
    version, seconds = OPTIONS[option]
    if (bundle['execution_bundle_id'] != f'e2e18-v{version}' or bundle.get('explore_idle_parent') != PARENT
            or bundle.get('explore_idle_parameters') != dict(idle_s=seconds, scope='own issued hold; no map or pose reset')):
        raise ValueError('REGISTERED_EXPLORE_IDLE_REQUIRED')
    parent = copy.deepcopy(bundle)
    parent['execution_bundle_id'] = parent.pop('explore_idle_parent')
    parent.pop('explore_idle_parameters'); parent['e2e_options'].pop('explore_idle')
    return parent


def install(robots, option='off'):
    if option == 'off':
        return
    if option not in OPTIONS:
        raise ValueError('UNKNOWN_EXPLORE_IDLE')
    for rid in ('r1', 'r2'):
        robots[rid].goal.explore_deadlock.idle_threshold_s = OPTIONS[option][1]
