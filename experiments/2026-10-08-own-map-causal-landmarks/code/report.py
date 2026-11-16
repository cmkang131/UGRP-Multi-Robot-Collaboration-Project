"""Report already sealed predictions and scores, never rerun or tune filters."""
from replay import *
from collections import Counter
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


def main():
    prepared=load(RAW/'prepared.json')
    results={mode:load(EXP/f'results/utility-{mode}.json') for mode in ('off','on')}
    historical=load(OLD/'results/utility.json')
    all_rows=[dict(r,mode='egomap41-invalid-leak') for r in historical['trials']]
    all_rows += [r for v in results.values() for r in v['trials']]
    inputs=load(RAW/'own-inputs.json')
    measurements=load(RAW/'own-measurements.json')
    prefix=[]
    for cut in prepared['cuts']:
        maps=results['on']['maps'];trial=cut['trial']
        mem=load(RAW/f'maps/own-{trial}-landmarks.json')
        sources=[f['source'] for f in mem['edges']+mem['doors']]
        assert all(before(s['t'],cut['cut_t']) for s in sources)
        assert mem['world_alignment'] is None
        saved=snapshot_before(rows(EP/'online-maps.jsonl'),cut['cut_t'],robot_id='r3')
        assert saved['grid']==load(snapshot_path('own',trial))
        ledger=load(RAW/f'maps/own-{trial}-ledger.json')
        assert ledger==saved['ledger'] and all(before(r['t'],cut['cut_t']) for r in ledger)
        prefix.append(dict(trial=trial,cut_t=cut['cut_t'],snapshot_t=cut['snapshot_t'],scans=cut['scans'],
            **maps[f'own-{trial}'],floor_line_records=len(mem['edges']),door_records=len(mem['doors']),
            landmark_frames=len(set(s['frame_id'] for s in sources)),
            last_landmark_t=max((s['t'] for s in sources),default=None),goal_observed=cut['own_goal'] is not None))
    diagnostic=[]
    for mode in ('off','on'):
        detail=load(RAW/f'evaluation-details-{mode}.json')
        for t in results[mode]['trials']:
            name=f"{t['condition']}-{mode}-{t['trial']}";pred=load(RAW/f'{name}.json');rr=pred['rows']
            assert all(after(r['t'],pred['cut_t']) for r in rr)
            d=detail[f"{t['condition']}-{t['trial']}"]
            yaw_ok=np.array([r['circular_yaw_std_rad']<=math.radians(5) for r in rr])
            true_ok=(np.array(d['xy_m'])<=.25)&(np.array(d['yaw_deg'])<=10)
            diagnostic.append(dict(condition=t['condition'],mode=mode,trial=t['trial'],
                resolved_frames=sum(r['resolved'] for r in rr),
                stable_resolved_frames=sum(r['stable_resolved'] for r in rr),
                yaw_std_pass_frames=int(yaw_ok.sum()),
                xy_support_veto_when_yaw_pass=sum(bool(ok and not r['resolved']) for ok,r in zip(yaw_ok,rr)),
                true_accuracy_pass_frames=int(true_ok.sum()),
                final_yaw_std_deg=rr[-1]['circular_yaw_std_rad']*180/math.pi,
                resampling_injections=sum(r['sensor'].get('injected',0) for r in rr if r['sensor']),
                landmark_update_frames=sum(r['updated'] and r['landmark_count']>0 for r in rr),
                plan_status=None if pred['plan'] is None else pred['plan']['status'],
                plan_pose=None if pred['plan'] is None else pred['plan']['pose']))
    summary=dict(preregistration='9c5ee9c3',prediction_source=prepared['source_sha'],
        criteria='egomap41 unchanged',historical_comparison_valid=False,
        historical_leakage='full 64-scan final map and future B goal; invalid comparator',
        prefix=prefix,trials=all_rows,gates={m:r['gates'] for m,r in results.items()},
        gate_pass={m:r['offline_proxy_gate'] for m,r in results.items()},diagnosis=diagnostic,
        global_feature_counts=dict(frames=len(inputs),feature_frames=sum(bool(r['features']) for r in inputs),
            types=dict(Counter(f['kind'] for r in inputs for f in r['features']))),
        physics=0,gt_alignment_in_prediction=False,retuning=0,physical_goal_success='unmeasured')
    dump(EXP/'results/comparison.json',summary)
    text='''\n## 결과 — 누설 제거 후 고정 기준 판정\n\n사전등록 **9c5ee9c3** → 구현/재생 **b68b94b7**. causal off/on×자기/정적×3,
12예측을 각1회 봉인 후 별도2조건 채점. 결과 후 설정/문턱 변경0, 물리/렌더/모델/잠금0.
과거 egomap41 자기 최종지도는 **미래 관측 누설로 비교 무효**이며 진척 기준으로 쓰지 않는다. 과거 정적 조건 자체는 미래 입력 누설이 없지만 누설 자기 조건과의 비교는 무효다.
\n|조건|잃은 시점 s|지도|RGB / 벽점 / 랜드마크 표본|정답 수렴·첫 시간 s|종료 XY m / yaw°|σXY m / σyaw°|올바른 목표 / 거짓 목표|\n|---|---:|---|---:|---|---:|---:|---|\n'''
    for r in all_rows:
        mode=r['mode'];label={'egomap41-invalid-leak':('과거 no-LM (자기 누설)' if r['condition']=='own' else '과거 no-LM (정적)'),'off':'causal no-LM','on':'causal + S2 LM'}[mode]
        conv=f"예 / {r['convergence_s']:.1f}" if r['converged'] else '없음 / —'
        yawstd=r.get('final_yaw_std_deg')
        if yawstd is None:
            oldpred=load(Path('/Users/changmin/projects/ugrp/outputs/own-map-utility-v1')/f"{r['condition']}-{r['trial']}.json")
            yawstd=oldpred['rows'][-1]['circular_yaw_std_rad']*180/math.pi
        text+=f"|{label}|{[60,90,120][r['trial']]}|{r['condition']}|{r['input_frames']} / {r['point_samples']:,} / {r.get('landmark_samples',0):,}|{conv}|{r['final_xy_m']:.3f} / {r['final_yaw_deg']:.2f}|{r['final_std_xy_m']:.3f} / {yawstd:.2f}|{int(r['correct_recorded_goal'])} / {int(r['false_goal'])}|\n"
    text+='''\nLM 수는 관측 선분 표본이며 서로 다른 물리 랜드마크 수가 아니다. 중첩 구간을
독립 프레임/독립 실행으로 합산하지 않는다. 새 재생은 경계시각 프레임을 제외해
600/450/300 RGB이며, 과거601/451/301과 1개씩 다르다. 상세 갱신/재표본/거짓수렴은
[comparison.json](results/comparison.json), 원 판정은 [off](results/utility-off.json)·[on](results/utility-on.json).
\n|잃은 시점 s|실제 snapshot t / 스캔|점유/free칸|관측 면적 m²|색 경계 / 문 / 출처 RGB 수|전체 벽 덮임 (표본)|벽 P / RMSE m|기억한 B|\n|---|---:|---:|---:|---:|---:|---:|---|\n'''
    for p in prefix:
        q=p['quality']
        text+=f"|{[60,90,120][p['trial']]}|{p['snapshot_t']:.1f} / {p['scans']}|{p['occupied']} / {p['free']}|{p['observed_area_m2']:.2f}|{p['floor_line_records']} / {p['door_records']} / {p['landmark_frames']}|{q['wall_coverage']:.1%} ({p['covered_wall_samples']}/{p['all_wall_samples']})|{q['precision_015']:.1%} / {q['wall_error_rmse_m']:.3f}|{'관측' if p['goal_observed'] else '미관측'}|\n"
    text+='\n이 표의 P/덮임은 전체 벽 기준이며 egomap34 최종 영역P/R63.6/76.0%와 분모가 다르다.\n'
    static=results['on']['maps']['static-0']
    text+=f"정적 지도는 매 시점 {static['occupied']}점유/{static['free']}free칸, 제공면적{static['observed_area_m2']:.2f}m²이다. 자기의 관측 면적 차이는 유지했다.\n"
    for mode in ('off','on'):
        r=results[mode];own=[q for q in r['trials'] if q['condition']=='own'];st=[q for q in r['trials'] if q['condition']=='static']
        text+=f"\n- **{mode}:** 정답수렴 자기{sum(q['converged'] for q in own)}/3·정적{sum(q['converged'] for q in st)}/3; 자기 거짓 내부수렴 프레임{sum(q['false_internal_frames'] for q in own)}, 정적{sum(q['false_internal_frames'] for q in st)}. 오차비{r['xy_ratio']}, 시간비{r['time_ratio']}. 등록조건 전체 통과={r['offline_proxy_gate']}."
        text+=f" 올바른 녹화상 도달 자기{sum(q['correct_recorded_goal'] for q in own)}/3·정적{sum(q['correct_recorded_goal'] for q in st)}/3. 자기 계획 어댑터 호출{sum(q['static_geometry_path_clear'] is not None for q in own)}회(목표 미관측 반환 포함).\n"
    text+='''\n자기60초는 B 관측 전이라 목표 미관측1/3(90/120초는72.1초 관측 기억).
정적 목표는 같은 개체B의 authored 중심으로 유지한다. 자기 지도/랜드마크/목표 준비에
GT 변환0, 평가 그림과 오차 계산에서만 출발 GT 정렬을 사용했다. 문 검출0도 그대로 보존한다.
고정 녹화는 새 목표 경로를 실행하지 않아 실제 폐루프 도달 성공은 계속 **미검증**이다.

![인과적 snapshot과 관측 기억; GT 정렬은 평가 그림에서만](figures/snapshots.png)
![동일 suffix 재위치 오차 off/on](figures/relocalization.png)

### 검증·보존

바뀐 모듈3시험 파일 **16 passed**. default/off 반환값·입자/logw·RNG bytes 동일,
미래 스캔/타로봇 차단, future append 불변, B 목표 prefix 제한, 원본 S2 함수/상수
정의 해시, 바닥 단독 관측, 원래 egomap41 판정 블록 동일을 검사했다.
원본 해시·관측 prefix/suffix 비중첩·GT 평가 분리·예측 봉인은
[verification.json](results/verification.json), raw 목록은 [raw-manifest.json](results/raw-manifest.json).
Raw는 등록한 절대 outputs 경로에 로컬 보존하며 원격 백업으로 표현하지 않는다.
원래 미추적4파일/다른 worktree/#406 파일 변경0. PR405 DRAFT/병합0.
'''
    (EXP/'results/table.md').write_text(text.replace('](results/', '](').replace('](figures/', '](../figures/'))
    # Static geometry appears ONLY in evaluation visualizations, never preparations.
    truth=rows(EP/'eval_only/trajectory.jsonl');origin=np.r_[truth[0]['robot_xyz_m'][:2],truth[0]['robot_yaw_rad']]
    static=load(EP/'inputs/static_map.json')
    fig,axes=plt.subplots(1,3,figsize=(14,5),layout='constrained')
    for trial,ax in enumerate(axes):
        cut=prepared['cuts'][trial]
        for o in static['obstacles']:
            ax.add_patch(Rectangle(np.array(o['center_m'])-o['half_extents_m'],*(2*np.array(o['half_extents_m'])),color='lightgrey'))
        g=load(snapshot_path('own',trial));c=np.array(g['cells']);points=transform((c[:,:2]+.5)*g['resolution_m'],origin)
        ax.scatter(*points[c[:,2]<0].T,s=3,c='lightblue',alpha=.5)
        ax.scatter(*points[c[:,2]>0].T,s=8,c='navy',label='Own occupied')
        mem=load(RAW/f'maps/own-{trial}-landmarks.json')
        for edge in mem['edges']:
            xy=transform([edge['a'],edge['b']],origin);ax.plot(*xy.T,c='orange',lw=.4,alpha=.25)
        gt=np.array([r['robot_xyz_m'][:2] for r in truth if before(r['t'],cut['cut_t'])])
        ax.plot(*gt.T,c='green',lw=1,label='Past GT path (evaluation)')
        ax.set(title=f"Loss {cut['elapsed_s']:.0f}s: {cut['scans']} scans\n{prefix[trial]['occupied']} occupied; {len(mem['edges'])} partial edges",
            aspect='equal',xlabel='World x: evaluation alignment only',ylabel='World y')
    axes[0].legend(fontsize=7)
    (EXP/'figures').mkdir(exist_ok=True)
    fig.savefig(EXP/'figures/snapshots.png',dpi=130);plt.close(fig)
    fig,axes=plt.subplots(2,3,figsize=(14,7),layout='constrained')
    for mode in ('off','on'):
        d=load(RAW/f'evaluation-details-{mode}.json')
        for r in results[mode]['trials']:
            v=d[f"{r['condition']}-{r['trial']}"];label=f"{r['condition']} / {mode}"
            style=dict(color='C0' if r['condition']=='own' else 'C1',ls='-' if mode=='on' else '--',lw=1)
            axes[0,r['trial']].plot(np.array(v['t'])-prepared['start_t'],v['xy_m'],label=label,**style)
            axes[1,r['trial']].plot(np.array(v['t'])-prepared['start_t'],v['yaw_deg'],label=label,**style)
    for trial in range(3):
        axes[0,trial].axhline(.25,color='gray',lw=.7);axes[1,trial].axhline(10,color='gray',lw=.7)
        axes[0,trial].set(title=f"Loss {[60,90,120][trial]}s",ylabel='Position error m')
        axes[1,trial].set(ylabel='Yaw error degrees',xlabel='Recorded elapsed s')
    axes[0,0].legend(fontsize=8)
    fig.savefig(EXP/'figures/relocalization.png',dpi=130);plt.close(fig)
    for name,h in prepared['input_hashes'].items():assert sha(name)==h
    for name,h in prepared['source_code_hashes'].items():assert sha(ROOT/name)==h
    for mode,result in results.items():
        for name,h in result['sealed_predictions'].items():assert sha(name)==h
    original=load(ROOT/'experiments/2026-10-08-wall-pr-operating-point/results/verification.json')['original_untracked_hashes']
    for name,h in original.items():assert sha(ROOT/name)==h
    assert '16 passed' in (RAW/'tests-before-replay.log').read_text()
    dump(EXP/'results/verification.json',dict(tests=16,files=['test_self_map_relocalize.py','test_self_map_causal.py','test_self_wall_export.py'],
        prediction_count=12,scores=2,prediction_source=prepared['source_sha'],
        disjoint_prefix_suffix=True,exact_online_snapshot=True,all_landmark_sources_before_cut=True,
        future_goal_removed=True,criteria_unchanged=True,off_bytes_rng_verified=True,
        original_input_hashes=prepared['input_hashes'],original_untracked_hashes=original,
        native_physics_calls=0,models=0,lock=0,retuning=0))
    print('Saved comparison, prefix provenance verification, and two evaluation figures.',flush=True)
    dump(EXP/'results/raw-manifest.json',{str(p):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(RAW.rglob('*')) if p.is_file()})


if __name__=='__main__': main()
