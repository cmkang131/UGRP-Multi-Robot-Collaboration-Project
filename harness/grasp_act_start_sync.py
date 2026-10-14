"""READY -> GO -> ACK start barrier; takes messages, never simulator state."""
from harness.pair_carry_sync import PairCarrySync


class GraspStartSync:
    def __init__(self,participants,delays):
        self.participants=tuple(participants);self.delays=dict(delays)
        if set(delays)!=set(self.participants) or any(not 0<=v<=1.5 for v in delays.values()):raise ValueError('bounded participant delays required')
        self.barrier=PairCarrySync('grasp',participants,allow_solo=len(self.participants)==1)
        self.go_at=None;self.acks=set();self.started=set();self.sequence=0;self.events=[]

    def tick(self,ready,now):
        if set(ready)!=set(self.participants) or any(type(v)is not bool for v in ready.values()):raise ValueError('READY messages only')
        for rid in self.participants:
            self.barrier.report(rid,plan_version=1,epoch=self.barrier.epoch,sequence=self.sequence,
                ready=ready[rid] or rid in self.started,observed_at_s=now,received_at_s=now,
                frame_id=f'{rid}:{self.sequence}',reason='own_READY_message')
        self.sequence+=1;decision=self.barrier.authorize(now)
        if decision['phase']!='GO':self.go_at=None;self.acks.clear();return {r:False for r in self.participants}
        if self.go_at is None:
            self.go_at=now;self.events.append({'t':now,'event':'GO','epoch':self.barrier.epoch})
            return {r:False for r in self.participants}
        for rid in self.participants:
            if ready[rid] and rid not in self.acks:
                self.acks.add(rid);self.events.append({'t':now,'event':'ACK','robot':rid})
        permit={r:len(self.acks)==len(self.participants) and ready[r] and now>=self.go_at+self.delays[r] for r in self.participants}
        for rid,ok in permit.items():
            if ok and rid not in self.started:self.events.append({'t':now,'event':'START','robot':rid});self.started.add(rid)
        return permit


class GraspApproachSync:
    """Three uses of the same boolean READY -> GO -> ACK barrier.

    Round meanings are fixed at construction on each robot, never inferred
    from host poses, teacher phases, paths or a hidden supervisor decision.
    Deliver GO only once per robot per approach round. The final round keeps
    the existing pick barrier semantics and its configured start delays.
    """
    def __init__(self, participants, delays):
        self.participants=tuple(participants);self.delays=dict(delays)
        if len(self.participants)!=2 or set(delays)!=set(self.participants) or any(not 0<=v<=1.5 for v in delays.values()):
            raise ValueError('two participants and bounded delays required')
        self.round=0;self.delivered=set();self.events=[];self.offset=0
        self.sync=GraspStartSync(self.participants,{r:0. for r in self.participants})

    def tick(self, ready, now):
        if self.round < 2 and len(self.delivered)==len(self.participants):
            self.round+=1;self.delivered.clear();self.offset=0
            self.sync=GraspStartSync(self.participants,self.delays if self.round==2 else {r:0. for r in self.participants})
        permits=self.sync.tick(ready,now)
        self.events.extend({**e,'round':self.round} for e in self.sync.events[self.offset:])
        self.offset=len(self.sync.events)
        if self.round==2:return permits
        result={r:ok and r not in self.delivered for r,ok in permits.items()}
        self.delivered.update(r for r,ok in result.items() if ok)
        return result
