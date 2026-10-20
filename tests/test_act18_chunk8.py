"""Default-off chunk gate: R8 is contract-sized; R100 is rejected, never sliced."""
import io
from pathlib import Path
import sys

import numpy as np
from PIL import Image
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from act18_chunk8 import (contract_chunk_predict,contract_chunk_rows,
                          pilot_checkpoint_chunk,require_contract_chunk)
from harness import grasp_act_contract as c
from harness.grasp_act_policy import ChunkExecutor
from harness.grasp_act_rollout import OwnHistory


def observation():
    stream=io.BytesIO();Image.new('RGB',(640,480),'red').save(stream,'JPEG')
    initial={'t':0.,'wheels':[0.]*4,'duration_s':[0.]*4,
             'pwm':{str(s):1500 for s in c.SERVOS}}
    history=OwnHistory('r1','synthetic-chunk8',initial)
    obs,jpgs,_=history.observe(0.,stream.getvalue(),skill='grasp',
                               object_kind='cyan',role='west')
    return obs,jpgs


def advance(obs,now):
    obs['t']=now
    for ref in obs['rgb']:ref['t']=now


def test_disabled_gate_is_a_strict_noop():
    rows=np.zeros((100,c.ACTION_DIM))
    assert contract_chunk_rows(rows,enabled=False) is rows
    assert require_contract_chunk(100,enabled=False) is None
    predict=lambda observation,jpegs:[]
    assert contract_chunk_predict(predict,enabled=False) is predict


def test_r100_long_chunk_is_rejected_instead_of_sliced():
    with pytest.raises(ValueError,match='frozen contract chunk 8'):
        require_contract_chunk(100,enabled=True)
    rows=np.zeros((100,c.ACTION_DIM))
    with pytest.raises(ValueError,match=r'\(100, 14\)'):
        contract_chunk_rows(rows,enabled=True)
    # The same object is untouched when the default-off gate is not selected.
    assert contract_chunk_rows(rows) is rows


def test_gate_on_does_not_change_r8_commands_and_off_stays_legacy():
    chunk=[[.4]*4+[1.]*4+[0.]*5+[0.]]*c.CHUNK
    off=ChunkExecutor(contract_chunk_predict(lambda *_:chunk,enabled=False))
    on=ChunkExecutor(contract_chunk_predict(lambda *_:chunk,enabled=True))
    obs_off,jpgs_off=observation();obs_on,jpgs_on=observation()
    for tick in range(c.CHUNK):
        advance(obs_off,tick*c.PERIOD_S);advance(obs_on,tick*c.PERIOD_S)
        assert off.step(obs_off,jpgs_off)==on.step(obs_on,jpgs_on)


def test_pilot_flag_off_keeps_the_previous_checkpoint_unchanged():
    r100={'schema':'ugrp.act18.adapter.v1','chunk':100}
    assert pilot_checkpoint_chunk(r100,takeover_pilot=True,enabled=False)==100
    act16w={'schema':'ugrp.grasp_act.adapter.act16w.v3'}
    assert pilot_checkpoint_chunk(act16w,takeover_pilot=True,enabled=False) is None


def test_pilot_flag_on_admits_r8_and_rejects_r100_before_the_owner_starts():
    r8={'schema':'ugrp.act18.adapter.v1','chunk':8}
    r100={'schema':'ugrp.act18.adapter.v1','chunk':100}
    assert pilot_checkpoint_chunk(r8,takeover_pilot=True,enabled=True)==8
    with pytest.raises(ValueError,match='frozen contract chunk 8'):
        pilot_checkpoint_chunk(r100,takeover_pilot=True,enabled=True)
    with pytest.raises(ValueError,match='takeover-pilot-only'):
        pilot_checkpoint_chunk(r8,takeover_pilot=False,enabled=True)
    with pytest.raises(ValueError,match='act18 adapter schema'):
        pilot_checkpoint_chunk({'schema':'ugrp.grasp_act.adapter.act16w.v3','chunk':8},
                               takeover_pilot=True,enabled=True)


def test_contract_boundary_is_exactly_eight():
    assert require_contract_chunk(c.CHUNK,enabled=True)==8
    for bad in (c.CHUNK-1,c.CHUNK+1,100,True,8.0,None):
        with pytest.raises(ValueError):
            require_contract_chunk(bad,enabled=True)
    for shape in ((c.CHUNK-1,c.ACTION_DIM),(c.CHUNK+1,c.ACTION_DIM),
                  (100,c.ACTION_DIM),(c.CHUNK,c.ACTION_DIM-1)):
        with pytest.raises(ValueError):
            contract_chunk_rows(np.zeros(shape),enabled=True)
    assert contract_chunk_rows(np.zeros((c.CHUNK,c.ACTION_DIM)),
                               enabled=True).shape==(c.CHUNK,c.ACTION_DIM)
    nonfinite=np.zeros((c.CHUNK,c.ACTION_DIM));nonfinite[0,0]=np.nan
    with pytest.raises(ValueError,match='nonfinite'):
        contract_chunk_rows(nonfinite,enabled=True)


def test_wrapped_r8_predict_is_identical_to_the_raw_chunk():
    values=np.arange(c.CHUNK*c.ACTION_DIM,dtype=float).reshape(c.CHUNK,c.ACTION_DIM)
    raw=contract_chunk_predict(lambda observation,jpegs:values.copy(),enabled=False)
    guarded=contract_chunk_predict(lambda observation,jpegs:values.copy(),enabled=True)
    assert raw is not guarded
    assert np.array_equal(np.asarray(guarded(None,None)),values)
    with pytest.raises(ValueError,match=r'\(100, 14\)'):
        contract_chunk_predict(lambda observation,jpegs:
                               np.zeros((100,c.ACTION_DIM)),enabled=True)(None,None)


def test_executor_queries_once_per_eight_tick_contract_block():
    obs,jpgs=observation();calls=[]
    def predict(*_):
        calls.append(1)
        return [[.4]*4+[1.]*4+[0.]*5+[0.]]*c.CHUNK
    executor=ChunkExecutor(predict)
    for tick in range(c.CHUNK):
        advance(obs,tick*c.PERIOD_S)
        executor.step(obs,jpgs)
    assert len(calls)==1
    advance(obs,c.CHUNK*c.PERIOD_S)
    executor.step(obs,jpgs)
    assert len(calls)==2


def test_executor_still_rejects_r100_chunk_at_the_contract_boundary():
    obs,jpgs=observation()
    executor=ChunkExecutor(lambda *_:[[0.]*c.ACTION_DIM]*100)
    with pytest.raises(ValueError,match='invalid action chunk'):
        executor.step(obs,jpgs)
