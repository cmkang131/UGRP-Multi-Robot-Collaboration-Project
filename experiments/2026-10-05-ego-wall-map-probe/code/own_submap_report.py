"""Verify and publish frozen graph artifacts; no loop matching or simulation."""
import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import sys

import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import own_submap_replay as replay
from harness.self_pose_graph import between,compose,rebuild


def verify(source,name):
    d=source/name
    s=replay.guard.load(d/'summary.json')
    for r in s['sources']:
        assert replay.base.sha(r['path'])==r['sha256']
    for f,h in s['prediction_hashes'].items():
        assert replay.base.sha(d/f)==h
    old=replay.base.read_rows(replay.SOURCE/name/'guarded-ledger.jsonl')
    rows=replay.base.read_rows(d/'graph-ledger.jsonl')
    assert len(old)==len(rows)==s['inserted_scans']
    for a,b in zip(old,rows):
        assert {k:v for k,v in a.items() if k!='pose'}=={k:v for k,v in b.items() if k not in ('pose','robot_id')}
    assert rebuild(name[-2:],rows).export()['cells']==replay.guard.load(d/'graph-grid.json')['cells']
    origpath=replay.base.read_rows(replay.SOURCE/name/'rbpf100-fixed-poses.jsonl')
    path=replay.base.read_rows(d/'graph-poses.jsonl')
    times=np.array([r['t'] for r in old])
    for a,b in zip(origpath,path):
        idx=np.searchsorted(times,a['t'],side='right')-1
        predicted=compose(rows[idx]['pose'],between(old[idx]['pose'],a['pose'])) if idx>=0 and s['changed'] else a['pose']
        np.testing.assert_allclose(predicted,b['pose'],atol=1e-12,rtol=0)
    assert len(path)==len(origpath)==s['path_frame_count']
    submaps=replay.guard.load(d/'submaps.json')
    loops=replay.base.read_rows(d/'loops.jsonl')
    constraints=replay.guard.load(d/'constraints.json')
    assert dict(Counter(e['reason'] for e in loops))==s['loop_counts']
    accepted=[e for e in loops if e['accepted']]
    assert len(accepted)==sum(e['kind']=='loop' for e in constraints)
    np.testing.assert_array_equal(submaps[0]['global_pose'],[0.,0.,0.])
    for e in accepted:
        assert e['frame_id'] not in submaps[e['submap']]['members']
        assert e['mode_gap']>=.02 and e['overlap']>=.60 and e['hessian_ratio']>=.03 and e['residual_m']<=.15
        assert np.linalg.eigvalsh(e['covariance']).min()>0
    if s['optimization']['accepted']:
        assert s['optimization']['final_cost']<=s['optimization']['initial_cost']
    scene=Path(next(r['path'] for r in s['sources'] if r['path'].endswith('inputs/static_map.json')))
    walls=[w for w in replay.guard.load(scene)['obstacles'] if w.get('kind')=='wall']
    rects=np.array([w['center_m']+w['half_extents_m'] for w in walls])
    v=replay.guard.load(replay.guard.DIAG/name/'wall_samples.json')
    samples=np.array(v['xy'])
    masks={k:np.array(v[k]) for k in s['visibility_counts']}
    for c in s['metrics']:
        grid=replay.base.OdomGrid(name[-2:])
        grid.cells={(x,y):xv for x,y,xv in replay.guard.load(d/f'{c}-grid.json')['cells']}
        assert replay.guard.diag.measure(grid,s['origin_eval_only'],rects,samples,masks)==s['metrics'][c]['final']
    m=s['metrics']
    assert replay.graph_criteria(m['off'],m['rbpf100_guard'],m['graph'],s['accepted_invalid_endpoints'],s['golden'])==s['checks']
    return {'case':name,'source_prediction_hashes':True,'same_guarded_local_evidence':True,'rebuilt_grid_exact':True,
            'full_path_transform_exact':True,'own_nonmember_constraints':True,'accepted_covariance_positive':True,
            'gauge_fixed':True,'all_four_map_scores_exact':True,'fixed_criteria_exact':True}


def tables(summaries):
    out=['### 22.4 고정 소스 6건 재생 결과','',
         '각 지도 칸은 **precision % / 전체 recall % / 가시 recall % / 벽 RMSE m**. GT+guard는 평가 전용이며 보정 성능에 합산하지 않는다.','',
         '| 녹화 | off | RBPF100+guard | RBPF100+guard+graph | GT+guard |','|---|---|---|---|---|']
    for n,s in summaries.items():
        vals=[]
        for c in ('off','rbpf100_guard','graph','gt_guard'):
            q=s['metrics'][c]['final']
            vals.append(f'{100*q["precision_015"]:.1f} / {100*q["wall_coverage"]:.1f} / {100*q["recall_visible"]:.1f} / {q["wall_error_rmse_m"]:.3f}')
        out.append('| '+n+' | '+' | '.join(vals)+' |')
    out+=['','위치 칸은 **종료 / median / P95 / 경로 RMSE m**. 전체 프레임 분포(P90/max 포함)는 JSON/원본 경로 오차 파일에 보존한다.','',
          '| 녹화 | off | RBPF100+guard | +graph | 전체 기준 |','|---|---|---|---|---|']
    for n,s in summaries.items():
        vals=[]
        for c in ('off','rbpf100_guard','graph'):
            q=s['metrics'][c];p=q['path_position_error']
            vals.append(f'{q["end_position_error_m"]:.3f} / {p["median_m"]:.3f} / {p["p95_m"]:.3f} / {p["rmse_m"]:.3f}')
        out.append('| '+n+' | '+' | '.join(vals)+' | '+('통과' if s['success'] else '실패')+' |')
    out+=['','### 22.5 루프 후보와 최적화','',
          '전체 scan–submap 쌍을 분모로 사전 제외와 실제 정합 거부를 구분한다. 루프 수락은 GT로 확인한 참 루프 수가 아니다.','',
          '| 녹화 | submap / scan | 회원/시간/거리 제외 | 정합 시도 | 수락 / 정합 거부 | 목적값 전→후 | 최대 XY 보정 m |','|---|---|---|---|---|---|---|']
    skip=('member_scan','temporal_separation','outside_candidate_radius')
    for n,s in summaries.items():
        counts=s['loop_counts'];a=counts.get('accepted',0);tries=sum(v for k,v in counts.items() if k not in skip)
        opt=s['optimization'];cost=f'{opt["initial_cost"]:.2f}→{opt["final_cost"]:.2f}' if 'initial_cost' in opt else opt['reason']
        out.append(f'| {n} | {s["submaps"]} / {s["inserted_scans"]} | '+ '/'.join(str(counts.get(k,0)) for k in skip)+
                   f' | {tries} | {a} / {tries-a} | {cost} | {opt.get("max_translation_change_m",0):.3f} |')
    reasons=sorted(set(k for s in summaries.values() for k in s['loop_counts'])-set(skip)-{'accepted'})
    out+=['','| 녹화 | '+' | '.join(reasons)+' |','|---|'+'---|'*len(reasons)]
    for n,s in summaries.items():
        out.append('| '+n+' | '+' | '.join(str(s['loop_counts'].get(k,0)) for k in reasons)+' |')
    out+=['','| 녹화 | 미달한 고정 기준 |','|---|---|']
    for n,s in summaries.items():
        out.append('| '+n+' | '+(', '.join(k for k,v in s['checks'].items() if not v) or '없음')+' |')
    return '\n'.join(out)+'\n'


def figures(source,out,summaries):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    fig,axes=plt.subplots(3,3,figsize=(12,10),constrained_layout=True)
    for i,seed in enumerate((911,912,913)):
        n=f's{seed}-r2';s=summaries[n]
        scene=Path(next(r['path'] for r in s['sources'] if r['path'].endswith('inputs/static_map.json')))
        walls=[w for w in replay.guard.load(scene)['obstacles'] if w.get('kind')=='wall']
        for j,c in enumerate(('rbpf100_guard','graph','gt_guard')):
            ax=axes[i,j]
            for w in walls:
                x,y=w['center_m'];hx,hy=w['half_extents_m']
                ax.add_patch(Rectangle((x-hx,y-hy),2*hx,2*hy,color='gray',alpha=.3))
            grid=replay.guard.load(source/n/f'{c}-grid.json')
            xy=np.array([[(x+.5)*.1,(y+.5)*.1] for x,y,v in grid['cells'] if v>0])
            xy=replay.base.transform(xy,s['origin_eval_only'])
            ax.scatter(xy[:,0],xy[:,1],s=5,c='#a33a22')
            q=s['metrics'][c]['final']
            ax.set(title=f'{n} {c}\nP {q["precision_015"]:.1%}, Rvis {q["recall_visible"]:.1%}, RMSE {q["wall_error_rmse_m"]:.3f}m',
                   aspect='equal',xlim=(-2.8,5.8),ylim=(-3.8,3.2))
            ax.grid(alpha=.2)
    fig.suptitle('Own submap graph: pre-v7 / pre-camera-v3 recordings, GT only for evaluation')
    fig.savefig(out/'r2-submap-graph-maps.png',dpi=115)
    plt.close(fig)
    fig,axes=plt.subplots(3,2,figsize=(11,8),constrained_layout=True)
    for ax,(n,s) in zip(axes.ravel(),summaries.items()):
        for c,label in [('off','DR off'),('rbpf100_guard','RBPF100 + guard'),('graph','+ graph')]:
            rows=replay.base.read_rows(source/n/f'{c}-path-errors.jsonl')
            ax.plot([r['t'] for r in rows],[r['xy_error_m'] for r in rows],label=label,linewidth=1)
        ax.set(title=n,xlabel='saved time (s)',ylabel='XY error (m)')
        ax.grid(alpha=.2)
    axes[0,0].legend(fontsize=8)
    fig.suptitle('Saved online path with latest scan local/global correction; GT scoring only')
    fig.savefig(out/'submap-path-errors.png',dpi=115)
    plt.close(fig)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    verified=[verify(args.source,n) for n in replay.guard.CASES]
    summaries={n:replay.guard.load(args.source/n/'summary.json') for n in replay.guard.CASES}
    args.output.mkdir(parents=True,exist_ok=False)
    for n in summaries:
        d=args.output/n;d.mkdir()
        shutil.copyfile(args.source/n/'summary.json',d/'summary.json')
        loops=replay.base.read_rows(args.source/n/'loops.jsonl')
        replay.write_rows(d/'matching-decisions.jsonl',[r for r in loops if r['reason'] not in ('member_scan','temporal_separation','outside_candidate_radius')])
        submaps=replay.guard.load(args.source/n/'submaps.json')
        replay.base.dump(d/'submap-membership.json',[{k:v for k,v in s.items() if k!='cells'} for s in submaps])
        shutil.copyfile(args.source/n/'constraints.json',d/'constraints.json')
    for f in ('cohort.json','development_fixed.json','environment.json'):
        shutil.copyfile(args.source/f,args.output/f)
    replay.base.dump(args.output/'verification.json',verified)
    (args.output/'tables.md').write_text(tables(summaries))
    figures(args.source,args.output,summaries)
    sources=replay.guard.load(replay.base.ROOT/'outputs/own-submap-v1-references/sources.json')
    old=replay.guard.load(replay.base.ROOT/'outputs/wall-projection-guard-references/references.json')
    sources+=old['files']
    replay.base.dump(args.output/'references.json',{'cartographer_commit':'877157a0d91788a7700221d87232d412cb3c1ef4',
        'files':sources,'documentation':['https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html',
        'https://google-cartographer-ros.readthedocs.io/en/latest/algo_walkthrough.html#global-slam']})
    local=[p for p in sorted(args.source.rglob('*')) if p.is_file()]+[args.source.with_suffix('.log')]
    committed=[p for p in sorted(args.output.rglob('*')) if p.is_file()]
    replay.base.dump(args.output/'manifest.json',{'replay_source_sha':next(iter(summaries.values()))['source_sha'],
        'local_only':[{'path':str(p.resolve()),'bytes':p.stat().st_size,'sha256':replay.base.sha(p)} for p in local],
        'git_artifacts':[{'path':str(p.relative_to(args.output)),'bytes':p.stat().st_size,'sha256':replay.base.sha(p)} for p in committed]})
    print('Verified 6 own lineages, 24 final map scores, full path transforms, loop gates/gauge, hashes and criteria.')


if __name__=='__main__':
    main()
