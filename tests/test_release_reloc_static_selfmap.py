"""Nonphysical checks for the own-gauge/static-gauge boundary."""
import importlib.util
from pathlib import Path
import sys
import types
import numpy as np
import pytest

PATH = Path(__file__).resolve().parents[1]/'scripts/release_reloc_static_selfmap.py'
spec = importlib.util.spec_from_file_location('static_release_test', PATH)
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)


def test_opt_in_and_rbpf_is_not_mislabeled_lk():
    with pytest.raises(ValueError, match='EXPLICIT'):
        module.StaticReleaseSelfmap({}, {}).observe(0, None, {}, command_delta=[0,0,0], settled=True)
    with pytest.raises(ValueError, match='RBPF_STATIC_RELEASE_NOT_QUALIFIED'):
        module.StaticReleaseSelfmap({}, {}, method='rbpf', registration=module.OPTION)


@pytest.mark.parametrize('accepted', [True, False])
def test_camera_origins_share_own_gauge_and_rejection_has_no_fallback(monkeypatch, accepted):
    def compose(a,b):
        c,s=np.cos(a[2]),np.sin(a[2]);return np.array([a[0]+c*b[0]-s*b[1],a[1]+s*b[0]+c*b[1],a[2]+b[2]])
    def transform(points,pose):return np.array([compose(pose,[*p,0])[:2] for p in points])
    class Reg:
        def __init__(self,*a,**kw):pass
        def register(self,segments,*,camera_origins):
            np.testing.assert_allclose(segments,[[[1,2],[1,3]]],atol=1e-12)
            np.testing.assert_allclose(camera_origins,[[1,2.1]],atol=1e-12)
            return dict(static_from_own=[3,4,0] if accepted else None,reason='accepted' if accepted else 'ambiguous_modes')
    fake={
        'harness.mapbuild_camera':dict(adapters=lambda _: (lambda *a: pytest.fail('sparse LK must stay unknown'),
            lambda *a:dict(segments=[[[0,0],[1,0]]],camera=[.1,0],columns=[dict(status='hit',reason='wall')]))),
        'harness.servo_camera_fk':dict(CARRY_OPTION='servo_fk_carry_v1'),
        'harness.mapbuild_static_registration':dict(StaticRegistration=Reg),
        'harness.scene_colour_boundary':dict(ColourBoundaryState=lambda *a,**kw:None,RELOC16_OPTION='v2'),
        'harness.e2e_rgb_vo':dict(compose=compose,PARAMS=dict(max_pair_gap_s=.25)),
        'harness.self_odom_grid':dict(transform=transform),
    }
    for n,attrs in fake.items():
        obj=types.ModuleType(n);obj.__dict__.update(attrs);monkeypatch.setitem(sys.modules,n,obj)
    loc=module.StaticReleaseSelfmap({}, {},method='lk',registration=module.OPTION)
    loc.observe(1.,None,{1:2000},command_delta=[1,2,np.pi/2],settled=True)
    r=loc.register()
    assert r['accepted']==accepted
    if accepted:np.testing.assert_allclose(r['map_pose'],[4,6,np.pi/2])
    else:assert r['map_pose'] is None
    with pytest.raises(ValueError,match='CAUSAL'):
        loc.observe(1.,None,{},command_delta=[0,0,0],settled=True)
