"""P03 version isolation and explicit candidate asset pins; no physics."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts import zone_study_provider_p03 as runner

ROOT = Path(__file__).resolve().parents[1]


def vision_bundle():
    import copy
    pre = runner.legacy.load_prereg('experiments/2026-09-26-zone-study-integration/prereg.json')
    pre['pose_provider'] = runner.PROVIDER_ID
    episode = copy.deepcopy(pre['episodes'][0])
    episode.update(map='zone_wide_door_geometry_v2',
                   scenario='configs/zone_study_integration/i1_cyan_three_slots_geometry_v2.json')
    return pre, episode


def test_vision_bundle_pins_effective_delay_and_model_camera_robot_combination():
    pre, episode = vision_bundle()
    bundle = runner.run_bundle(pre, episode)[0]
    contract = bundle['pose_provider']['runtime_contract']
    assert contract['active']['robot_model'] == 'masterpi_v2'
    assert contract['active']['camera']['final_model_calibration_verified'] is False
    assert contract['delay']['effective_sim_s'] == bundle['perception_delay_s'] == .16
    assert contract['delay']['worker_inference_sim_s'] == 0.
    assert contract['delay']['worker_sim_time_charge']['charged'] is False
    assert contract['candidate_opt_in']['runtime_selectable'] is False
    assert contract['candidate_opt_in']['release'] is None
    assert 'configs/vision_loc_provider_p03.json' in bundle['runtime_files_sha256']
    assert 'configs/model_artifacts.json' in bundle['runtime_files_sha256']
    assert bundle['pose_provider']['calibration_sha256'] == contract['active']['files_sha256'][pre['student']['calibration']]
    assert bundle['pose_provider']['pose_provider'] == runner.PROVIDER_ID
    assert bundle['study_invariant']['pose_provider'] == bundle['pose_provider']['label']
    assert bundle['study_invariant']['execution_bundle_id'] is None


def test_vision_refuses_unpinned_calibration_before_any_host_or_model(monkeypatch):
    from harness import vision_loc_contract_p03 as vp
    pre, episode = vision_bundle()
    pre['student']['calibration'] = 'experiments/2026-09-26-zone-owncam-loop-v2/calibration_loop_v2.json'
    monkeypatch.setattr(runner, 'StudyTeamHost', lambda *a, **kw: pytest.fail('host forbidden'))
    with pytest.raises(vp.ProtocolError, match='combination'):
        runner.run_bundle(pre, episode)


@pytest.mark.parametrize('changed', ['model', 'camera', 'robot', 'render'])
def test_runtime_combination_mismatch_is_rejected(changed, tmp_path):
    import json
    from harness import vision_loc_contract_p03 as vp
    config = vp.load_config()
    pin = vp.load_json(vp.PROVIDER_PIN_FILE)
    root = tmp_path
    paths = set(pin['active']['files_sha256']) | {'configs/vision_loc_provider_p03.json', 'configs/model_artifacts.json'}
    for rel in paths:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / rel).read_bytes())
    if changed == 'model':
        config['model']['sha256'] = pin['candidate_opt_in']['local_checkpoint']['sha256']
    else:
        rel = {'camera': 'sim/masterpi_camera_profile.py', 'robot': 'sim/masterpi_dynamics_v2.py',
               'render': 'sim/render_profile.py'}[changed]
        (root / rel).write_text('# changed\n')
    with pytest.raises(vp.ProtocolError, match='pin|hash'):
        vp.provider_runtime_contract(map_id='zone_wide_door_geometry_v2', cfg=config, root=root)


def test_candidate_preserves_successor_bytes_and_rejects_historical_admission(tmp_path):
    """C312-1: P03 cannot change the seal or re-admit historical v6e on v6h."""
    from scripts import run_zone_pair_dev as dev
    from scripts.zone_pair_v6_contract import PREREG_V6E, contract
    from tests.v6h_successor_pins import successor_pins

    pre, episode = vision_bundle()
    candidate = runner.run_bundle(pre, episode)[0]
    for rel, expected in successor_pins().items():
        assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == expected, rel
    with pytest.raises(ValueError, match='historical'):
        contract('v6e')
    output = tmp_path / 'never-executed'
    args = dev.parser().parse_args(['--prereg', str(PREREG_V6E), '--run-id', 'v6e-s911-bv6g',
                                   '--output', str(output)])
    with pytest.raises(ValueError, match='historical'):
        dev.load_config(args)
    assert not output.exists()
    assert candidate['execution_bundle_id'] is None
    assert candidate['runnable'] is candidate['physical_ready'] is False


def test_candidate_requires_new_identity_without_rebinding_legacy_factory():
    import importlib
    from harness.vision_pose_source import VisionPoseSourceV2 as LegacySource
    from harness.vision_pose_source_p03 import VisionPoseSourceV2 as CandidateSource
    from harness.zone_study_pose_delay import DelayedPoseSource as LegacyDelay

    pre, episode = vision_bundle()
    old_spec = runner.zi.pose_provider_spec(runner.BASELINE_PROVIDER_ID, map_id=episode['map'])
    module, _, name = old_spec['factory'].partition(':')
    assert getattr(importlib.import_module(module), name) is LegacySource
    assert runner.zi.DelayedPoseSource is LegacyDelay
    assert CandidateSource.provider_id != LegacySource.provider_id
    assert CandidateSource.source_prefix != LegacySource.source_prefix
    with pytest.raises(runner.zi.ContractViolation, match='explicit candidate'):
        runner.run_bundle({**pre, 'pose_provider': runner.BASELINE_PROVIDER_ID}, episode)
    with pytest.raises(runner.zi.ContractViolation, match='unknown pose provider'):
        runner.zi.pose_provider_spec(runner.PROVIDER_ID, map_id=episode['map'])


def test_planner_roots_declare_pin_json_and_all_referenced_assets():
    """C311-1 seam: AST readers and full closure readers can both find P03 inputs."""
    import ast
    from harness import vision_loc_contract_p03 as vp

    tree = ast.parse((ROOT / 'scripts/zone_study_provider_p03.py').read_text())
    assets = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == 'RUNTIME_ASSETS' for t in node.targets))
    assert 'configs/vision_loc_provider_p03.json' in assets
    pre, episode = vision_bundle()
    bundle = runner.run_bundle(pre, episode)[0]
    pin = vp.load_json(vp.PROVIDER_PIN_FILE)
    assert set(pin['active']['files_sha256']) <= bundle['runtime_files_sha256'].keys()
    assert set(assets) <= bundle['runtime_files_sha256'].keys()


@pytest.mark.parametrize('changed', ['combination_json', 'camera_asset'])
def test_saved_preview_rejects_changed_p03_json_or_referenced_asset(monkeypatch, tmp_path, changed):
    """C311-1: reproduce a saved draft followed by a changed camera pin/file."""
    from harness import vision_loc_contract_p03 as vp

    pre, episode = vision_bundle()
    original = runner.run_bundle(pre, episode)[0]
    saved_path = tmp_path / 'saved-preview.json'
    saved_path.write_text(json.dumps(original))
    saved = json.loads(saved_path.read_text())
    assert runner.check_preview(saved, pre, episode) == runner.digest(original)
    rel = ('configs/vision_loc_provider_p03.json' if changed == 'combination_json'
           else 'sim/masterpi_camera_profile.py')
    target = ROOT / rel
    replacement = tmp_path / target.name
    if changed == 'combination_json':
        pin = json.loads(target.read_text())
        pin['active']['camera']['intrinsics_mount'] = 'changed-camera-unvalidated'
        replacement.write_text(json.dumps(pin))
    else:
        replacement.write_bytes(target.read_bytes() + b'\n# changed camera\n')
    read_bytes, read_text = Path.read_bytes, Path.read_text
    monkeypatch.setattr(Path, 'read_bytes', lambda p: read_bytes(replacement if p == target else p))
    monkeypatch.setattr(Path, 'read_text', lambda p, *a, **kw: read_text(replacement if p == target else p, *a, **kw))
    if changed == 'combination_json':
        current = runner.run_bundle(pre, episode)[0]
        assert current['runtime_files_sha256'][rel] != original['runtime_files_sha256'][rel]
        assert runner.digest(current) != runner.digest(saved)
        with pytest.raises(runner.zi.ContractViolation, match='preview/source hash mismatch'):
            runner.check_preview(saved, pre, episode)
    else:
        with pytest.raises(vp.ProtocolError, match='source hash mismatch'):
            runner.check_preview(saved, pre, episode)
