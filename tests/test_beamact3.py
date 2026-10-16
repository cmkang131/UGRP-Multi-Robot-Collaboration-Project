"""Non-physics contracts; optional tiny synthetic torch checks on GCP2 only."""
import json
import numpy as np
import pytest

from harness import grasp_act_contract as c
from harness.beamact3 import COMPACT_HISTORY, transform_state, transform_batch


def test_compact_ab_diff_is_only_recent_wheel_pulse_and_preserves_role():
    state=np.arange(2*c.CONTEXT_DIM,dtype=np.float32).reshape(2,-1)+1
    before=state.copy()
    assert transform_state(state) is state
    a=transform_state(state,'A');b=transform_state(state,'B')
    end=(c.HISTORY-COMPACT_HISTORY)*14
    assert not a[:,:end].any() and not b[:,:end].any()
    assert np.array_equal(a[:,end:],state[:,end:])
    columns=[j*14+k for j in range(c.HISTORY-COMPACT_HISTORY,c.HISTORY) for k in range(8)]
    rest=sorted(set(range(c.CONTEXT_DIM))-set(columns))
    assert not b[:,columns].any() and np.array_equal(a[:,rest],b[:,rest])
    assert np.array_equal(state,before)
    labels=object();images=object()
    out=transform_batch({'observation.state':state,'action':labels,'image':images},'A')
    assert out['action'] is labels and out['image'] is images
    with pytest.raises(ValueError):transform_state(state[:,:-1],'A')
    with pytest.raises(ValueError):transform_state(state,'C')


def test_main_admission_rejects_cross_arm_resume(tmp_path):
    from scripts.grasp_act_training_guard import authorize_main
    data=dict(approved=True,stage='main',source_sha='s',dataset_manifest_sha256='d',
        smoke_summary_sha256='h',steps=20000,blank_images=False,
        gate_promotion_authorized_if_all_conditions_pass=False,beamact3_v1='A')
    path=tmp_path/'admission.json';path.write_text(json.dumps(data))
    kw=dict(source='s',dataset_hash='d',smoke_hash='h',steps=20000,blank=False)
    authorize_main(path,**kw,beamact3_v1='A')
    with pytest.raises(ValueError,match='arm'):authorize_main(path,**kw,beamact3_v1='B')
    with pytest.raises(ValueError,match='arm'):authorize_main(path,**kw)


def test_categorical_loss_gradient_and_padding_optional():
    import platform
    if platform.system()!='Linux':pytest.skip('GCP2 synthetic torch only; no Mac model')
    import torch
    from torch import nn
    from types import SimpleNamespace
    from harness.beamact3 import install_head,policy_loss,WHEEL_VALUES
    class Model(nn.Module):
        def __init__(self):
            super().__init__();self.action_head=nn.Linear(6,14)
        def forward(self,b):return self.action_head(b['features']), (None,None)
    class Policy(nn.Module):
        def __init__(self):
            super().__init__();self.model=Model();self.config=SimpleNamespace(dim_model=6)
        def forward(self,b):
            y=self.model(b)[0];valid=~b['action_is_pad']
            loss=(y-b['action']).abs()[valid].mean()
            return loss,dict(l1_loss=loss.item())
    stats=dict(action_mean=[0.]*14,action_std=[1.]*14)
    torch.manual_seed(7);p=install_head(Policy(),stats)
    state=torch.zeros(2,c.CONTEXT_DIM);state[:,c.HISTORY*14]=1
    y=torch.zeros(2,8,14);y[0,:,:4]=.35;y[1,:,:4]=-.35;y[0,:,-1]=1
    pad=torch.zeros(2,8,dtype=torch.bool);pad[:,4:]=True
    b={'features':torch.randn(2,8,6),'observation.state':state,'action':y,'action_is_pad':pad}
    kw=dict(mode='balanced_bce_v1',stats=stats,priors={'grasp':{'positive_fraction':.5}})
    loss,metrics=policy_loss(p,b,**kw);loss.backward()
    assert p.model.action_head.wheel.weight.grad.abs().sum()>0
    assert p.model.action_head.continuous.weight.grad.abs().sum()>0
    assert metrics['wheel_ce_loss']>0
    pred=p.model(b)[0].detach().numpy()
    assert np.isin(pred[...,:4],np.asarray(WHEEL_VALUES,np.float32)).all()
    old=loss.item();b['action']=y.clone();b['action'][:,4:,:4]=.123
    other,_=policy_loss(p,b,**kw)
    assert other.item()==pytest.approx(old)
