"""pairact -c4: fail-closed MuJoCo/Warp pins + host-loop timing in the warp flow runner (no simulator)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import runtime_pins as rp  # noqa: E402

GOOD = {'mujoco': '3.16.0', 'warp-lang': '1.15.0'}


def test_rollout_pins_match_r13_records():
    rec = rp.check('rollout', versions=GOOD, commit=rp.MJWARP_COMMIT, module_mujoco='3.16.0')
    assert rec['mujoco_warp']['status'] == 'match' and rec['want'] == rp.ROLLOUT
    r13 = ROOT/'experiments/2026-10-15-simalt3/evidence/warp-freeze.txt'
    text = r13.read_text()
    assert 'mujoco==3.16.0' in text and 'warp-lang==1.15.0' in text and rp.MJWARP_COMMIT in text
    assert 'mujoco==3.12.0' in (ROOT/'experiments/2026-10-15-simalt3/evidence/c-freeze.txt').read_text()


@pytest.mark.parametrize('versions,module', [
    ({'mujoco': '3.12.0', 'warp-lang': '1.15.0'}, '3.12.0'),     # gcp6 2026-10-21 case
    ({'mujoco': '3.16.0', 'warp-lang': '1.16.0'}, '3.16.0'),
    ({'mujoco': None, 'warp-lang': '1.15.0'}, '3.16.0'),
    (GOOD, '3.12.0'),                                             # metadata vs imported module disagree
])
def test_rollout_mismatch_stops(versions, module):
    with pytest.raises(SystemExit, match='RUNTIME_PIN_MISMATCH'):
        rp.check('rollout', versions=versions, commit=rp.MJWARP_COMMIT, module_mujoco=module)


def test_mjwarp_commit_mismatch_stops():
    with pytest.raises(SystemExit, match='mujoco-warp'):
        rp.check('rollout', versions=GOOD, commit='0'*40, module_mujoco='3.16.0')


def test_unverifiable_mjwarp_is_recorded_not_fatal(monkeypatch):
    monkeypatch.setattr(rp, 'mjwarp_commit', lambda: None)
    rec = rp.check('rollout', versions=GOOD, module_mujoco='3.16.0')
    assert rec['mujoco_warp'] == {'want': rp.MJWARP_COMMIT, 'have': None, 'status': 'unverified_no_direct_url'}
    json.dumps(rec, allow_nan=False)


def test_export_requires_312_and_none_mode_checks_nothing():
    assert rp.check('export', versions={'mujoco': '3.12.0'}, module_mujoco='3.12.0')['want'] == {'mujoco': '3.12.0'}
    with pytest.raises(SystemExit, match='RUNTIME_PIN_MISMATCH'):
        rp.check('export', versions={'mujoco': '3.16.0'}, module_mujoco='3.16.0')
    assert rp.check('none', versions={})['want'] == {}
    with pytest.raises(ValueError):
        rp.check('bogus', versions={})


def test_mode_for():
    assert rp.mode_for('mjwarp_batch_v1', False) == 'rollout'
    assert rp.mode_for('mjwarp_batch_v1', True) == 'export'
    assert rp.mode_for('c_pilot_v1', False) == 'none'


def test_direct_url_parsing(monkeypatch):
    class D:
        def __init__(self, raw): self.raw = raw
        def read_text(self, name): return self.raw
    for raw, want in [
        (json.dumps({'url': 'https://github.com/google-deepmind/mujoco_warp', 'vcs_info': {'commit_id': 'a'*40}}), 'a'*40),
        (json.dumps({'url': f'https://github.com/google-deepmind/mujoco_warp/archive/{rp.MJWARP_COMMIT}.tar.gz'}), rp.MJWARP_COMMIT),
        (json.dumps({'url': 'file:///tmp/simalt1/mujoco_warp', 'dir_info': {}}), None),
        (None, None)]:
        monkeypatch.setattr(rp.importlib.metadata, 'distribution', lambda name, raw=raw: D(raw))
        assert rp.mjwarp_commit() == want


def test_runner_checks_pins_before_any_model_or_cuda_work():
    src = (ROOT/'scripts/run_warp_flow_teacher.py').read_text()
    main = src[src.index('def main():'):]
    guard = main.index('runtime_pins=check_runtime_pins(runtime_pin_mode(a.physics_backend,a.export_compiled_only))')
    for later in ('from simalt_host import gcp2_identity', 'import mujoco', 'nvidia-smi', 'make_lane(', 'import warp'):
        assert guard < main.index(later), later
    assert "report['runtime_pins']=runtime_pins" in main
    # the existing 3.12 export assertion is kept
    assert "if mujoco.__version__!='3.12.0':raise ValueError('C312 reference export requires3.12')" in main


def test_host_loop_timing_is_recorded():
    src = (ROOT/'scripts/run_warp_flow_teacher.py').read_text()
    for key in ('capture_s', 'rings_review_s', 'lane_teacher_s', 'world_ticks'):
        assert f"host_loop['{key}']" in src
    assert "progress['host_loop_s']=dict(host_loop)" in src and "report['host_loop_s']=dict(host_loop)" in src
