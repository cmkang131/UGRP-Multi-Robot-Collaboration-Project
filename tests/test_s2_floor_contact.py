import copy,json
from types import SimpleNamespace as NS
from pathlib import Path
import numpy as np
import pytest
from test_solo_cyan_v106 import static,cal,FakePose,FakeVision
from harness.zone_solo_cyan_floor_contact import Runtime,Previous,PARAMS,features,reference_histograms,floor_pixels,floor_contacts,validate


def table(images):
    h=np.zeros(256,bool);i=np.zeros(256,bool)
    for image in images:
        hh,ih=reference_histograms(image,np.ones(image.shape[:2],bool))
        h|=hh>=60;i|=ih>=80
    return dict(schema='ugrp.s2.floor_appearance.v1',runtime_gt=False,fit_uses_gt=False,
        parameters=PARAMS,hue_floor_bins=h.tolist(),intensity_floor_bins=i.tolist())


def test_default_and_off_preserve_commands_record_bytes(static,cal):
    rs=[cls(static,None,None,provider_factory=lambda *a,**k:FakePose(copy.deepcopy(cal)),
        vision_factory=FakeVision,**opts) for cls,opts in [(Previous,{}),(Runtime,{}),(Runtime,dict(contact_filter='off'))]]
    try:
        commands=[]
        for r in rs:
            commands.append(r.initial_commands(0.,{'r3':{1:2000,3:600,4:2200,5:1400,6:1500}}))
            r.fail('CYAN_NOT_UNIQUELY_VISIBLE',1.)
        assert len(set(json.dumps(x).encode() for x in commands))==1
        assert len(set(json.dumps(r.record()).encode() for r in rs))==1
    finally:
        for r in rs:r.close()


def test_fixed_multimodal_reference_removes_floor_edge_preserves_wall():
    # Two separately observed floor colours; no current-frame reference fitting.
    dark=np.full((80,1000,3),80,np.uint8);light=np.full_like(dark,160)
    image=np.vstack([dark,light])
    # Include a floor reference spanning the boundary: unseen intermediate
    # Gaussian colours correctly remain unknown with constant-only references.
    assert not floor_contacts(NS(columns=np.array([30]),b_kind=np.ones(1,int),b_lo=np.array([79.])),floor_pixels(image,table([dark,light]))).any()
    ref=table([dark,image]);validate(ref)
    obs=NS(columns=np.array([30,70]),b_kind=np.ones(2,int),b_lo=np.full(2,79.))
    assert floor_contacts(obs,floor_pixels(image,ref)).all()
    image[:80]=20
    assert not floor_contacts(obs,floor_pixels(image,ref)).any()
    # No RGB and clipped support are unknown, never claimed to be floor.
    assert not floor_contacts(obs,None).any()
    obs.b_lo[:]=1
    assert not floor_contacts(obs,np.ones((160,100),bool)).any()


def test_hsi_grey_black_invalid_hue_and_frozen_table_validation(static,cal):
    _,i,valid=features(np.full((5,5,3),90,np.uint8))
    assert np.all(i==90) and not valid.any()
    cfg=json.loads(Path('configs/calibration/s2_floor_appearance_v1.json').read_text());validate(cfg)
    for change in [dict(fit_uses_gt=True),dict(intensity_floor_bins=[True]),dict(parameters={**PARAMS,'hue_count_threshold':1})]:
        with pytest.raises(ValueError):validate({**cfg,**change})
    for kw in [dict(contact_filter='bad'),dict(contact_filter='floor_appearance_v1',floor_appearance=cfg)]:
        with pytest.raises(ValueError):Runtime(static,None,None,**kw)


def test_v126_admits_only_fixed_floor_table_and_fresh_full_dev(tmp_path):
    from harness import zone_s2_realism_contract_v126 as c
    from scripts import run_s2_realism_v126 as runner
    b=c.bundle('a'*40,seed=1051,stage_probe='place',**c.NEW_OPTIONS);c.require_execution(b)
    assert b['options']['idle_robot_contacts']=='freeze_v1'
    for key in ('contact_filter','visibility_policy'):
        bad=copy.deepcopy(b);bad['options'][key]='off'
        with pytest.raises(ValueError):c.require_execution(bad)
    for seed in (1050,1049):
        bad=copy.deepcopy(b);bad['task']['seed']=seed
        with pytest.raises(ValueError):c.require_execution(bad)
    bad=copy.deepcopy(b);bad['floor_appearance']['intensity_floor_bins'][0]^=True
    with pytest.raises(ValueError):c.require_execution(bad)
    for key,value in [('scenario','S3'),('transport','pair'),('research_result',True)]:
        bad=copy.deepcopy(b);bad[key]=value
        with pytest.raises(ValueError):c.require_execution(bad)
    args=runner.parser().parse_args(['--expected-source-sha','a'*40,'--output',str(tmp_path)])
    assert args.visibility_policy==args.contact_filter=='off'
