"""Default-off source-replay to staged-baseline policy handoff, without map reset."""
import copy

OPTION = 'baseline_v1'
# These are constructor-time perceptual/estimator policies. A change requires a
# separate tested state migration; this adapter never silently rebuilds a map.
CONSTRUCTION = ('exploration_progress','pose_fix','path_follow','stall_odometry',
    'stall_recovery','stall_noise','mapping_budget_s','boundary_views','boundary_frame',
    'b_marker_detect','b_partial_accept','vo_floor_mask','vo_rotation_policy',
    'explore_deadlock','boundary_association','boundary_retry','boundary_coverage',
    'beam_end_model','beam_decode','speed4','speed5','exact_speedups')


def install(robots, source_options, baseline_options, option='off'):
    if option == 'off':
        return {'option': 'off', 'applied': False}
    if option != OPTION:
        raise ValueError('UNKNOWN_STAGE_POLICY_HANDOFF')
    changed = [k for k in CONSTRUCTION if source_options.get(k, 'off') != baseline_options.get(k, 'off')]
    if changed:
        raise ValueError('UNSUPPORTED_STAGE_STATE_MIGRATION:' + ','.join(changed))
    from harness.e2e_explore_idle import install as idle_install
    from harness.e2e_explore_deadlock import PARAMS
    before = {rid: dict(body_controller=getattr(r, 'body_controller', 'off'),
        idle_s=getattr(getattr(r.goal, 'explore_deadlock', None), 'idle_threshold_s', None))
        for rid, r in robots.items()}
    # Off means the baseline default, not the source run's old override.
    for rid, r in robots.items():
        r.body_controller = baseline_options.get('body_controller', 'off')
        r.decider = baseline_options.get('decider', 'off')
        if rid in ('r1', 'r2') and hasattr(r.goal, 'explore_deadlock'):
            r.goal.explore_deadlock.idle_threshold_s = PARAMS['idle_s']
    idle_install(robots, baseline_options.get('explore_idle', 'off'))
    after = {rid: dict(body_controller=r.body_controller,
        idle_s=getattr(getattr(r.goal, 'explore_deadlock', None), 'idle_threshold_s', None))
        for rid, r in robots.items()}
    return dict(option=option, applied=True, before=before, after=after,
                state_reset=False, baseline_explore_idle=baseline_options.get('explore_idle','off'))
