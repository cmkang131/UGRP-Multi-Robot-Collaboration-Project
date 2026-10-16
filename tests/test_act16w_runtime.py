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


def test_recording_adapts_only_recorded_host_fields_and_binds_pilots(tmp_path):
    from scripts.act16w_runtime import recording_host_schema_approval
    host=dict(project_id=PROJECT,instance='ugrp-act-l4-gcp2',machine_type='g2-standard-8',zone='asia-northeast3-a')
    checks=[]
    for i in range(2):
        p=tmp_path/f'pilot-{i}.json';p.write_text('{"passed":true}')
        checks.append(dict(path=str(p),sha256=sha256(p),passed=True))
    proof=dict(approved=True,source_sha='qualified',gate_promotion_authorized_if_all_conditions_pass=False,
        corrected_teacher_gate=dict(source_sha='qualified',solo_truth_free_lookaround_v1=True,n=40,N=40,execution_host=host),pilot_checks=checks)
    p=tmp_path/'approval.json';p.write_text(json.dumps(proof))
    assert recording_host_schema_approval(p,source_sha='qualified',gate_host=host,current_host=host)==proof
    with pytest.raises(ValueError,match='host mismatch'):
        recording_host_schema_approval(p,source_sha='qualified',gate_host={**host,'instance':'ugrp-act-l4-gcp2b'},current_host=host)
    from pathlib import Path
    Path(checks[0]['path']).write_text('{"changed":true}')
    with pytest.raises(ValueError,match='approval'):
        recording_host_schema_approval(p,source_sha='qualified',gate_host=host,current_host=host)


def test_final_seeds_require_completed_comparisons_and_pre_frozen_selection():
    from scripts.act16w_runtime import evaluation_seed_guard,LEROBOT_ACT_SHA256
    model=dict(step=10000,schedule_steps=10000,lerobot_act_sha256=LEROBOT_ACT_SHA256)
    protocol=dict(train_seeds=[86820],validation_seeds=[86865],final_evaluation_seeds=[91620])
    evaluation_seed_guard(model,[86865],split='validation',protocol=protocol,model_sha256='hash')
    for provenance,seeds in [({**model,'step':300},[86865]),({**model,'synthetic_only':True},[86865]),(model,[91620])]:
        with pytest.raises(ValueError):evaluation_seed_guard(provenance,seeds,split='validation',protocol=protocol,model_sha256='hash')
    with pytest.raises(ValueError,match='required comparisons'):
        evaluation_seed_guard(model,[91620],split='final',protocol=protocol,model_sha256='hash')
    selection=dict(approved=True,frozen_before_final=True,checkpoint_sha256='hash',validation_complete=True,completed_comparisons=dict(A_B=True,h4=True,h5=True))
    evaluation_seed_guard(model,[91620],split='final',protocol=protocol,model_sha256='hash',selection=selection)
    with pytest.raises(ValueError):evaluation_seed_guard(model,[91620],split='final',protocol=protocol,model_sha256='changed',selection=selection)
