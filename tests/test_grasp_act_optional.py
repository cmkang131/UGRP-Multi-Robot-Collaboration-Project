"""Real upstream forward/backward/readback; no physical rollout."""
import io
import pytest
pytest.importorskip('lerobot')
import torch
from PIL import Image
from harness.grasp_act import make_policy, GraspAct, batch
from harness.grasp_act_contract import CHUNK,ACTION_DIM
from harness.grasp_act_contract import SCHEMA, HISTORY

def observation():
    cmd={'t':0.,'drive':[0.,0.,0.],'duration_s':0.,'pwm':{'1':2000,'3':740,'4':2320,'5':1320,'6':1500}}
    return {'schema':SCHEMA,'sample_id':'smoke:0:r1','robot_id':'r1','t':0.,
            'object_kind':'long_beam','skill':'grasp','role':'teal','issued':[cmd]*HISTORY,
            'rgb':[{'path':'rgb/smoke.jpg','sha256':'a'*64,'t':0.,'robot_id':'r1'} for _ in range(2)]}


def jpeg():
    stream=io.BytesIO();Image.new('RGB',(64,48),(70,150,110)).save(stream,format='JPEG')
    return stream.getvalue()


def test_real_conditional_act_backward_and_reload(tmp_path):
    torch.set_num_threads(2);torch.manual_seed(17)
    policy=make_policy('smoke');obs=observation();images=[jpeg(),jpeg()]
    b=batch(obs,images,'smoke');b.update(action=torch.zeros(1,CHUNK,ACTION_DIM),action_is_pad=torch.zeros(1,CHUNK,dtype=torch.bool))
    loss,_=policy(b);assert torch.isfinite(loss);loss.backward()
    assert any(p.grad is not None and torch.count_nonzero(p.grad) for p in policy.parameters())
    actor=GraspAct(policy,'smoke');expected=actor.predict_chunk(obs,images)
    assert len(expected)==CHUNK
    actor.save(tmp_path/'act');loaded=GraspAct.load(tmp_path/'act')
    assert loaded.predict_chunk(obs,images)==expected
    other=observation();other['role']='blue'
    a=batch(obs,images,'smoke');b=batch(other,images,'smoke')
    assert not torch.equal(a['observation.environment_state'],b['observation.environment_state'])


def test_deployed_done_loss_retains_zero_latent_gradient():
    from scripts.train_grasp_act import deployed_done_loss
    torch.set_num_threads(2);policy=make_policy('smoke');obs=observation();b=batch(obs,[jpeg(),jpeg()],'smoke')
    b['action']=torch.zeros(1,CHUNK,ACTION_DIM);b['action'][:,:, -1]=1
    b['action_is_pad']=torch.zeros(1,CHUNK,dtype=torch.bool)
    policy.train();loss=deployed_done_loss(policy,b);assert policy.training and loss.requires_grad
    loss.backward();assert torch.count_nonzero(policy.model.action_head.weight.grad)>0


def test_old_pulse_checkpoint_cannot_load_as_continuous(tmp_path):
    import json
    from harness.grasp_act import metadata
    old=metadata('smoke');old.pop('action_contract');old.pop('actuator_port')
    old['schema']='ugrp.grasp_act.adapter.v2'
    (tmp_path/'adapter.json').write_text(json.dumps(old))
    with pytest.raises(ValueError,match='wrong ACT adapter'):GraspAct.load(tmp_path)
