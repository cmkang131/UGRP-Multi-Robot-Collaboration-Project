from pathlib import Path
from scripts import run_own_route_heading_stability as runner
from harness.path_heading_stability import OPTION

def test_delivery_keeps_all_four_denominators_and_blocked_trials():
    import importlib.util
    path=runner.ROOT/'experiments/2026-10-10-own-route-heading-stability/code/deliver.py'
    spec=importlib.util.spec_from_file_location('egomap65_delivery_test',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    rows=[dict(seed=s,profile=p,heading_stability=h,status='BLOCKED',samples=0)
          for s in runner.SEEDS for p in ('baseline','a') for h in ('off',OPTION)]
    result=m.aggregate(rows)
    assert len(result)==4
    assert all(r['registered']==6 and r['measured']==0 and r['frames']==0 for r in result.values())
    assert all(r['B']==0 and r['returned']==0 and r['final_error_median'] is None for r in result.values())


def test_remote_verifier_rejects_running_batch_and_checks_raw(tmp_path):
    import hashlib,importlib.util,json,pytest
    path=runner.ROOT/'experiments/2026-10-10-own-route-heading-stability/code/verify_remote.py'
    spec=importlib.util.spec_from_file_location('egomap65_verify_test',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    batch=tmp_path/'egomap65-batch/data';batch.mkdir(parents=True)
    smoke=tmp_path/'egomap65-smoke/data';smoke.mkdir(parents=True)
    jobs=[dict(status='RUNNING',heading_stability=OPTION) for i in range(24)]
    (batch/'batch-status.json').write_text(json.dumps(jobs))
    with pytest.raises(ValueError,match='WAIT_ALL_24_TERMINAL'):m.verify(batch,smoke)
    for j in jobs:j['status']='BLOCKED'
    (batch/'batch-status.json').write_text(json.dumps(jobs))
    (batch/'batch-plan.json').write_text(json.dumps({'source_sha':'a'*40}))
    (smoke/'raw.bin').write_bytes(b'original')
    (smoke/'artifacts.sha256.json').write_text(json.dumps({'raw.bin':hashlib.sha256(b'original').hexdigest()}))
    m.verify(batch,smoke)
    r=json.loads((batch/'server-verification.json').read_text());assert r['files_verified']==1 and r['mismatches']==[]
    (smoke/'raw.bin').write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='SERVER_ARTIFACT_HASH_MISMATCH'):m.verify(batch,smoke)


def test_recovery_only_five_zero_physics_input_losses_and_same_commands(tmp_path):
    import json,pytest
    from scripts.retry_own_route_heading_inputs import admission,SOURCE,EXPECTED
    root=tmp_path/'original/data';root.mkdir(parents=True)
    (root.parent/'EXIT').write_text('0')
    jobs=[]
    for s,p,h in sorted(EXPECTED):
        name=f'{s}-{p}-{h}';cp=tmp_path/name;cp.write_bytes(b'fixture')
        old=root/name
        row=dict(seed=s,profile=p,heading_stability=h,status='HOST_ERROR_NO_RESULT',name=name,checkpoint=str(cp),output=str(old),command=['python','-m','scripts.run_own_route_heading_stability','--output',str(old)])
        jobs.append(row);(root/(name+'.log')).write_text('FileNotFoundError '+str(cp))
    (root/'batch-status.json').write_text(json.dumps(jobs))
    out=tmp_path/'new';result=admission(root,out,tmp_path/SOURCE)
    assert len(result)==5
    for a,b in zip(jobs,result):assert a['command'][:-1]==b['command'][:-1] and a['output']!=b['output']
    bad=Path(jobs[0]['output']);bad.mkdir();(bad/'own-controller.jsonl').write_text('prior physics')
    with pytest.raises(ValueError,match='PHYSICS_ALREADY_STARTED'):admission(root,out,tmp_path/SOURCE)
