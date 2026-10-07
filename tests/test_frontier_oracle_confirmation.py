"""Evaluation wiring/gates only; no new confirmation episodes in unit tests."""
import copy
from pathlib import Path
import sys
import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments/2026-10-07-mapfree-frontier-oracle/code'))
import run_frontier as r
from harness.self_map_prob import V7CommandOdometry


def test_oracle_pose_bridge_preserves_time_commands_and_corrects_contact_drift():
    sampled=[.2,.3,.4]
    odom=V7CommandOdometry()
    bridge=r.OraclePoseBridge(odom,lambda:sampled)
    bridge.command(dict(t=0.,kind='mecanum',forward=.5,left=0.,turn=0.,duration_s=1.))
    bridge.advance(.5)
    # The privileged environment may have blocked the commanded translation.
    np.testing.assert_allclose(bridge.pose,sampled,atol=1e-12)
    assert bridge.t==.5 and not bridge.covariance.any()
    sampled[:]=[.25,.4,-.2]
    bridge.advance(1.)
    np.testing.assert_allclose(bridge.pose,sampled,atol=1e-12)
    with pytest.raises(ValueError,match='POSE_ONLY'):
        r.OraclePoseBridge(odom,lambda:[1,2,3,4])


def complete_rows():
    return [dict(scenario=f's{i}',start=s,seed=seed,condition=mode,status='B_confirmed',
        first_B=dict(time_s=60.,distance_m=2.),coverage=.5,time_s=60.,distance_m=2.,
        collisions=0,wrong_door_attempts=0,false_candidate_passage_attempts=0,door_attempts=1,
        end_position_error_m=0.)
        for i in range(1,9) for s in ('K','L') for seed in (6701,6702) for mode in ('static_map','own_frontier')]


def test_gate_keeps_original_five_criteria_and_fixed_denominator():
    rows=complete_rows()
    assert r.summary(rows,True)['passed']
    assert not r.summary(rows[:-1],True)['passed']
    assert not r.summary(rows,False)['passed']
    failed=copy.deepcopy(rows)
    own=[q for q in failed if q['condition']=='own_frontier']
    for q in own[:7]:q['status']='budget';q['first_B']=None
    assert not r.summary(failed,True)['checks']['B_confirmation'] #25/32, not25/25
    for q in own:q['collisions']=1
    assert not r.summary(failed,True)['checks']['safety']
    for q in own:q['collisions']=0;q['door_attempts']=0
    assert not r.summary(failed,True)['checks']['safety']
    for q in own:q['status']='budget';q['first_B']=None
    assert not r.summary(failed,True)['checks']['efficiency']


def test_registered_new_starts_are_deterministic_and_source_is_frozen():
    manifest=r.read(r.EXP/'cohort.json')
    assert r.registration.generate()==manifest
    assert len(manifest['rows'])==32
    assert {x['seed'] for x in manifest['rows']}=={6701,6702}
    assert len({(x['scenario'],tuple(x['pose'])) for x in manifest['rows']})==16
    frozen=r.read(r.v5.EXP/'freeze.json')
    assert r.verify_frozen()==frozen['hashes']
    assert r.SETTINGS==frozen['settings']
    assert 'mujoco' not in sys.modules


def test_new_wrapper_does_not_replace_frozen_episode_or_actor_implementation():
    import inspect
    source=inspect.getsource(r.configure)
    assert 'old.episode=' not in source
    assert 'condition==\'own_frontier\'' in source
    assert 'static_grid is None and static_goal is None' in source
    assert 'not actor.grid.odds' in source
    # The only shared actor correction is explicitly confined to this eval adapter.
    assert r.OraclePoseBridge.__module__=='run_frontier'
