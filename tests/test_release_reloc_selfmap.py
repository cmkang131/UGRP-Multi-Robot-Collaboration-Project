import importlib.util
from pathlib import Path
import sys
import types

import numpy as np
import pytest

PATH = Path(__file__).resolve().parents[1]/'scripts/release_reloc_selfmap.py'
spec = importlib.util.spec_from_file_location('release_selfmap_tested', PATH)
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)


def test_default_off_rejects_observations():
    loc = module.ReleaseSelfmap({}, {})
    with pytest.raises(ValueError, match='EXPLICIT_RELEASE_SELFMAP_REQUIRED'):
        loc.observe(0., None, {})


def test_loaded_unknown_keeps_command_prediction_and_cannot_acquire_map(monkeypatch):
    # Camera calibration rejection is not a stationary visual measurement.
    fake = {
        'harness.scene_colour_boundary': dict(ColourBoundaryState=lambda *a, **kw: None, RELOC16_OPTION='v2'),
        'harness.servo_camera_fk': dict(transform_from_commands=lambda *a, **kw: (None, 'loaded_or_unknown_load_not_qualified')),
        'harness.e2e_rgb_vo': dict(ground_pair=lambda *a: pytest.fail('unqualified LK'),
            image_mask=lambda *a: pytest.fail('unqualified mask'), compose=lambda a,b: a+b, PARAMS={}),
        'harness.mapbuild_rbpf': dict(virtual_scan=lambda *a: pytest.fail('unqualified scan'), MapbuildRBPF=None, OPTION='rbpf'),
    }
    for name,values in fake.items():
        obj=types.ModuleType(name);obj.__dict__.update(values);monkeypatch.setitem(sys.modules,name,obj)
    loc=module.ReleaseSelfmap({}, {}, method='lk')
    row=loc.observe(1.,np.zeros((480,640,3),np.uint8),{1:1000},command_delta=[.1,0.,0.])
    assert row['motion_status']=='command_prediction'
    assert row['lk_relative_pose']==[.1,0.,0.]
    assert row['floor_features'] is None and row['wall_hit_columns']==0
    assert not row['map_correction_accepted'] and row['map_pose'] is None
    assert not loc.decision()['accepted']
    with pytest.raises(ValueError, match='CAUSAL_OWN_FRAMES_REQUIRED'):
        loc.observe(1.,None,{})
