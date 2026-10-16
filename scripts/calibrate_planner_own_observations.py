"""Read-only r80 calibration. Referee data stays in this offline evaluator.

Decision ticks are the sampling units, not repeated camera frames. A last-seen
beam is a remembered perception, never an inferred absence. Geometric error
is a proxy for synthetic fact corruption, NOT a measured categorical error.
"""
import argparse
import bisect
import collections
import hashlib
import json
import math
from pathlib import Path
import subprocess


def read(path):
    if path.exists():
        return path.read_bytes()
    return subprocess.check_output(['zstd', '-qdc', str(path)+'.zst'])


def calibrate(root):
    samples, manifest = [], {}
    def load(path, lines=False):
        data = read(path)
        manifest[str(path)] = hashlib.sha256(data).hexdigest()
        return [json.loads(x) for x in data.splitlines()] if lines else json.loads(data)
    for run in sorted(root.glob('e2e18-*-r80')):
        raw = run/'raw'
        requests = load(raw/'llm/requests.json')
        setup = load(raw/'eval_only/setup.json')
        truth = load(raw/'eval_only/referee_truth.jsonl', True)
        truth_times = [r['t'] for r in truth]
        streams = {}
        for rid in ('r1', 'r2', 'r3'):
            rows = load(raw/f'robots/{rid}/ownmap.jsonl', True)
            streams[rid] = ([r['t'] for r in rows], rows)
        for req in requests:
            ctx = json.loads(req['user']); rid = req['robot']; now = req['sim_s']
            times, rows = streams[rid]; end = bisect.bisect_right(times, now)
            seen = [r for r in rows[:end] if r.get('own_beam')]
            sample = dict(run=run.name, request_id=req['request_id'], robot=rid,
                          sim_s=now, available=bool(seen),
                          request_has_observed_facts=bool(ctx.get('observed_facts')),
                          allowed_envelope={k:ctx.get(k) for k in
                              ('own_rgb','own_map_summary','own_command_history')})
            if seen:
                row=seen[-1]; beam=row['own_beam']; at=beam['rgb']['t_sim']
                sample.update(age_s=now-at, stale=now-at>30,
                    observation=dict(entity={'kind':'long_beam','id':'beam_1'},
                        observed_at=at, rgb=beam['rgb'], pose_own_m=beam['pose_own_m'],
                        observer_pose_own_m=row['pose_own_m'],
                        source='own RGB + issued commands', remembered=at<now))
                # The center is explicitly inferred in e2e_live_mapping._receive
                # from near end + known .60 m length. Transform only for scoring.
                ti=bisect.bisect_right(truth_times, at)-1
                if ti>=0:
                    item=truth[ti]['items']['beam_1']; sx,sy,_,yaw=setup['spawns'][rid]
                    x,y=beam['pose_own_m'][:2]
                    wx=sx+math.cos(yaw)*x-math.sin(yaw)*y
                    wy=sy+math.sin(yaw)*x+math.cos(yaw)*y
                    error=math.hypot(wx-item['x'],wy-item['y'])
                    sample['evaluation_only']=dict(center_error_m=error,
                        large_error=error>.30, referee_t=truth[ti]['t'])
            samples.append(sample)
    counts=collections.Counter('absent' if not s['available'] else
        ('stale' if s['stale'] else 'fresh')+'_'+
        ('large_error' if s.get('evaluation_only',{}).get('large_error') else
         'small_error' if 'evaluation_only' in s else 'unscored') for s in samples)
    return dict(schema='planner.r80.calibration.v1', unit='robot decision request',
        runs=len({s['run'] for s in samples}), N=len(samples), counts=dict(counts),
        geometric_threshold_m=.30, threshold_basis='half the fixed .60 m beam length; gross localization error, not grasp tolerance',
        limitation='Geometric localization error cannot identify categorical task truth; mapping it to synthetic fact corruption is a declared stress-test assumption. r80 only contains one beam task, not eight task domains.',
        direct_fact_requests=sum(s['request_has_observed_facts'] for s in samples),
        sources_sha256=manifest, samples=samples)


if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--root',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True); a=ap.parse_args()
    result=calibrate(a.root); a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('samples','sources_sha256')},indent=2))
