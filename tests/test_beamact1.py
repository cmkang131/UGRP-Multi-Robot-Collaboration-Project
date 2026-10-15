import json
import numpy as np
import pytest

from harness import grasp_act_contract as c
from harness.beamact_input import MASK_COLUMNS, transform_state, transform_batch, contract_check
from scripts.prepare_beamact1 import split_seeds
from scripts.evaluate_beamact1 import persistence, refresh_grid, summarize
from scripts.grasp_act_training_guard import authorize_main


def test_seed_split_is_grouped_deterministic_and_never_uses_heldout():
    seeds = list(range(8328000, 8328185))
    reserved = list(range(8329000, 8329020))
    train, val = split_seeds(seeds, reserved)
    assert (len(train), len(val)) == (166,19)
    assert not set(train) & set(val) and set(train+val) == set(seeds)
    assert split_seeds(seeds[::-1], reserved) == (train,val)
    with pytest.raises(ValueError):
        split_seeds(seeds, [seeds[0]])


def test_mask_retains_pwm_ages_instructions_and_clocks_without_mutation():
    contract_check(c)
    state = np.arange(2*c.CONTEXT_DIM).reshape(2,-1).astype(np.float32)+1
    before = state.copy()
    assert transform_state(state) is state
    changed = transform_state(state, 'wheel_pulse_train_mean')
    assert (changed[:, MASK_COLUMNS] == 0).all()
    rest = sorted(set(range(c.CONTEXT_DIM)) - set(MASK_COLUMNS))
    assert np.array_equal(changed[:, rest], state[:, rest])
    assert np.array_equal(state,before)
    batch = {'observation.state':state, 'images':object(), 'action':object()}
    candidate = transform_batch(batch, 'wheel_pulse_train_mean')
    assert candidate['images'] is batch['images'] and candidate['action'] is batch['action']
    with pytest.raises(ValueError):
        transform_state(state[:,:-1], 'wheel_pulse_train_mean')


def test_main_rejects_mask_mismatch_with_legacy_compatible_default(tmp_path):
    approval = dict(approved=True,stage='main',source_sha='sha',dataset_manifest_sha256='data',
        smoke_summary_sha256='smoke',steps=10000,blank_images=False,
        gate_promotion_authorized_if_all_conditions_pass=False)
    path = tmp_path/'approval.json';path.write_text(json.dumps(approval))
    kwargs = dict(source='sha',dataset_hash='data',smoke_hash='smoke',steps=10000,blank=False)
    authorize_main(path,**kwargs)
    with pytest.raises(ValueError,match='mask'):
        authorize_main(path,**kwargs,history_causal_split_v1='wheel_pulse_train_mean')
    approval['history_causal_split_v1']='wheel_pulse_train_mean';path.write_text(json.dumps(approval))
    authorize_main(path,**kwargs,history_causal_split_v1='wheel_pulse_train_mean')


def test_persistence_uses_latest_raw_issued_command_and_refresh_resets_at_gaps():
    state = np.zeros((3,c.CONTEXT_DIM),np.float32)
    state[:,:14] = 999  # oldest command must never be the baseline
    state[:,210:223] = np.arange(13)
    baseline = persistence(state)
    assert np.array_equal(baseline[:,:13],np.tile(np.arange(13),(3,1)))
    assert not baseline[:,-1].any()
    rows = [dict(robot_id='r1',role='teal',object_kind='long_beam',skill='grasp',t=i*.1) for i in range(10)]
    rows[9]['t']=2
    assert np.flatnonzero(refresh_grid(rows)).tolist() == [0,8,9]


def test_metrics_compare_same_rows_and_keep_empty_ACT_unmeasured():
    y = np.zeros((3,14));base=y.copy();base[:,:4]=.35;base[:,4:8]=1
    report = summarize(None,base,y,['approach','align','align'],np.array([True,False,True]))
    assert report['all_h0']['all']['persistence']['N'] == 3
    assert report['refresh_h0']['all']['persistence']['N'] == 2
    assert report['refresh_h0']['align']['persistence']['N'] == 1
    assert report['all_h0']['all']['persistence']['pulse_mae_ms'] == 150
    assert 'ACT' not in report['all_h0']['all']


def test_masked_actor_serialization_optional(tmp_path):
    """CPU library check only; never substitutes for L4 optimizer smoke."""
    import os
    import platform
    if platform.system() != 'Linux' or os.environ.get('UGRP_BEAMACT_SERIALIZE_CHECK') != '1':
        pytest.skip('explicit GCP2 CPU adapter check only')
    from scripts.beamact1_runtime import require_gcp2
    require_gcp2(training=False)
    import io
    import torch
    from PIL import Image
    from harness.beamact_input import BeamActor, save_actor
    from harness.grasp_act_data import fit_stats
    from harness.grasp_act_policy import make_policy, GraspActor
    from harness.grasp_act_rollout import OwnHistory
    torch.set_num_threads(2)
    torch.manual_seed(20261015)
    initial = dict(t=0., wheels=[0.]*4, duration_s=[0.]*4,
                   pwm={str(s):2000 for s in c.SERVOS})
    pixels = io.BytesIO();Image.new('RGB',(640,480),'gray').save(pixels,'JPEG')
    observation,jpegs,_ = OwnHistory('r1','serialization',initial).observe(0.,pixels.getvalue(),
        skill='grasp',object_kind='long_beam',role='teal')
    stats = fit_stats([c.context(observation)],[c.encode_action(initial)],[1])
    policy = make_policy(device='cpu')
    path = tmp_path/'actor'
    save_actor(policy,path,stats,{'scope':'random initialization serialization only'},
               mode='wheel_pulse_train_mean')
    original = BeamActor(GraspActor(policy,stats,device='cpu',done_mode='balanced_bce_v1'),
                         'wheel_pulse_train_mean')
    restored = BeamActor.load(path,device='cpu')
    assert np.array_equal(original.predict(observation,jpegs),restored.predict(observation,jpegs))
    with pytest.raises(ValueError):
        GraspActor.load(path,device='cpu')  # stock loader cannot forget masking
