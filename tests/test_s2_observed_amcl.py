import copy,json
from types import SimpleNamespace as NS
import numpy as np
import pytest
from test_solo_cyan_v106 import static,cal,FakePose,FakeVision
from harness.zone_solo_cyan_observed_amcl import Runtime,Previous,install,OPTION


def test_default_and_explicit_off_commands_record_byte_equal(static,cal):
    rs=[cls(static,None,None,provider_factory=lambda *a,**k:FakePose(copy.deepcopy(cal)),
        vision_factory=FakeVision,**opts) for cls,opts in [(Previous,{}),(Runtime,{}),(Runtime,dict(visibility_policy='off'))]]
    try:
        for r in rs:
            r.initial_commands(0.,{'r3':{1:2000,3:600,4:2200,5:1400,6:1500}})
            r.fail('CYAN_NOT_UNIQUELY_VISIBLE',1.)
        assert len(set(json.dumps(r.record()).encode() for r in rs))==1
    finally:
        for r in rs:r.close()


def test_observed_columns_do_not_depend_on_any_particle_prior():
    # A deliberately minimal PF: any attempt to read its prior fails.
    cm=NS(alpha=np.tile([0.,0.,1.],(4,1)),beta=np.tile([0.,0.,1.],(4,1)),
        t_of_row=lambda rows:np.ones(4))
    pf=NS(column_model_for=lambda pose:cm)
    depths=np.full((480,4),np.inf);depths[100,1]=.1
    cargo=np.zeros((480,4),bool);cargo[100,2]=True
    v=NS(audit=dict(parameters=dict(robot_padding_m=.002,cargo_padding_px=2),rows=[]),
        cargo=cargo,depth_image=lambda *a:depths)
    obs=NS(columns=np.arange(4),b_kind=np.array([1,1,1,0]),b_lo=np.full(4,100.),t_kind=np.ones(4))
    install(v);out=v.apply(pf,obs,{},10.)
    np.testing.assert_array_equal(out.b_kind,[1,0,0,0])
    np.testing.assert_array_equal(obs.b_kind,[1,1,1,0])
    assert v.audit['rows'][-1]['kept']==1  # no arbitrary six-column gate
    assert v.audit['rows'][-1]['prior_view_columns'] is None
    assert not v.audit['prior_visibility_veto']
    obs.b_kind[:]=0;assert v.apply(pf,obs,{},11.) is None


def test_policy_rejects_unknown_and_incompatible_model(static,cal):
    for opts in [dict(visibility_policy='lower_95_percent'),dict(visibility_policy=OPTION),
                 dict(visibility_policy=OPTION,amcl_update='ros_motion_prob_v1',visibility_mask='command_geometry_v1')]:
        with pytest.raises(ValueError):Runtime(static,None,None,**opts)
