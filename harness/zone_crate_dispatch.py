"""Opt-in T06 kind dispatch; the v6e-pinned beam entry points stay byte-identical.

The existing study runner is NOT rewired. A future registered crate adapter can
select these facades explicitly after source pinning and independent review.
Until then a crate request receives a native-adapter refusal, including in fakes.
"""
from collections.abc import Mapping

from harness.zone_crate_skill import executor_request, refuse_native
from harness.zone_pair_executor import PairTeam as BeamPairTeam
from harness.zone_study_integration import Plan, executor_plan as beam_executor_plan


def executor_plan(action, job, *, actor=None, orders=()):
    if isinstance(action, Mapping) and action.get('kind') == 'claim':
        row = next((o for o in orders if o.get('order_id') == action.get('order_id')), None)
        if row and row.get('kind') == 'heavy_crate':
            try:
                return Plan('pair_carry', executor_request(row, actor, action.get('role'),
                                                           action.get('destination_zone')))
            except ValueError as exc:
                return Plan(None, rejected_reason=str(exc))
    return beam_executor_plan(action, job, actor=actor, orders=orders)


class PairTeam(BeamPairTeam):
    """Only kind dispatch changes. Beam lifecycle, policy and roles are inherited."""
    def start(self, rid, item_ref=None, target_zone=None, partner_id=None, *, now):
        ex = self.executors[rid]
        if isinstance(item_ref, str) and ex.orders.get(item_ref, {}).get('kind') == 'heavy_crate':
            return refuse_native(ex, item_ref, target_zone, partner_id, now=now)
        return super().start(rid, item_ref, target_zone, partner_id, now=now)
