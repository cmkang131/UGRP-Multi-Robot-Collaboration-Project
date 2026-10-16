"""Offline experiment-design checks; no simulator import or integration."""
import importlib.util
from pathlib import Path


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
