import pytest
from scripts.act16w_runtime import PROJECT, require_gcp2, validate_host


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
