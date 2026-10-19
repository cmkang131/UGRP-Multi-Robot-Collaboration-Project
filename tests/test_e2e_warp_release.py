"""Mac-only (non-physical) tests for the default-off e2ewarp release adapter."""
import hashlib
import json
from pathlib import Path

import pytest

from harness import e2e_warp_components as components
from harness import grasp_act_contract as contract
from harness import e2e_warp_release as release

ROOT = Path(__file__).resolve().parents[1]
STATIC = dict(orders=[{'id': 'o1'}], static_map={'cells': [], 'frame': 'static'},
              condition='peer_en', input_boundary='own RGB and own issued commands only')
SEARCH_PWM = {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}


class Frame:
    def __init__(self, robot_id='r1', t=0.0, jpeg=b'own-rgb', pwm=None):
        self.robot_id, self.sim_s, self.jpeg = robot_id, t, jpeg
        self.issued = tuple([dict(t=t, pwm=dict(pwm or SEARCH_PWM))])


def start(adapter, instruction=None):
    adapter.start(instruction or dict(destination_zone='A', object_kind='long_beam', role='teal'), {})
    return adapter


def owner_ok(evidence):
    assert set(evidence) == {'robot_id', 'static_sha256', 'instruction', 'views'}
    assert evidence['robot_id'] == 'r1'
    for view in evidence['views']:
        assert set(view) == {'t', 'rgb_sha256', 'pwm'}  # own RGB + own issued PWM only
        assert len(view['rgb_sha256']) == 64
    return dict(owner='warp8f', relocalized=True, static_map_registered=True,
                static_map_sha256=evidence['static_sha256'], map_pose=[0.1, -0.2, 0.3],
                source='own_rgb', views=len(evidence['views']), truth_inputs=0, held_world_reads=0)


def collect_views(adapter, start_t=0.0):
    """Run the fixed three settled own-camera views and feed matching own frames."""
    dwell = release._view_dwell_s()
    pwm = {'1': 2000, '3': 740, '4': 2320, '5': 1320, '6': adapter.command(start_t)['pwm']['6']}
    t = start_t
    out = None
    for _ in range(release.PAN_VIEWS):
        cmd = adapter.command(t)
        pwm = cmd['pwm']
        t += dwell
        out = adapter.observe(Frame(t=t, pwm={int(k): int(v) for k, v in pwm.items()}))
        t += 0.1
    return out, t


def test_default_off_fails_closed():
    adapter = start(release.release_factory('r1', STATIC))
    report = adapter.observe(Frame(t=0.0))
    assert report['relocalized'] is False and report['static_map_registered'] is False
    assert report['reason'] == 'own_lookaround_views_0_of_3'
    command = contract.command(adapter.command(1.0))  # whitelist-valid issued command
    assert command['wheels'] == [0.0] * 4 and 500 <= command['pwm']['6'] <= 2500
    assert report['audit']['truth_inputs'] == 0 and report['audit']['top_camera_control'] is False


def test_selfmap_without_owner_pending():
    adapter = start(release.release_factory('r1', STATIC, option=release.OPTION_SELFMAP))
    report, _ = collect_views(adapter)
    assert report['relocalized'] is False
    assert report['reason'] == 'owner_static_map_acquisition_api_pending'


def test_selfmap_owner_accepts_own_inputs_only():
    adapter = start(release.release_factory('r1', STATIC, option=release.OPTION_SELFMAP, owner=owner_ok))
    report, _ = collect_views(adapter)
    assert report['relocalized'] is True and report['static_map_registered'] is True
    assert report['map_pose'] == [0.1, -0.2, 0.3]
    assert report['evidence']['static_map_sha256'] == adapter.static_sha256
    assert report['audit']['views'] == release.PAN_VIEWS


def test_owner_forbidden_inputs_rejected():
    def owner(evidence):
        return dict(owner_ok(evidence), truth_inputs=1)
    adapter = start(release.release_factory('r1', STATIC, option=release.OPTION_SELFMAP, owner=owner))
    report, _ = collect_views(adapter)
    assert report['relocalized'] is False and report['reason'] == 'owner_reports_forbidden_inputs'


def test_owner_static_map_hash_mismatch_rejected():
    def owner(evidence):
        return dict(owner_ok(evidence), static_map_sha256='0' * 64)
    adapter = start(release.release_factory('r1', STATIC, option=release.OPTION_SELFMAP, owner=owner))
    report, _ = collect_views(adapter)
    assert report['relocalized'] is False and report['reason'] == 'owner_static_map_hash_mismatch'


def test_owner_failure_is_unknown_not_claim():
    def owner(evidence):
        raise RuntimeError('owner down')
    adapter = start(release.release_factory('r1', STATIC, option=release.OPTION_SELFMAP, owner=owner))
    report, _ = collect_views(adapter)
    assert report['relocalized'] is False
    assert report['reason'] == 'owner_relocalizer_error:RuntimeError'


def test_pan_commands_alone_do_not_count_as_relocalization():
    adapter = start(release.release_factory('r1', STATIC, option=release.OPTION_SELFMAP, owner=owner_ok))
    adapter.command(0.0)
    # A frame arrives before the existing settle interval: not a qualified view.
    report = adapter.observe(Frame(t=0.05, pwm=SEARCH_PWM))
    assert report['relocalized'] is False and adapter.rows == []
    # Wrong pan (frame from an old pwm) is not counted either.
    report = adapter.observe(Frame(t=release._view_dwell_s() + 1.0, pwm=SEARCH_PWM))
    assert report['relocalized'] is False and adapter.rows == []


def test_cross_robot_and_causality_rejected():
    adapter = start(release.release_factory('r1', STATIC))
    with pytest.raises(ValueError, match='cross-robot'):
        adapter.observe(Frame(robot_id='r2', t=1.0))
    adapter.observe(Frame(t=2.0))
    with pytest.raises(ValueError, match='causal'):
        adapter.observe(Frame(t=2.0))
    with pytest.raises(ValueError, match='start required'):
        release.release_factory('r1', STATIC).observe(Frame())


def test_start_requires_instruction_and_own_report():
    adapter = release.release_factory('r1', STATIC)
    with pytest.raises(ValueError):
        adapter.start({'object_kind': 'long_beam'}, {})
    with pytest.raises(ValueError):
        adapter.start({'destination_zone': 'A'}, None)


def test_module_boundary_has_no_sim_evaluator_or_gt_input():
    source = (ROOT / 'harness' / 'e2e_warp_release.py').read_text()
    # 'warp'/'warp8f' is the required owner name; the scan checks for simulator,
    # measurement, verdict and file-read tokens instead.
    forbidden = ('e2e_warp_physics', 'sim.', 'evaluator', 'evaluation', 'mujoco',
                 'top_camera_control=True', 'ground_truth', 'hidden_state', 'open(')
    for token in forbidden:
        assert token not in source, token
    allowed_imports = ('__future__', 'hashlib', 'json', 'math',
                       'harness.active_camera', 'harness.e2e_rgb_vo',
                       'harness.e2ewarp_selfnav', 'harness.grasp_act_contract',
                       'harness.warp8f_memory')
    for line in source.splitlines():
        line = line.strip()
        if line.startswith('from ') or line.startswith('import '):
            assert any(token in line for token in allowed_imports), line


def test_hash_bound_manifest_entry_and_factory():
    path = ROOT / 'harness' / 'e2e_warp_release.py'
    entry = {'entry': release.ENTRY, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    assert entry['entry'] == 'harness.e2e_warp_release:release_factory'
    module, attr = entry['entry'].split(':')
    assert (ROOT / (module.replace('.', '/') + '.py')).is_file()
    adapter_factory = components.factory(entry)
    adapter = adapter_factory(robot_id='r1', static=STATIC)
    assert isinstance(adapter, release.ReleaseRelocalization)
    fragment = json.loads((ROOT / 'experiments' / '2026-10-18-e2ewarp-r4-release'
                           / 'manifest-entry.json').read_text())
    assert fragment['adapter']['entry'] == entry['entry']
    assert fragment['adapter']['sha256'] == entry['sha256']
    assert fragment['component'] == 'release_relocalization'
    assert fragment['adapter']['default'] == 'off'
