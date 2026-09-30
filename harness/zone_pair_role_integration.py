"""Opt-in role-aware study adapter; no changes to sealed study admission."""
from collections.abc import Mapping

from harness import zone_study_integration as legacy
from harness import zone_study_offline as zo
from harness.zone_study_integration import (Plan, ROBOTS, MAIN_CONDITIONS, condition_invariant_config,
                                            action_log_record)
from harness.zone_pair_roles import PairRoles, PROFILE
from harness import zone_pair_role_executor


class PairStatusBus(legacy.PairStatusBus):
    def __init__(self, order_sheet, records=None, *, role_assignment=None):
        super().__init__(order_sheet, records)
        self.roles = PairRoles.from_mapping(role_assignment) if role_assignment is not None else None

    def config(self):
        row = super().config()
        row['executor_profile'] = zone_pair_role_executor.PROFILE
        if self.roles:
            row.update(participants=list(self.roles.participants),
                       roles={r: self.roles.role(r) for r in self.roles.participants},
                       role_profile=PROFILE, role_to_robot=self.roles.mapping(),
                       role_assignment_sha256=self.roles.sha256())
        return row


def executor_plan(action, job, *, actor=None, orders=(), role_assignment=None):
    if role_assignment is not None and isinstance(action, Mapping) and action.get('kind') == 'claim':
        order, zone = action.get('order_id'), action.get('destination_zone')
        if not isinstance(order, str) or not isinstance(zone, str):
            return Plan(None, rejected_reason='BAD_CLAIM')
        row = next((o for o in orders if o['order_id'] == order), None)
        if row and row['required_robots'] > 1:
            if row['kind'] != 'long_beam' or row['required_robots'] != 2 or row['count'] != 1:
                return Plan(None, rejected_reason='UNSUPPORTED_TEAM_ORDER')
            try:
                roles = PairRoles.from_mapping(role_assignment)
                role = roles.role(actor)
            except ValueError as exc:
                return Plan(None, rejected_reason=str(exc))
            if action.get('role') != role:
                return Plan(None, rejected_reason='UNSUPPORTED_PAIR_ROLE')
            return Plan('pair_carry', (order, zone, roles.partner(actor), role))
    return legacy.executor_plan(action, job, actor=actor, orders=orders)


class IntegratedTrial(legacy.IntegratedTrial):
    def __init__(self, *args, pair_role_assignment=None, pair_records=None, **kwargs):
        super().__init__(*args, pair_records=pair_records, **kwargs)
        self.pair_status = PairStatusBus(self.sheet, pair_records, role_assignment=pair_role_assignment)
        self.pair_role_assignment = self.pair_status.roles.mapping() if self.pair_status.roles else None

    def _on_action(self, actor, action, sim_s):
        """A released action reaches THIS robot's executor at its charged SIM time."""
        call_id = self.scheduler.calls[-1].call_id
        extra = getattr(self, '_pending', {}).get(call_id)
        if extra is None or self.scheduler.calls[-1].actor != actor:
            raise AssertionError(f'released action of {actor} has no recorded call')
        link = self.links[actor]
        plan = executor_plan(action, link.job(), actor=actor, orders=self.sheet['orders'],
                             role_assignment=self.pair_role_assignment)
        kind, arguments, order_id, role = zo._action_row(action)
        ack = link.call(plan.api, *plan.args) if plan.api else None
        self.dispatch_log.append({'call_id': call_id, 'actor': actor, 'sim_s': sim_s, 'action': action,
                                  'api': plan.api, 'args': list(plan.args), 'ack': ack,
                                  'rejected_reason': plan.rejected_reason})
        accepted = ack['accepted'] if ack else plan.rejected_reason is None
        reason = ack['rejected_reason'] if ack else plan.rejected_reason
        local = ack['local_state'] if ack else ('command_rejected' if reason else
                                                'command_issued' if link.job() else 'queue_empty')
        self.actions.append(action_log_record(
            run_id=self.run_id, condition_name=self.condition, seed=self.seed, actor=actor,
            action_id=extra['action_id'], request_id=extra['request_id'], submitted_at_sim_s=sim_s, kind=kind,
            arguments=arguments, accepted=accepted, order_id=order_id, role=role, rejected_reason=reason,
            local_state=local))
        if ack or reason:
            self._remember_command(actor, call_id, sim_s, plan, ack, kind, arguments, local)
        if self.scheduler.call_causes[call_id]['cause'] == 'common':
            self._arm_reask(actor, sim_s)
