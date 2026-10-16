import pytest
import json
from scripts.act16w_runtime import PROJECT, require_gcp2, validate_host, sha256, training_admission


def test_gcp1_or_unknown_project_cannot_admit():
    row = dict(project_id=PROJECT, instance='ugrp-act-l4-gcp2',
               machine_type='g2-standard-8', zone='asia-northeast3-a')
    assert validate_host(row, training=True) == row
    for changed in ({'project_id': 'ugrp-act-train-1014'}, {'instance': 'ugrp-act-l4-pilot1'},
                    {'machine_type': 'g2-standard-4'}, {'zone': 'us-central1-a'}):
        with pytest.raises(ValueError):
            validate_host({**row, **changed}, training=True)


def test_cpu_cannot_train_and_mac_fails_before_metadata(monkeypatch):
    with pytest.raises(ValueError):
        validate_host(dict(project_id=PROJECT, instance='ugrp-sim-gcp2',
                           machine_type='n4-highcpu-64', zone='asia-northeast3-a'), training=True)
    monkeypatch.setattr('scripts.act16w_runtime.platform.system', lambda: 'Darwin')
    with pytest.raises(RuntimeError, match='Mac'):
        require_gcp2(training=True)


def admission_fixture(tmp_path):
    dataset = tmp_path / 'dataset'; dataset.mkdir()
    (dataset / 'manifest.json').write_text('{"complete": true}')
    data = dict(approved=True, source_sha='source', act_source_sha='act',
                dataset_manifest_sha256=sha256(dataset / 'manifest.json'),
                backend='mjwarp_batch_v1', project_id=PROJECT, training_rgb_during_gate=False,
                input_audit_violations=0, fresh_record_confirmation=dict(n=38,N=40,seeds=list(range(80000,80040)),independent_of_warp1_debugging=True),teacher_success_n=38, teacher_attempts_N=40,
                valid_future_action_targets_verified=True)
    for name in ('gate_summary', 'fresh_recording_gate','rejection_table', 'scene_decision', 'dataset_audit'):
        evidence = tmp_path / (name + '.json'); evidence.write_text('{"reviewed": true}')
        data[name] = dict(path=str(evidence), sha256=sha256(evidence))
    path = tmp_path / 'admission.json'
    def check(changed=None):
        path.write_text(json.dumps({**data, **(changed or {})}))
        return training_admission(path, source='source', dataset=dataset, act_source='act')
    return check, data


def test_gate_needs_full_denominator_and_95_percent(tmp_path):
    check, _ = admission_fixture(tmp_path)
    assert check()['teacher_success_n'] == 38
    for changed in (dict(teacher_success_n=38, teacher_attempts_N=39),
                    dict(teacher_success_n=37), dict(teacher_success_n=True),
                    dict(training_rgb_during_gate=True), dict(input_audit_violations=1)):
        with pytest.raises(ValueError):
            check(changed)


def test_missing_or_changed_funnel_evidence_cannot_admit(tmp_path):
    check, data = admission_fixture(tmp_path)
    from pathlib import Path
    Path(data['rejection_table']['path']).write_text('{"changed": true}')
    with pytest.raises(ValueError):
        check()


def test_fresh_camera_recording_cannot_reuse_bootstrap_or_heldout(tmp_path):
    check,data=admission_fixture(tmp_path)
    for seed in (8317100,91620):
        fresh={**data['fresh_record_confirmation'],'seeds':[seed,*range(80001,80040)]}
        with pytest.raises(ValueError,match='fresh independent'):
            check({'fresh_record_confirmation':fresh})
    with pytest.raises(ValueError,match='fresh independent'):
        check({'fresh_record_confirmation':{**data['fresh_record_confirmation'],'n':37}})
