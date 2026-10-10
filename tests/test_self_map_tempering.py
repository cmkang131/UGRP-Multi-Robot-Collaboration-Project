import hashlib
import json
from pathlib import Path
import numpy as np
import pytest
from harness.self_map_relocalize import Relocalizer
from harness.self_map_causal import landmark_object
from harness.own_map_amcl_vendor.tempering import TEMPER, ALPHA

FIXTURE=Path(__file__).parent/'fixtures/own_map_tempering/golden.json'

def run(option=None):
    f=json.loads(FIXTURE.read_text())
    p=Relocalizer(f['grid'],seed=41001,sensor_landmarks='floor_zones_doors_v1',
        landmark_map=landmark_object(f['landmarks']),**({} if option is None else {'likelihood_tempering':option}))
    rows=[]
    for i,r in enumerate(f['sequence']):
        rows.append(p.step(t=r['t'],points=r['points'],delta=r['delta'] if i else [0,0,0],
            servo={int(k):v for k,v in r['servo'].items()},features=r['features']))
    return f,p,rows

@pytest.mark.parametrize('option',[None,'off'])
def test_off_frozen_prechange_bytes(option):
    f,p,rows=run(option);sha=lambda b:hashlib.sha256(b).hexdigest()
    assert sha(json.dumps(rows,sort_keys=True).encode())==f['rows']
    assert sha(p.px.tobytes())==f['particles']
    assert sha(p.logw.tobytes())==f['logw']
    assert p.rng.bit_generator.state==f['rng'] and p.tempering_audit==[]

def test_joint_likelihood_attenuation_and_prior_not_tempered(monkeypatch):
    from harness.own_map_amcl_vendor import field,landmarks,kld
    f=json.loads(FIXTURE.read_text())
    pf=Relocalizer(f['grid'],seed=4,sensor_landmarks='floor_zones_doors_v1',
        landmark_map=landmark_object(f['landmarks']),likelihood_tempering=TEMPER)
    pf.n=4;pf.px=pf.px[:4];pf.logw=np.log([.1,.2,.3,.4])
    monkeypatch.setattr(field,'likelihood',lambda f,p,o:np.array([.2,.5,.8,1.]))
    monkeypatch.setattr(landmarks,'landmark_likelihood',lambda f,p,o:np.array([1.,.7,.4,.1]))
    monkeypatch.setattr(kld.Policy,'measure',lambda *a:dict(resampled=False))
    pf.step(t=1,points=[[1,0]],delta=[0,0,0],servo={3:740,4:2320,5:1320,6:1500},features=[])
    expected=np.array([.1,.2,.3,.4])*np.sqrt(np.array([.2,.5,.8,1.])*[1.,.7,.4,.1]);expected/=expected.sum()
    assert np.allclose(pf._weights(),expected,atol=1e-15)
    assert ALPHA==.5 and pf.tempering_audit[0]['prior']['unique_poses']==4
