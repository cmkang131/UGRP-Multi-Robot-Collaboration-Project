import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import act17_data as m


def test_source_jpeg_digest_is_checked_before_decoding(tmp_path):
    p=tmp_path/'frame.jpg';p.write_bytes(b'changed capture')
    import pytest
    with pytest.raises(ValueError,match='source JPEG changed'):
        m.raw_image(str(p),'0'*64,False)


def test_episode_uniform_done_prior_is_not_raw_frame_fraction(monkeypatch):
    import harness
    contract=SimpleNamespace(SKILLS=('grasp','release'))
    monkeypatch.setattr(harness,'grasp_act_contract',contract,raising=False)
    monkeypatch.setitem(sys.modules,'harness.grasp_act_contract',contract)
    d=m.Dataset.__new__(m.Dataset)
    d.split='train';d.episode_indices=[np.arange(4),np.arange(4,12)]
    d.index=[(0,i) for i in range(4)]+[(1,i) for i in range(8)]
    d.metadata=[dict(skill=k) for k in ['grasp','grasp','release','release','grasp','grasp','grasp','grasp','release','release','release','release']]
    a=np.zeros((4,8,14),np.float32);b=np.zeros((8,8,14),np.float32)
    a[[1,3],0,-1]=1;b[[3,7],0,-1]=1
    d.shards=[dict(action=a),dict(action=b)]
    priors=d.completion_priors('uniform_episode_v1')
    assert priors['grasp']['positive_fraction']==.375
    assert priors['release']['positive_fraction']==.375
    assert priors['grasp']['positive_n']==2
    assert priors['grasp']['rows_N']==6
