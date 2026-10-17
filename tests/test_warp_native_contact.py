import xml.etree.ElementTree as ET
import pytest
from sim.warp_native_contact import apply, record

XML = '''<mujoco><option noslip_iterations="10" iterations="80"/>
<worldbody><body name="r1__robot"/></worldbody><contact>
<pair geom1="r1__left_finger" geom2="box" friction="3 3 .01 .001 .001" solreffriction="0 -6000"/>
<pair geom1="wheel" geom2="floor" friction=".9 .9 .01 .001 .001"/>
</contact><equality><weld active="false"/></equality></mujoco>'''


def test_default_preserves_source_bytes():
    assert apply(XML) == XML


def test_candidate_preserves_wheels_material_and_geometry():
    root = ET.fromstring(apply(XML, 'warp_native_contact_v2'))
    before = ET.fromstring(XML)
    assert ET.tostring(root.find('worldbody')) == ET.tostring(before.find('worldbody'))
    assert root.findall('contact/pair')[1].attrib == before.findall('contact/pair')[1].attrib
    assert root.findall('contact/pair')[0].get('friction') == before.findall('contact/pair')[0].get('friction')
    assert root.findall('contact/pair')[0].get('solreffriction') == '0 0'
    assert root.find('option').get('noslip_iterations') == '0'
    assert root.find('option').get('iterations') == '80'


def test_fail_closed_and_distinct_records():
    with pytest.raises(ValueError):
        apply(XML.replace('active="false"', 'active="true"'), 'warp_native_contact_v1')
    with pytest.raises(ValueError):
        apply(XML, 'typo')
    assert record('warp_native_contact_v1')['sha256'] != record('warp_native_fast_v1')['sha256']


def test_recording_preserves_short_pulse_boundaries():
    from scripts.warpfit import recording_ticks
    meta=dict(kind='drive',groups={'group0':['left-.06','forward-.25']},cases=[
        dict(id='left-.06',settle_s=1,duration_s=.06,tail_s=1),
        dict(id='forward-.25',settle_s=1,duration_s=.25,tail_s=1)])
    ticks=recording_ticks(meta,'group0',24000,.00025)
    assert all(round(t/.00025) in ticks for t in (1,1.06,1.25,2.06,2.25))
    assert all((b-a)%10==0 for a,b in zip(ticks,ticks[1:]))
    assert ticks[0]==0 and ticks[-1]==24000


def test_recorded_clear_fixture_routes_with_or_without_trailing_slash():
    from scripts.warpfit_analyze import drive_scene
    # Actual result.json stores the directory without a trailing slash. Using
    # '/drive-clear-v1/' incorrectly routed it to the original pulse metadata.
    path='/home/ugrp/ugrp-sim/runs/warpfit/primitive-v1/drive-clear-v1'
    assert drive_scene(path)==drive_scene(path+'/')=='clear-overlap-v1'
    assert drive_scene('/home/ugrp/ugrp-sim/runs/warpfit/primitive-v1/drive')=='initial-overlap'


def test_thirty_lifts_are_not_thirty_frames_and_reference_quantiles_pass(tmp_path, monkeypatch):
    import json
    import os
    import sys
    from scripts import warpfit_report
    ref=dict(height_p05_m=.07,slip_p95_m=.000002)
    def run(n,repeat):
        worlds=[dict(world=w,hold_samples=30,all_finger_samples=30,loaded_contact_samples=30,
            height_m=dict(min=.069,p05=.07),slip_m=dict(p95=.000002),tilt_deg=dict(max=0),
            # Percentile bounds naturally exclude some individual frames even
            # when the trajectory exactly equals the reference distribution.
            pass_samples=27) for w in range(n)]
        return dict(path=f'/R{2 if n==16 else 3}/repeat{repeat}',protocol='primitive-v1',engine='warp',
            round=2 if n==16 else 3,nworld=n,profile='warp_native_contact_v1',kind='box',case='tape',
            status='complete',completed=1,HOST_ERROR=0,cap_end=False,cohort_repeat=repeat,
            threshold=ref,worlds=worlds)
    analysis=tmp_path/'analysis';analysis.mkdir();output=tmp_path/'report'
    # Deliberately unordered input: selection must use recorded repeat/world
    # order, including all16 initial lifts before the next14.
    (analysis/'rows.json').write_text(json.dumps([run(16,2),run(64,1),run(16,1)]))
    (analysis/'thresholds.json').write_text(json.dumps(ref))
    actual=os.uname()
    monkeypatch.setattr(warpfit_report.os,'uname',lambda: os.uname_result(
        (actual.sysname,'ugrp-sim-gcp2-test',actual.release,actual.version,actual.machine)))
    monkeypatch.setattr(sys,'argv',['warpfit_report','--analysis',str(analysis),'--output',str(output)])
    warpfit_report.main()
    result=json.loads((output/'summary.json').read_text())
    assert all(r['selected']==r['loaded_retained']==r['C_reference_quantile_pass']==30 for r in result['box30'])
    selections=json.loads((output/'box30-selection.json').read_text())
    first=next(r for r in selections if r['nworld']==16)['selection']
    assert [(r['repeat'],r['world']) for r in first]==[(1,w) for w in range(16)]+[(2,w) for w in range(14)]
