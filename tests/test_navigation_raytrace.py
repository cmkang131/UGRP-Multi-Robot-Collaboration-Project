"""Camera-ray semantics and legacy boundaries, no cohort mission runs."""
import copy
from pathlib import Path
import sys
import numpy as np
import pytest
from harness.own_map_navigation import ObservedGrid
from harness.public_navigation_raytrace import receive_rays, navigation_output_v6, RaytraceActor
from harness.public_navigation_persistent import raytrace_cells


def observation(frame=0, floor=(), wall=(), origin=(.075,.025)):
    return dict(robot_id='r1',frame_id=frame,floor_source='floor_visible',floor_xy=list(floor),wall_xy=list(wall),
                floor_origins_xy=[list(origin) for _ in floor],wall_origins_xy=[list(origin) for _ in wall])


@pytest.mark.parametrize('resolution',[.025,.05,.1])
def test_clear_continuous_camera_to_return_and_hit_last_at_any_resolution(resolution):
    grid=ObservedGrid('r1',resolution)
    obs=observation(floor=[(.875,.325)],wall=[(.475,.175)])
    latest={}
    receive_rays(grid,latest,set(),obs,[0,0,0])
    traced=set(raytrace_cells(grid.cell((.075,.025)),grid.cell((.875,.325))))
    hit=grid.cell((.475,.175))
    assert all(grid.state(c)==-1 and c in grid.floor_frames for c in traced-{hit})
    assert grid.state(hit)==1 and latest[hit]
    # No arbitrary ray extension or body-centred clearing.
    assert grid.state(grid.cell((1.175,.425)))==0
    if grid.cell((.075,.025)) != (0,0):
        assert (0,0) not in grid.odds


def test_old_obstacles_clear_only_on_ray_and_static_layer_survives():
    grid=ObservedGrid('r1',.05)
    latest={}
    receive_rays(grid,latest,set(),observation(wall=[(.475,.025),(.475,.525)]),[0,0,0])
    on,off=grid.cell((.475,.025)),grid.cell((.475,.525))
    fixed=grid.cell((.275,.025))
    grid.odds[fixed]=4.
    receive_rays(grid,latest,{fixed},observation(1,floor=[(.875,.025)]),[0,0,0])
    assert grid.state(on)==-1 and not latest[on]
    assert grid.state(off)==1 and latest[off]
    assert grid.odds[fixed]==4.
    assert grid.state(grid.cell((.925,.025)))==0


def test_own_transform_and_duplicate_peer_origin_validation_before_mutation():
    grid=ObservedGrid('r1',.05)
    latest={}
    obs=observation(wall=[(.875,.025)])
    pose=[-.4,-.5,np.pi/2]
    receive_rays(grid,latest,set(),obs,pose)
    assert grid.state(grid.cell((-.425,.375)))==1
    before=copy.deepcopy(grid.odds)
    for bad,pattern in [({**obs,'robot_id':'r2'},'PEER'),(obs,'DUPLICATE'),
                        ({**obs,'frame_id':1,'wall_origins_xy':[]},'ORIGIN')]:
        with pytest.raises(ValueError,match=pattern):receive_rays(grid,latest,set(),bad,pose)
        assert grid.odds==before


def test_off_is_lazy_byte_identity_and_explicit_v6_required():
    legacy=b'{"native":"unchanged"}\n'
    class Poison:
        def update(self,**kwargs): raise AssertionError('off evaluated input')
    assert navigation_output_v6(legacy,navigator=Poison(),hidden_truth=object()) is legacy
    with pytest.raises(ValueError,match='V6_REQUIRED'):RaytraceActor('own_frontier')


def test_sensor_metadata_preserves_original_observation_draws_and_endpoints():
    root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root/'experiments/2026-10-07-mapfree-raytrace/code'))
    import common
    from ray_world import RayOracleWorld
    from contact_world import ContactOracleWorld
    # Seen development geometry only; no new cohort result is sampled here.
    old=common.read(common.prior.EXP/'cohort.json')['rows'][0]
    args=(old['scenario'],old['pose'],old['seed'],'confirmation')
    a,b=ContactOracleWorld(*args),RayOracleWorld(*args)
    for w in (a,b):w.advance(dict(t=0.,kind='stop'),2.)
    x,y=a.observe(0),b.observe(0)
    assert {k:v for k,v in y[0].items() if not k.endswith('_origins_xy')}==x[0]
    assert x[1:]==y[1:]
    assert len(y[0]['floor_xy'])==len(y[0]['floor_origins_xy'])
    assert len(set(map(tuple,y[0]['floor_origins_xy'])))==2
    assert a.sensor_rng.bit_generator.state==b.sensor_rng.bit_generator.state
    assert 'mujoco' not in sys.modules


def test_v6_gate_preserves_original_thresholds_on_new_identifiers():
    import common
    import gate
    from test_frontier_oracle_confirmation import complete_rows
    rows=complete_rows()
    for row in rows:
        row['start']={'K':'M','L':'N'}[row['start']]
        row['seed']+=1000
    assert gate.summary(rows,True)['criteria']==common.prior.CRITERIA
    assert gate.summary(rows,True)['passed']
    assert not gate.summary(rows[:-1],True)['passed']
    assert common.prior.verify_frozen()==common.read(common.prior.v5.EXP/'freeze.json')['hashes']
