"""Post-result integrity checks; no prediction, GT fitting, or physics."""
from collections import Counter
from replay import EXP, ROOT, RAW, OUT, load, rows, sha, dump
from scripts.run_wall_parallax_strafe import USER_FILES


def main():
    freeze=load(EXP/'freeze.json')
    assert all(sha(ROOT/p)==h for p,h in freeze['files'].items())
    assert all(sha(ROOT/p)==h for p,h in USER_FILES.items())
    report=load(EXP/'results/replay.json')
    assert report['passed_count']==sum(report['physical_gate'].values())
    assert report['eligible_for_new_seed']==all(report['physical_gate'].values())
    assert not report['eligible_for_new_seed'] and report['physical_runs']==0
    checks={}
    seals={}
    for mode in ('off','on'):
        seal=load(OUT/mode/'seal.json')
        assert seal['source_sha']==report['source'] and not seal['gt_parsed']
        assert all(sha(OUT/mode/p)==h for p,h in seal['files'].items())
        assert all(sha(RAW/p)==h for p,h in seal['inputs'].items())
        pred=load(OUT/mode/'prediction.json')
        decisions=pred['decisions']
        reasons=dict(Counter(d['reason'] for d in decisions))
        assert len(decisions)==891 and reasons==report['modes'][mode]['motion_reasons']
        count=sum(bool(d.get('inserted')) for d in decisions)
        assert count==len(pred['ledger'])==891-reasons['gmapping_motion_gate']
        rejected=[d for d in decisions if d['status']=='rejected']
        assert all(d['inserted'] and not d['resampled'] and not d['sensor_weight_update'] for d in rejected)
        front,graph=[report['modes'][mode][k] for k in ('frontend','graph')]
        assert all(front[k]==v for k,v in graph.items())
        checks[mode]=dict(frames=len(decisions),insertions=count,reasons=reasons,
            grid_rejected=pred['grid']['rejected'],rejected_insertions=len(rejected),
            rejected_resamples=0,rejected_weight_updates=0,frontend_graph_metrics_identical=True)
        seals[mode]=seal
    assert (OUT/'off/traces.jsonl').read_bytes()==(RAW/'own-controller.jsonl').read_bytes()
    result=dict(source_sha=report['source'],execution_freeze_unchanged=True,
        tests_passed_before_execution=freeze['tests_passed'],
        test_files=['tests/test_self_pulse_rotation.py','tests/test_self_pulse_odom.py','tests/test_active_wall_nav2.py'],
        preserved_untracked=USER_FILES,checks=checks,seals=seals,
        result_hashes={str(p.relative_to(EXP)):sha(p) for p in
            [EXP/'results/calibration.json',EXP/'results/replay.json',EXP/'figures/replay-errors.png',EXP/'code/verify.py']},
        physical_runs=0,gate_passed=report['passed_count'],gate_total=7)
    dump(EXP/'results/verification.json',result)
    print('PASS: sealed predictions, source/input hashes, 891-frame golden, stage counts, no rejected resampling, preserved user files; gate 5/7, physics 0')


if __name__=='__main__':main()
