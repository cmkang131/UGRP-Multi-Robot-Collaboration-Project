"""Complete offline integration probe, never physics or a success benchmark."""
from tests import s3_stage_probe as probe


def test_s3_stage_sweep(tmp_path, monkeypatch):
    import copy
    from harness.zone_s3_consistent_runtime import Runtime
    def factory(*a,config,**kw):
        config=copy.deepcopy(config)
        config['options']['pose_validity']='defer_unmeasured_v1'
        return Runtime(*a,config=config,**kw)
    monkeypatch.setattr(probe,'Runtime',factory)
    report=probe.sweep(tmp_path,monkeypatch,invalid_pose_cases=True)
    assert report['error_count']==0, report['errors']
