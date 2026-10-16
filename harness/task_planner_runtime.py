"""Task-level candidate compilation, condition channel and independent actors.

The port is intentionally robot-local. It must enforce each parameter or reject
it: an actuator adapter is not allowed to reinterpret a selected task. The
runtime owns no scene, simulator, peer belief or referee interface.
"""
from __future__ import annotations
import copy
import math
from concurrent.futures import ThreadPoolExecutor

from harness.dispatch_plan_guidance import task_preview
from harness.task_planner import Planner, candidate, recipients, signature, parse, strong_rule


class ActPort:
    """Strict bridge to existing skills. Each handler owns the complete args.

    Bind carry to the own executor, joint carry/help to the paired skill,
    search/goto/yield/reroute to navigation, regrip to its safe lower/grasp
    sequence. Unbound capabilities never appear in the executable menu.
    """
    def __init__(self, handlers, check):
        self.handlers, self.safety_check = dict(handlers), check
        self.active = None

    def check(self, value):
        if value['act'] not in self.handlers: return 'SKILL_UNAVAILABLE:' + value['act']
        return self.safety_check(value)

    def start(self, value):
        refusal = self.check(value)
        if refusal: return dict(accepted=False, reason=refusal)
        ack = self.handlers[value['act']](**copy.deepcopy(value['args']))
        if not isinstance(ack, dict) or type(ack.get('accepted')) is not bool:
            raise ValueError('SKILL_ACK_REQUIRED')
        if ack['accepted'] and value['act'] != 'report': self.active = copy.deepcopy(value)
        return ack


def build_candidates(orders, static, own, port):
    """Enumerate destination x route x approach x partners. Never rank away
    an option: the model chooses order, slot, route, approach and team size.

    Static capability catalog is authored; estimates/occupancy are robot-local.
    No remote claim or remote readiness is used to remove a candidate.
    """
    rows = []
    own_xy = own.get('pose', {}).get('xy')
    for order in orders:
        if order['order_id'] in own.get('completed_orders', []): continue
        for destination in order['destinations']:
            for route in static['routes']:
                for approach in order['approaches']:
                    n = order['required_robots']
                    partners = [None] if n == 1 else [p for p in ('r1', 'r2', 'r3') if p != own['robot_id']]
                    for partner in partners:
                        args = dict(cargo=order['order_id'], to=destination, via=route['id'],
                                    approach=approach, mode='solo' if n == 1 else 'joint')
                        if partner: args.update(partner=partner, side=approach)
                        preview = task_preview(own_xy=own_xy, pickup_xy=order.get('pickup_xy'),
                            destination_xy=static['stations'].get(destination), via_xy=route['waypoints'],
                            required_robots=n,
                            blockage_risk=own.get('route_risk', {}).get(route['id'], 'unknown'),
                            unloading_empty=own.get('unloading_empty', {}).get(destination, 'unknown'))
                        rows.append(candidate('carry', args, **preview))
                        if partner:
                            rows.append(candidate('help', dict(partner=partner, cargo=order['order_id'], side=approach),
                                                  **preview))
    rows += [candidate('go_to', dict(station=s)) for s in static['stations']]
    rows += [candidate('search', dict(area=a)) for a in static['search_areas']]
    rows += [candidate('yield', dict(where=s)) for s in static.get('yield_stations', [])]
    rows += [candidate('reroute', dict(via=r['id'])) for r in static['routes']]
    rows += [candidate('wait', dict(until='new_observation_or_message', max_s=5.), expected_s=5.),
             candidate('set_down_and_regrip', {}),
             candidate('report', dict(fact='Own observation is uncertain; please verify.'))]
    unique = {signature(r): r for r in rows if not port.check(r)}
    return list(unique.values())


class Channel:
    """Actual bounded-delay channel. All peer inputs must be delivered here.

    Leader relaying is a new message chosen by that actor, not a shared inbox.
    Envelope IDs and timestamps are transport metadata, never status votes.
    """
    def __init__(self, arm, *, leader='r1', delay_s=.1):
        from harness.task_planner import condition
        self.arm, self.leader, self.delay_s = condition(arm), leader, delay_s
        self.pending, self.ledger, self.subscribers = [], [], []
        self.counter = 0

    def send(self, sender, messages, now, *, safety=False):
        for message in messages:
            if message['recipient'] not in recipients(self.arm, sender, leader=self.leader):
                raise ValueError('CHANNEL_TOPOLOGY_REFUSAL')
            self.counter += 1
            prefix='planner-safety' if safety else 'planner-msg'
            self.pending.append(dict(id=f'{prefix}-{self.counter}', sender=sender,
                recipient=message['recipient'], sent_at=now, delivered_at=now+self.delay_s,
                body=copy.deepcopy(message['body'])))

    def deliver(self, planners, now):
        ready = [e for e in self.pending if e['delivered_at'] <= now]
        self.pending = [e for e in self.pending if e['delivered_at'] > now]
        for e in ready:
            for callback in self.subscribers: callback(e, now)
            planners[e['recipient']].receive(e, now); self.ledger.append(copy.deepcopy(e))


EVENT_MAP = dict(job_done='act_success', job_failed='act_failure', job_refused='act_refused',
                 blockage_seen='s2_blocked', partner_delayed='s3_partner_delayed',
                 corridor_occupied='s4_occupied', item_missing='s5_missing', grip_anomaly='grip_anomaly')


class Runtime:
    """One model turn and memory per robot, concurrent calls, serial motor commit.

    Snapshot callbacks must read THAT robot's RGB/commands/estimate only. Model
    workers cannot touch motors. The latest main-thread safety check can refuse
    a stale decision, giving exactly one repair before the audited fallback.
    """
    def __init__(self, *, arm, models, ports, snapshots, leader='r1', deadline_s=30.):
        self.planners = {r: Planner(r, arm, leader=leader, deadline_s=deadline_s) for r in ports}
        self.ports, self.snapshots, self.models = ports, snapshots, models
        self.channel = Channel(arm, leader=leader)
        self.pool = ThreadPoolExecutor(max_workers=len(ports), thread_name_prefix='task-planner')
        self.pending, self.repairs, self.audit, self.started_at = {}, {}, [], {}
        self.closed = False
        self.model_attempts = {}; self.next_decision = {}

    def event(self, rid, event, now):
        kind = EVENT_MAP.get(event['kind'], event['kind'])
        if kind in ('act_success', 'act_failure', 'act_refused'):
            port = self.ports[rid]
            if port.active is not None:
                self.planners[rid].feedback(port.active, kind[4:], event.get('reason', ''), now,
                                           now-self.started_at.get(rid, now))
                port.active = None
        else:
            self.planners[rid].trigger(kind, now, event.get('reason', ''))

    def step(self, now):
        if self.closed: raise RuntimeError('PLANNER_CLOSED')
        self.channel.deliver(self.planners, now)
        for rid, planner in self.planners.items():
            if rid in self.pending:
                future, context, audit_start = self.pending[rid]
                if not future.done(): continue
                result = future.result(); del self.pending[rid]
                self.model_attempts[rid] = self.model_attempts.get(rid,0) + sum('request' in x for x in planner.audit[audit_start:])
                decision = result['decision']
                if decision is None:
                    self.model_attempts[rid] = 0
                    self.next_decision[rid] = now + .5
                    continue
                refusal = self.ports[rid].check(decision)
                ack = dict(accepted=False, reason=refusal) if refusal else self.ports[rid].start(decision)
                if not ack['accepted']:
                    planner.feedback(decision, 'refused', ack.get('reason', 'ACT_REFUSED'), now)
                    self.repairs[rid] = self.repairs.get(rid, 0) + 1
                    self.audit.append(dict(robot_id=rid, at=now, status='refused', decision=decision, ack=ack))
                    if result['fallback'] or self.model_attempts[rid] >= 2:
                        fresh = self.snapshots[rid](now)
                        if not fresh['candidates']:
                            self.model_attempts[rid] = 0
                            self.audit.append(dict(robot_id=rid, at=now, status='no_safe_candidate'))
                            planner.events.clear()
                            continue
                        ctx = planner.context(now=now, **fresh)
                        result = planner._fallback(ctx, self.ports[rid], 'RUNTIME_REPAIR_EXHAUSTED')
                        self.repairs[rid] = 0
                        self.model_attempts[rid] = 0
                        self.next_decision[rid] = now + .5
                        if result['decision'] is None: continue
                        ack = planner.audit[-1]['ack']
                    else: continue
                if result['decision']['act'] == 'report':
                    planner.feedback(result['decision'], 'success', 'report_recorded', now)
                else:
                    self.started_at[rid] = now
                self.repairs[rid] = 0; self.model_attempts[rid] = 0
                self.next_decision[rid] = now + .5
                self.channel.send(rid, result['messages'], now)
                self.audit.append(dict(robot_id=rid, at=now, decision=result['decision'],
                                       fallback=result['fallback'], ack=ack))
            if planner.events and rid not in self.pending and now >= self.next_decision.get(rid,0.):
                while len(planner.events) > 32: planner.events.popleft()
                snapshot = self.snapshots[rid](now)
                if not snapshot['candidates']:
                    self.audit.append(dict(robot_id=rid, at=now, status='no_safe_candidate'))
                    planner.events.clear()
                    self.model_attempts[rid] = 0
                    continue
                context = planner.context(now=now, **snapshot)
                planner.events.clear()
                audit_start = len(planner.audit)
                self.pending[rid] = (self.pool.submit(planner.decide, context, self.models[rid],
                    repair_budget=max(0,1-self.model_attempts.get(rid,0))), context, audit_start)

    def close(self):
        self.closed = True
        for future, _, _ in self.pending.values(): future.cancel()
        self.pool.shutdown(wait=True, cancel_futures=True)
