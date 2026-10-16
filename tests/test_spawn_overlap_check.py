from sim.spawn_overlap_check import OPTION,assess,classify,check


def point(a,b,d):
    return dict(classes=[a,b],dist_m=d,geoms=[a+'_g',b+'_g'],bodies=[a,b])


def test_default_off_does_not_touch_model():
    assert check(None,None,floor_geoms=set(),cargo_bodies=set(),wall_geoms=set())['status']=='not_checked'


def test_signed_zero_and_floor_are_not_rejections():
    assert assess([point('robot','floor',-.02),point('robot','cargo',0),point('cargo','wall',.001)],option=OPTION)['accepted']


def test_all_requested_categories_and_tiny_penetration_are_recorded():
    result=assess([point('robot','cargo',-.0153449),point('cargo','cargo',-1e-12),
                   point('cargo','wall',-.002),point('robot','robot',-.003)],option=OPTION)
    assert result['rejected_contact_points_n']==4
    assert result['reasons']==dict(robot_nonfloor=2,cargo_cargo=1,cargo_wall=1)
    assert result['rejections'][0]['penetration_depth_m']==.0153449
    assert all(r['blocked_object'] and r['reason'] and r['gap_status']=='measured' for r in result['rejections'])


def test_namespace_is_explicit_not_appearance():
    kwargs=dict(floor_geoms={'floor'},cargo_bodies={'cargo_1'},wall_geoms={'wall_1'})
    assert classify('floor','world',**kwargs)=='floor'
    assert classify('roller','r2__wheel',**kwargs)=='robot'
    assert classify('cargo_geom','cargo_1',**kwargs)=='cargo'
    assert classify('wall_1','world',**kwargs)=='wall'
    assert classify('ramp','world',**kwargs)=='other'
