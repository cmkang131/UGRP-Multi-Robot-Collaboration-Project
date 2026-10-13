"""Concrete task planner port for existing ZoneOwnExecutor / pair team APIs.

This port advertises the actual native skill limits (cyan/west/one mapped
passage for solo; configured pair role/profile for joint). It never silently
throws away to/via/approach, substitutes another cargo, or claims a new skill
was physically validated. Broader actuator catalogs use ActPort with their own
complete handlers; unsupported instructions get a model-visible refusal.
"""
from __future__ import annotations
import copy
from harness.task_planner_runtime import ActPort, build_candidates


class ZonePort(ActPort):
    def __init__(self, executor, call, *, pair_roles=None, regrip=None, stop_scheduled=None):
        self.ex, self.call = executor, call
        self.pair_roles = pair_roles or {}
        self.regrip = regrip
        self.recovery = None
        if stop_scheduled is not None:
            from harness.task_planner_recovery import OwnRecovery
            self.recovery = OwnRecovery(self, stop_scheduled)
            self.regrip = lambda: self.recovery.start('set_down_and_regrip', self.ex.now)
        self.last_ack = None
        self.completed_orders = []
        self.completed_counts = {}
        self.immediate = None
        self.catalog = self._catalog()
        handlers = dict(carry=self.carry, help=self.help, go_to=self.go_to, search=self.search,
                        wait=self.wait, yield_=self.yield_to, reroute=self.reroute, report=self.report)
        handlers['yield'] = handlers.pop('yield_')
        if self.regrip is not None: handlers['set_down_and_regrip'] = self.regrip
        super().__init__(handlers, self.validate)

    def _catalog(self):
        stations = {}
        for slots in self.ex.map['zone_slots'].values():
            for s in slots: stations[s['slot_id']] = list(s['center_m'])
        for p in self.ex.map['passages']: stations[p['id']] = list(p['center_m'])
        # Slot centre is fixed map geometry, not a current object position.
        for name, rect in self.ex.slots.items():
            if isinstance(rect, dict) and 'center_m' in rect: stations[name] = list(rect['center_m'])
        return dict(stations=stations,
                    routes=[dict(id=self.ex.door_id, waypoints=[list(self.ex.door_xy)])],
                    search_areas=list(self.ex.slots), yield_stations=list(self.ex.slots))

    def orders(self):
        result = []
        for oid, order in self.ex.orders.items():
            n = order['required_robots']
            destinations = [s['slot_id'] for s in self.ex.map['zone_slots'][order['destination_zone']]]
            if n == 2: destinations = [order['destination_zone']]
            result.append(dict(order_id=oid, kind=order['kind'], count=order.get('count',1),
                own_confirmed_count=self.completed_counts.get(oid,0), required_robots=n,
                destinations=destinations, approaches=['west'] if n == 1 else ['end_neg', 'end_pos'],
                pickup_xy=self.catalog['stations'].get((order.get('initial_location') or {}).get('slot'))))
        return result

    def validate(self, value):
        act, a = value['act'], value['args']
        if self.ex.stopped is not None: return 'ROBOT_STOPPED'
        if act == 'report': return None
        if self.recovery is not None:
            if act == 'carry' and self.ex.job is not None and self.recovery.can_resume(value): return None
            if act in ('wait','set_down_and_regrip') and self.ex.job is not None:
                return self.recovery.check(act)
        if act == 'set_down_and_regrip':
            return 'OWN_STABLE_CARRY_PHASE_REQUIRED'
        if self.ex.job is not None: return 'ACT_STILL_RUNNING'
        if act in ('carry', 'help'):
            if a['cargo'] in self.completed_orders: return 'OWN_ORDER_ALREADY_COMPLETED'
            order = self.ex.orders.get(a['cargo'])
            if order is None: return 'UNKNOWN_ORDER'
            if act == 'help' or a['mode'] == 'joint':
                if order['required_robots'] != 2: return 'JOINT_ORDER_REQUIRED'
                expected = self.pair_roles.get(self.ex.robot_id)
                if expected != a.get('side'): return 'PAIR_SIDE_UNSUPPORTED'
                if a['partner'] not in self.pair_roles or a['partner'] == self.ex.robot_id: return 'PAIR_PARTNER_UNSUPPORTED'
                if act == 'carry' and (a['to'] != order['destination_zone'] or a['via'] != self.ex.door_id
                                      or a['approach'] != a['side']): return 'PAIR_ROUTE_OR_DESTINATION_UNSUPPORTED'
            else:
                if order['required_robots'] != 1 or order['kind'] != 'cyan': return 'SOLO_SKILL_KIND_UNSUPPORTED'
                slots = [s['slot_id'] for s in self.ex.map['zone_slots'][order['destination_zone']]]
                if a['to'] not in slots: return 'ORDER_DESTINATION_REFUSED'
                if a['via'] != self.ex.door_id or a['approach'] != 'west': return 'SOLO_ROUTE_OR_APPROACH_UNSUPPORTED'
        elif act == 'go_to' and a['station'] not in self.catalog['stations']: return 'UNKNOWN_STATION'
        elif act == 'search' and a['area'] not in self.catalog['search_areas']: return 'UNKNOWN_SEARCH_AREA'
        elif act == 'yield' and a['where'] not in self.catalog['yield_stations']: return 'UNKNOWN_YIELD_STATION'
        elif act == 'reroute' and a['via'] not in [r['id'] for r in self.catalog['routes']]: return 'UNKNOWN_ROUTE'
        return None

    def carry(self, cargo, to, via, approach, mode, partner=None, side=None):
        value = dict(act='carry', args=dict(cargo=cargo,to=to,via=via,approach=approach,mode=mode))
        if mode=='joint': value['args'].update(partner=partner,side=side)
        if self.recovery is not None and self.recovery.can_resume(value): return self.recovery.resume(value)
        # Validated route/approach exactly match the existing frozen skill.
        ack = self.call('deliver', cargo, to) if mode == 'solo' else self.call('pair_carry', cargo, to, partner)
        if ack.get('accepted') and self.ex.job is not None:
            self.ex.job.args['task_planner_directive'] = dict(cargo=cargo, to=to, via=via, approach=approach, mode=mode)
        return ack

    def help(self, partner, cargo, side):
        return self.call('pair_carry', cargo, self.ex.orders[cargo]['destination_zone'], partner)

    def go_to(self, station): return self.call('goto', station)
    def search(self, area):
        # Existing goto(slot) moves to that slot's viewing standoff; sweep on completion.
        ack = self.call('goto', area)
        if ack.get('accepted'): self.search_next = True
        return ack
    def wait(self, until, max_s):
        if self.ex.job is not None and self.recovery is not None:
            return self.recovery.start('wait', self.ex.now, max_s)
        return self.call('wait', max_s)

    def poll(self, now):
        return None if self.recovery is None else self.recovery.poll(now)
    def yield_to(self, where): return self.call('goto', where)
    def reroute(self, via): return self.call('goto', via)
    def report(self, fact):
        return dict(accepted=True, reason='report_recorded')

    def snapshot(self, now):
        rep = self.ex.last_report
        pose = dict(xy=[rep.x_m, rep.y_m] if rep is not None and rep.initialized else None,
                    source='own_rgb_and_issued_commands', uncertainty='unknown' if rep is None else str(rep.std_xy_m))
        obs = self.ex.last_obs
        own = dict(robot_id=self.ex.robot_id, pose=pose,
                   rgb=None if obs is None else dict(frame_id=obs['frame_id'], sha256=obs['sha256'],
                                                     observed_at=obs['sim_time'], image_b64=obs['image']),
                   holding=self.ex.holding(), completed_orders=list(self.completed_orders),
                   active_act=None if self.active is None else dict(act=self.active['act'], args=self.active['args']))
        orders = self.orders()
        return dict(orders=orders, static_map=self.catalog, own=own,
                    candidates=build_candidates(orders, self.catalog, own, self),
                    task='Complete your fixed orders. You choose the next cargo, destination slot, route, approach and timing. '
                         'Native skills may have only one supported route/approach; do not invent another.')

    def event(self, event):
        """Convert own native completion; search's goto is not search completion."""
        detail = event.get('detail', event)
        kind = event.get('kind', event.get('event'))
        if kind == 'job_done' and getattr(self, 'search_next', False):
            self.search_next = False
            ack = self.call('look_around')
            if ack.get('accepted'): return None
            return dict(kind='job_failed', reason=ack.get('reason', 'SEARCH_SWEEP_REFUSED'))
        if kind == 'job_done' and self.active and self.active['act'] == 'carry':
            # Only an own-camera-confirmed completion can remove an order.
            if detail.get('confirmation') == 'own_camera_confirmed':
                oid = self.active['args']['cargo']
                self.completed_counts[oid] = self.completed_counts.get(oid,0) + 1
                if self.completed_counts[oid] >= self.ex.orders[oid].get('count',1):
                    self.completed_orders.append(oid)
        if kind == 'job_failed': self.search_next = False
        if kind in ('job_done','job_failed') and self.recovery is not None: self.recovery.close()
        return dict(kind=kind, reason=str(detail.get('reason', detail.get('confirmation', ''))))
