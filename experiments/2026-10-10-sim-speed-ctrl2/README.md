# speedctrl2 — 정합 성장·타이머 밖 비용·무손실 기록

main `77eba22c`/PR #423 이후의 저장 입력 개발 진단이다. 첫 소스 `c35cd553`에서
S3·55001 ABBA와 55003 단일 A가 완료됐고, S3 연구 순번을 위해 큐를 반환했다.
**후속 후보 측정은 아직 미실행**이다. 이전 off/on의 부하 평균 4.8/2.9가 달라 절감률을
공정한 속도 증거로 재사용하지 않는다. 물리 근사·입자 감소·새 관측 생략은 적용하지 않는다.

## 확인한 병목과 적용 범위

- frontend 정합은 이미 ±0.5m, pose-graph 정합은 ±1m의 고정 탐색 창이다.
  늦은 cProfile 창에는 과거 submap×scan 정합 32,056회/194.753초가 있다.
  지도 칸 합계와 비용의 동반 증가는 관찰됐지만 지도 면적에 대한 선형 비례는 증명하지 않았다.
  기존 8192 pair/64 field 캐시를 바꾸면 실행 진단 카운터까지 달라진다.
  별도의 유한 순수 결과 캐시로 원래 카운터·lazy field 생성·후보·동점 순서를 유지한다.
  pair 항목은 128MiB 추정 상한과 weak owner 참조, 각 field cache는 64MiB 상한을 둔다.
  첫 재생 후 확인한 miss 경로의 중복 field 해시를 없애 새 pair는 post-state 한 번만
  해시한다. per-pair submap segment 원본 바이트도 32B 지문으로 바꾸고 지문/키/결과를
  메모리 추정에 포함한다. 기존 pair 결과를 바꾼 채 재사용하지 않고 현재 field 지문을 검증한다.
- 정확한 거리장은 최근접 장애물 witness로 추가/삭제의 영향을 추적한다.
  제거한 장애물을 최근접으로 쓰던 모든 칸을 갱신하며, 영향이 큰 경우 원래 전체 EDT로 fallback한다.
  원래 거리는 무한 범위이므로 임의의 dirty halo로 잘라 갱신하지 않는다.
  전체 rebuild도 EDT 한 번에서 거리와 witness를 함께 얻어 계산을 중복하지 않는다.
  확률장은 같은 geometry에서 값이 바뀐 칸만 원래 scalar sigmoid로 계산한다.
- `UGRP_CONTROLLER_SCAN_SPEEDUPS=off`가 기본이며 #423 경로다. `exact-v2`는 명시적 비교 옵션이다.
  첫 55001 ABBA가 바이트는 동일하지만 1.363→1.406 wall/input-SIM으로 느려 기본 채택하지 않는다.
  부모 `UGRP_CONTROLLER_EXACT_SPEEDUPS=off`는 모든 가속을 끈다. 실행 기록에 설치·fallback·통계를 남긴다.
  source/API guard가 불일치하면 원래 계산을 쓴다. 새로운 기본 가속은 전체 논리 바이트 증명 이후 판정한다.
- `UGRP_CONTROLLER_LOCAL_SUBMAP_M=0`이 기본 off다. 양수는 기존 후보 거리 상한을 줄이므로
  **결과가 바뀔 수 있는 별도 옵션**이다. 2m 비교는 동결 입력·명령의 추정 궤적 차이로 보고하며
  재생 이후에만 eval_only trajectory/초기 spawn으로 절대 RMSE를 평가한다.
  raw frontend와 기록된 시각부터만 적용하는 online map→odom 자세를 별도로 비교한다.
  두 GT 파일은 원본 manifest 해시를 검증한다. graph 제한은 frontend PF/RNG를 직접 바꾸지
  않으므로 frontend 오차가 같아도 map-frame 오차·지도·생성 명령은 달라질 수 있다.
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
- `UGRP_CONTROLLER_VISIBILITY_SPEEDUPS=shared-v1` 후보 기본 on/`off`로 해제한다.
  기존 Visibility 인스턴스 캐시는 그대로 두고 pure `shadow_depths`의 실제 origin·rays·상자
  형상 바이트가 같은 경우만 공유한다. C-contiguous/aligned float64와 고정 source guard,
  8항목/64MiB 추정 상한을 적용하며 반환 배열은 복사한다. 연산·후보·마스크는 바꾸지 않는다.
  불지원 layout·큰 입력·slab 함수 변경은 원래 계산이다. 후보 속도/전체 바이트 검증은 대기 중이다.
- 심판 소유 기록 생성자는 입력 첫 행도 deep copy하고 2행 이상의 외부 기록을 거부한다.
  기존 caller alias가 내부 과거 행을 바꾸는 경로를 차단한다. 외부 list append/import 검증은 유지한다.
- 후속 interval 타이머는 `bind()`가 복사한 private globals의 pure helper도 계측한다.
  cvtColor·remap을 `rgb_preprocess`로 분리해 중첩 vision/receive에서 exclusive 비용을 뺀다.
  타이머는 새 인터프리터에만 적용하며 새 후보 전체 재생의 행동 바이트로 계측 불변성도 확인한다.
  독립 검토에서 발견한 `rgb_preprocess` snapshot 카테고리 누락을 측정 전에 고쳤다.
  중첩 vision/RGB 구간의 exclusive 합계가 전체 구간을 보존하는 반례 시험을 추가했다.
  S3 우선 실행은 DEV_DELIVERED/DEV_NOT_DELIVERED/HOST_ERROR의 종료 상태와 명시적 반환을
  함께 확인한다. 실패한 종료와 실행 중 상태를 구분하며 RUNNING/무상태 결과를 거부한다.
  각 adapter의 모든 Python 파일 이름/내용 지문을 ABBA 계획에 고정하고, 매 자식의 시작·종료
  및 다음 자식 전 다시 검증한다. 기존 adapter pyc를 읽지 않고 동결 Python 소스를 로드한다.
  `adapter-source.json`/result에 지문·파일 목록을 남긴다. 이 출처 검증 시간은 controller wall
  밖이며 별도 기록한다. 이전 c35 자료의 adapter 지문은 미기록으로 구분한다.

## 첫 측정과 순번 반환

raw: `/Users/changmin/projects/ugrp/outputs/speedctrl2-20261010-v1`, source `c35cd553`.
이 수치는 controller-only이며 physics/render 0회다.

| 입력 | A wall/input-SIM | B wall/input-SIM | 복원 행동 바이트 | 부하 판정 / 절감률 |
|---|---:|---:|---|---|
| S3 v148 | 1.971245 | 1.966085 | 3파일 모두 동일 | 교차 부하 실패 / 미보고 |
| ego59 55001 | 1.363485 | 1.406348 | 20파일 모두 동일 | 기준 통과 / -3.144% |
| ego59 55003 | 3.959559 | 미실행 | 단일 A, 후보 비교 없음 | ABBA 미완료 / 제외 |

55001 입자 수는 100→100, 지도 칸은 0→236377이다. A의 처음/마지막 100프레임
scan-match 평균은 0.00809→0.15481s/frame이며 B는 0.00912→0.16473이다.
정합 캐시 hit 0/12059 miss였고 scan_match 합계는 A 약0.387/B 약0.420 wall/input-SIM이다.
55001 행동 기록 380993680 논리 바이트는 gzip 저장 102624707 바이트(약73.1% 감소)다.
직렬화·압축·flush·footer·hash 비용은 wall 및 record_io에 포함된다.

S3 B의 ‘기타’ 분해는 visibility_geometry 0.441, receive 잔여0.352,
pose_estimate 0.160, cache_key 0.021, belief_report 0.005 wall/input-SIM이다.
55001은 raytrace0.164, costmap0.156, floor0.122, wall0.099, forecast0.068,
receive 잔여0.205로 나뉜다. 새 RGB/private binding 타이머로 잔여를 더 확인한다.

연구 S3의 순번 요청 뒤 상위 큐 PID57475만 일시 대기시켰고, 진행 중인
55003 A가 2460 완료 콜백/491.8 input-SIM을 전부 끝내고 자식이 종료한 경계에서
큐를 SIGINT/SIGCONT로 정상 종료했다. `abba.json`의 complete=false/KeyboardInterrupt를
그대로 보존한다. 이 취소는 완료된 자식의 입력 실패가 아니며 불완전 55003 ABBA를 채택하지 않는다.
잠금 반환/NI0/원본 보존 기록은 `outputs/speedctrl2-20261010-control-v3/handoff.json`과
[순번 반환 댓글](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/424#issuecomment-6092099201)에 있다.

후속 후보의 miss 해시/메모리 경로가 두 ego 사례 모두에 영향을 주므로 세 입력을
**동일한 새 SHA의 연속 ABBA**로 다시 측정한다. 이전 source·4회 수치는 진단 자료로
보존하며 최종 후보의 새 부하 조건 speedup으로 재표현하지 않는다.
별도 cProfile·기본 off local2m·종료 심판 ABBA는 새 S3 스모크와 무거운 사후 작업이
완료·순번 반환된 다음 수행한다. 새 후보는 아직 온라인 ≤1.5를 달성했다고 주장하지 않는다.

## ABBA 계획과 채택 기준

[plan.json](plan.json)의 초기 계획은 S3 v148, ego59 55001/55003 각각 **A→B→B→A**였다.
순번 반환 이후의 새 전체 비교 범위와 SHA는 각 실행의 plan/measurement_source에 남긴다.
A는 #423 exact-v1/scan off/referee off/plain 기록,
B는 exact-v1/scan exact-v2/referee owned-v1/gzip-v1 기록이다.
후속 후보는 A visibility off/B shared-v1도 비교한다.
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
- [Thrun, Burgard, Fox, *Probabilistic Robotics*, MIT Press](https://mitpress.ublish.com/book/probabilistic-robotics):
  출판사 목차에서 4장 비모수 필터, 6장 로봇 지각, 8장 격자/Monte Carlo 위치 추정을 확인했다.
  PF·likelihood field·MCL의 참고 범위다. 점유 격자 mapping은 9장으로 바로잡는다.
  장 본문 전체를 새로 검증한 인용으로 표현하지 않는다. 입자 축소/KLD는 이번 후보에 적용하지 않았다.
## 032c2167 후속 실행 중단과 재개

고정 후보의 `outputs/speedctrl2-20261010-v2`는 S3/55001 ABBA 8자식 뒤,
55003 첫 A의 마지막 flush된 `t=145.7`에서 관리 세션이 SIGTERM/143으로
종료됐다. 발신자는 확인하지 못했다. `abba.json`과 `lock.json`은 미생성 상태로
보존하며 완료로 바꾸지 않는다. 종료 기록은
`outputs/speedctrl2-20261010-control-v7/termination.json`이다.
공용 잠금 기록은 PID2362가 죽은 뒤 stale 해제됐음을 보여 준다.
다른 연구가 살아 있는 잠금을 바꿨거나 측정이 겹쳤다는 초기 추정은 정정했다.
이 확인 과정에서 프로세스에 보낸 신호는 0회다.

완료된 S3의 3파일/55001의 20파일은 직접 복원 바이트·입력·입자/RNG·어댑터
지문이 같았다. S3 A/B는 1.98349/1.68258 wall/inputSIM이지만 교차 부하 실패로
절감률을 판정하지 않는다. 55001은 부하 기준을 통과했고 A/B
1.36002/1.39911, **B가 2.87% 느렸다**. 따라서 스캔 캐시는 기본 off를 유지한다.
55001의 논리 기록 380,993,680바이트는 gzip 102,624,707바이트로 줄었으며
쓰기·flush·해시를 포함한 I/O는 평균 .0263/.0312 wall/inputSIM이다.
이는 제어기 재생 수치이며 온라인 물리 wall/SIM 개선률이 아니다.

실행기는 TERM/HUP를 기록 가능한 예외로 바꿔 기존 실패/정리 경로를 실행하고,
그 정리 동안 반복 신호를 무시한 뒤 원래 핸들러를 복원한다.
잠금 해제는 owner뿐 아니라 branch/PID/취득 시각까지 현재 lease와 같을 때만
시도한다. SIGKILL·프로세스 크래시의 기록 보장은 없다.
제어기 수학과 캐시 구현은 변경하지 않았다.
중단 시 관리 CLI에 TERM을 전달하고 그 CLI가 소유 워커를 정리한 뒤에만
상위 잠금을 해제한다. `subprocess.run`이 예외 때 CLI만 즉시 죽이는 경로를
피하며 관리 계층의 기존 유한 timeout과 그룹 정리를 따른다.
근거: [Python signal](https://docs.python.org/3.12/library/signal.html),
[subprocess의 세션·표준입출력 관리](https://docs.python.org/3.12/library/subprocess.html).
새 실행은 원본을 보존하는 `outputs/speedctrl2-20261010-v3`에서 연구 순번
반환 뒤 세 입력 모두 같은 새 후보의 ABBA로 재개한다. 이 S3 묶음이 사전에
고정한 단 한 번의 부하 재측정이며, 통과할 때까지 추가로 반복하지 않는다.

독립 검토에서 관리 실행기의 Popen 생성과 신호 핸들러 등록 사이 경합을
찾았다. 핸들러를 먼저 등록하고, Popen이 반환되기 전 신호는 보류해 자식
핸들을 받은 뒤 소유 그룹을 정리한다. 정리 중 반복 신호를 무시하고 원래
핸들러를 복원한다. 생성 중 신호 주입·timeout·자손 정리·manifest 보존의
변경 범위 5시험이 통과했다. 제어기/기록 모듈 수학은 그대로다.
