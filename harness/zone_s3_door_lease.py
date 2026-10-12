"""Default-off bounded door leases, fixed FIFO/tie priority, epoch fencing.

Only own estimates produce request/clear/progress bits. A lease expiry is
NOT evidence of an empty doorway: an occupied resource stays fenced until
the previous team clears it. No world/peer pose capability crosses the relay.
"""
import copy
import math
from dataclasses import dataclass, asdict
from harness.zone_own_guards import CHASSIS_X_M, CHASSIS_Y_M
from harness.zone_own_guards_v3 import body_spheres

OPTION = 'door_lease_v2'
TEAMS = (('r1', 'r2'), ('r3',))
ROBOTS = ('r1', 'r2', 'r3')
LEASE_S, NO_PROGRESS_S = 30., 10.
APPROACH_M, PROGRESS_M = .45, .02


def estimated_bounds(r, servo, *, loaded, offset=None, envelope=None):
    """Public chassis/arm geometry and own issued posture, never peer truth."""
    co,si=math.cos(r.yaw_rad),math.sin(r.yaw_rad)
    points=[(x,y,0.) for x in CHASSIS_X_M for y in (-CHASSIS_Y_M,CHASSIS_Y_M)]
    points += [(x,y,radius) for x,y,z,radius in body_spheres(servo,loaded=loaded)]
    world=[(r.x_m+co*x-si*y,r.y_m+si*x+co*y,radius) for x,y,radius in points]
    radius=max(math.hypot(x,y)+a for x,y,a in points)
    if loaded and offset is not None:
        ox,oy,heading=offset; yaw=r.yaw_rad-heading
        c,s=math.cos(yaw),math.sin(yaw)
        x,y=r.x_m-c*ox+s*oy,r.y_m-s*ox-c*oy
        a,b=envelope
        world += [(x+c*dx-s*dy,y+s*dx+c*dy,0.) for dx in (-a,a) for dy in (-b,b)]
        radius=max(radius,math.hypot(ox,oy)+math.hypot(a,b))
    bounds=(min(x-a for x,y,a in world),max(x+a for x,y,a in world),
            min(y-a for x,y,a in world),max(y+a for x,y,a in world))
    padding=3*r.std_xy_m+2*radius*math.sin(min(math.pi,3*r.std_yaw_rad)/2)
    return bounds,padding


@dataclass(frozen=True)
class Signal:
    robot_id: str
    request: bool
    clear: bool
    progress: bool


class Board:
    def __init__(self):
        self.owner = self.blocker = None
        self.epoch = 0
        self.deadline = self.progress_deadline = 0.
        self.queue, self.events = [], []
        self.round = 0

    def event(self, now, event, **detail):
        self.events.append(dict(sim_s=now, event=event, epoch=self.epoch, **detail))

    def exchange(self, signals, now):
        if (len(signals) != 3 or {s.robot_id for s in signals} != set(ROBOTS)
                or any(type(s) is not Signal or any(type(v) is not bool
                    for v in (s.request, s.clear, s.progress)) for s in signals)):
            raise ValueError('DOOR_LEASE_INVALID_BATCH')
        table = {s.robot_id: s for s in signals}
        wanted = lambda team: any(table[r].request for r in team)
        clear = lambda team: all(table[r].clear for r in team)
        # Stable request-time FIFO, with the public team order for equal rounds.
        self.queue = [t for t in self.queue if wanted(t)]
        for team in TEAMS:
            if wanted(team) and team != self.owner and team not in self.queue:
                self.queue.append(team)
        if self.owner is not None:
            team = self.owner
            if any(table[r].progress for r in team): self.progress_deadline = now+NO_PROGRESS_S
            reason = ('clear' if clear(team) and not wanted(team) else
                      'lease_expired' if now >= self.deadline else
                      'no_progress' if now >= self.progress_deadline else None)
            if reason:
                self.owner = None
                self.epoch += 1  # fence every outstanding grant before reassignment
                self.blocker = None if clear(team) else team
                if wanted(team) and team not in self.queue: self.queue.append(team)
                self.event(now, 'revoke', team=list(team), reason=reason,
                           occupied=not clear(team), queue=[list(t) for t in self.queue])
                self.round += 1
                return  # one full control boundary has no grant
        if self.blocker is not None and clear(self.blocker):
            self.event(now, 'clear_after_revoke', team=list(self.blocker))
            self.blocker = None
        if self.owner is None and self.queue:
            # An expired occupant alone may regain an exclusive recovery epoch.
            # Other teams still wait; elapsed time never certifies empty space.
            team = self.blocker if self.blocker is not None else self.queue[0]
            if team in self.queue: self.queue.remove(team)
            self.owner = team
            self.epoch += 1
            self.deadline, self.progress_deadline = now+LEASE_S, now+NO_PROGRESS_S
            self.event(now, 'grant', team=list(team), recovery=self.blocker is not None)
        self.round += 1

    def permits(self, team, epoch):
        return team == self.owner and epoch == self.epoch


class Client:
    def __init__(self, rid, own, board, passage, legacy, audit=None):
        self.robot_id, self.own, self.board = rid, own, board
        self.team = next(t for t in TEAMS if rid in t)
        self.x, self.y = passage['center_m'][:2]
        self.hx, self.hy = passage['half_extents_m'][:2]
        self.state, self.request, self.grant = 'CLEAR', False, -1
        self.last_position = None
        self.offset, self.envelope, self.audit = legacy.offset, legacy.envelope, audit

    def offer(self, now):
        r = self.own.last_report
        try:
            valid = (r is not None and r.initialized and all(math.isfinite(float(v))
                for v in (r.t_est, r.x_m, r.y_m, r.yaw_rad, r.std_xy_m, r.std_yaw_rad))
                and r.std_xy_m >= 0 and r.std_yaw_rad >= 0
                and -1e-8 <= now-r.t_est)
        except (TypeError,ValueError):
            valid = False
        if not valid:
            self.request = True
            return Signal(self.robot_id, True, False, False)
        if now-r.t_est > 1.:
            if self.audit is None:
                self.request = True
                return Signal(self.robot_id, True, False, False)
            self.audit.note(self.own,now,'DOOR_POSE_STALE','door.clearance',
                estimate_age_s=now-r.t_est)
        loaded = self.own.pose.provider.loc._pf.load.loaded
        (xmin,xmax,ymin,ymax),padding=estimated_bounds(r,self.own.servo,
            loaded=loaded,offset=self.offset if self.robot_id!='r3' else None,
            envelope=self.envelope)
        dx=max(xmin-self.x-self.hx,self.x-self.hx-xmax)
        dy=max(ymin-self.y-self.hy,self.y-self.hy-ymax)
        if self.audit is None:
            dx,dy=dx-padding,dy-padding
        elif any((dx > margin or dy > margin) and
                 not (dx-padding > margin or dy-padding > margin) for margin in (.05,APPROACH_M)):
            self.audit.note(self.own,now,'DOOR_POSE_UNCERTAIN','door.clearance',
                sigma_padding_m=padding,continued_with_geometry='current own estimate')
        clear = dx > .05 or dy > .05
        self.request = dx <= APPROACH_M and dy <= APPROACH_M
        pos = (r.x_m, r.y_m)
        progress = self.last_position is not None and math.dist(pos, self.last_position) >= PROGRESS_M
        if self.last_position is None or progress: self.last_position = pos
        return Signal(self.robot_id, bool(self.request), bool(clear), bool(progress))

    def permits(self):
        # A remote team's pending lease cannot stop local pickup/approach.
        return not self.request or self.board.permits(self.team, self.grant)


def attach(runtime, *, static=None, door_lease='off', dev_light=False):
    if door_lease == 'off': return runtime
    if door_lease != OPTION: raise ValueError('unknown door_lease')
    passage = next(p for p in static['passages'] if p['id'] == 'door_1')
    board = Board()
    audit=runtime.pair.s3_dev_light_audit if dev_light else None
    clients = {r: Client(r, own, board, passage, runtime.clients[r], audit)
               for r, own in runtime.localizers.items()}
    runtime.clients = clients
    for producer in (runtime.pair, runtime.solo): producer.clients = clients
    runtime.relay = board
    # The base calls exchange twice initially/after producer stepping. Lease
    # decisions occur once per clock tick so revoke cannot be bypassed at t=t.
    last = None
    status_events=[]
    previous_states=None
    def exchange(now):
        nonlocal last, previous_states
        if last == now: return
        last = now
        signals = [c.offer(now) for c in clients.values()]
        board.exchange(signals, now)
        for c in clients.values():
            c.grant = board.epoch if board.owner == c.team else -1
            c.state = 'USING' if c.request and c.permits() else 'REQUEST' if c.request else 'CLEAR'
        states={r:c.state for r,c in clients.items()}
        if states != previous_states:
            status_events.append(dict(sim_s=now,epoch=board.epoch,signals=[dict(robot_id=r,
                resource='door_1',round=board.round,state=state) for r,state in states.items()]))
            previous_states=states
    runtime.exchange = exchange
    record = runtime.record
    def recorded():
        out = record()
        out['door_yield'] = dict(profile=OPTION, lease_s=LEASE_S, no_progress_s=NO_PROGRESS_S,
            critical_section='own estimated door approach only', priority='FIFO then fixed pair/solo order',
            timeout_releases=True, expiry_proves_clear=False, gt_inputs=False,
            dev_light_nominal_geometry=dev_light, uncertainty_veto_logged=dev_light,
            owner=None if board.owner is None else list(board.owner), epoch=board.epoch,
            wait_robot_s=dict(runtime.wait_robot_s), events=copy.deepcopy(status_events),
            lease_events=copy.deepcopy(board.events),
            final_states={r:c.state for r,c in clients.items()}, failure=runtime.door_failure)
        return out
    runtime.record = recorded
    runtime.door_lease_board = board
    return runtime
