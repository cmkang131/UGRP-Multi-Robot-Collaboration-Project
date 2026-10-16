import copy
from harness.zone_s3_alignment_entry import attach_endpoint, OPTION


def test_off_identity():
    marker = object()
    assert attach_endpoint(marker) is marker


def test_probe_plan_has_no_execution_and_exact_source_bundle(capsys, tmp_path):
    from scripts.run_s3_alignment_entry_probe import main, bundle, BUNDLE_ID, WORKFLOW_VERSION
    out = tmp_path/'not_started'
    assert main(['--expected-source-sha', '0'*40, '--output', str(out)]) == 0
    assert not out.exists()
    b = bundle('0'*40, 'pair')
    assert b['execution_bundle_id'] == BUNDLE_ID and b['workflow_version'] == WORKFLOW_VERSION
    assert b['servo_option'] == 'off' and b['case_cap_s'] == 60.
    assert b['alignment_entry'] == OPTION
    assert 'harness/zone_s3_alignment_entry.py' in b['source_sha256']


def test_actual_align_start_keeps_issued_inspect_and_native_port(tmp_path, monkeypatch):
    from tests import s3_stage_probe as stage
    from harness import zone_s3_recovery_contract as contract
    from harness.zone_s3_proposal_runtime import Runtime
    from harness.owncam_pair_beam_v2 import pose_of
    old_bundle = contract.bundle
    def bundle(sha):
        b = old_bundle(sha)
        b['controller_config']['options']['alignment_entry'] = OPTION
        return b
    monkeypatch.setattr(stage, 'contract', contract)
    monkeypatch.setattr(contract, 'bundle', bundle)
    monkeypatch.setattr(stage, 'Runtime', Runtime)
    probe = stage.Probe(tmp_path, monkeypatch)
    try:
        for rid, ep in probe.eps.items():
            ctl = ep.controller
            servo = {1: 2000, **pose_of('inspect')}
            for sid, pulse in servo.items():
                action = dict(kind='look', pan_pulse=pulse) if sid == 6 else dict(kind='arm', servo_id=sid, pulse=pulse)
                probe.issue(rid, action, 1.)
            assert ep.own.servo == servo
            ctl.arm.commanded = dict(servo); ctl.arm.events.clear(); ctl.arm.until = .5
            probe.refresh(1.)
            ctl.set('align_start', 1.)
            ctl._align_start(1., True)
            assert ctl.state == 'align' and ctl.look_name == 'inspect'
            assert not ctl.arm.events and ctl.aligned_streak == 0
            assert not ctl.claims.get('aligned')
            assert ctl.s3_alignment_entry['entries'][-1]['preserved']
            assert ep.own.servo == servo
            ctl.set('align_start', 2.)
            ctl._align_start(2., False)
            assert ctl.state == 'align_start'
            # Unknown pose falls back to the frozen search entry, not an
            # invented calibration or a previous stale look_name.
            probe.issue(rid, dict(kind='arm', servo_id=5, pulse=servo[5]+1), 2.)
            ctl._align_start(2., True)
            assert ctl.look_name == 'search' and ctl.arm.events
            assert not ctl.s3_alignment_entry['entries'][-1]['preserved']
    finally: probe.runtime.close()
