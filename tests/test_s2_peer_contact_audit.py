"""Geometry and evidence accounting regressions; no simulation."""
import importlib.util
from pathlib import Path
import numpy as np

P=Path(__file__).resolve().parents[1]/'experiments/2026-10-06-s2-realism/audit_peer_contact.py'
spec=importlib.util.spec_from_file_location('peer_audit',P)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_segment_interior_and_zero_length():
    assert m.segment_distance([.5,1],[0,0],[1,0])==1
    assert m.segment_distance([2,0],[0,0],[1,0])==1
    assert m.segment_distance([0,1],[0,0],[0,0])==1


def test_envelope_separation_is_signed_not_mesh_contact():
    a=m.polygon([0,0,0]);b=m.polygon([.5,0,0])
    assert np.isclose(m.separating_gap(a,b),.04)
    assert m.separating_gap(a,m.polygon([.2,0,0]))<0
    assert np.isclose(m.separating_gap(a,m.polygon([.46,0,0])),0)


def test_peer_contact_count_excludes_floor_self_and_cargo():
    contacts=[dict(geom1=a,geom2=b,dist_m=-.001) for a,b in [
        ('r1__base','r3__roller'),('r3__roller','r1__base'),('floor','r3__roller'),
        ('r3__base','r3__roller'),('cargo_box_00_geom','r3__finger')]]
    assert len(m.peer_contacts([dict(t=1,contacts=contacts)]))==2


def test_initial_servo_is_not_drive_but_nonzero_lateral_is():
    assert m.commanded_motion([dict(kind='initial_servo_command'),dict(kind='hold')])==[]
    q=dict(kind='mecanum',left=.65,forward=0,turn=0)
    assert m.commanded_motion([q,dict(kind='drive',forward=0)])==[q]


def test_missing_peer_evidence_cannot_pass_registered_gate():
    import json
    c=json.loads((P.parent/'peer-clearance-criteria.json').read_text())
    assert c['proposed_option']['default']=='off'
    assert c['planning_gate']['all_three_recordings_required'] is True
    assert c['threshold_changes_after_results'] is False
    assert c['pose_report']['xy_nees_95_exceedance_rate_max']==.2
    assert 'unknown, not pass' in c['planning_gate']['missing_peer_position_or_sigma']
