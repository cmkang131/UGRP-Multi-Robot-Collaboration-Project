"""Nonphysics input/weighting regression; CUDA save/readback is real smoke."""
import importlib
from types import SimpleNamespace
import numpy as np
import pytest
from harness import grasp_act_contract as c
m=importlib.import_module('harness.C1-beamact3c')

def test_c1_removes_entire_history_without_mutating_task_or_source():
    a=np.arange(c.CONTEXT_DIM,dtype=np.float32)+1
    old=a.copy();b=m.transform_state(a,'C1')
    assert not b[:c.HISTORY*14].any()
    assert np.array_equal(b[c.HISTORY*14:],old[c.HISTORY*14:])
    assert np.array_equal(a,old)
    assert np.array_equal(m.transform_state(old*2,'C1')[:c.HISTORY*14],b[:c.HISTORY*14])

def test_c2_deployment_keeps_a_five_commands_no_randomness():
    from harness.beamact3 import transform_state
    a=np.arange(2*c.CONTEXT_DIM,dtype=np.float32).reshape(2,-1)
    assert np.array_equal(m.transform_state(a,'C2'),transform_state(a,'A'))
    with pytest.raises(ValueError):m.transform_state(a,'A')

def test_unique_train_distribution_defines_probability_and_balanced_weight():
    state=np.zeros((4,c.CONTEXT_DIM),np.float32)
    action=np.zeros((4,c.CHUNK,c.ACTION_DIM),np.float32);action[0,0,0]=.35
    p,w=m.train_priors(SimpleNamespace(shards=[dict(state=state,action=action)]))
    assert p['transition_n']==1 and p['stable_n']==3
    assert p['command_history_dropout']==.75
    assert p['transition_to_stable_weight']==3
    assert w[0]==pytest.approx(w[1:].sum())
    assert w.sum()==pytest.approx(1)
