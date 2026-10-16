"""Synthetic commands and pinned protocol only: no physics, render or ML."""
from copy import deepcopy

import numpy as np
import pytest

from harness import grasp_act_contract as c
from harness.grasp_act_rollout import OwnHistory
from harness.beamact4_execution import PairChunkExecutor, decode_stages
from harness.beamact_pair_student import (StudentBarrier, RearmingStartSync,
    STAGE_MODE, RECOVERY_MODE, LEARNED_STAGES)
from harness.beamact_replay import protocol_class, replay


def command(t=0., grip=2000):
    return dict(t=t, wheels=[.35]*4, duration_s=[.1]*4,
        pwm={'1':grip, '3':800, '4':2400, '5':1320, '6':1500})


def logits(stages):
    return [[float(s == label) for label in LEARNED_STAGES] for s in stages]


def test_PWM_decrease_is_not_READY_and_head_READY_needs_no_PWM_decrease():
    b=StudentBarrier(stage_mode=STAGE_MODE)
    previous=command()
    with pytest.raises(ValueError,match='before issuing'):b.issue(0.,previous,command(grip=1500),False,True)
    assert not b.propose(command(grip=1999),False,previous,stage='alignment')
    assert not b.ready and b.blocked
    value,done=b.issue(.1,previous,command(grip=1999),False,True)
    assert value['pwm']==previous['pwm'] and value['wheels']==[0.]*4 and not done
    assert b.events[-1]['reason_category']=='close_before_learned_ready'
    assert b.events[-1]['blocked_object'] and 'min_gap_m' in b.events[-1]
    assert b.propose(previous,False,previous,stage='ready') and b.ready
    value,_=b.issue(.2,previous,previous,False,False)
    assert value['wheels']==[0.]*4
    value,_=b.issue(.3,previous,previous,False,True)
    assert value==dict(previous,t=.3) and b.started
    b.propose(command(grip=2100),False,previous,stage='recover')
    assert not b.ready and not b.started
    b.propose(command(grip=1500),False,previous,stage='execute')
    value,_=b.issue(.4,previous,command(grip=1500),False,True)
    assert b.blocked and value['pwm']==previous['pwm']  # stale permit cannot rearm
    with pytest.raises(ValueError,match='learned stage'):b.propose(previous,False,previous)


def test_withdrawal_rearms_exact_protocol_and_preserves_start_delay():
    sync=RearmingStartSync(('r1','r2'),{'r1':0.,'r2':1.},protocol_class())
    assert not any(sync.tick({'r1':True,'r2':False},0.).values())
    assert not any(sync.tick({'r1':True,'r2':True},.1).values())  # GO
    assert sync.tick({'r1':True,'r2':True},.2)=={'r1':True,'r2':False}
    assert not any(sync.tick({'r1':False,'r2':True},.3).values())
    assert not any(sync.tick({'r1':True,'r2':True},.4).values())  # new GO
    assert sync.tick({'r1':True,'r2':True},.5)=={'r1':True,'r2':False}
    assert sync.tick({'r1':True,'r2':True},1.4)=={'r1':True,'r2':True}
    assert [e['event'] for e in sync.events].count('GO')==2
    assert sum(e['event']=='READY_withdrawn_rearm' for e in sync.events)==1


def test_done_recovery_forces_fresh_inference_and_legacy_still_absorbs():
    for mode,expected_calls in [('off',1),(RECOVERY_MODE,2)]:
        calls=[];history=OwnHistory('r1','done',command())
        def predict(obs,pictures):
            calls.append(obs)
            return np.tile(c.encode_action(command(),done=len(calls)==1),(c.CHUNK,1)).tolist()
        executor=PairChunkExecutor(predict,done_recovery=mode)
        obs,pictures,_=history.observe(0.,b'rgb',skill='grasp',object_kind='long_beam',role='teal')
        value,done=executor.step(obs,pictures);assert done
        history.issue(value)
        obs,pictures,_=history.observe(.1,b'rgb2',skill='grasp',object_kind='long_beam',role='teal')
        value,done=executor.step(obs,pictures)
        assert len(calls)==expected_calls and done==(mode=='off')
        if mode!= 'off':assert value['wheels']==[.35]*4


def fixture_run():
    rids=('r1','r2');initial={r:command() for r in rids};previous=deepcopy(initial)
    histories={r:OwnHistory(r,'stage-replay',initial[r]) for r in rids}
    barriers={r:StudentBarrier(stage_mode=STAGE_MODE) for r in rids}
    sync=RearmingStartSync(rids,{'r1':0.,'r2':.3},protocol_class())
    inputs=[];commands=[];predictions=[]
    def predict(obs,pictures):
        first=round(obs['t']/c.PERIOD_S);rid=obs['robot_id'];stages=[];chunk=[]
        for tick in range(first,first+c.CHUNK):
            if tick<2:stage,grip='alignment',1999  # regression: noisy early close
            elif tick < (4 if rid=='r1' else 6):stage,grip='alignment',2000
            elif tick<(10 if rid=='r1' else 11):stage,grip='ready',1500
            elif rid=='r1' and 13<=tick<15:stage,grip='recover',2000
            elif 15<=tick<18:stage,grip='ready',1500
            else:stage,grip='execute',1500
            done=tick==12 and rid=='r1' or tick>=25
            if done:stage='complete'
            stages.append(stage);chunk.append(c.encode_action(command(grip=grip),done=done))
        result=dict(chunk=chunk,stage_logits=logits(stages))
        predictions.append(dict(t=obs['t'],robot=rid,**result));return result
    executors={r:PairChunkExecutor(predict,stage_mode=STAGE_MODE,done_recovery=RECOVERY_MODE) for r in rids}
    for tick in range(35):
        now=tick*c.PERIOD_S;proposals={}
        for rid in rids:
            obs,pictures,_=histories[rid].observe(now,b'own-rgb',skill='grasp',object_kind='long_beam',
                role='teal' if rid=='r1' else 'blue')
            inputs.append(obs)
            proposal,done=executors[rid].step(obs,pictures)
            barriers[rid].propose(proposal,done,previous[rid],stage=executors[rid].stage)
            if barriers[rid].blocked:executors[rid].discard_pending()
            proposals[rid]=(proposal,done)
        permits=sync.tick({r:b.ready for r,b in barriers.items()},now)
        for rid in rids:
            b=barriers[rid];proposal,done=proposals[rid]
            value,done=b.issue(now,previous[rid],proposal,done,permits[rid])
            if b.blocked or (b.ready and not permits[rid]):executors[rid].discard_pending()
            commands.append(dict(t=now,robot=rid,command=value,done=done,ready=b.ready,
                permit=permits[rid],waiting=b.ready and not permits[rid],
                learned_stage=executors[rid].stage,proposal_rejected=b.blocked))
            histories[rid].issue(value);previous[rid]=value
    protocol=dict(events=sync.events,own_events={r:b.events for r,b in barriers.items()},
        delays_s=sync.delays,beamact4_stage_v1=STAGE_MODE,beamact4_done_recovery_v1=RECOVERY_MODE)
    return inputs,commands,predictions,initial,protocol


def test_staged_pair_replay_detects_tampering_and_recovers_after_one_done():
    args=fixture_run();inputs,commands,predictions,initial,protocol=args
    result=replay(*args)
    assert result['command_mismatches']==0 and result['command_rows']==70
    first_close={r:next(x['t'] for x in commands if x['robot']==r and x['command']['pwm']['1']==1500) for r in initial}
    assert first_close['r1']>=.7 and first_close['r2']>=.9
    assert any(x['robot']=='r1' and x['done'] for x in commands if 1.1<x['t']<1.3)
    assert any(x['robot']=='r1' and not x['done'] and x['learned_stage']=='recover' for x in commands if 1.2<x['t']<1.5)
    assert any(e['event']=='READY_withdrawn_rearm' for e in protocol['events'])
    assert any(p['robot']=='r1' and p['t']==pytest.approx(1.3) for p in predictions)
    changed=deepcopy(commands);changed[-1]['command']['pwm']['3']+=1
    with pytest.raises(ValueError,match='command replay'):replay(inputs,changed,predictions,initial,protocol)
    changed=deepcopy(predictions);changed[0]['stage_logits']=logits(['ready']*c.CHUNK)
    with pytest.raises(ValueError,match='command replay'):replay(inputs,commands,changed,initial,protocol)


def test_stage_output_and_observation_allowlists_fail_closed_before_inference():
    with pytest.raises(ValueError,match='ambiguous'):decode_stages(np.zeros((c.CHUNK,len(LEARNED_STAGES))))
    with pytest.raises(ValueError,match='finite'):decode_stages(np.full((c.CHUNK,len(LEARNED_STAGES)),np.nan))
    history=OwnHistory('r1','boundary',command())
    obs,pictures,_=history.observe(0.,b'rgb',skill='grasp',object_kind='long_beam',role='teal')
    def forbidden(*args):raise AssertionError('inference must not be reached')
    executor=PairChunkExecutor(forbidden,stage_mode=STAGE_MODE)
    with pytest.raises(ValueError,match='whitelist'):executor.step(dict(obs,stage_target='ready'),pictures)
    executor=PairChunkExecutor(lambda *args:[[0.]*14]*c.CHUNK,stage_mode=STAGE_MODE)
    with pytest.raises(ValueError,match='checkpoint output'):executor.step(obs,pictures)
    executor=PairChunkExecutor(lambda *args:dict(chunk=[[0.]*14]*c.CHUNK,
        stage_logits=logits(['ready']*c.CHUNK),beam_xyz=[0,0,0]),stage_mode=STAGE_MODE)
    with pytest.raises(ValueError,match='checkpoint output'):executor.step(obs,pictures)
