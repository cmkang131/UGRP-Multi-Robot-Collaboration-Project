"""S4 DEV boundary: validated claim -> one S3 own-robot API, without physics.

The fixed dev_s1lite roles are not a general allocation policy. S3 owns the
executors; S4 neither starts a runtime nor silently substitutes another robot.
"""
from harness import pair_llm_dispatch as pair
from harness.zone_study_integration import Plan

VERSION = 'ugrp.s4_llm_routing.v1'
ROBOTS = ('r1', 'r2', 'r3')


def executor_plan(action, job, *, actor, orders):
    if action.get('kind') == 'claim':
        order = next((row for row in orders if row['order_id'] == action.get('order_id')), None)
        if order is None:
            return Plan(None, rejected_reason='UNKNOWN_ORDER')
        if action.get('destination_zone') != order['destination_zone']:
            return Plan(None, rejected_reason='WRONG_DESTINATION')
        if order['kind'] == 'cyan' and order['required_robots'] == 1 and order['count'] == 1:
            if actor != 'r3' or action.get('role') != 'solo':
                return Plan(None, rejected_reason='UNSUPPORTED_SOLO_ROLE')
        elif order['kind'] != 'long_beam' or order['required_robots'] != 2 or order['count'] != 1:
            return Plan(None, rejected_reason='UNSUPPORTED_ORDER')
    if action.get('kind') in pair.decisions.HOOK_ACTIONS or action.get('kind') == pair.LOOK_AROUND:
        if actor not in ('r1', 'r2'):
            return Plan(None, rejected_reason='PAIR_ONLY_ACTION')
    return pair.pair_executor_plan(action, job, actor=actor, orders=orders)
