import ast
from pathlib import Path

from scripts.run_s2_loaded_rotation import schedule, main


def test_schedule_exact_original_and_split():
    source=Path('experiments/2026-10-06-s2-realism/references/egomap32_run_pulse_rotation_audit.py.txt').read_text()
    fn=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='schedule')
    ns={};exec(compile(ast.Module(body=[fn],type_ignores=[]),'pinned_schedule','exec'),ns)
    assert schedule()==ns['schedule']()
    blocks,commands,ticks=schedule()
    assert ticks==1200 and len(blocks)==20 and len(commands)==110
    assert len([b for b in blocks if b['split']=='fit'])==12
    assert len([b for b in blocks if b['split']=='check'])==8
    for b in blocks:
        assert [k for k in commands if b['start_tick']<=k<b['end_tick']]==list(range(b['start_tick'],b['end_tick'],4))


def test_preview_never_starts_world_or_lock(monkeypatch,capsys,tmp_path):
    from scripts import run_s2_loaded_rotation as runner
    monkeypatch.setattr(runner,'run',lambda *a:(_ for _ in ()).throw(AssertionError('physics not permitted')))
    monkeypatch.setattr('sys.argv',['run','--expected-source-sha','a'*40,'--output',str(tmp_path/'none')])
    main()
    assert '"execution_started": false' in capsys.readouterr().out
    assert not (tmp_path/'none').exists()


def test_sealed_fit_recovers_both_over_and_under_prediction(tmp_path):
    import hashlib
    import importlib.util
    import json
    import math
    import numpy as np
    source=Path('experiments/2026-10-06-s2-realism/fit_loaded_rotation.py')
    spec=importlib.util.spec_from_file_location('loaded_fit_test',source)
    fit=importlib.util.module_from_spec(spec);spec.loader.exec_module(fit)
    raw=tmp_path/'raw';raw.mkdir();blocks,commands,ticks=schedule()
    model=json.loads(Path('configs/s2_motion_v7_pulse_cal_v1.json').read_text())
    steps=np.zeros(ticks+1)
    for tick,cmd in commands.items():
        gain=1.1 if cmd['turn']>0 else .9
        delta=model['profiles'][f"1:turn:{cmd['turn']:.2f}:0.10"]['mean_delta'][2]*gain
        steps[tick+1:tick+5]+=delta/4
    yaw=np.cumsum(steps)
    rows=[dict(t=i/20,rpy=[0,0,float(v)],xyz=[0,0,.0325],cargo_xyz=[0,0,.15],contacts=[]) for i,v in enumerate(yaw)]
    (raw/'eval-only.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    (raw/'schedule.json').write_text(json.dumps(dict(blocks=blocks)))
    (raw/'result.json').write_text(json.dumps(dict(status='RECORDED',source_sha='test',start_sim_s=0,bilateral_fraction=1.)))
    (raw/'artifacts.sha256.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in raw.iterdir()}))
    fit.score(raw,tmp_path/'fit')
    result=json.loads((tmp_path/'fit/result.json').read_text())
    assert math.isclose(result['accepted_gains']['1:turn:0.35:0.10'],1.1)
    assert math.isclose(result['accepted_gains']['1:turn:-0.35:0.10'],.9)
