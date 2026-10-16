"""Offline command/protocol replay from serialized own inputs and ACT chunks.

No model inference, physics, evaluation state, images or teacher are read.
"""
from collections import deque
from copy import deepcopy
import subprocess
from types import ModuleType

from harness import grasp_act_contract as c
from harness.beamact_pair_student import StudentBarrier, RearmingStartSync
from harness.beamact4_execution import PairChunkExecutor
from harness.beampair_teacher import DEPENDENCY_SHA


def protocol_class():
    raw=subprocess.check_output(['git','show',DEPENDENCY_SHA+':harness/grasp_act_start_sync.py'],text=True)
    # Current shared primitive is byte-identical to the pinned dependency.
    actual=subprocess.check_output(['git','hash-object','harness/pair_carry_sync.py'],text=True).strip()
    expected=subprocess.check_output(['git','rev-parse',DEPENDENCY_SHA+':harness/pair_carry_sync.py'],text=True).strip()
    if actual!=expected:raise ValueError('shared primitive differs from pinned protocol')
    module=ModuleType('beamact_pinned_protocol')
    exec(compile(raw,'pinned_start_sync.py','exec'),module.__dict__)
    return module.GraspStartSync


def replay(inputs,commands,predictions,initial,protocol):
    if len(inputs)!=len(commands) or len(inputs)%2:
        raise ValueError('paired complete actor rows required')
    rids=tuple(initial);chunks=iter(predictions);used=0
    histories={r:deque([deepcopy(initial[r])]*c.HISTORY,maxlen=c.HISTORY) for r in rids}
    stage_mode=protocol.get("beamact4_stage_v1", "off")
    done_recovery=protocol.get("beamact4_done_recovery_v1", "off")
    barriers={r:StudentBarrier(stage_mode=stage_mode) for r in rids};previous=deepcopy(initial)
    def predict(obs,jpegs):
        nonlocal used
        row=next(chunks)
        if (row['t'],row['robot'])!=(obs['t'],obs['robot_id']):
            raise ValueError('chunk request identity/time mismatch')
        used+=1
        return {k:row[k] for k in ('chunk','stage_logits')} if stage_mode!='off' else row['chunk']
    executors={r:PairChunkExecutor(predict,stage_mode=stage_mode,done_recovery=done_recovery) for r in rids}
    factory=protocol_class()
    sync=(RearmingStartSync(rids,protocol['delays_s'],factory) if stage_mode!='off'
          else factory(rids,protocol['delays_s']))
    def issue(obs,actual,proposal,done,waiting,permits):
        rid=obs['robot_id'];b=barriers[rid];now=obs['t']
        value,done=b.issue(now,previous[rid],proposal,done,permits[rid])
        if stage_mode!='off' and (b.blocked or (b.ready and not permits[rid])):
            executors[rid].discard_pending()
        expected=dict(t=now,robot=rid,command=value,done=done,ready=b.ready,
            permit=permits[rid],waiting=waiting)
        if stage_mode!='off':
            expected.update(learned_stage=executors[rid].stage,
                waiting=b.ready and not permits[rid],proposal_rejected=b.blocked)
        if expected!=actual:raise ValueError('ACT/protocol command replay mismatch at '+str((rid,now)))
        previous[rid]=value;histories[rid].append(value)
    for i in range(0,len(inputs),2):
        now=inputs[i]['t']
        permits=sync.tick({r:b.ready for r,b in barriers.items()},now) if stage_mode=='off' else None
        proposals=[]
        for obs,actual in zip(inputs[i:i+2],commands[i:i+2]):
            rid=obs['robot_id'];c.validate_observation(obs)
            if obs['t']!=now or actual['robot']!=rid or obs['issued']!=list(histories[rid]):
                raise ValueError('own issued history/time mismatch')
            b=barriers[rid]
            waiting=(b.pending is not None and not permits[rid]) if stage_mode=='off' else False
            if obs['skill']!=('wait' if waiting else 'grasp'):
                raise ValueError('instruction differs from boolean message schedule')
            proposal=None;done=False
            if stage_mode!='off' or b.pending is None:
                proposal,done=executors[rid].step(obs,[])
                b.propose(proposal,done,previous[rid],stage=executors[rid].stage)
                if stage_mode!='off' and b.blocked:executors[rid].discard_pending()
            if stage_mode=='off':issue(obs,actual,proposal,done,waiting,permits)
            else:proposals.append((obs,actual,proposal,done,waiting))
        if stage_mode!='off':
            permits=sync.tick({r:b.ready for r,b in barriers.items()},now)
            for args in proposals:issue(*args,permits)
    try:next(chunks)
    except StopIteration:pass
    else:raise ValueError('unconsumed ACT chunks')
    if sync.events!=protocol['events'] or {r:b.events for r,b in barriers.items()}!=protocol['own_events']:
        raise ValueError('protocol event replay mismatch')
    return dict(passed=True,command_rows=len(commands),inference_chunks=used,
        command_mismatches=0,issued_history_mismatches=0,protocol_event_mismatches=0,
        scope='serialized own inputs/chunks to issued commands only; no physics/model inference replay')
