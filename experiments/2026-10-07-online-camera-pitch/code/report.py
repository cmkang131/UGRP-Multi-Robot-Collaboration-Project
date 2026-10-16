"""Render saved diagnostics only; never rerun/tune pitch or map prediction."""
from collections import Counter
import json
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0,str(Path(__file__).parent))
import conditions as c
import evaluate_pitch as e
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import cv2

EXP=e.EXP
RAW=Path('/Users/changmin/projects/ugrp/outputs/online-camera-pitch-v1-complete')


def fmt(v,d=3):
    return 'NA' if v is None else f'{v:.{d}f}'


def support_overlay(ax,case,frame_id):
    rows=c.a.old.base.read_rows(RAW/'online_vp_v1'/case/'own-predictions.jsonl')
    r=next(x for x in rows if x['frame_id']==frame_id)
    fs,_=c.a.old.own_inputs(c.a.old.EPISODES[case],'r3')
    f=next(x for x in fs if x['frame_id']==frame_id)
    path=c.a.old.EPISODES[case]/f['path']
    assert c.a.digest(path)==f['sha256']==r['image_sha256']
    image=c.a.old.mp.undistort(cv2.imread(str(path)))
    k=c.a.old.mp.K
    scale=k[1,1]/k[0,0]
    if scale!=1:
        image=cv2.warpAffine(image,np.array([[scale,0.,0.],[0.,1.,0.]]),
                            (int(np.ceil(image.shape[1]*scale)),image.shape[0]))
    grey=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    lines=np.asarray(cv2.createLineSegmentDetector(0).detect(grey)[0]).reshape(-1,4)
    lines=lines[np.linalg.norm(lines[:,:2]-lines[:,2:],axis=1)>=e.PARAMETERS['length_px']]
    vps=np.asarray(r['meta']['vps'])
    mid=(lines[:,:2]+lines[:,2:])/2
    direction=lines[:,:2]-lines[:,2:]
    direction/=np.linalg.norm(direction,axis=1)[:,None]
    pp=np.array([k[0,2]*scale,k[1,2]])
    rays=k[1,1]*vps[:,None,:2]+(pp-mid)[None]*vps[:,None,2:]
    norms=np.linalg.norm(rays,axis=2)
    cos=np.divide(np.einsum('vnc,nc->vn',rays,direction),norms,out=np.zeros_like(norms),where=norms>1e-12)
    angle=np.arccos(np.clip(abs(cos),0,1))
    labels=np.argmin(angle,axis=0)
    supported=np.min(angle,axis=0)<=np.radians(e.PARAMETERS['cluster_deg'])
    ax.imshow(cv2.cvtColor(image,cv2.COLOR_BGR2RGB))
    for line,label,ok in zip(lines,labels,supported):
        if ok and label==r['meta']['vertical_axis']:
            ax.plot(line[[0,2]],line[[1,3]],color='#ff00df',lw=2)
    result=c.a.load(EXP/f'results/online_vp_v1/{case}.json')
    f=next(x for x in result['frame_scores'] if x['frame_id']==frame_id)
    ax.set_title(f"{case} frame {frame_id}: VP {f['candidate_pitch_deg']:.2f} deg\n"
                 f"actual {f['actual_pitch_deg']:.2f} deg (evaluation only)")
    ax.set_axis_off()


def main():
    frozen=c.a.load(EXP/'freeze.json')
    assert e.hashes()==frozen['hashes']
    results=[c.a.load(EXP/f'results/online_vp_v1/s{i}.json') for i in range(1042,1048)]
    for r in results:
        pred=RAW/'online_vp_v1'/r['case']/'own-predictions.jsonl'
        assert c.a.digest(pred)==r['prediction_sha256']
        assert r['hashes']==frozen['hashes']
    groups=c.a.load(EXP/'results/conditions.json')
    figs=EXP/'figures'
    figs.mkdir(exist_ok=True)
    fig,axs=plt.subplots(1,2,figsize=(12,4.9))
    # Diagnostic selection made after scoring: first accepted vs known wrong frame.
    support_overlay(axs[0],'s1045',217)
    support_overlay(axs[1],'s1045',775)
    fig.suptitle('Magenta: lines assigned to vertical VP (not ground-truth vertical lines)')
    fig.tight_layout(rect=(0,0,1,.90))
    fig.savefig(figs/'vp-support.png',dpi=140)
    plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(11,4.5))
    colors=['#3465a4','#ef8a26','#458b45']
    for j,(pose,load) in enumerate([('SEARCH','unloaded_ground'),('HIGH','held_airborne'),('CARRY','held_airborne')]):
        xs,ys,lower,upper=[],[],[],[]
        for i,(case,d) in enumerate(groups.items()):
            g=d['groups'].get(f'pose_load={pose}|{load}|settled')
            if not g:continue
            s=g['pitch_delta_deg']
            xs.append(i+(j-1)*.18)
            ys.append(s['median'])
            lower.append(s['median']-s['p05'])
            upper.append(s['p95']-s['median'])
        axs[0].errorbar(xs,ys,yerr=[lower,upper],fmt='o',capsize=3,label=f'{pose} / {load}',color=colors[j])
    axs[0].set_xticks(range(4),list(groups))
    axs[0].set_ylabel('Actual - unloaded-table pitch (deg), median / P05-P95')
    axs[0].legend(fontsize=8)
    x=np.arange(6)
    axs[1].bar(x-.18,[r['metrics']['baseline']['median'] for r in results],.36,label='Off: all fixed points')
    axs[1].bar(x+.18,[r['metrics']['candidate']['median'] for r in results],.36,label='VP: positive points ONLY')
    for i,r in enumerate(results):
        axs[1].text(i,.8,f"{r['positive']}/{r['points']}",ha='center',fontsize=8)
    axs[1].axhline(.1,color='red',linestyle='--',label='Median gate 0.10 m')
    axs[1].set_xticks(x,[r['case'] for r in results])
    axs[1].set_ylabel('Projection median error (m)')
    axs[1].set_ylim(0,1.)
    axs[1].set_title('All 6 FAIL; labels = retained positive / fixed points')
    axs[1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(figs/'conditions-and-gate.png',dpi=140)
    plt.close(fig)
    lines=['# egomap13 결과 — 자기 지도 트랙 중단','',
        '기존 투영 관문 **0/6 통과**. 개발2 → `10eb7add` 동결 → 확인4를 각1회 수행했다.',
        '설정 재튜닝0, 지도/RBPF/graph 재생0, 지도 그림 갱신0, MuJoCo/렌더/모델 호출0.',
        '새 옵션은 연구용 기본-off로 보존하며 실행 번들에 승격하지 않는다.',
        '', '## 조건 분해 (actual − 고정 unloaded 표, 도)', '',
        '모든30,512프레임 join, 누락0. 표는 팔 명령 변경 후0.5s 이상만; 전체/정착 중/각 PWM/교차표는',
        '[CSV](results/conditions.csv)와 [JSON](results/conditions.json)에 모두 남겼다.',
        'held=양쪽 손가락 접촉+공중, unloaded=무접촉+바닥, 애매한 표본은 제외하지 않고 별도 그룹이다.', '',
        '| 녹화 | 팔·적재 | n | pitch P05 / 중앙 / P95 | 실제 pitch 중앙 | 차체 tilt 중앙 / P95 | #406 loaded 표 차 중앙(반사실) |',
        '|---|---|---:|---|---:|---|---:|']
    for case,d in groups.items():
        for pose,load in [('SEARCH','unloaded_ground'),('HIGH','held_airborne'),('CARRY','held_airborne'),
                          ('PICK_transition','unloaded_ground'),('PICK_transition','held_airborne')]:
            g=d['groups'].get(f'pose_load={pose}|{load}|settled')
            if not g:continue
            s,b=g['pitch_delta_deg'],g['body_tilt_deg']
            lines.append(f"| {case} | {pose} / {load} | {g['n']} | {fmt(s['p05'])} / {fmt(s['median'])} / {fmt(s['p95'])} | {fmt(g['actual_pitch_deg']['median'])} | {fmt(b['median'])} / {fmt(b['p95'])} | {fmt(g['loaded_counterfactual_delta_deg']['median'])} |")
    lines += ['', 'PICK/transition은 여러 명령 자세의 혼합이며 단일 정적 보정 오차로 해석하지 않는다.',
        '같은 HIGH에서 무하중·적재가 충분히 겹치는 비교군이 없어 **순수 하중 효과는 식별 불가**.',
        's1050도 SEARCH −0.869°, HIGH 적재 −2.798°로 이전과 같다. 잘 맞았던 구간은',
        'real CARRY(600/2200/1400/1500) + #406 loaded 표이며 HIGH(896/2035/1894/1500)와 다르다.',
        's1050 전체 정착 CARRY의 loaded 차 −0.256°는 기존1Hz 감사 +0.237°와 부호·표본수가 다르다.',
        '기존접점1.53cm는5171개 visible 검출 열; 이번 수동 고정 관문과 합산하지 않는다.',
        '', '### 이동/정지·가감속 교차 분포', '',
        '| 녹화 | 팔·적재 | 이동 | 가감속 | n | pitch P05 / 중앙 / P95 (°) | tilt 중앙 (°) |',
        '|---|---|---|---|---:|---|---:|']
    for case,d in groups.items():
        for key,g in d['groups'].items():
            if not key.startswith('cross='):continue
            pose,load,motion,acc,settle=key[6:].split('|')
            if settle!='settled' or pose=='PICK_transition':continue
            s=g['pitch_delta_deg']
            lines.append(f"| {case} | {pose}/{load} | {motion} | {acc} | {g['n']} | {fmt(s['p05'])} / {fmt(s['median'])} / {fmt(s['p95'])} | {fmt(g['body_tilt_deg']['median'])} |")
    lines += ['', 's1045–47 HIGH의 이동 가속/정속/감속 중앙 차이는 각0.008/0.012/0.025°에 그친다.',
        '정지 정속에서도 HIGH 불일치가 −2.80~−2.82°로 남는다. 현재 차체 tilt 중앙0.04–0.11°만으로',
        'SEARCH 약0.87°/HIGH 약2.8°를 설명하기 어렵다. 이는 기록에서 얻은 추론이며 인과 확정이 아니다.',
        '차체 signed pitch/roll 및 실측 관절이 없어 고정 보정 기준·서보 처짐·팔 유격을 분리할 수 없다.',
        'CSV의 `non_body_residual_lower_bound_deg`는 **보정 기준 차체가 수평이었다고 가정할 때만**',
        '현재 tilt를 뺀 잔차 하한이다. 보정 당시 차체 tilt는 없어 무조건적인 팔 처짐 하한으로 해석하지 않는다.',
        '', '## 고정 접점 투영 관문', '',
        '| 녹화 | split | 고정 점 | off 중앙/P90 m | VP 중앙/P90 m (양의 점만) | 양의·4m 점 | oracle 중앙 m | 판정 |',
        '|---|---|---:|---|---|---|---:|---|']
    totals=Counter()
    for r in results:
        b,p,o=[r['metrics'][k] for k in ('baseline','candidate','oracle')]
        totals.update(r['counts'])
        lines.append(f"| {r['case']} | {r['split']} | {r['points']} | {fmt(b['median'])}/{fmt(b['p90'])} | {fmt(p['median'])}/{fmt(p['p90'])} | {r['positive']}/{r['points']} ({100*r['positive']/r['points']:.1f}%) | {fmt(o['median'])} | FAIL |")
    lines += ['', f'VP 수락{totals["accepted"]}/36, 수직 지지 부족{totals["insufficient_vertical_support"]}, 축 모호{totals["ambiguous_vertical_axis"]}.',
        '**고정2170점 중807점이 양의 투영을 잃었다.** 위 VP 오차는 남은1363점만의 값이며 전체 성능 개선으로 해석하면 안 된다.',
        '분모 유지 및 양의100%/4m≥95% 검사로 모두 실패. 특히 s1045의0.046m도302/380점만 남아 실패다.',
        's1046/47은 절반 이상 무효이므로 무효=무한 오차로 계산한 전체 중앙값도 무한이다.',
        '기존 positive_depth 가드는 이 점들을 삽입하지 않겠지만, 그것이 투영 관문 성공은 아니다.',
        '수직축으로 분류된 약한 선분이 잘못된 VP를 지지한다. s1045 frame775에서는 실제−19.05°를',
        '−10.32°로 추정했다. 원문1° 구면 격자, 좁은 FOV/짧은 수직선, 물체·자기 차체 선 혼입의 한계를',
        '이번 설정에서 분리 추정할 수 없으며 추후 임계값 조정·선분 마스킹으로 결과를 덮지 않았다.',
        '', '![조건과 관문](figures/conditions-and-gate.png)', '',
        '![VP 지지선](figures/vp-support.png)', '',
        '그림의 좋은/나쁜 예는 **결과 확인 후 설명용으로 선택**했으며 평가 표본/설정에는 영향이 없다.',
        '', '## 중단과 필요한 실물 측정', '',
        '자기 지도 트랙을 여기서 중단한다. 고정 보정 각도를 +/−0.87° 옮기거나 실패 검출기를 재튜닝하지 않는다.',
        '다음 측정이 확보되기 전 지도 재생/성공 주장은 하지 않는다:',
        '',
        '1. 실제 장착 카메라의 높이·전후 위치·pitch/roll/yaw 및 장착 유격: 수평 기준판/독립 측량과 체커보드 외부 보정.',
        '2. SEARCH/HIGH/real CARRY 각각의 무하중·실제 블록 적재에서 서보 명령과 **실측 관절각**·정착 시간 동기 기록.',
        '3. 정지·가속·정속·감속에서 **부호 있는 차체 pitch/roll**과 카메라 자세를 따로 측정. 현재 unsigned tilt만으로는 원인 배분 불가.',
        '4. 현재 camera v3 intrinsic/왜곡/영상 시각 동기 검증과 거리별 바닥 기준점 재투영. 모델/시뮬레이터 정답을 제어에 넣지 않는다.',
        '', '## 검증·보존', '',
        '원문/라이선스 byte hash, 고정 source/parameter hash, own 예측 봉인 뒤 GT 채점을 확인했다.',
        'off는 `d857d79b`의21자세×기존3경로 geometry/투영 bytes와 비교한다. 빈 영상/평행선은 안전하게 abstain한다.',
        'OpenCV5 API 배열 형식 오류1회와 수정은 [EXECUTION.md](EXECUTION.md)에 보존한다. venv 변경/추가 설치0.',
        'raw는 로컬 primary outputs의 `online-camera-pitch-v1`(조건/원문/실패 흔적) 및',
        '`online-camera-pitch-v1-complete`(개발/확인 봉인 결과). [provenance.json](results/provenance.json)에',
        '파일별 SHA/크기를 기록한다. GitHub에는 코드·표·그림을 보존하며 raw 원격 백업으로 표현하지 않는다.',
        '출처: [REFERENCES.md](REFERENCES.md). §17·§19, 기존 detector/FK/graph 결과 불변.',
        'PR #406 파일 수정0, PR #405 DRAFT 유지·병합 없음. TensorBoard 변환은 기존 사용자 결정대로 생략.']
    (EXP/'RESULTS.md').write_text('\n'.join(lines)+'\n')
    manifest=[]
    for root in [c.OUT,RAW]:
        for path in sorted(root.rglob('*')):
            if path.is_file():manifest.append(dict(path=str(path),bytes=path.stat().st_size,sha256=c.a.digest(path)))
    c.a.write(EXP/'results/provenance.json',dict(files=manifest,raw_files=len(manifest),raw_bytes=sum(x['bytes'] for x in manifest),
        condition_code_sha256=c.a.digest(EXP/'code/conditions.py'),condition_source_commit='7428987b',
        development_source='c9c4aba0',confirmation_source='10eb7add',map_replays=0,retuning=0,physics=0,models=0))
    print('report saved',len(manifest),'raw files',sum(x['bytes'] for x in manifest),'bytes',flush=True)


if __name__=='__main__':
    main()
