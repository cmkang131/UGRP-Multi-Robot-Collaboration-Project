"""Pure safety/provenance tests; never import a simulator or make a GL context."""
import json
from pathlib import Path
import pytest
from scripts.simalt_pilot import trace_rows, runtime


def test_trace_rejects_teacher_truth(tmp_path):
    p=tmp_path/'trace.jsonl'
    p.write_text(json.dumps({'t':1.,'phase':'hold','command':{},'visible_target':{'xyz':[1,2,3]}}))
    with pytest.raises(ValueError,match='issued commands'):
        trace_rows(p)


def test_trace_requires_contiguous_control_clock(tmp_path):
    p=tmp_path/'trace.jsonl'
    p.write_text('\n'.join(json.dumps({'t':t,'phase':'hold','command':{}}) for t in (1.,1.2)))
    with pytest.raises(ValueError,match='10 Hz'):
        trace_rows(p)


def test_no_simulator_import_on_mac(monkeypatch):
    monkeypatch.setattr('scripts.simalt_pilot.platform.system',lambda:'Darwin')
    with pytest.raises(RuntimeError,match='Mac physics/render forbidden'):
        runtime('/does/not/exist','egl_l4_v1')


def test_defaults_keep_training_and_gpu_disabled():
    p=Path(__file__).resolve().parents[1]/'experiments/2026-10-15-simalt1/protocol.json'
    config=json.loads(p.read_text())
    assert config['render_backend']=='legacy'
    assert config['egl_l4_v1'] is False
    assert config['stage_D_training'] is False
    assert Path(config['rejection_table']).is_file()
