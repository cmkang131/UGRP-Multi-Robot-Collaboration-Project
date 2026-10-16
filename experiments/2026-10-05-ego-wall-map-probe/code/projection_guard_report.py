"""Post-process and verify fixed-pose guard replay artifacts, no new inference."""
import argparse
import json
from pathlib import Path
import shutil
import sys

import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import projection_guard_replay as replay
from map_oracle_report import points


def verify_case(source, name):
    d=source/name
    s=replay.load(d/'summary.json')
    for f in s['sources']:
        assert replay.base.sha(f['path']) == f['sha256']
    for f,h in s['prediction_hashes'].items():
        assert replay.base.sha(d/f) == h
    rows=replay.base.read_rows(d/'guarded-ledger.jsonl')
    rebuilt=replay.rebuild(name[-2:],rows)
    assert rebuilt.export()['cells'] == replay.load(d/'rbpf100_guard-grid.json')['cells']
    original=replay.base.read_rows(replay.RBPF/name/'map_ledger.jsonl')
    by_frame={r['frame_id']:r for r in original}
    assert all(r['pose']==by_frame[r['frame_id']]['pose'] for r in rows)
    assert replay.base.sha(d/'rbpf100-fixed-poses.jsonl') == replay.base.sha(replay.RBPF/name/'poses.jsonl')
    log=replay.base.read_rows(d/'projection-decisions.jsonl')
    assert sum(l['accepted_segments'] for l in log) == sum(len(r['segments']) for r in rows)
    assert all(all(v is not None and v>0 for v in e['optical_z_m']+e['ray_t'])
               for l in log for e in l['segments'] if e['accepted'])
    scene=Path(next(f['path'] for f in s['sources'] if f['path'].endswith('scene.xml'))).parent
    walls=[w for w in replay.load(scene/'inputs/static_map.json')['obstacles'] if w.get('kind')=='wall']
    rects=np.array([w['center_m']+w['half_extents_m'] for w in walls])
    visibility=replay.load(replay.DIAG/name/'wall_samples.json')
    samples=np.array(visibility['xy'])
    masks={k:np.array(visibility[k]) for k in s['visibility_counts']}
    origin=np.array(s['origin_eval_only'])
    for c in s['metrics']:
        g=replay.base.OdomGrid(name[-2:])
        g.cells={(x,y):v for x,y,v in replay.load(d/f'{c}-grid.json')['cells']}
        assert replay.diag.measure(g,origin,rects,samples,masks) == s['metrics'][c]
    false=replay.base.read_rows(d/'guard-false-cells.jsonl')
    assert len(false)==s['attribution']['false_cells']
    assert abs(sum(s['attribution']['cell_equivalents'].values())-len(false))<1e-8
    assert sum(r['behind_camera_share'] for r in false)==0.
    before=s['metrics']['rbpf100']
    after=s['metrics']['rbpf100_guard']
    occupied=[{(x,y) for x,y,v in replay.load(d/f'{c}-grid.json')['cells'] if v>0} for c in ('rbpf100','rbpf100_guard')]
    removed=occupied[0]-occupied[1]
    removed_xy=replay.base.transform((np.array(sorted(removed)).reshape(-1,2)+.5)*.1,origin)
    true_removed=int((replay.base.boundary_dist(removed_xy,rects)<=.15).sum())
    assert replay.criterion(before,after,behind_false_cells=0,invalid_endpoints=0,golden=s['golden'],pose_fixed=True)==s['checks']
    return {'case':name,'source_and_prediction_hashes':True,'lineage_grid_exact':True,'all_four_quality_scores_exact':True,
            'accepted_endpoints_positive':True,'fixed_pose_bytes':True,'false_cell_mass_conserved':True,
            'removed_true_cells':true_removed,'removed_false_cells':len(removed)-true_removed,
            'new_occupied_cells':len(occupied[1]-occupied[0]),'criterion_results_exact':True}


def tables(summaries,verified):
    out=['### 21.3 고정 자세 재생 결과', '',
         '각 칸: **precision % / 전체 recall % / 가시 recall % / 벽 RMSE m**. off는 기존 DR 지도다. GT는 guard를 통과한 **동일 RBPF100 원장**의 자세만 평가용 GT로 치환했다.', '',
         '| 녹화 | off | RBPF100 | RBPF100+guard (자세 고정) | GT 자세+guard (평가) |', '|---|---|---|---|---|']
    for n,s in summaries.items():
        vals=[]
        for c in ('off','rbpf100','rbpf100_guard','gt_guard'):
            q=s['metrics'][c]
            vals.append(f'{100*q["precision_015"]:.1f} / {100*q["wall_coverage"]:.1f} / {100*q["recall_visible"]:.1f} / {q["wall_error_rmse_m"]:.3f}')
        out.append('| '+n+' | '+' | '.join(vals)+' |')
    out+=['','| 녹화 | 입력→수락 선분 | 입력→삽입 프레임 | 뒤 교점 거짓 셀 기여 전→후 | Δprecision %p | Δ가시 recall %p | 전체 기준 |', '|---|---|---|---|---|---|---|']
    for n,s in summaries.items():
        g=s['guard'];a=s['metrics']['rbpf100'];b=s['metrics']['rbpf100_guard']
        old=replay.load(replay.DIAG/n/'summary.json')['conditions']['rbpf100']['attribution']['behind_camera_cell_equivalents']
        out.append(f'| {n} | {g["input_segments"]}→{g["inserted_segments"]} | {g["input_frames"]}→{g["inserted_frames"]} | {old:.3f}→0 | {100*(b["precision_015"]-a["precision_015"]):+.3f} | {100*(b["recall_visible"]-a["recall_visible"]):+.3f} | '+('통과' if s['success'] else '실패: precision 하락')+' |')
    out+=['','**전체 4/6, 개발 1/2, 확인 재생 3/4, r2 3/3 통과.** 가시 recall 감소와 수락된 비양수 깊이/광선 교점은 6건 모두 0이다. 전체 성공 기준(6/6)은 미달했으며 기본 off를 유지한다.', '',
          '| 녹화 | 제거된 참 셀 | 제거된 거짓 셀 | 새 점유 셀 |', '|---|---|---|---|']
    for v in verified:
        out.append(f'| {v["case"]} | {v["removed_true_cells"]} | {v["removed_false_cells"]} | {v["new_occupied_cells"]} |')
    out+=['','### 21.4 위치 오차와 남은 지도 오류 (합산하지 않음)', '',
          '위치 값은 기존 RBPF100 값을 그대로 보존한다. guard가 개선한 위치 성능으로 주장하지 않는다.', '',
          '| 녹화 | 종료 XY m | 경로 median m | 경로 P95 m | 경로 RMSE m |', '|---|---|---|---|---|']
    for n,s in summaries.items():
        p=s['unchanged_rbpf_pose_metrics'];d=p['path_position_error']
        out.append(f'| {n} | {p["end_position_error_m"]:.3f} | {d["median_m"]:.3f} | {d["p95_m"]:.3f} | {d["rmse_m"]:.3f} |')
    out+=['','guard 후 최종 거짓 셀의 운영적 증거 분해(§20 규칙 유지), 단위 %:', '',
          '| 녹화 | 거짓 셀 | 거리/투영 | 자세 | 비벽 | 칸 경계 | 판별 불가 |', '|---|---|---|---|---|---|---|']
    for n,s in summaries.items():
        a=s['attribution']
        out.append(f'| {n} | {a["false_cells"]} | '+' | '.join(f'{100*a["fractions"][k]:.1f}' for k in replay.diag.CATEGORIES)+' |')
    return '\n'.join(out)+'\n'


def figure(source,out,summaries):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    fig,axes=plt.subplots(3,3,figsize=(12,10),constrained_layout=True)
    for i,seed in enumerate((911,912,913)):
        n=f's{seed}-r2';s=summaries[n]
        scene=Path(next(f['path'] for f in s['sources'] if f['path'].endswith('scene.xml'))).parent
        walls=[w for w in replay.load(scene/'inputs/static_map.json')['obstacles'] if w.get('kind')=='wall']
        for j,c in enumerate(('rbpf100','rbpf100_guard','gt_guard')):
            ax=axes[i,j]
            for w in walls:
                x,y=w['center_m'];hx,hy=w['half_extents_m']
                ax.add_patch(Rectangle((x-hx,y-hy),2*hx,2*hy,color='gray',alpha=.3))
            xy=replay.base.transform(points(replay.load(source/n/f'{c}-grid.json')),s['origin_eval_only'])
            ax.scatter(xy[:,0],xy[:,1],s=5,c='#b54232')
            q=s['metrics'][c]
            ax.set(title=f'{n} {c}\nP {q["precision_015"]:.1%}, Rvis {q["recall_visible"]:.1%}, RMSE {q["wall_error_rmse_m"]:.3f}m',
                   aspect='equal',xlim=(-2.8,5.8),ylim=(-3.8,3.2))
            ax.grid(alpha=.2)
    fig.suptitle('Positive depth guard: fixed RBPF100 pose lineage / GT evaluation only (world metres)')
    fig.savefig(out/'r2-positive-depth-maps.png',dpi=115)
    plt.close(fig)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    verified=[verify_case(args.source,n) for n in replay.CASES]
    summaries={n:replay.load(args.source/n/'summary.json') for n in replay.CASES}
    args.output.mkdir(parents=True,exist_ok=False)
    for n in replay.CASES:
        dest=args.output/n
        dest.mkdir()
        for f in ('summary.json','projection-decisions.jsonl','guard-false-cells.jsonl'):
            shutil.copyfile(args.source/n/f,dest/f)
    for f in ('development_fixed.json','cohort.json'):
        shutil.copyfile(args.source/f,args.output/f)
    refs=replay.ROOT/'outputs/wall-projection-guard-references/references.json'
    shutil.copyfile(refs,args.output/'references.json')
    replay.base.dump(args.output/'verification.json',verified)
    (args.output/'tables.md').write_text(tables(summaries,verified))
    figure(args.source,args.output,summaries)
    files=[p for p in sorted(args.source.rglob('*')) if p.is_file()]+[args.source.with_suffix('.log')]
    references=replay.load(refs)
    files += [Path(r['path']) for r in references['files']]
    committed=[p for p in sorted(args.output.rglob('*')) if p.is_file()]
    replay.base.dump(args.output/'manifest.json',{'replay_source_sha':summaries[replay.CASES[0]]['source_sha'],
        'local_only':[{'path':str(p.resolve()),'bytes':p.stat().st_size,'sha256':replay.base.sha(p)} for p in files],
        'git_artifacts':[{'path':str(p.relative_to(args.output)),'bytes':p.stat().st_size,'sha256':replay.base.sha(p)} for p in committed]})
    print('6 cases: source/prediction hashes, 24 map scores, exact guarded lineage, fixed poses and zero behind-camera evidence verified.')


if __name__=='__main__':
    main()
