"""No local model; optional tiny synthetic shared-head/loss check on Linux CI."""
import platform
import pytest

from harness.beamact4_policy import install_stage_head
from harness.beamact_pair_student import STAGE_MODE, LEARNED_STAGES


def test_head_is_off_by_default_and_unknown_mode_fails():
    policy=object()
    assert install_stage_head(policy) is policy
    with pytest.raises(ValueError,match='stage mode'):install_stage_head(policy,stage_mode='unknown')


def test_stage_target_is_not_forward_input_and_valid_horizons_have_gradients():
    if platform.system()!='Linux':pytest.skip('Linux CI synthetic tensors only; no Mac ML')
    torch=pytest.importorskip('torch')
    from torch import nn
    from types import SimpleNamespace
    from harness import grasp_act_contract as c
    from harness import beamact3
    from harness.beamact4_policy import policy_loss
    class Model(nn.Module):
        def __init__(self):
            super().__init__();self.action_head=nn.Linear(6,14);self.calls=0
        def forward(self,b):
            assert 'stage_target' not in b
            self.calls+=1
            return self.action_head(b['features']),(None,None)
    class Policy(nn.Module):
        def __init__(self):
            super().__init__();self.model=Model();self.config=SimpleNamespace(dim_model=6)
        def forward(self,b):
            y=self.model(b)[0];loss=(y-b['action']).abs()[~b['action_is_pad']].mean()
            return loss,dict(l1_loss=loss.item())
    stats=dict(action_mean=[0.]*14,action_std=[1.]*14)
    torch.manual_seed(11)
    p=install_stage_head(beamact3.install_head(Policy(),stats),stage_mode=STAGE_MODE)
    state=torch.zeros(2,c.CONTEXT_DIM);state[:,c.HISTORY*14]=1
    action=torch.zeros(2,c.CHUNK,14);action[0,:,:4]=.35;action[1,:,:4]=-.35;action[0,:,-1]=1
    pad=torch.zeros(2,c.CHUNK,dtype=torch.bool);pad[:,4:]=True
    targets=torch.arange(16).reshape(2,8)%len(LEARNED_STAGES)
    b=dict(features=torch.randn(2,8,6),action=action,action_is_pad=pad,
        stage_target=targets,**{'observation.state':state})
    kw=dict(stage_mode=STAGE_MODE,mode='balanced_bce_v1',stats=stats,priors={'grasp':{'positive_fraction':.5}})
    loss,metrics=policy_loss(p,b,**kw);loss.backward()
    assert p.model.calls==1 and metrics['stage_ce_loss']>0
    assert p.model.action_head.stage.weight.grad.abs().sum()>0
    assert p.model.action_head.action.wheel.weight.grad.abs().sum()>0
    assert p.model.action_head.action.continuous.weight.grad.abs().sum()>0
    b['stage_target']=targets.clone();b['stage_target'][:,4:]=1000
    changed,_=policy_loss(p,b,**kw);assert changed.item()==pytest.approx(loss.item())
    b['stage_target'][0,0]=1000
    with pytest.raises(ValueError,match='categorical stage targets'):policy_loss(p,b,**kw)
