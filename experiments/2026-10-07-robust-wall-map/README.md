# egomap21 — Switchable Constraints와 관측 증거량 (구현 전 사전 등록)

2026-10-07 사용자 요청. 시작 `2ff5fe9c`의 egomap20 정/역방향 **기존 녹화만** 쓴다.
새 물리/렌더/모델/agent_lock/유료·원격 계산0. S2 프로세스·PR406·다른 worktree 변경0.
동일 거짓 정합 재발로 기존 문턱 조정을 중단하고 아래 공개 방법을 한 번 적용한다.
이미 열람한 DEV 자료이며 새 확증 자료가 아니다. 결과 후 문턱/모션 재적합0.

## 방법 선택과 고정 옵션

|옵션|기본|on 의미|
|---|---|---|
|`loop_rejection`|`off`|`switchable_v1`: Sünderhauf–Protzel IROS2012 식(1)의 선형 switch, 초기값/사전 평균1, 사전 분산1, 범위[0,1]|
|`wall_evidence`|`off`|`tsdf_weight_v1`: Cartographer TSDF의 누적 fusion weight와 관측 횟수/시선 각도 분산을 별도 지도 필드로 기록|

Switchable Constraints는 기존 submap/scan 그래프에 루프별 변수만 추가하므로 PCM의
상관 경로 공분산 추정이나 새 라이브러리가 필요 없다. 기존 Huber만으로 실패한 자료에
같은 min_score를 올리는 튜닝을 하지 않는다. 목적함수는 intra 제약 제곱합 +
`s² × loop Mahalanobis 잔차² + (1−s)²`. 첫 submap 고정, 기존 제약/공분산 유지,
SciPy sparse least_squares 기존200회 한도. on에서 loop Huber를 switch 항으로 대체한다.
연속 switch를 최적화하며 hard 삭제/두 번째 재최적화는 하지 않는다. **s≥.5 유지, s<.5 억제**는
이번 진단 집계 기준으로만 사전 고정한다(원 논문이 요구한 이진 문턱이라는 주장은 하지 않음).
수렴 실패 시 frontend로 되돌리고 실패를 기록한다. GT는 switch/후보 선택에 쓰지 않는다.

TSDF 공개 구현의 Gaussian incidence kernel σ=.5rad, distance-to-hit kernel σ=.5m,
truncation=.3m, 최대weight10, range exponent0, 한 scan의 셀 중복 갱신 금지를 따른다.
전체 signed-distance/weight를 보조 필드로 적분하고 기존 log-odds 격자/자유 공간 지우기는
그대로 둔다. 제한된 벽 선분의 법선을 쓰는 부분만 LiDAR의 이웃점 법선 추정과 다르다.
동일 cell의 관측 수, 시선 방향의 원형 분산 `1−|Σ exp(iθ)|/N`도 함께 기록한다.
**각도 다양성은 별도 진단값**이며 임의의 보너스로 weight를 부풀리지 않는다.
보고 score=`min(weight/10,1)`은 관측 지원량, **실제 벽일 확률이 아니다**.
기존 점유 log-odds는 셀 점유 판정/정합에만 유지하며 on의 벽 신뢰도로 노출하지 않는다.
TSDF가 점유 지도 자체를 대체하거나 자세 오류를 해결한다는 주장은 하지 않는다.

## 재생 봉인·GT 경계

입력: `outputs/arena-wall-map-v1/predictions/{forward,reverse}`의 egomap20 봉인된
자기 접점, RBPF100 frontend ledger/path, graph 후보·공분산. 이전 prediction 두 receipt와
파일 hash를 검증한다. RGB/명령→frontend가 동일하므로 76,648회 후보 정합을 다시 하지 않고
동일 후보를 재사용한다. 새 optimizer 및 지도 적분만 재생하는 **back-end 비교**다.
예측 단계에서 eval_only/static_map/GT를 읽지 않고 두 건을 먼저 저장·해시 봉인한다.
off는 기존 graph ledger/path/grid/문구 bytes를 그대로 복제해 SHA 일치 검사한다.
on은 원 frontend에서 시작하며 기존 graph 최적화 결과를 초기값으로 쓰지 않는다.
기존 detector/positive_depth/servo_stiffness/tape/v122/RBPF100/inverse_sensor 모두 동결.
새 wall_evidence는 inverse_sensor_v1 삽입 weight와 다른 이름/의미로 공존한다.

채점은 그 뒤 출발 GT SE(2) 한 번으로 정렬한다. 정답 벽·실제 pose는 평가 전용.
두 조건 각각 P(.15m), 전체 R=덮임(329표본), 벽/경로 RMSE, 종료XY, median/P95,
loop 유지/억제/기존 거부 이유, yaw RMSE/P95/종료를 보고한다. DR→frontend→graph off/on의
yaw를 나란히 놓아 기존 yaw 정합의 회전오차 흡수 여부만 확인한다. v122 변경0.
ECE는 같은10개 bin/벽 .15m 라벨을 유지한다. off의 기존 점유 ECE와 on의 증거 score-ECE를
함께 보고하되 **on 값은 확률 calibration이 아닌 score와 정답률의 간극**으로 명시한다.
두 수치 차이만으로 calibration 개선을 주장하지 않는다. 원 점유 ECE도 보조열로 남긴다.

## 결과 전 고정 관문

- 기존 §17/§19의7개 상대 기준을 동일 관측 DR 대비 그대로 재사용한다. 추가로 off→on
  P 비감소, R 하락≤2%p, 벽/경로 RMSE 비증가를 요구한다.
- 유지(s≥.5) 루프의 GT 상대제약 XY 오차>.30m인 거짓 유지 **0개**(평가에만 사용).
- on score≥.9 셀 실제벽 비율≥.90, score-ECE≤.10. 해당 셀0개면 고신뢰 검증 불가로 실패.
- F 내보내기는 egomap20 그대로 각 녹화의 P≥.90, R≥.70, 벽RMSE≤.15m,
  경로RMSE≤.25m와 위 기준을 모두 만족할 때만 구현한다. 기존 실제 완주0/2는 바뀌지 않으므로
  전체 경기장 지도 완주 주장은 금지한다. 완주 조건도 egomap20의 별도 미충족 항목으로 남긴다.
- 어떤 관문이든 미달이면 `wall_export=segments_confidence_v1`은 보류하고 원인만 기록·종료.
  같은 두 건으로 재튜닝/재채점하지 않는다. 입력 누락/비유한 값/ENOSPC는 HOST_ERROR.

관련 시험1–3파일 통과 후 사전 등록 commit/push → 구현·골든 시험 → 소스 commit/push →
두 건 예측·봉인 → 평가1회 → 결과 commit/push. 새 venv/의존성0, 잠금·속도 비교0.
새 raw: `/Users/changmin/projects/ugrp/outputs/robust-wall-map-v1/`, 기존 자료 덮어쓰기/삭제0.
PR405 DRAFT, 병합/force/reset0. TensorBoard 생략 지시 유지, Drive0.
원시 결과는 로컬 보관이며 Git 원격 백업은 코드·작은 결과·그림에 한정한다.

출처와 원본 대조: [REFERENCES.md](REFERENCES.md).

### 구현 경계 (자료 재생 전)

기존 동결 파일은 수정하지 않았다. `harness.self_wall_memory_robust.SelfWallMemory`가
기존 motion memory를 상속하여 새 옵션을 노출한다. 두 옵션 off는 기존 메서드로 그대로
위임하고 snapshot/격자/graph 결과의 직렬화 bytes를 검사한다. on의 결과는
`pose_graph_result` 및 `evidence_view`에만 저장하고 frontend/RNG/명령 모델에 되먹이지 않는다.
command/관측을 받으면 최종 view를 무효화한다. 기존 LLM 문구는 좌표만 유지하며
게이트 전 F 선분+신뢰도 export API는 만들지 않는다.

`code/backend_replay.py`는 동일 후보 cache의 hash와 기존29개 동결 파일을 확인한 뒤
두 조건을 봉인한다. `code/offline_score.py`는 두 봉인이 모두 있어야 GT를 읽는다.
TSDF의 ray-cell 순회는 기존 0.1m Amanatides–Woo를 재사용(원본 superscaled ray mask와
격자 경계 tie 차이 가능). 표면 법선은 기존 선분으로 계산하고 원본 kernel/weight 식은 유지한다.
새 라이브러리/C++ 소스 복사0. 최초 합성 시험에서 bounded solver의 s≈1 끝자리 오차를
과하게 요구한 검사1개가 실패하여, 해석해 대비 목적함수 차이<1e−6 검사로 고쳤다.
optimizer/사전 문턱은 바꾸지 않았다. 실제 녹화 결과로 단위 시험을 맞춘 것이 아니다.
