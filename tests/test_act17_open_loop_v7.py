"""Completed subset admission; no torch, simulator or renderer."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from act17_open_loop_v7 import audit_candidate


def test_offline_subset_requires_final_weights_and_matching_data():
    manifest=dict(protocol=dict(training=dict(steps_round1=10000)),normalization=dict(sha256='norm'))
    meta=dict(provenance=dict(candidate='F',cohort='act17-v7-native',contact_profile='warp_native_contact_v1',training_complete=True,step=10000,dataset_manifest_sha256='data',normalization_sha256='norm'))
    training=dict(complete=True,readback_verified=True,steps_completed=10000,checkpoint_sha256='weights')
    audit_candidate('F',meta,training,manifest,'data','weights')
    for field,value in [('training_complete',False),('step',9999),('dataset_manifest_sha256','other')]:
        bad=deepcopy(meta);bad['provenance'][field]=value
        with pytest.raises(ValueError,match='completed exact-dataset'):audit_candidate('F',bad,training,manifest,'data','weights')
    with pytest.raises(ValueError,match='completed exact-dataset'):audit_candidate('F',meta,training,manifest,'data','changed-weights')
