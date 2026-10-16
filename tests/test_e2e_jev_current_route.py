import copy

import pytest
from harness.e2e_runtime_registration import require_current
from scripts.run_e2e_ownmap_live import ROOT, bundle
from tests import test_e2e_camera_hold as parent_test


def candidate(monkeypatch):
    captured = {}
    def save(*args, **kwargs):
        captured.update(args=args, kwargs=kwargs)
        return bundle(*args, **kwargs)
    monkeypatch.setattr(parent_test, 'bundle', save)
    parent_test.test_registered_wheel_wait_candidate('zero_wheel_v1',275,'range_wall_v1')
    kwargs = dict(captured['kwargs'], decider='jev_v1')
    return bundle(*captured['args'], **kwargs)


def test_current_jev_uses_all_parent_guards_and_default_off_identity(monkeypatch):
    b = candidate(monkeypatch)
    assert b['execution_bundle_id'] == 'e2e18-v278'
    assert b['jev_current_route']['handshake_windows_unchanged']
    assert 'harness/e2e_jev_decider.py' in b['source_sha256']
    require_current(b, ROOT)
    for field, value in [('decider','off'), ('capture_pose','off'), ('pulse_authorization','off')]:
        bad=copy.deepcopy(b);bad['e2e_options'][field]=value
        with pytest.raises(ValueError):require_current(bad, ROOT)
    from harness.e2e_jev_current_route import compose
    old=dict(execution_bundle_id='e2e18-v275',e2e_options={'decider':'off'})
    before=copy.deepcopy(old)
    assert compose(old)==() and old==before
