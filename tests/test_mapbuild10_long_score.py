"""Synthetic post-seal gauge check; no physical/simulation success evidence."""
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace
from scripts import mapbuild10_long_score as scoring


def test_off_gets_only_start_gauge_amcl_keeps_absolute_prior_error(tmp_path, monkeypatch):
    monkeypatch.setattr(scoring.platform,'node',lambda:'ugrp-act-l4-gcp5')
    b=tmp_path/'raw';b.mkdir();out=tmp_path/'score'
    def put(n,x):(b/n).write_text(json.dumps(x))
    rgb=b/'mock.rgb';rgb.write_bytes(b'synthetic fixture, not a camera frame')
    h=hashlib.sha256(rgb.read_bytes()).hexdigest()
    put('own.json',dict(frames=[dict(frame_id=i,t=i,rgb=rgb.name,sha256=h) for i in range(2)]))
    put('online-trajectory.json',[
        dict(frame_id=0,t=0,stage='diagnostic_route',motion_delta=[0,0,0],map_event=dict(absolute_proposal=[.1,0,0],attempted=True,converged=True)),
        dict(frame_id=1,t=1,stage='diagnostic_route',motion_delta=[4.3,0,math.pi],map_event=dict(absolute_proposal=[4.1,0,math.pi],attempted=True,converged=True))])
    put('eval-only.json',dict(frames=[dict(frame_id=0,t=0,pose=[0,0,0]),dict(frame_id=1,t=1,pose=[4,0,math.pi])]))
    put('summary.json',dict(status='ROUTE_COMMAND_COMPLETE'))
    for n in ['map-correction.json','commands.json','public-start-zone.json','events.json']:put(n,{})
    put('scans.json',[dict(t=0,segments=[]),dict(t=1,segments=[])])
    put('static-map.json',dict(bounds_m=[-1,6,-1,1],obstacles=[dict(id='wall_north',center_m=[2.5,.95],half_extents_m=[3.5,.05])]))
    root=Path(__file__).resolve().parents[1]
    scoring.main(SimpleNamespace(source=root,input=b,output=out,requirements=root/'experiments/2026-10-17-mapbuild8/requirements.json'))
    s=json.loads((out/'summary.json').read_text())
    assert s['status']=='OFFLINE_LONG_DIAGNOSTIC_PASS'
    assert abs(s['off']['end_xy_m']-.3)<1e-12
    assert abs(s['amcl']['end_xy_m']-.1)<1e-12
    assert s['actual_route_path_m']==4 and s['loaded_frames']==0
    g=json.loads((out/'rejection_table.json').read_text())
    assert all(x['cumulative_pass_n']==1 for x in g['case_gates'])
