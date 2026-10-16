"""Offline experiment-design checks; no simulator import or integration."""
import importlib.util
from pathlib import Path
import pytest


def test_requested_lateral_matrix_and_controls():
    path=Path(__file__).resolve().parents[1]/'scripts/mapbuild4_pulse.py'
    spec=importlib.util.spec_from_file_location('mapbuild4_pulse',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    rows=module.cases()
    assert len(rows)==20
    lateral=[r for r in rows if r['axis']=='left']
    assert len({(r['pose'],r['ms'],r['u']) for r in lateral})==16
    assert {r['ms'] for r in lateral}=={60,100,200,400}
    assert {r['u'] for r in lateral}=={-.35,.35}
    assert len({r['name'] for r in rows})==20


def motion_module():
    path=Path(__file__).resolve().parents[1]/'harness/mapbuild_motion.py'
    spec=importlib.util.spec_from_file_location('mapbuild_motion',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_pulse_prediction_never_silently_uses_unmeasured_primitives():
    m=motion_module()
    data=dict(physics_backend='mjwarp',profiles={'drive:forward:0.35:0.10':
        dict(times=[0,.1,.3],curve=[[0,0,0],[.01,0,0],[.017,0,0]])})
    with pytest.raises(ValueError,match='EXPLICIT'):m.PulsePrediction(data)
    with pytest.raises(ValueError,match='MJWARP'):
        m.PulsePrediction({**data,'physics_backend':'cpu'},option=m.OPTION)
    p=m.PulsePrediction(data,option=m.OPTION)
    with pytest.raises(ValueError,match='UNMEASURED'):
        p.issue(dict(t=0,axis='left',value=.35,duration_s=.06))
    p.issue(dict(t=0,axis='forward',value=.35,duration_s=.1))
    assert p.advance(.1)[0]==pytest.approx(.01)
    assert p.advance(.3)[0]==pytest.approx(.007)
    assert p.advance(.4)[0]==pytest.approx(0)
    with pytest.raises(ValueError,match='NON_CAUSAL'):p.advance(.2)
