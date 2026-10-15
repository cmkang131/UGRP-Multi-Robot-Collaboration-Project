from copy import deepcopy
from types import SimpleNamespace

import pytest

from harness.beampair_teacher import HeldCargoGuard, validate_plan, perturb_model, defer_ready_during_probe, PairRecoveryPerturb
from harness.grasp_act_perturb import RecoveryPerturb


def command(pwm=2000):
    return dict(t=1.,pwm={str(i):pwm if i==1 else 1500 for i in (1,3,4,5,6)},
                wheels=[.35]*4,duration_s=[.1]*4)


def test_distinct_color_roles_required():
    p=dict(object_kind='long_beam',target_item='beam_1',roles={'r1':'teal','r2':'blue'},
           end_color_scene='grasp_act_teal_blue_v1',burst_ticks=12)
    validate_plan(p)
    with pytest.raises(ValueError,match='distinct'):
        validate_plan({**p,'roles':{'r1':'teal','r2':'teal'}})


def test_either_close_hides_both_inputs_without_truth_and_clears_memory():
    guard=HeldCargoGuard();guard.issued(command())
    assert not guard.active
    guard.issued(command(1500));assert guard.active
    world=dict(beam={'secret_position':[1,2,3]},objects={'beam_1':{},'red_1':{}},
        visibility={'r1':dict(visible_probes=15,objects=['beam_1','red_1'],
            observations={'band_teal':{},'band_blue':{},'beam_1':{},'red_1':{}})})
    before=deepcopy(world)
    model=SimpleNamespace(memory={'band_teal':{},'band_blue':{},'beam_1':{},'red_1':{}})
    guard.sanitize_memory(model)
    hidden=guard.sanitize_world(world)
    assert model.memory=={'red_1':{}}
    assert hidden['beam'] is None and hidden['objects']=={'red_1':{}}
    assert hidden['visibility']['r1']['observations']=={'red_1':{}}
    assert world==before
    guard.validate_measurements([{'id':'red_1'}])
    assert guard.held_world_reads==0
    with pytest.raises(ValueError,match='held cargo'):
        guard.validate_measurements([{'id':'band_blue'}])
    assert guard.held_world_reads==1


@pytest.mark.parametrize('ticks',[1,3,5,8,10,12])
def test_mixed_disturbances_have_exact_issued_length_and_stop_on_close(ticks):
    model=perturb_model(ticks);model.update(probability_per_eligible_tick=1.,minimum_eligible_ticks=1)
    p=RecoveryPerturb(model,seed=7)
    values=[p.apply(command(),phase_before='approach',phase_after='approach',holding=False,visible=True)[1]
            for _ in range(ticks+1)]
    assert [v['tick'] for v in values if v] == list(range(1,ticks+1))
    assert values[-1] is None
    q=RecoveryPerturb(model,seed=7)
    clean=command(1500)
    actual,noise=q.apply(clean,phase_before='approach',phase_after='pick',holding=True,visible=True)
    assert actual==clean and noise is None


def test_ready_transition_cannot_truncate_an_active_twelve_tick_burst():
    m=perturb_model(12);m.update(probability_per_eligible_tick=1.,minimum_eligible_ticks=1)
    noise=RecoveryPerturb(m,seed=7)
    teacher=SimpleNamespace(phase='align',phase_t=0.,events=[])
    issued=[]
    for tick in range(13):
        before=teacher.phase
        if tick:
            teacher.phase='ready';teacher.events.append({'to':'ready'})
        defer_ready_during_probe(teacher,before,0.,noise.active)
        _,record=noise.apply(command(),phase_before=before,phase_after=teacher.phase,holding=False,visible=True)
        if record:issued.append(record['tick'])
    assert issued==list(range(1,13))
    assert teacher.phase=='ready'


def test_loss_to_search_does_not_shorten_requested_burst_but_pick_cancels():
    m=perturb_model(12);m.update(probability_per_eligible_tick=1.,minimum_eligible_ticks=1)
    probe=PairRecoveryPerturb(m,seed=7);issued=[]
    for i in range(13):
        before='approach' if i<4 else 'search';after='approach' if i<3 else 'search'
        _,d=probe.apply(command(),phase_before=before,phase_after=after,holding=False,visible=i<3)
        if d:issued.append(d['tick'])
    assert issued==list(range(1,13))
    probe=PairRecoveryPerturb(m,seed=7)
    probe.apply(command(),phase_before='align',phase_after='align',holding=False,visible=True)
    _,d=probe.apply(command(1500),phase_before='align',phase_after='pick',holding=True,visible=False)
    assert d is None and not probe.active
