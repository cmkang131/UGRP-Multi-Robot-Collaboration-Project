# egomap39 — Ulrich 바닥 외형 분류와 시간 참조 큐

2026-10-08. 오프라인 only, physics/render/MuJoCo/model/lock0. PR405 DRAFT.
TensorBoard 생략 유지, 다른 worktree/PR406 수정0. 기본off·기존 출력 bytes 보존.

## 실행 전 사전 등록

- `contact_rule=floor_appearance_ulrich_v1`, 기본off. egomap37의 단일 프레임 방식과
  egomap38의 edge 연결은 그대로 보존한다. 이번에는 RGB HSI 외형으로 분류한다.
- **관문: 검출점 P≥.90 AND R≥.50.** seed31001에서만 개발 → 소스/설정/결과 해시
  동결 커밋 → seed32002 on1회 평가. 실패해도 재튜닝0. 두 녹화는 과거에 본 자료이며
  독립 미개봉 확증으로 부르지 않는다. 지도 절대기준 P≥.90/R≥.70/RMSE≤.15m도 기록.
- 원문 [Ulrich & Nourbakhsh, AAAI 2000 §3–7](https://www.cs.cmu.edu/~illah/PAPERS/abod.pdf)
  직접 확인. 이미지5×5 Gaussian → HSI → 전방 사다리꼴 H/I histogram → 평균필터.
  hue<60 또는 intensity<80 count이면 obstacle. 열별 최하단 obstacle 접점 사용.
- §5: 각 프레임 histogram+odometry를 candidate queue에 추가; 현재와 방향 차이
  >18° 항목 먼저 폐기, 위치 차이 >1m인 나머지를 reference queue로 이동.
  reference histogram의 허용 bin을 OR 결합. §6 assistive 모드(동적 참조만), 최근10개 유지.
  시작 학습 자료가 없으므로 queue가 차기 전은 미학습/검출 없음으로 기록한다.
  같은 프레임의 점/면 API는 공유 상태 캐시를 사용해 큐를 두 번 갱신하지 않는다.
- **원문에 형태학/작은 blob 제거는 없다.** §7은 추가 blob filtering을 하지 않았다고
  명시한다. noise 처리는 원문 Gaussian과 histogram 평균만; 새로운 opening/closing0.
  bin 수, histogram 평균 폭, HSI 유효 수치, 참조 폭은 원문 미명시다. 아래 값을
  논문값으로 주장하지 않고 기존 코드값/기하로 실행 전에 고정한다.

|항목|고정값·근거|
|---|---|
|처리 이미지|320×260(원문); native640×480 보정 후 resize, 분류mask는 nearest로 원 해상도 복원|
|HSI bins / 평균 폭|256 / 5bin, 기존 `wall_floor_boundary.py`의 수치; 원문 미명시|
|H 유효값|I>10/255, S>.1, 기존 수치; 원문 미명시. I=(R+G+B)/3|
|참조영역|차체 전방 x0–1m, 좌우±.30m; 깊이1m 원문, 폭은 기존 구현 고정|
|histogram 문턱|H60/I80 count, 원문. 정규화/사후 문턱 변경 없음|
|갱신|방향>18° 폐기 우선, 거리>1m 승격, 최근10개 OR; 원문 그대로|
|odometry 입력|own-controller의 발행 펄스 `predicted_delta`를 SE(2) 누적. GT/정합 pose 미사용|
|출력|기존96열/면 연결/positive_depth/4m 그대로. border/self 가림이면 해당 열 abstain|
|영상 유효영역|undistort support와 Gaussian5×5 support만; semantic morphology 아님|

변경 이유: 로봇의 카메라·FOV·높이가 논문 플랫폼과 달라 참조 사다리꼴은 명령 FK로
투영한다. RGB 크기 변환은 FOV를 바꾸지 않고 분류용 격자만 바꾼다. 논문의 encoder 대신
로봇이 아는 명령 DR을 쓴다. 메카넘 횡/후진에서도 원문의 두 수치 규칙은 바꾸지 않는다.
따라서 '지나간 곳은 안전' 가정과 DR 오차가 깨질 수 있으며 이를 평가에 기록한다.
참조에 체크 두 색이 실제로 들어가는지 histogram/RGB로 확인하되 색을 강제로 추가하지 않는다.

## 고정 평가

891 own-contact 프레임/seed. 원본 추정 자세와47/64 삽입 시각은 고정, RBPF 재추정0.
참조 갱신용 DR은 별도로 누적하며 지도 자세를 교체하지 않는다. off/on 공통으로 저장된
정합 후 공분산에서 기존 inverse_sensor confidence를 재계산(egomap37/38과 동일).
다중시점/segments 필터 off. 사용자가 요청한 칸 지도 평가를 주 비교로 한다.

점 P/R는 egomap38의 GT-body .15m 허용/프레임별96열 잠재가시 첫 벽 접점 분모 그대로.
GT는 예측 봉인 후 평가에만. 전체891프레임(미학습 포함) 관문, 학습 후 보조값은 따로.
지도 전체 P/R=coverage, 영역 P/R, 벽RMSE, 칸수 모두 보고. 전체 벽329표본·영역119/146.
과거 egomap34의32002 **영역P/R63.6/76.0%, 전체 coverage64.7%,381칸**과 분모를
맞춰 나란히 기록하며 영역 recall과 전체 coverage를 혼동하지 않는다.
테이프 FP와 체크/테두리 실패 예시는 평가용 RGB/기하 분류로 기록. 상위 예시와 고정
시간6분위 예시를 구분하고, 예시를 보고 옵션·문턱·참조영역을 바꾸지 않는다.

raw `/Users/changmin/projects/ugrp/outputs/ulrich-floor-contact-v1`.
소스/설정 커밋 후 실행, 관련1–3시험 통과 후에만 커밋·push. 감독 파일 단계마다 cat.
ENOSPC=HOST_ERROR, 원본/raw 삭제0, 다른 프로세스 변경0, 유료/원격 계산0.

## 31001 개발 결과와 동결

사전 등록 `9d7a8662`, 구현/예측 `e001b029`. 관련3시험 파일 **17 passed**.
검출 설정을 조정하지 않고 `freeze.json`의 코드·설정·개발 결과 해시를 커밋한다.
32002는 이 동결 커밋 이후 예측1회/평가1회만 수행한다.

|31001 조건|검출 P / R|검출점 수|영역 칸 P / R|전체 칸 P / coverage|점유 칸|벽 RMSE m|
|---|---:|---:|---:|---:|---:|---:|
|원본 지도(egomap34 계열)|—|—|56.8 / 52.1%|39.0 / 37.7%|359|.760|
|paired off|94.3 / 57.8%|53,232|57.5 / 52.1%|39.2 / 37.7%|357|.762|
|Ulrich on|7.9 / 2.4%|24,504|6.5 / 2.5%|22.7 / 4.6%|75|.783|

**검출 관문 실패(0/2 항목), 재튜닝0.** GT는 봉인 후 평가에만 읽었다.
원본 지도와 paired off의2칸 차이는 저장된 정합 후 공분산으로 confidence를 재계산한
동일 비교 절차 때문이며 off 검출기 변화가 아니다. off 면 출력은 원본 삽입47프레임
전부와 동일함을 assert했다. 검출점 P는 GT 차체 자세에서 측정하므로 지도 P와 다르다.

- 첫 학습39.5s, 미학습181/891프레임, 분류710, reference 승격57, 회전 폐기819.
  학습 후에도 P7.9/R3.0%라 초기 학습 지연만의 실패가 아니다.
- 거짓점22,571개: 체크19,756(87.5%), 색 구역2,815(12.5%), 테이프0.
  기존 off 테이프2,201→0이지만 바닥 경계가 대신 선택되어 recall은 회복되지 않았다.
- 승격57프레임의 참조영역 GT 희소 감사67,488표본은 전부 바닥이었다.
  이는 전체 픽셀의 완전한 의미분할 보증이 아니다. `31001-examples.jpg`의 f476은
  두 체크 색 근처 intensity bin을 배웠어도 중간 밝기 경계가 비바닥이 되는 예,
  f214는 과거 참조에 없는 색 구역, f219는 하단 자체가 비바닥으로 분류되어 기권한 예다.
  검출 edge 연산은0이며, 학습한 bin의 범위 밖을 막는 외형 분류의 실패다.
  논문 count 문턱을 우리 영상에 재적합하지 않았고 숫자를 바꾸지 않는다.
- 검출 있는 프레임891→395, 원본47 삽입 시각 중 비어 있지 않은 면47→22.
  원본의 `gmapping_range_v1`·`insert_selective_v1`은 on이며 이번에 RBPF/이동 관문은
  다시 실행하지 않았다: raw901→초기대기10→검출891→이동관문844→삽입47;
  bootstrap1/improved22/low_overlap8/high_residual14/search_boundary2.
  거부 후 삽입24, 거부 후 재표본0. 예전 egomap30의20프레임과 혼동하지 않는다.

![31001 실패 유형·분류mask·학습 histogram](figures/31001-examples.jpg)
![31001 고정 시간6분위](figures/31001-time-quantiles.jpg)

원문·코드 대응과 미공개 수치의 한계는 [REFERENCES.md](REFERENCES.md), 상세 분모는
`results/31001-comparison.json`, 유형은 `results/31001-diagnosis.json`에 기록했다.
