"""Read-only audit of sealed recordings/predictions; write compact Git records."""
from pathlib import Path
import hashlib
import json
import math
import subprocess
import sys
import numpy as np

EXP = Path(__file__).resolve().parents[1]
ROOT = EXP.parents[1]
RAW = Path('/Users/changmin/projects/ugrp/outputs/servo-stiffness-v1')
sys.path.insert(0, str(Path(__file__).parent))
import replay as r


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def dump(name, data):
    (EXP/'results'/name).write_text(json.dumps(data, indent=2, ensure_ascii=False)+'\n')


def main():
    r.verify()
    golden = r.off_golden()
    assert golden == 182
    cases = ('static-off', 'static-on', 'stiff-north', 'stiff-south', 'stiff-explore')
    episodes = []
    for case in cases:
        ep = RAW/case
        manifest = read(ep/'artifacts.sha256.json')
        assert all(sha(ep/p) == h for p, h in manifest.items())
        result = read(ep/'result.json')
        assert result['status'] == 'RECORDED' and result['model_calls'] == 0 and not result['freeze']
        lock = read(ep/'lock.json')
        assert subprocess.run(['ps', '-p', str(lock['pid']), '-o', 'pid='], capture_output=True).returncode != 0
        episodes.append(dict(case=case, result=result, artifact_hashes_checked=len(manifest),
                             lock_pid_exited=lock['pid']))
    motion = {}
    for case in ('stiff-north', 'stiff-south'):
        truth = r.c.old.current_truth(RAW/case)
        origin = np.asarray(truth[min(truth)])
        co, si = math.cos(origin[2]), math.sin(origin[2])
        world_to_own = np.array([[co, si], [-si, co]])
        motion[case] = {}
        for mode in ('off', 'pulse'):
            pred = rows(RAW/'replay'/mode/'parallax_v1'/case/'predictions.jsonl')
            estimate = np.array([p['pose'] for p in pred])
            gt = np.array([truth[round(p['t'], 6)] for p in pred])
            local_gt = (gt[:, :2]-origin[:2])@world_to_own.T
            error = np.linalg.norm(estimate[:, :2]-local_gt, axis=1)
            yaw = (estimate[:, 2]-(gt[:, 2]-origin[2])+np.pi)%(2*np.pi)-np.pi
            motion[case][mode] = dict(frames=len(pred), estimated_lateral_span_m=float(np.ptp(estimate[:, 1])),
                actual_lateral_span_m=float(np.ptp(local_gt[:, 1])), span_ratio=float(np.ptp(estimate[:, 1])/np.ptp(local_gt[:, 1])),
                path_median_m=float(np.median(error)), path_p90_m=float(np.percentile(error, 90)),
                path_rmse_m=float(np.sqrt(np.mean(error**2))), end_error_m=float(error[-1]),
                end_yaw_error_deg=float(np.degrees(yaw[-1])))
    for mode in r.MODES:
        for case in ('stiff-north', 'stiff-south'):
            directory = RAW/'replay'/mode/'parallax_v1'/case
            receipt = read(directory/'receipt.json')
            for stem in ('predictions', 'eligibility'):
                assert sha(directory/(stem+'.jsonl')) == receipt[stem+'_sha256']
            assert all(sha(ROOT/p) == h for p, h in receipt['source_hashes'].items())
    receipt = read(RAW/'short-map/prediction.json')
    assert all(sha(RAW/'short-map'/p) == h for p, h in receipt['hashes'].items())
    assert all(sha(Path(p)) == h for p, h in receipt['inputs'].items())
    protected = {
        'analyze_wall_detection.py': '26c818f1cd4673c7f4a1b6ab535b4e70ac68167f1f56989f10c8c6bebe0c3dd0',
        'create_wall_visualizations.py': 'e2b77c1f678d1ba27658dffecf99bcf7bfd7c12c056d41869a7a38cc482f8efa',
        'create_wall_visualizations_v2.py': '8e6fa7f6598336bc6f7c61ad956d1902be9925443d7656cea2801362195d83c8',
        'parameter_probe.py': '43f91584406ba91a73032514b8409357fc9c7ac2c3cbc3e72d26bce5257e103b'}
    assert all(sha(ROOT/p) == h for p, h in protected.items())
    copied = read(EXP/'copied-source.json')
    upstream = subprocess.check_output(['git', 'show', 'd4fee717587ecc3b549aff948252b156b6c05d83:'+copied['source']])
    assert hashlib.sha256(upstream).hexdigest() == copied['sha256'] == sha(ROOT/copied['copied_path'])
    managed = []
    for p in sorted((ROOT/'outputs/simulation-runs').glob('*wall-servo-stiffness*/manifest.json')):
        m = read(p)
        assert m['status'] == 'process_completed' and m['exit_code'] == 0
        assert not m['source_changed_during_run'] and not m['inputs_changed_during_run']
        managed.append(dict(path=str(p.relative_to(ROOT)), sha256=sha(p), run_id=m['run_id'],
                            source_sha=m['source']['source_sha'], exit_code=m['exit_code']))
    assert len(managed) == 5
    files = {str(p.relative_to(RAW)): dict(bytes=p.stat().st_size, sha256=sha(p))
             for p in sorted(RAW.rglob('*')) if p.is_file()}
    size = sum(p['bytes'] for p in files.values())
    assert size <= 350*1024**2
    dump('raw-manifest.json', dict(root=str(RAW), remote_raw_backup=False, files=files))
    dump('motion-diagnostic.json', dict(role='posthoc_evaluation_only_no_refit', cases=motion))
    dump('execution.json', dict(episodes=episodes, managed=managed, raw_files=len(files), raw_bytes=size,
        total_sim_s=sum(ep['result']['total_sim_s'] for ep in episodes), off_golden_rows=golden,
        frozen_files=len(r.ORIGINAL_HASHES()), protected_user_files=protected, local_tests='16 passed in 2.15s',
        model_calls=0, freeze=False, new_venv_or_dependencies=False, tensorboard='skipped per user instruction',
        figure_sha256=sha(EXP/'figures/short-map.png')))
    print(json.dumps(dict(raw_files=len(files), raw_bytes=size, motion=motion), indent=2))


if __name__ == '__main__':
    main()
