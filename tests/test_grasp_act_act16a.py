import numpy as np
import pytest

from scripts.analyze_grasp_act_act16a import validate_cpu_identity, reversal_events


def test_analysis_rejects_first_project_and_gpu():
    with pytest.raises(ValueError):
        validate_cpu_identity('ugrp-act-train-1014','ugrp-sim-gcp1','n4-highcpu-64','z')
    with pytest.raises(ValueError):
        validate_cpu_identity('ugrp-sim-b-1014','ugrp-act-l4-gcp2','g2-standard-8','z')
    assert validate_cpu_identity('ugrp-sim-b-1014','ugrp-sim-gcp2','n4-highcpu-64','z')['instance']=='ugrp-sim-gcp2'


def test_reversal_ends_at_next_target_change_and_keeps_censoring():
    def row(t, target, act, previous):
        return {'t':t,'valid':True,'phase':'align',
                'target':{'wheels':[target]*4},'act':{'wheels':[act]*4},
                'persistence':{'wheels':[previous]*4}}
    events=reversal_events([row(0.,1.,1.,1.),row(.1,-1.,1.,1.),row(.2,-1.,-1.,1.),row(.3,0.,0.,-1.)])
    assert len(events)==4
    assert events[0]['act_delay_s']==pytest.approx(.1)
    assert events[0]['persistence_censored'] is True


def test_mask_preserves_pwm_ages_tokens_and_clocks():
    torch=pytest.importorskip('torch')
    from harness import grasp_act_contract as c
    from scripts.analyze_grasp_act_act16a import mask_wheel_pulse_history
    state=torch.arange(c.CONTEXT_DIM,dtype=torch.float32)[None,:]
    masked=mask_wheel_pulse_history(state)
    changed=[]
    for lag in range(c.HISTORY):changed.extend(range(lag*14,lag*14+8))
    kept=[i for i in range(c.CONTEXT_DIM) if i not in changed]
    assert torch.all(masked[:,changed]==0)
    assert torch.equal(masked[:,kept],state[:,kept])
    assert state[0,1]==1
