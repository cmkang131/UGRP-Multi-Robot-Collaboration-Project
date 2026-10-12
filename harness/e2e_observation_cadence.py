"""Default-off synchronization of estimator freshness with configured RGB cadence.

Only the fixed acquisition schedule changes the maximum pair interval.
Measurement age, monotonicity, quality, uncertainty and motion checks remain.
"""
OPTION='on_v1'
BUNDLE_ID='e2e18-v220'
WORKFLOW='configs/simulation_workflows.d/e2e18_v220.json'


def limits(period):
    if period not in (.2,.4):raise ValueError('UNREGISTERED_RGB_CADENCE')
    return dict(observation_period_s=period,max_pair_gap_s=period+.05,max_range_gap_s=period+.05)


def configure(goal,option,period):
    if option=='off':return
    if option!=OPTION:raise ValueError('UNKNOWN_OBSERVATION_CADENCE')
    spec=limits(period)
    vo=goal.e2e_vo
    vo.max_pair_gap_s=spec['max_pair_gap_s']
    if vo.range_stall is not None:vo.range_stall.max_gap_s=spec['max_range_gap_s']


def compose(bundle,option):
    if option=='off':return ()
    if option!=OPTION or bundle['execution_bundle_id']!='e2e18-v219':
        raise ValueError('CADENCE_REQUIRES_E2E18_V219')
    bundle['e2e_options']['observation_cadence']=option
    bundle['estimator_cadence']=limits(bundle['speed3_profile']['observation_period_s'])
    bundle.update(schema='ugrp.e2e_ownmap_live.v220',execution_bundle_id=BUNDLE_ID,workflow_version='7.113.0')
    return (WORKFLOW,)
