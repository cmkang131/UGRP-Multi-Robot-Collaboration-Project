import pytest
from sim.warp_native_runtime import allocation


def envelope(**kw):
    e=dict(fixed_work_complete=True,overflow=[0]*16,max_nacon=1001,max_nefc=301,nworld=16,
           source_states_sha256='states',source_result_sha256='result')
    e.update(kw)
    return dict(every_step_envelope=e)


def test_global_contacts_round_up_and_import_is_included():
    c=allocation('warp_measured_capacity_v1',envelope(),64,62,300)
    assert (c['naconmax'],c['njmax'])==(63*64,301)
    c=allocation('warp_measured_capacity_v1',envelope(),16,70,400)
    assert (c['naconmax'],c['njmax'])==(70*16,400)


@pytest.mark.parametrize('change',[dict(fixed_work_complete=False),dict(overflow=[0,1024]),
                                  dict(source_result_sha256=None)])
def test_incomplete_overflow_and_unverifiable_envelopes_reject(change):
    with pytest.raises(ValueError):allocation('warp_measured_capacity_v1',envelope(**change),16,1,1)


def test_off_is_not_an_implicit_allocation_change():
    assert allocation('off',{},16,1,1) is None
    assert allocation('warp_upstream_plane_v1',{},16,1,1) is None
    with pytest.raises(ValueError):allocation('typo',{},16,1,1)
