"""Existing M2 safety protocol transported through the selected planner channel.

This is an opt-in replacement for M2's shared status bus. Each controller sees
its own publications plus messages actually delivered to it. NL uses explicit
sentences, structured uses a closed fixed status signal, no_comm delivers none.
Neither task planner nor controller can inspect the other endpoint's object.
"""
from __future__ import annotations
import copy
import hashlib
import json
import re
from types import MethodType
from harness.zone_pair_status import PairStatusChannel, PairStatusEndpoint, FIELDS, STATES, READINESS_TTL_S
from harness.task_planner import recipients

SIGNAL_FIELDS = {'code', *FIELDS}


def encode(row, arm):
    if arm == 'structured': return dict(code='PAIR_STATUS', **copy.deepcopy(row))
    def word(v): return 'none' if v is None else str(v)
    return (f"I am {row['robot_id']}. For task {row['task_id']}, my safety state is {row['state']}. "
            f"Report {row['seq']} was sent at {row['sent_at_s']} s. My frame is {word(row['frame_id'])}, "
            f"observed at {word(row['observed_at_s'])} s, and ready until {word(row['ready_until_s'])} s.")


def decode(body):
    if isinstance(body, dict):
        if body.get('code') != 'PAIR_STATUS': return None
        if set(body) != SIGNAL_FIELDS: raise ValueError('BAD_PAIR_SIGNAL_FIELDS')
        row = {k:copy.deepcopy(body[k]) for k in FIELDS}
    else:
        if not isinstance(body,str) or not body.startswith('I am '): return None
        match = re.fullmatch(r'I am (r[123])\. For task ([A-Za-z0-9_-]+), my safety state is ([a-z0-9_]+)\. '
            r'Report ([0-9]+) was sent at ([0-9.eE+-]+) s\. My frame is ([A-Za-z0-9_-]+), '
            r'observed at ([0-9.eE+none-]+) s, and ready until ([0-9.eE+none-]+) s\.', body)
        if match is None: return None
        rid,task,state,seq,sent,frame,observed,until=match.groups()
        row=dict(robot_id=rid,task_id=task,state=state,seq=int(seq),sent_at_s=float(sent),
                 frame_id=None if frame=='none' else frame,
                 observed_at_s=None if observed=='none' else float(observed),
                 ready_until_s=None if until=='none' else float(until))
    if row['state'] not in STATES: raise ValueError('BAD_PAIR_STATE')
    return row


class LocalStatus(PairStatusChannel):
    def __init__(self, owner, robot_id):
        super().__init__(owner.task_id, owner.participants,
                         heartbeat_timeout_s=owner.heartbeat_timeout_s,
                         readiness_ttl_s=owner.readiness_ttl_s)
        self.owner, self.robot_id = owner, robot_id

    def publish(self, raw, received_at_s):
        if raw.get('robot_id') != self.robot_id: raise ValueError('OWN_STATUS_ONLY')
        accepted = super().publish(raw, received_at_s)
        if accepted:
            self.owner.channel.send(self.robot_id,
                [dict(recipient=r,body=encode(raw,self.owner.channel.arm)) for r in
                 recipients(self.owner.channel.arm,self.robot_id,leader=self.owner.channel.leader)
                 if r in self.participants], received_at_s, safety=True)
            self.owner.log.append(copy.deepcopy(raw))
        return accepted

    def receive(self, envelope, now):
        if not envelope['id'].startswith('planner-safety-'): return
        row = decode(envelope['body'])
        if row is None or row['task_id'] != self.task_id: return
        if row['robot_id'] != envelope['sender'] or envelope['recipient'] != self.robot_id:
            raise ValueError('PAIR_CHANNEL_SENDER_MISMATCH')
        # No direct call to peer.publish: this is downstream of the actual
        # condition channel commit, with its delay and immutable sent bytes.
        super().publish(row, now)


class ConditionStatus:
    def __init__(self, task_id, channel, *, heartbeat_timeout_s=.15, readiness_ttl_s=READINESS_TTL_S):
        self.task_id, self.channel = task_id, channel
        self.participants=('r1','r2')
        self.heartbeat_timeout_s,self.readiness_ttl_s=heartbeat_timeout_s,readiness_ttl_s
        self.locals={};self.log=[];self.rejected=[]
        if channel.arm == 'leader_en' and channel.leader not in self.participants:
            raise ValueError('PAIR_LEADER_RELAY_NOT_SUPPORTED_BY_THIS_NATIVE_SKILL')
        channel.subscribers.append(self.deliver)

    def endpoint(self,rid):
        if rid not in self.locals: self.locals[rid]=LocalStatus(self,rid)
        return self.locals[rid]

    def deliver(self,envelope,now):
        if envelope['recipient'] in self.locals:
            self.locals[envelope['recipient']].receive(envelope,now)


def install(team, channel):
    """Reuse each own submission path without the legacy pending-peer matcher.

    Task IDs derive from each actor's fixed order and its own attempt count.
    Different submissions cannot abort a peer or reveal its private request.
    Only delivered status for the same task ID can open the motor barrier.
    """
    if team.sessions: raise ValueError('PAIR_CHANNEL_BIND_BEFORE_FIRST_SUBMISSION')
    from harness.active_camera import bind
    attempts={};buses={}
    original=type(team).start
    def start(self,rid,item_ref=None,target_zone=None,partner_id=None,*,now):
        local=copy.copy(self)
        local.sessions=[]  # do not inspect another actor's pending submission
        def bus(unused_random_id,**kw):
            own=self.executors[rid]
            public=dict(order=own.orders.get(item_ref),sheet=self.sheets.get(item_ref),
                        target=target_zone,participants=sorted((rid,partner_id)))
            key=hashlib.sha256(json.dumps(public,sort_keys=True).encode()).hexdigest()[:24]
            seq=attempts.get((rid,key),0)+1;attempts[rid,key]=seq
            task_id=f'pair-{key}-{seq}'
            if task_id not in buses:buses[task_id]=ConditionStatus(task_id,channel,**kw)
            return buses[task_id]
        def endpoint(bus,rid):return PairStatusEndpoint(bus.endpoint(rid),rid)
        isolated=bind(original,PairStatusChannel=bus,PairStatusEndpoint=endpoint)
        ack=isolated(local,rid,item_ref,target_zone,partner_id,now=now)
        self.sessions.extend(local.sessions)  # evaluation/scheduling only
        return ack
    team.start=MethodType(start,team)
