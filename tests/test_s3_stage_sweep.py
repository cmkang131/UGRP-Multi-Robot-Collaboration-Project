"""Complete offline integration probe, never physics or a success benchmark."""
from tests.s3_stage_probe import sweep


def test_s3_stage_sweep(tmp_path, monkeypatch):
    report=sweep(tmp_path,monkeypatch)
    assert report['error_count']==0, report['errors']
