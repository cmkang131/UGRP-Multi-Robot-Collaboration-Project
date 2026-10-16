"""Opt-in ownership repair when an active own-RGB viewpoint loses its target."""
import copy
import math
import numpy as np

VERSIONS = {('e2e18-v347','abort_v1'):352, ('e2e18-v348','abort_v1'):353,
            ('e2e18-v350','abort_v1'):354, ('e2e18-v350','restore_v1'):355}


def compose(bundle, option='off'):
    if option == 'off': return ()
    parent = bundle['execution_bundle_id']; version = VERSIONS.get((parent, option))
    if version is None: raise ValueError('REGISTERED_RULE_PARENT_REQUIRED_BEFORE_BOUNDARY_LIFECYCLE')
    bundle['boundary_lifecycle_parent'] = parent
    bundle['e2e_options']['boundary_lifecycle'] = option
    bundle['boundary_lifecycle_parameters'] = dict(missing_target=option, preserve_map_pose=True,
                                                 revalidate_current_coverage=True)
    bundle.update(execution_bundle_id=f'e2e18-v{version}', schema=f'ugrp.e2e_ownmap_live.v{version}',
                  workflow_version=f'7.{version-107}.0')
    return ('harness/e2e_boundary_lifecycle.py',f'configs/simulation_workflows.d/e2e18_v{version}.json')


def parent_for_validation(bundle):
    option = bundle['e2e_options'].get('boundary_lifecycle'); parent = bundle.get('boundary_lifecycle_parent')
    version = VERSIONS.get((parent, option))
    if (version is None or bundle['execution_bundle_id'] != f'e2e18-v{version}'
            or bundle.get('boundary_lifecycle_parameters') != dict(missing_target=option, preserve_map_pose=True,
                                                                  revalidate_current_coverage=True)):
        raise ValueError('REGISTERED_BOUNDARY_LIFECYCLE_REQUIRED')
    old = copy.deepcopy(bundle); old['execution_bundle_id'] = old.pop('boundary_lifecycle_parent')
    old.pop('boundary_lifecycle_parameters'); old['e2e_options'].pop('boundary_lifecycle')
    return old


def install_navigator(navigator, option='off'):
    if option == 'off': return
    if option not in ('abort_v1','restore_v1'): raise ValueError('UNKNOWN_BOUNDARY_LIFECYCLE')
    update = navigator.update
    def updated(costmap, pose, t, static_goal=None):
        n = navigator
        if n.view_active and n.target is None:
            own = n.view_target_own
            if (option == 'restore_v1' and own is not None and np.shape(own) == (2,)
                    and np.isfinite(own).all() and math.isfinite(n.heading)):
                from harness.self_odom_grid import transform
                # Re-express the already observed, owned viewpoint in the
                # current estimated frame. Original update checks coverage/path.
                n.target = transform([own], n.goal.explorer.map_to_odom)[0]
                n.event(t, 'B_view_owned_target_restored', target=n.target.tolist())
            else:
                n.end_view(t, 'B_view_external_target_invalidated')
                n.last_view_search = t
        return update(costmap, pose, t, static_goal)
    navigator.update = updated


def install(robots, option='off'):
    if option == 'off': return
    for rid in ('r1','r2'):
        install_navigator(robots[rid].goal.explorer.navigator, option)
