"""S4 dispatch contract only: no simulator, executor runtime or network."""
import pytest

from harness.s4_llm_routing import executor_plan

ORDERS = [dict(order_id='order-1', kind='cyan', required_robots=1, count=1, destination_zone='A'),
          dict(order_id='order-5', kind='long_beam', required_robots=2, count=1, destination_zone='B')]


@pytest.mark.parametrize('actor,order,role,api,args', [
    ('r3', 'order-1', 'solo', 'deliver', ('order-1', 'A')),
    ('r1', 'order-5', 'end_neg', 'pair_carry', ('order-5', 'B', 'r2')),
    ('r2', 'order-5', 'end_pos', 'pair_carry', ('order-5', 'B', 'r1')),
])
def test_claim_selects_only_the_requested_executor(actor, order, role, api, args):
    action = dict(kind='claim', order_id=order, role=role, destination_zone=args[1])
    plan = executor_plan(action, None, actor=actor, orders=ORDERS)
    assert (plan.api, plan.args, plan.rejected_reason) == (api, args, None)


@pytest.mark.parametrize('actor,order,role,zone,reason', [
    ('r1', 'order-1', 'solo', 'A', 'UNSUPPORTED_SOLO_ROLE'),
    ('r3', 'order-5', 'end_neg', 'B', 'UNSUPPORTED_PAIR_ROLE'),
    ('r3', 'missing', 'solo', 'A', 'UNKNOWN_ORDER'),
    ('r3', 'order-1', 'solo', 'B', 'WRONG_DESTINATION'),
])
def test_bad_claim_never_falls_back_to_another_executor(actor, order, role, zone, reason):
    plan = executor_plan(dict(kind='claim', order_id=order, role=role, destination_zone=zone),
                         None, actor=actor, orders=ORDERS)
    assert plan.api is None and plan.rejected_reason == reason
