"""Wall sensor inverse model regression checks, without physics/rendering."""
import math
from copy import deepcopy
from harness.beampair_wall_layer import WallLayer, ray_cells, HIGH, LOW


def world(t, walls):
    return dict(t=t,robots={'r2':{'pose':[0.,0.,0.]}},objects={},beam=None,
                walls=[(*m['xyz'][:2],*m['half_extents'],m['yaw']) for m in walls],
                visibility={'r2':dict(observations={m['id']:m for m in walls})})


def wall(t):
    return dict(id='north',kind='wall',xyz=[.5,0.,.2],half_extents=[.025,.2],yaw=0.,seen_t=t)


def test_stale_wall_requires_observed_misses_not_expiry_and_clamps():
    layer=WallLayer();m=wall(0.);w=world(0.,[m]);before=deepcopy(w)
    assert layer.update(w,'r2',[m],[]) is w and w==before  # inactive path unchanged
    layer.active=True
    for t in range(1,50):layer.update(world(float(t),[m]),'r2',[],[])
    assert layer.odds[(20,0)]>0  # empty frame / age cannot clear
    ray=dict(origin=[0.,.0125,.1],end=[1.,.0125,0.],hit_wall=None)
    for t in range(50,70):layer.update(world(float(t),[m]),'r2',[],[ray])
    assert layer.odds[(20,0)]==LOW and layer.odds[(20,3)]>0
    assert any(e['cleared_cell_N'] for e in layer.events)
    for t in range(70,90):
        fresh=wall(float(t));layer.update(world(float(t),[fresh]),'r2',[fresh],[ray])
    assert layer.odds[(20,0)]==HIGH  # current occupied support wins over free


def test_grid_geometry_keeps_blocker_names_and_clears_only_traversed_cells():
    layer=WallLayer();layer.active=True;m=wall(0.)
    w=layer.update(world(0.,[m]),'r2',[m],[])
    cells=[m for k,m in w['visibility']['r2']['observations'].items() if ':grid:' in k]
    assert cells and all(m['wall_layer_owner']=='north' for m in cells)
    assert all(m['half_extents'][0]>=.0125 for m in cells)
    assert (20,0) in set(ray_cells((0.,.0125),(1.,.0125)))
    assert (40,0) not in set(ray_cells((0.,.0125),(1.,.0125)))
    assert list(ray_cells((-.01,-.01),(-.06,-.06)))==[(-1,-1),(-2,-2)]
