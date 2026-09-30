"""P02 planning/dispatch extension, separate from the registered study source."""
from collections.abc import Mapping

from harness import zone_study_integration as zi


def executor_plan(action, job, *, actor=None, orders=()):
    if isinstance(action, Mapping) and action.get('kind') == 'claim':
        order, zone = action.get('order_id'), action.get('destination_zone')
        if isinstance(order, str) and isinstance(zone, str):
            row = next((o for o in orders if o['order_id'] == order), None)
            if orders and row is None:
                return zi.Plan(None, rejected_reason='UNKNOWN_ORDER')
            if row and zone != row['destination_zone']:
                return zi.Plan(None, rejected_reason='WRONG_ORDER_DESTINATION')
            if row and row['required_robots'] == 1 and row['kind'] != 'cyan':
                return zi.Plan(None, rejected_reason='UNSUPPORTED_SOLO_ORDER')
    return zi.executor_plan(action, job, actor=actor, orders=orders)


class MixedIntegratedTrial(zi.IntegratedTrial):
    def _on_action(self, actor, action, sim_s):
        """Same charged-time logging as the frozen base, with P02 planning.

        The base has no planner hook. Keep this small dispatch boundary local
        to P02 rather than replacing its module globals for concurrent trials.
        """
        call_id = self.scheduler.calls[-1].call_id
        extra = getattr(self, '_pending', {}).get(call_id)
        if extra is None or self.scheduler.calls[-1].actor != actor:
            raise AssertionError(f'released action of {actor} has no recorded call')
        link = self.links[actor]
        plan = executor_plan(action, link.job(), actor=actor, orders=self.sheet['orders'])
        kind, arguments, order_id, role = zi.zo._action_row(action)
        ack = link.call(plan.api, *plan.args) if plan.api else None
        self.dispatch_log.append({'call_id': call_id, 'actor': actor, 'sim_s': sim_s, 'action': action,
                                  'api': plan.api, 'args': list(plan.args), 'ack': ack,
                                  'rejected_reason': plan.rejected_reason})
        accepted = ack['accepted'] if ack else plan.rejected_reason is None
        reason = ack['rejected_reason'] if ack else plan.rejected_reason
        local = ack['local_state'] if ack else ('command_rejected' if reason else
                                                'command_issued' if link.job() else 'queue_empty')
        self.actions.append(zi.action_log_record(
            run_id=self.run_id, condition_name=self.condition, seed=self.seed, actor=actor,
            action_id=extra['action_id'], request_id=extra['request_id'], submitted_at_sim_s=sim_s, kind=kind,
            arguments=arguments, accepted=accepted, order_id=order_id, role=role, rejected_reason=reason,
            local_state=local))
        if ack or reason:
            self._remember_command(actor, call_id, sim_s, plan, ack, kind, arguments, local)
        if self.scheduler.call_causes[call_id]['cause'] == 'common':
            self._arm_reask(actor, sim_s)
