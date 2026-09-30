from pathlib import Path
from harness.python_source_closure import source_closure

def test_no_hidden_environment_dependency_in_legacy_candidate():
    root=Path(__file__).resolve().parents[1]
    paths=source_closure(root,['scripts/run_zone_study_integration.py','sim/zone_own_scene_provider.py'])
    assert 'harness/zone_environment_registry.py' not in paths
