import copy
import pytest
from tests.s2_ci_inputs import portable_s2_inputs

pytestmark = pytest.mark.usefixtures("portable_s2_inputs")
from scripts import run_s2_v133_reproduction as r


def test_frozen_profile_only_seed_and_administrative_provenance_change():
    old = r.baseline()
    for seed in r.read_plan()['seeds']:
        b = r.bundle(seed, 'a'*40)
        r.require_execution(b)
        expected = copy.deepcopy(old)
        expected['task']['seed'] = seed
        expected['source_sha'] = r.read_plan()['frozen_source_sha']
        expected['reproduction'] = b['reproduction']
        expected['bundle_sha256'] = b['bundle_sha256']
        assert b == expected
        assert b['options'] == old['options']
        assert b['source_sha256'] == old['source_sha256']
        assert b['execution_bundle_id'] == 'zone-s2-realism-v133'
    with pytest.raises(ValueError):
        r.bundle(1051, 'a'*40)


def test_no_option_threshold_or_task_mutation_admitted():
    b = r.bundle(1053, 'a'*40)
    for section, key, val in [('options', 'slip_detection', 'off'),
                              ('options', 'idle_robot_contacts', 'off'),
                              ('task', 'pickup_slot', 'P1-1')]:
        q = copy.deepcopy(b); q[section][key] = val
        with pytest.raises(ValueError):r.require_execution(q)
    q = copy.deepcopy(b); q['case_cap_s'] += 1
    with pytest.raises(ValueError):r.require_execution(q)


def test_workflow_is_separate_admission_not_replacement_profile():
    from sim.workflow_manager import _row
    row, _ = _row(r.ROOT, 'zone-s2-v133-reproduction')
    assert row['runner'] == 'scripts.run_s2_v133_reproduction'
    original, _ = _row(r.ROOT, 'zone-s2-realism-v133')
    assert original['runner'] == 'scripts.run_s2_landmarks_dev'
