# speedctrl2 — 정합 성장·타이머 밖 비용·무손실 기록

main `77eba22c`/PR #423 이후의 저장 입력 개발 진단이다. **새 ABBA 측정은 아직 미실행**이며,
이 문서는 실행 전 계획이다. 이전 off/on의 부하 평균 4.8/2.9가 달라 절감률을
공정한 속도 증거로 재사용하지 않는다. 물리 근사·입자 감소·새 관측 생략은 적용하지 않는다.

## 확인한 병목과 적용 범위

- frontend 정합은 이미 ±0.5m, pose-graph 정합은 ±1m의 고정 탐색 창이다.
  늦은 cProfile 창에는 과거 submap×scan 정합 32,056회/194.753초가 있다.
  지도 칸 합계와 비용의 동반 증가는 관찰됐지만 지도 면적에 대한 선형 비례는 증명하지 않았다.
  기존 8192 pair/64 field 캐시를 바꾸면 실행 진단 카운터까지 달라진다.
  별도의 유한 순수 결과 캐시로 원래 카운터·lazy field 생성·후보·동점 순서를 유지한다.
  pair 항목은 128MiB 추정 상한과 weak owner 참조, 각 field cache는 64MiB 상한을 둔다.
- 정확한 거리장은 최근접 장애물 witness로 추가/삭제의 영향을 추적한다.
  제거한 장애물을 최근접으로 쓰던 모든 칸을 갱신하며, 영향이 큰 경우 원래 전체 EDT로 fallback한다.
  원래 거리는 무한 범위이므로 임의의 dirty halo로 잘라 갱신하지 않는다.
  전체 rebuild도 EDT 한 번에서 거리와 witness를 함께 얻어 계산을 중복하지 않는다.
  확률장은 같은 geometry에서 값이 바뀐 칸만 원래 scalar sigmoid로 계산한다.
- `UGRP_CONTROLLER_SCAN_SPEEDUPS=exact-v2`가 후보 기본이며 `off`는 #423 경로다.
  부모 `UGRP_CONTROLLER_EXACT_SPEEDUPS=off`는 모든 가속을 끈다. 실행 기록에 설치·fallback·통계를 남긴다.
  source/API guard가 불일치하면 원래 계산을 쓴다. 기본 채택은 전체 논리 바이트 증명 이후 판정한다.
- `UGRP_CONTROLLER_LOCAL_SUBMAP_M=0`이 기본 off다. 양수는 기존 후보 거리 상한을 줄이므로
  **결과가 바뀔 수 있는 별도 옵션**이다. 2m 비교는 동결 입력·명령의 추정 궤적 차이로 보고하며
  재생 이후에만 eval_only trajectory/초기 spawn으로 절대 RMSE를 평가한다.
  온라인 정확도나 새 임무 성공으로 표현하지 않는다. 기존 ±1m scan 탐색 창 자체는 유지한다.
- S3의 `vision` 경계는 OpenCV 관측/경계 검출이며 실행 중 영상 인코딩이 아니다.
  저장 S3 각 로봇 439장과 ego59 55003의 2461장 JPEG는 각 로봇 내 해시가 모두 다르다.
  제어 관측을 오프라인으로 옮기거나 원본 프레임을 중복이라고 제외하지 않는다.
- `controller_other` 내부를 receive/step/명령 기억, provider 보고·pose estimate·cache key,
  visibility geometry/likelihood, raytrace/costmap/export/forecast/바닥·벽 검출로 나눈다.
  프레임 해시/디코드, 상태·RNG 증명, 계측 기록도 별도 exclusive 타이머에 둔다.
  cProfile은 처음·마지막 100프레임과 초기화/최종 직렬화만 계측한다.
- S3 v151 종료 심판에서 과거 이벤트 실행 키를 매번 전부 검증하는 N(N−1)/2 비용도 발견됐다.
  [s3fix6 진단](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/423#issuecomment-6091325311)은
  다른 작업의 표본이며, 기존 v148 제어기 ‘기타’와 동일한 구간으로 합산하지 않는다.
  공통 가속의 `UGRP_REFEREE_EVENT_SPEEDUPS=owned-v1`(기본 on, `off`로 해제)은 source-guarded
  심판이 새로 만든 private 기록만 append-only 소유한다. 새 키는 매번 검증하고 snapshot은 deep copy다.
  외부 mutable list의 과거 키 검사와 가져온 기록의 전체 key/sequence/hash-chain replay는 원래대로다.
  close 시 살아 있는 심판을 원래 private list로 되돌린다. 심판 정답은 제어에 전달하지 않는다.

## ABBA 계획과 채택 기준

[plan.json](plan.json)의 S3 v148, ego59 55001/55003을 각각 **A→B→B→A**로 직렬 재생한다.
A는 #423 exact-v1/scan off/referee off/plain 기록,
B는 exact-v1/scan exact-v2/referee owned-v1/gzip-v1 기록이다.
속도 ABBA는 cProfile 없이 구간 타이머만 사용하며, 이후 별도 B 전체 재생에서 cProfile을 얻는다.
profile 재생도 ABBA B와 논리 바이트를 직접 비교한다. profiler overhead를 속도 표에 혼합하지 않는다.
이 비교는 정합과 저장 변경을 함께 측정한다. 직렬화·버퍼 flush·gzip footer·파일 hash까지
실행 wall에 포함한다. 구간 계측으로 저장 쓰기 비용과 정합 효과를 구분한다.
물리/렌더는 실행하지 않으며 **controller-only wall/input-SIM**이다. 온라인 ≤1.5 달성 주장과 구분한다.

S3 v151 결과 파일과 명시적인 PR 순번 반환의 해시 receipt를 확인한 뒤 agent_lock을 취득한다.
v151의 완료 심판 이벤트에 대한 별도 A→B→B→A도 4회 실행하고, 심판 record 전체 복원 bytes를 비교한다.
이 입력은 source `3ec2d781`의 별도 종료평가 자료이며 v148 제어기 재생 수치에 합산하지 않는다.
다른 잠금/프로세스를 해제·종료하지 않는다. 유한 예산 6시간, 각 재생 상한 90분, 반복은 1 ABBA 묶음이다.
프레임별 1/5/15분 부하 평균을 기록한다. 두 교차 쌍과 A/B 평균 모두
`|load_A-load_B| <= max(0.5, 0.25*min(load_A,load_B))`인 경우만 절감률을 보고한다.
부하 평균은 스케줄링·캐시 상태의 완전한 통제가 아니며, 이 기준 미달이면 비교 불가로 남긴다.

3개 S3/20개 ego 행동 산출물의 **복원 후 전체 바이트를 직접 비교**한다.
명령·추정 자세·프레임별 입자 배열 지문·RNG 상태·최종 입자 지도 및 원본 입력 해시를 포함한다.
압축 저장 바이트는 의도적으로 달라지며 논리 SHA/크기와 저장 SHA/크기를 따로 보존한다.
지연/타이머/프로파일/출처/storage receipt만 제외한다. 실패·불완전 callback은 성공으로 판정하지 않는다.
55003 원본 HOST_BUDGET의 미완료 마지막 callback을 만들지 않고 기존 완료 접두 경계를 유지한다.

## 기록과 디스크

`--record-storage gzip-v1`은 명시적 opt-in이다. 동일 JSON serializer의 UTF-8 바이트를
64KiB 버퍼와 gzip level1/mtime0으로 기록한다. 기존 직접 `.json` reader와의 호환 때문에 기본은 plain이다.
`harness.lossless_recording.logical_open`으로 plain/gzip을 읽고 둘 다 있으면 모호함을 거부한다.
압축은 새로운 파생 실행 기록에만 적용하며 **기존 raw·프레임·영상·해시는 수정/삭제하지 않는다**.
따라서 이 시험이 과거 프로젝트 디스크 점유를 이미 줄였다고 주장하지 않는다.
[디스크 관리](../../docs/disk_management.md)의 보존 등급과 10GiB 여유 조건을 지킨다.
raw는 기본 checkout outputs 아래에, 작은 표·해시·실패 기록은 이 실험 폴더에 저장한다. Drive는 사용하지 않는다.

표준 관리 workflow `controller-replay-abba`가 각 `controller-replay-profile` 실행 기록을 연결한다.
커밋 SHA를 고정하고 바뀐 모듈 시험만 돌린다. 완료/실패 결과는 새 TensorBoard snapshot으로 전달한다.

## 참고 자료

- [Olson, ICRA 2009](https://april.eecs.umich.edu/media/pdfs/olson2009icra.pdf): prior 주변 유한 탐색과 다해상도 정합.
  우리의 exact 캐시는 후보/점수를 바꾸지 않으며 논문의 다해상도 구현을 완료했다고 주장하지 않는다.
- [Cartographer FastCorrelativeScanMatcher2D](https://github.com/cartographer-project/cartographer/blob/master/cartographer/mapping/internal/2d/scan_matching/fast_correlative_scan_matcher_2d.cc):
  submap 확률장·유한 검색·branch-and-bound. 해당 구현의 양자화 점수로 원래 float 점수를 대체하지 않는다.
- [Cartographer 알고리즘 설명](https://google-cartographer-ros.readthedocs.io/en/latest/algo_walkthrough.html):
  local SLAM은 현재 submap으로 정합하고 global SLAM은 가까운 과거 node/submap의 loop constraint를 찾는다.
- [Nav2 AMCL map_cspace.cpp](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/map/map_cspace.cpp):
  거리 lookup cache와 likelihood-field 구성. 이 파일 자체는 dirty-cell 증분 EDT 구현이 아니다.
- [OctoMap DynamicEDT3D](https://github.com/OctoMap/octomap/blob/devel/dynamicEDT3D/include/dynamicEDT3D/dynamicEDT3D.h):
  obstacle witness/정수 제곱거리·추가/삭제 갱신의 공개 구현. 우리의 2D 증분은 float64 전체 EDT와 바이트 대조한다.
- [SciPy 1.17.1 EDT 원문](https://github.com/scipy/scipy/blob/v1.17.1/scipy/ndimage/_morphology.py):
  feature transform으로 거리와 최근접 index를 함께 반환한다. 동일 sqrt/multiply 순서를 유지한다.
- [Fowler Event Sourcing](https://martinfowler.com/eaaDev/EventSourcing.html),
  [Python deep copy](https://docs.python.org/3.12/library/copy.html): append-only 이벤트의 소유와 snapshot 격리.
  private producer만 새 이벤트를 검증하며 외부 mutable 기록의 기존 전체 검증은 생략하지 않는다.
- Thrun, Burgard, Fox, *Probabilistic Robotics* 4·6·8장: PF·likelihood field·occupancy grid의 표준 근거.
  판본 원문은 이번 실행에서 별도로 확인하지 않았으며 장별 내용은 #423의 기존 참고 범위를 승계한다.
