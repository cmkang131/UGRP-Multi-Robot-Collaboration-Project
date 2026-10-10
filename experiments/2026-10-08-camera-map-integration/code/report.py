"""Static figures and auditable tables, consuming sealed evaluation results."""
import hashlib
import math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
from evaluate import geometry, occupied
from replay import *
from harness.self_odom_grid import transform


def percent(x):
    return f'{100*x:.1f}%'


def report():
    comparison = load(EXP/'results/maps.json')
    baseline = load(ROOT/'experiments/2026-10-08-own-map-causal-landmarks/results/utility-on.json')
    current = load(EXP/'results/utility-on.json')
    missing = load(EXP/'results/missing.json')
    prepared = load(RAW/'prepared.json')
    out = ['## 결과 (설정 동결, 재튜닝 0)', '',
        '녹화 **1개**, RGB 901/제어 입력 891/비어 있지 않은 검출 878. 가시 벽 표본 146/329.',
        '새 물리·모델 호출 0. 이동 거리 7.449 m, 실제 footprint 합집합 2.268 m²는 원본과 같다.', '',
        '### 누락 벽 칸', '',
        'GT 벽 표본 329개를 자기 0.1 m 칸별 대표점으로 묶으면 249칸이다. '
        '0.15 m 대응 허용에서 144칸 덮임/105칸 누락이다. 정확한 같은 칸만 비교하면 185칸 누락으로, '
        '이를 자세 오차로 합산하지 않는다. 대표점의 잠재 가시 칸은 92/249이다.', '',
        '| 누락 이유 | 칸 | 누락 105칸 중 | 전체 249칸 중 |', '|---|---:|---:|---:|']
    names = dict(a_not_potentially_visible='a: 대표점 시야·4 m·벽 가림 밖',
        b_no_projected_detection='b: 가시 기회 있으나 투영 검출 없음',
        c_detection_not_inserted='c: 검출됐으나 삽입 안 됨',
        d_inserted_pose_displaced='d: 삽입 시 자세로 다른 곳에 놓임',
        e_free_evidence_or_cell_boundary='e: 맞게 삽입 후 free/칸 경계 잔여')
    for k, label in names.items():
        n = missing['causes'].get(k, {}).get('cells', 0)
        out.append(f'| {label} | {n} | {percent(n/105)} | {percent(n/249)} |')
    out += ['', '**c의 3칸은 모두 이동 관문**: 각각 6/7/9개 검출 프레임이 보류됐다. '
        '가시 누락 26칸 중 이동 관문 3칸(11.5%), 자세 배치 17칸(65.4%), 잔여 6칸(23.1%)다. '
        '814개 보류 프레임이 곧 서로 다른 814개 벽의 손실이라는 뜻은 아니다.',
        '가시성은 실제 카메라와 벽 가림만 계산한 **잠재 가시성**이다. 자기 몸/물체 가림은 '
        '복원하지 못했다. 같은 칸의 첫 GT 표본을 대표로 쓰므로 그 칸 모든 면의 가시성은 보장하지 않는다. '
        '(b)는 픽셀 누락과 투영 오차를 구별하지 않는 운영 정의다.', '',
        '### 지도 (영역과 전체를 혼합하지 않음)', '',
        '| 구성 | 삽입 | 영역 P / R | 전체 P / R(덮음) | 점유 칸 | 관측 칸 | 벽 RMSE(m) |',
        '|---|---:|---:|---:|---:|---:|---:|']
    labels = {'egomap34':'egomap34 최종 입자/graph', 'sparse_online_control':'동일 online 자세 64프레임 대조',
              'camera_every_frame_v1':'매 프레임 online 지도'}
    for key, r in comparison['maps'].items():
        out.append(f'| {labels[key]} | {r["inserted_frames"]} | '
            f'{percent(r["region_precision"])} / {percent(r["region_recall"])} | '
            f'{percent(r["precision_015"])} / {percent(r["wall_coverage"])} | '
            f'{r["occupied_cells"]} | {r["observed_cells"]} | {r["wall_error_rmse_m"]:.3f} |')
    on = comparison['maps']['camera_every_frame_v1']
    control = comparison['maps']['sparse_online_control']
    on_correct = round(on['precision_015']*on['occupied_cells'])
    control_correct = round(control['precision_015']*control['occupied_cells'])
    out += ['', f'지도 관문 **{sum(comparison["gates"].values())}/6, 실패**. 삽입 증가·자세 원장 불변만 통과.',
        f'같은 online 자세 대조에서도 점유 {control["occupied_cells"]}→{on["occupied_cells"]}칸, '
        f'참 칸 {control_correct}→{on_correct}, 거짓 칸 '
        f'{control["occupied_cells"]-control_correct}→{on["occupied_cells"]-on_correct}이다. '
        '통합 증가가 반복된 거짓 접점/부정확한 당시 자세의 흔적을 제거하지 못했다. '
        'free ray와 clamping은 작동하지만 hit의 의미 자체가 벽임을 검증하지 않는다.',
        f'영역 P 분모 {on["region_precision_cells"]}칸(참 {on["region_precision_correct"]}), '
        f'영역 R 분모 146표본(덮임 {on["region_recalled"]}), 전체 덮임 {on["covered_samples"]}/329. '
        f'관측 격자 면적 {on["observed_area_m2"]:.2f} m²는 추정 ray의 합집합이며 실제 탐색 면적이 아니다.', '',
        '![세 지도와 경로](figures/maps.png)', '',
        '### 누설 없는 snapshot 재위치 — egomap42 LM on 6조건', '',
        'AMCL/KLD·랜드마크·seed·suffix·기억 B·판정은 그대로, tempering off. '
        '원본 3쌍과 새 지도 3쌍을 비교하며 독립 표본 6개로 합산하지 않는다.', '',
        '| 조건/잃은 시각 | 삽입 off→on | 수렴 off→on | 최초 수렴 s off→on | 거짓 수렴 프레임 off→on | 종료 XY m off→on |',
        '|---|---:|---|---:|---:|---:|']
    for a, b in zip(baseline['trials'], current['trials']):
        assert (a['condition'], a['trial']) == (b['condition'], b['trial'])
        i = a['trial']; name = a['condition']
        def val(v): return '—' if v is None else f'{v:.1f}'
        scans = f'{[27,34,38][i]}→{prepared["cuts"][i]["scans"]}' if name == 'own' else '정적 고정'
        out.append(f'| {name} / {[60,90,120][i]}s | {scans} | '
            f'{int(a["converged"])}→{int(b["converged"])} | '
            f'{val(a["convergence_s"])}→{val(b["convergence_s"])} | '
            f'{a["false_internal_frames"]}→{b["false_internal_frames"]} | '
            f'{a["final_xy_m"]:.3f}→{b["final_xy_m"]:.3f} |')
    out += ['', f'재위치 쓸모 관문 **{sum(current["gates"].values())}/10**, '
        f'통과 여부 `{current["offline_proxy_gate"]}`. 동일 scorer의 상세 항목은 '
        '`results/utility-on.json`에 보존. 거짓 수렴이 남으면 정확히 수렴한 적이 있어도 안정적인 위치 복구로 보고하지 않는다.',
        '60초 B는 여전히 미관측이다. 90/120초 B는 이전 자기 RGB 관측 ID `r3-obs-000355`에서만 온다. '
        '기존 녹화 명령이 B를 향하지 않으므로 실제 폐루프 목표 도달은 **미측정**이며 물리 실행은 하지 않았다.', '',
        '| cut | 이전 점유 칸 / 덮음 | 새 점유 칸 / 덮음 | 새 관측 칸 |', '|---|---:|---:|---:|']
    for i in range(3):
        a = baseline['maps'][f'own-{i}']; b = current['maps'][f'own-{i}']
        out.append(f'| {[60,90,120][i]}s | {a["occupied"]} / {percent(a["quality"]["wall_coverage"])} | '
                   f'{b["occupied"]} / {percent(b["quality"]["wall_coverage"])} | {b["observed_cells"]} |')
    out += ['', '![지도 칸 누락 원인](figures/missing.png)', '',
        '후속 해석: 이동 관문은 실제로 대부분의 프레임을 버리지만, 이 녹화에서 매 프레임 지도 통합만으로 '
        '유용성이 좋아진다는 증거는 얻지 못했다. 이번에는 추가 문턱·검출기·자세 보정·물리를 시도하지 않는다.', '']
    (EXP/'results/table.md').write_text('\n'.join(out).replace('(figures/', '(../figures/'))

    truth, origin, rects, _ = geometry()
    true_path = np.array([r['robot_xyz_m'][:2] for r in truth])
    online = transform(np.array([r['pose'][:2] for r in rows(EP/'frontend-covariances.jsonl')]), origin)
    graph = transform(np.array([r['pose'][:2] for r in load(EP/'graph.json')['poses']]), origin)
    fig, axes = plt.subplots(1, 3, figsize=(14, 5.3), sharex=True, sharey=True)
    all_xy = []
    for ax, (key, filename, title) in zip(axes, [
            ('egomap34','off-grid.json','Frozen egomap34'),
            ('sparse_online_control','sparse-online-grid.json','Online pose / 64 scans'),
            ('camera_every_frame_v1','on-grid.json','Online pose / every frame')]):
        g = load(RAW/filename); pts = occupied(g, origin); all_xy.append(pts)
        for x,y,hx,hy in rects:
            ax.add_patch(Rectangle((x-hx,y-hy), 2*hx, 2*hy, color='.7', zorder=1))
        evidence = np.array([r[2] for r in g['cells'] if r[2] > 0])
        colors = np.tile([.02, .20, .75, 1.], (len(pts),1))
        colors[:,3] = .25+.75*np.clip(evidence/math.log(.971/.029), 0, 1)
        ax.scatter(*pts.T, s=9, c=colors, marker='s', label='Mapped cells (log-odds shade)', zorder=3)
        ax.plot(*true_path.T, color='#208b37', lw=1, ls='--', label='True path (evaluation)')
        ax.plot(*(graph if key=='egomap34' else online).T, color='#d25a26', lw=.8, label='Estimated path')
        r = comparison['maps'][key]
        ax.set_title(f'{title}\nN={r["occupied_cells"]}, region P/R={100*r["region_precision"]:.1f}/{100*r["region_recall"]:.1f}%', fontsize=10)
        ax.set_aspect('equal'); ax.set_xlabel('World x (m), evaluation alignment only'); ax.grid(alpha=.2)
    pts = np.concatenate(all_xy)
    for ax in axes:
        ax.set_xlim(min((rects[:,0]-rects[:,2]).min(),pts[:,0].min())-.3,
                    max((rects[:,0]+rects[:,2]).max(),pts[:,0].max())+.3)
        ax.set_ylim(min((rects[:,1]-rects[:,3]).min(),pts[:,1].min())-.3,
                    max((rects[:,1]+rects[:,3]).max(),pts[:,1].max())+.3)
    axes[0].set_ylabel('World y (m)'); axes[0].legend(fontsize=6,loc='lower left')
    fig.suptitle('One recording: seed32002 / log-odds is NOT calibrated wall correctness', fontsize=12)
    fig.tight_layout(); (EXP/'figures').mkdir(exist_ok=True)
    fig.savefig(EXP/'figures/maps.png', dpi=140); plt.close(fig)
    data = load(RAW/'missing-wall-cells.json')
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.7))
    for x,y,hx,hy in rects:
        axes[0].add_patch(Rectangle((x-hx,y-hy),2*hx,2*hy,color='.85'))
    palette = ['#777777','#e0a326','#b35b1b','#bb2288','#4050bd']
    for (k, label), color in zip(names.items(), palette):
        xy = np.array([r['world_xy'] for r in data if r['category']==k]).reshape(-1,2)
        if len(xy): axes[0].scatter(*xy.T, s=18, color=color, label=f'{k[0]}: {len(xy)}')
    axes[0].plot(*true_path.T, color='#208b37', lw=.8)
    axes[0].set_aspect('equal'); axes[0].legend(fontsize=8); axes[0].set_title('Missing representative wall cells')
    counts = [missing['causes'].get(k,{}).get('cells',0) for k in names]
    axes[1].bar(['a: unseen','b: detection','c: gate','d: pose','e: other'], counts, color=palette)
    for i, n in enumerate(counts): axes[1].text(i,n+1,str(n),ha='center')
    axes[1].set_ylim(0,max(counts)*1.15);axes[1].set_ylabel('Cells (105 missing / 249 total)')
    fig.suptitle('Potential FOV only: wall occlusion; object/self occlusion unavailable')
    fig.tight_layout();fig.savefig(EXP/'figures/missing.png',dpi=140);plt.close(fig)
    print('WROTE results/table.md and two figures', flush=True)


if __name__ == '__main__': report()
