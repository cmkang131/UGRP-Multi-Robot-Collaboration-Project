import importlib.util
from pathlib import Path
import sys
import pytest


def module(monkeypatch):
    root=Path(__file__).resolve().parents[1];monkeypatch.syspath_prepend(str(root/'scripts'))
    spec=importlib.util.spec_from_file_location('act16w_package_test',root/'scripts/package_act16w.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_synthetic_and_unverified_models_cannot_be_released(monkeypatch):
    m=module(monkeypatch)
    with pytest.raises(ValueError,match='synthetic'):
        m.check_model({'provenance':{'synthetic_only':True,'step':10000}}, {},allow_incomplete=True)
    prov=dict(step=300,source_sha='source',act_source_sha=m.ACT_SHA,lerobot_act_sha256=m.LEROBOT_ACT_SHA256,dataset_manifest_sha256='data')
    summary=dict(status='complete',steps_completed=300,readback_verified=True,source_sha='source',dataset_manifest_sha256='data',complete=True)
    with pytest.raises(ValueError,match='incomplete'):
        m.check_model({'provenance':prov},summary)
    assert m.check_model({'provenance':prov},summary,allow_incomplete=True)==(300,False)
    with pytest.raises(ValueError,match='readback'):
        m.check_model({'provenance':prov},{**summary,'readback_verified':False},allow_incomplete=True)
