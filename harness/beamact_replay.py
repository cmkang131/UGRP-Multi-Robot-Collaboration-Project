"""Offline command/protocol replay from serialized own inputs and ACT chunks.

No model inference, physics, evaluation state, images or teacher are read.
"""
from collections import deque
from copy import deepcopy
import subprocess
from types import ModuleType

from harness import grasp_act_contract as c
from harness.beamact_pair_student import StudentBarrier
from harness.grasp_act_policy import ChunkExecutor
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
    barriers={r:StudentBarrier() for r in rids};previous=deepcopy(initial)
    def predict(obs,jpegs):
        nonlocal used
        row=next(chunks)
        if (row['t'],row['robot'])!=(obs['t'],obs['robot_id']):
            raise ValueError('chunk request identity/time mismatch')
        used+=1
        return row['chunk']
    executors={r:ChunkExecutor(predict) for r in rids}
    sync=protocol_class()(rids,protocol['delays_s'])
    for i in range(0,len(inputs),2):
        now=inputs[i]['t'];permits=sync.tick({r:b.ready for r,b in barriers.items()},now)
        for obs,actual in zip(inputs[i:i+2],commands[i:i+2]):
            rid=obs['robot_id'];c.validate_observation(obs)
            if obs['t']!=now or actual['robot']!=rid or obs['issued']!=list(histories[rid]):
                raise ValueError('own issued history/time mismatch')
            b=barriers[rid];waiting=b.pending is not None and not permits[rid]
            if obs['skill']!=('wait' if waiting else 'grasp'):
                raise ValueError('instruction differs from boolean message schedule')
            proposal=None;done=False
            if b.pending is None:
                proposal,done=executors[rid].step(obs,[])
                b.propose(proposal,done,previous[rid])
            value,done=b.issue(now,previous[rid],proposal,done,permits[rid])
            expected=dict(t=now,robot=rid,command=value,done=done,ready=b.ready,
                permit=permits[rid],waiting=waiting)
            if expected!=actual:raise ValueError('ACT/protocol command replay mismatch at '+str((rid,now)))
            previous[rid]=value;histories[rid].append(value)
    try:next(chunks)
    except StopIteration:pass
    else:raise ValueError('unconsumed ACT chunks')
    if sync.events!=protocol['events'] or {r:b.events for r,b in barriers.items()}!=protocol['own_events']:
        raise ValueError('protocol event replay mismatch')
    return dict(passed=True,command_rows=len(commands),inference_chunks=used,
        command_mismatches=0,issued_history_mismatches=0,protocol_event_mismatches=0,
        scope='serialized own inputs/chunks to issued commands only; no physics/model inference replay')
