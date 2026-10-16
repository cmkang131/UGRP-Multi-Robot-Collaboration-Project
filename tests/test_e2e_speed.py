"""Profiling admission and accounting; no simulator or model execution."""
import pytest
from scripts.s4_proxy_relay import accepted_call_id
from scripts.e2e_speed_measure import profile_rows, measured_run
from types import SimpleNamespace


def test_profile_ledger_is_closed_to_registered_cells():
    for name in ('profile','off','index','validate','copy','both'):
        assert accepted_call_id(f'e2e13-{name}-s61001:call-0001-r1:1')
    assert not accepted_call_id('e2e13-off-s61002:call-0001-r1:1')
    assert not accepted_call_id('e2e13-arbitrary-s61001:call-0001-r1:1')


def test_top20_uses_cumulative_time_with_explicit_denominator():
    stats=SimpleNamespace(stats={(f'{i}.py',i,'f'):(1,2,.1,float(i),{}) for i in range(25)})
    rows=profile_rows(stats,60)
    assert len(rows)==20 and rows[0]['cumulative_s']==24
    assert rows[0]['cumulative_wall_per_sim']==.4


def test_measurement_limit_rejected_before_backend_import():
    with pytest.raises(ValueError):measured_run(None,None,None,None,1,False)


@pytest.mark.parametrize('bits', range(8))
@pytest.mark.parametrize('fault', ['none','foreign','future','unobserved','uppercase','extra','covariance','forbidden'])
def test_exact_validation_acceptance_and_rejection_are_identical(bits,fault):
    import copy
    from tests.test_e2e_own_inputs import state
    from harness import e2e_own_inputs as own
    from harness.e2e_exact_speedups import Options
    mapped,refs,_=state()
    # Keep provenance independent so mutating a source cannot grant admission.
    refs=copy.deepcopy(refs)
    if fault=='foreign':mapped['sources'][0]['robot_id']='r2'
    if fault=='future':mapped['sources'][0]['t_sim']=2.
    if fault=='unobserved':refs=[]
    if fault=='uppercase':mapped['sources'][0]['sha256']='A'*64
    if fault=='extra':mapped['sources'][0]['extra']=1
    if fault=='covariance':mapped['pose']['covariance'][0][0]=-.1
    if fault=='forbidden':mapped['walls'][0]['truth']=True
    options=Options(bool(bits&1),bool(bits&2),bool(bits&4))
    def outcome(**kwargs):
        try:return ('ok',own.validate_map(mapped,'r1',1.,refs,**kwargs))
        except Exception as e:return (type(e).__name__,str(e))
    baseline=outcome();candidate=outcome(speedups=options)
    if baseline[0]=='ok':
        assert candidate==('ok',None if options.omit_discarded_copy else baseline[1])
    else:assert candidate==baseline


def test_provenance_index_cannot_retain_mutated_or_removed_sources():
    import copy
    from tests.test_e2e_own_inputs import state
    from harness import e2e_own_inputs as own
    from harness.e2e_exact_speedups import Options
    mapped,refs,_=state();refs=copy.deepcopy(refs);options=Options(True,True,True)
    own.validate_map(mapped,'r1',1.,refs,speedups=options)
    refs[0]['sha256']='b'*64
    with pytest.raises(own.ContractViolation,match='UNOBSERVED'):
        own.validate_map(mapped,'r1',1.,refs,speedups=options)
    refs.clear()
    with pytest.raises(own.ContractViolation,match='UNOBSERVED'):
        own.validate_map(mapped,'r1',1.,refs,speedups=options)


def test_actual_robot_payload_bytes_and_caller_ownership_survive_shortcuts():
    import json
    from tests.test_e2e_stall_odometry import robot,receive,Options as Stall
    from harness.e2e_exact_speedups import Options
    r=robot(Stall());receive(r,0)
    baseline=r.own_inputs_at(0.)
    r.exact_speedups=Options(True,True,True)
    accelerated=r.own_inputs_at(0.)
    assert json.dumps(baseline)==json.dumps(accelerated)
    accelerated['own_map']['pose']['mean'][0]=999
    assert r.own_inputs_at(0.)['own_map']['pose']['mean'][0]!=999


def test_opt_in_bundle_retains_physical_parameters_and_default_off():
    from scripts.run_e2e_ownmap_live import bundle
    from harness.e2e_exact_speedups import Options
    common=dict(enabled=True,mapping_budget='case_cap_v1',path_follow='rpp_v1',dev_light=True,
        stall_odometry='rgb_pulse_gate_v1',stall_recovery='backup_replan_v1',stall_noise='amcl_alpha_v1')
    old=bundle('a'*40,61001,'study_gemma4_31b_v1',**common)
    new=bundle('a'*40,61001,'study_gemma4_31b_v1',**common,exact_speedups=vars(Options(True,True,True)))
    assert old['execution_bundle_id']=='e2e-stall-budget-v199'
    assert new['execution_bundle_id']=='e2e-exact-speed-v200'
    assert 'exact_speedups' not in old['e2e_options']
    changed={k for k in old if old[k]!=new[k]}
    assert changed=={'schema','execution_bundle_id','workflow_version','e2e_options','source_sha256'}


def test_scalar_cell_float64_boundaries_and_fallback_equal_legacy():
    import numpy as np
    from harness.own_map_navigation import ObservedGrid
    from harness.e2e_exact_speedups import Options,using
    rng=np.random.default_rng(43)
    for resolution in (.1,.05,.2):
        grid=ObservedGrid('r1',resolution)
        values=np.r_[rng.uniform(-100,100,3000),np.arange(-100,101)*resolution,0.,-0.]
        values=np.r_[values,np.nextafter(values,np.inf),np.nextafter(values,-np.inf)]
        points=np.column_stack((values,values[::-1]))
        baseline=[grid.cell(p) for p in points]
        with using(Options(scalar_cells=True)):
            assert [grid.cell(p) for p in points]==baseline
            for p in ([.1,-.1],np.array([.1,-.1],np.float32),np.array([1,2],np.int64)):
                assert grid.cell(p)==tuple(int(v) for v in np.floor(np.asarray(p)/resolution))


def test_geometry_cache_is_bit_exact_owned_and_invalidates_changed_inputs():
    import numpy as np
    from harness.e2e_exact_speedups import Options,using
    from harness.floor_goal import optical_rays,floor_intersections
    from harness.floor_goal_self_mask import project_envelopes,body_envelopes
    from harness.active_camera import SEARCH,goal_camera
    origin,axes=goal_camera(SEARCH,'camera_v3');rays=optical_rays(64,48)
    expected=floor_intersections(rays,origin,axes)
    mask=project_envelopes(body_envelopes(SEARCH,'camera_v3'),origin,axes,64,48)
    with using(Options(geometry_cache=True)):
        for _ in range(2):
            result=floor_intersections(rays,origin,axes)
            assert [a.tobytes() for a in result]==[a.tobytes() for a in expected]
            result[0][0,0]=[999]*3
            got=project_envelopes(body_envelopes(SEARCH,'camera_v3'),origin,axes,64,48)
            assert got.tobytes()==mask.tobytes();got[:]=~got
        changed=origin.copy();changed[2]+=.01
        actual=floor_intersections(rays,changed,axes)
    fresh=floor_intersections(rays,changed,axes)
    assert [a.tobytes() for a in actual]==[a.tobytes() for a in fresh]
    # Context must never leak into another robot or the default path.
    from harness.e2e_exact_speedups import geometry_enabled,cells_enabled
    assert not geometry_enabled() and not cells_enabled()


def test_dense_integer_indexing_preserves_duplicates_unknown_and_provenance():
    import numpy as np
    from harness.own_map_navigation import ObservedGrid
    from harness.e2e_exact_speedups import Options,using
    grid=ObservedGrid('r1',.05)
    for i in range(-20,21):
        grid.odds[(i,i//3)]=float((i%3)-1)
        if i%2:grid.floor_frames[(i,i//3)]={1}
        if i%5:grid.support.add((i,i//3))
    grid.support.add((-24,3))
    for pose in ([0.,0.,0.],[-1.05,.15,0.],[2.,-2.,1.]):
        before=grid.dense(pose)
        with using(Options(scalar_cells=True)):after=grid.dense(pose)
        assert all(a.dtype==b.dtype and a.shape==b.shape and a.tobytes()==b.tobytes() for a,b in zip(before,after))
