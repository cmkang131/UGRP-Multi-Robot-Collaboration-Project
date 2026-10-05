"""v98: the HIGH 'beam edge' is the renderer's near-clip trace (outputs/v98-znear-live-check-20261004), so it is not used.

Checks (no physics): (1) the flag is off; (2) the provider never feeds the tracker and its yaw fallback is the
own-command-sync ('pm') variant with the calibrated extra std; (3) the carry wait does not wait for an edge reference
that can never come (no HIGH_CARRY_EDGE_REFERENCE_TIMEOUT), and the recorded nominal HIGH run still releases."""
import math
from types import SimpleNamespace

import pytest

from harness import owncam_carry_v6e as v6e
from harness import zone_pair_highpose_edge as ed
from harness import vision_pose_source_highpose as vsh
from tests import test_highpose_transit as tt
from tests.test_highpose_dev_pilot import dev_file, admit, MAPS, c


def test_flag_is_off():
    assert ed.HIGH_EDGE_INFORMATIVE is False


def test_provider_never_feeds_the_tracker_and_falls_back_to_pm(tmp_path, monkeypatch):
    path, _ = dev_file(tmp_path)
    sha = c.base.sha(path)
    admit(monkeypatch, sha)
    provider = vsh.HighPoseSource(c.resolve(MAPS[0])[0], path, sha)
    try:
        def boom(*a, **k):
            raise AssertionError('tracker must not be observed')
        monkeypatch.setattr(provider.beam_edge, 'observe', boom)
        monkeypatch.setattr(vsh.VisionPoseSource, 'on_frame', lambda self, now, rgb: 'ok')
        monkeypatch.setattr(vsh.contract, 'camera_record', lambda *a, **k: None)
        provider.servo = {1: 1500, **vsh.pose.HIGH}
        assert provider.on_frame(1., None) == 'ok'
        assert provider.beam_edge.total_rad == 0. and not provider.beam_edge.available(100.)
        cfg = provider.carry_yaw_fallback
        assert cfg['edge'] is False and cfg['pair'] is True
        std, key = v6e.fallback_std(cfg, True, provider.beam_edge.available(100.))
        assert key == 'pm'
        assert std == pytest.approx(math.sqrt(cfg['b']['pm']**2-cfg['b_full']**2))
        assert 0. <= std < 5e-4          # rad/s (test calibration; about 1.9e-4 in the recorded v98 dev file)
        std_np, key_np = v6e.fallback_std(cfg, False, False)
        assert key_np == '' and std_np == pytest.approx(math.sqrt(cfg['b']['']**2-cfg['b_full']**2))   # plan mismatch: unchanged
    finally:
        provider.close()


@pytest.fixture(autouse=True)
def short_route(monkeypatch):
    monkeypatch.setattr(tt.legacy, 'build_schedule',
                        lambda rid, t: [(t, t+.2, {'forward': .01, 'left': 0., 'turn': 0.})])


def test_carry_wait_does_not_depend_on_an_edge_reference():
    _, ctls = tt.pair()
    for ctl in ctls:
        ctl.port.own.pose.provider.beam_edge.available = lambda now: False     # never available
    tt.run(ctls, until=45.)
    for ctl in ctls:
        assert ctl.failure is None and ctl.state == 'released' and tt.opened(ctl)
