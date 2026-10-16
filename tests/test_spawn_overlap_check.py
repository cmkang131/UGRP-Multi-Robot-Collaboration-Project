from sim.spawn_overlap_check import OPTION,assess,classify,check,cargo_owner


def point(a,b,d):
    return dict(classes=[a,b],dist_m=d,geoms=[a+'_g',b+'_g'],bodies=[a,b])


def test_default_off_does_not_touch_model():
    assert check(None,None,floor_geoms=set(),cargo_bodies=set(),wall_geoms=set())['status']=='not_checked'


def test_nested_collision_parts_inherit_their_cargo_root():
    from types import SimpleNamespace
    names=['world','cargo_root','cargo_tip','r1__robot']
    model=SimpleNamespace(body_parentid=[0,0,1,0],body=lambda i:SimpleNamespace(name=names[i]))
    assert cargo_owner(model,2,{'cargo_root'})=='cargo_root'
    assert cargo_owner(model,3,{'cargo_root'}) is None


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


def test_fixture_requires_exact_saved_bytes_and_scene(tmp_path):
    import hashlib,json
    import numpy as np
    import pytest
    from scripts.mapbuild3_prepare import load_fixture
    path=tmp_path/'fixture.npz';np.savez_compressed(path,drive_qpos=[1.,2.])
    meta=dict(fixture_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
              scene_xml_sha256=hashlib.sha256(b'scene').hexdigest(),
              selected={p:dict(selected_xy=[0.,0.]) for p in ('drive','high')})
    (tmp_path/'fixture.json').write_text(json.dumps(meta))
    assert load_fixture(tmp_path,'scene')['drive_qpos'].tolist()==[1.,2.]
    with pytest.raises(ValueError,match='SCENE_MISMATCH'):load_fixture(tmp_path,'other')
    path.write_bytes(b'changed')
    with pytest.raises(ValueError,match='HASH_MISMATCH'):load_fixture(tmp_path,'scene')


def test_fixture_rejects_posture_viewpoint_confound(tmp_path):
    import hashlib,json
    import numpy as np
    import pytest
    from scripts.mapbuild3_prepare import load_fixture
    path=tmp_path/'fixture.npz';np.savez_compressed(path,x=[1.])
    (tmp_path/'fixture.json').write_text(json.dumps(dict(fixture_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        scene_xml_sha256=hashlib.sha256(b'scene').hexdigest(),selected=dict(drive=dict(selected_xy=[0,0]),high=dict(selected_xy=[0,1])))))
    with pytest.raises(ValueError,match='SHARED_POSTURE_START_REQUIRED'):load_fixture(tmp_path,'scene')
