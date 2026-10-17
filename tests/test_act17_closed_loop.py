"""Closed-job admission only; no physics, rendering or model loading."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from act17_closed_loop import completed_v7_groups


def test_v7_analysis_preserves_candidate_assignment_and_rejects_partial_jobs(tmp_path):
    out=tmp_path/'MFS-0/evaluation';out.mkdir(parents=True)
    (out.parent/'plans.json').write_text(json.dumps(dict(episodes=[dict(seed=1),dict(seed=1)])))
    child=dict(complete=True,status='cap_end',cohort='act17-v7-native',student_scores=[dict(seed=1,candidate='M'),dict(seed=1,candidate='F')])
    (out/'summary.json').write_text(json.dumps(child))
    parent=dict(complete=True,status='complete',cohort='act17-v7-native',finished=[dict(out=str(out),returncode=0,candidates=['M','F'])])
    (tmp_path/'summary.json').write_text(json.dumps(parent))
    assert completed_v7_groups(tmp_path)==[out.parent]
    child['student_scores'][1]['candidate']='S';(out/'summary.json').write_text(json.dumps(child))
    with pytest.raises(ValueError,match='assignment differs'):completed_v7_groups(tmp_path)
    parent['complete']=False;(tmp_path/'summary.json').write_text(json.dumps(parent))
    with pytest.raises(ValueError,match='complete registered'):completed_v7_groups(tmp_path)
