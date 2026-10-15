"""Known-mode tracking, retained global recovery, budget and v7 boundaries."""
import json
import math
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from harness.reloc14_tracking import track


def registration():
    return SimpleNamespace(map_from_own=np.zeros(3),command_registration_anchor=np.zeros(3),
        geometry_supported=lambda *a:(True,{'independent_line_axes':True}),
        confirmations=[np.zeros(3)]*3,confirmation_views={1,2,3},
        execution_r7_admitted=True,tracking_state='TRACKING')


def row(updated=True):
    return dict(pose=[.02,0,.01],covariance=np.diag([.01**2,.01**2,.01**2]).tolist(),
        updated=updated,resolved=True,cluster={'mass':1.},sensor=None)


def test_tracking_measurement_and_motion_gate_do_not_repeat_global_views():
    r=registration()
    fix,handled=track(r,row(),{'features':[]},np.zeros(3),1.)
    assert handled and r.last['tracking']['measurement']
    assert not r.last['tracking']['global_confirmations_required']
    assert len(r.confirmation_views)==3
    track(r,row(False),{'features':[]},np.zeros(3),2.)
    assert r.execution_r7_admitted and not r.last['tracking']['measurement']


def test_fresh_tracking_failure_loses_mode_stale_frame_does_not():
    r=registration();r.geometry_supported=lambda *a:(False,{})
    assert track(r,row(False),{'features':[]},np.zeros(3),1.)[1]
    assert not track(r,row(True),{'features':[]},np.zeros(3),2.)[1]
    assert r.tracking_state=='LOST' and not r.execution_r7_admitted
    assert not r.confirmations and not r.confirmation_views
    assert r.last_tracking_failure['category']=='tracking_evidence_lost'


def test_prior_seeded_orb_cannot_take_over_pf_tracking(monkeypatch):
    from harness.selfmap6_safety import GatedPriorSLAM
    s=GatedPriorSLAM('r1',max_sigma_xy_m=.15,max_sigma_yaw_rad=math.radians(5))
    s.reloc14_pf_tracking=True
    p,_,d=s._fit(np.empty((0,2)),np.empty((0,32)),np.zeros(3),1)
    assert p is None and d['reason']=='pf_tracking_or_relocalization'


def test_refitted_carry_envelope_retains_partial_epoch_and_existing_task_limit():
    from sim.solo_carry_pose import CommandPose,task_start
    c=CommandPose(task_start({'regions':{'pickup':{'center_m':[0,0],'half_extents_m':[.5,.5]}}}),
        drive_model_deadband_v1=True,reloc10_rotation_calibration_v1=True,reloc14_carry_budget_v1=True)
    c.turn_since_fix=2.
    assert c.sigmas()[2]>math.radians(20) and not c.ready(0.)
    c.partial_epoch=(0.,1.)
    assert c.sigmas()[2]==pytest.approx(math.radians(4.522386263900104+20.584161983501907))
    assert c.yaw_budget_limit()==pytest.approx(math.radians(20))


def test_v7_scene_source_and_carry_plan_keep_crate_out():
    from harness.zone_environment_registry import load_scenario
    root=Path(__file__).resolve().parents[1]
    manifest=json.loads((root/'experiments/2026-10-15-reloc14/v7-scenario-source.json').read_text())
    import hashlib
    for name,sha in manifest['sha256'].items():
        assert hashlib.sha256((root/name).read_bytes()).hexdigest()==sha
        s=load_scenario(Path(name).stem)
        assert all(p['kind']!='heavy_crate' for p in s['eval']['setup']['placements'])


def test_tracking_option_requires_global_safety_chain():
    from harness.self_map_integration import Options
    with pytest.raises(ValueError):Options(reloc14_continuous_tracking_v1=True)
