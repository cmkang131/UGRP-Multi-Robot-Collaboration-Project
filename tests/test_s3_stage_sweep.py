"""Complete offline integration probe, never physics or a success benchmark."""
from tests import s3_stage_probe as probe


def test_s3_stage_sweep(tmp_path, monkeypatch):
    from harness import zone_s3_consistency_contract as contract
    from harness.zone_s3_consistent_runtime import Runtime
    monkeypatch.setattr(probe, 'contract', contract)
    monkeypatch.setattr(probe, 'Runtime', Runtime)
    report=probe.sweep(tmp_path,monkeypatch,invalid_pose_cases=True)
    assert report['error_count']==0, report['errors']
