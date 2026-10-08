# egomap41 — 자기 지도 기억 내보내기와 쓸모 진단

2026-10-08 사용자 결정: **검출기 개선 중단**, egomap34 seed32002 구성 고정.
목표를 지도 품질(P≥.90/R≥.70/RMSE≤.15m)에서 **재위치 추정·목표 도달에 쓸 수
있는가**로 변경한다. 이는 결과를 보고 문턱을 낮추는 조치가 아니라 사용자의 목표
변경이다. 과거 품질 관문의 실패는 그대로 남고, 그 관문 없이 모듈 F를 구현한다.

## 실행 전 사전등록

- 원본: `outputs/wall-segment-dev-v1/new-seed`, 소스 `9ff00833`, seed32002.
  tape_v1/SEARCH/real_v1/rotL_v1/RBPF100/±20°/Manhattan/selective/insertion/
  switchable 구성과 원본 `grid.json`·64스캔을 바꾸지 않는다. 검출기 옵션은off.
  영역 P/R63.58/76.03%, 전체 덮임64.74%,381점유칸은 기존 값으로 별도 보존한다.
- 물리·렌더·모델·다른 로봇 지도·지도 합치기·잠금0. TensorBoard 생략 유지.
  raw는 `/Users/changmin/projects/ugrp/outputs/own-map-utility-v1`에 보존한다.
  ENOSPC=HOST_ERROR, 원본 삭제/덮어쓰기0. 결과 후 설정·문턱 변경0.

### A. F 인터페이스

`wall_export=segments_confidence_v1`, 기본off. 기존 격자를 **읽기만** 하며,
이미 있는 `OdomGrid.lines()`의 Hough/TLS·gap split로 자기 LLM용 상위 선분을
표현한다(지도·추정·navigation 변경0). 기존 segments_v1의 별도 지도 재적합은
이번에 켜지 않는다. 전체 내보내기와 상위K=6/ASCII UTF-8≤1024byte 요약을 분리한다.

- `source: own`, robot_id, 관측 ID/시각/원 RGB SHA256, 근거 스캔 수,
  관측자 추정 pose·위치 std, 자기 출발 프레임(x전방/y좌측/CCW+,m/rad).
- 선분 끝점, 근거 셀 수, 기존 TSDF support score와 관측 다양성.
  **support는 보정된 벽 정답 확률이 아니다.** 점유 log-odds를 confidence로 쓰지 않는다.
- 근거가 없는 선분은 confidence/source를 만들어내지 않고 명시한다.
  마지막/최대 관측 위치 std를 함께 표시해 부정확한 지도를 확정 사실로 쓰지 않는다.
- 자기 LLM snapshot 요약만 추가한다. 상대 메시지·배열 전송·merge API 추가0.
  off snapshot/기존 격자·RNG 상태 bytes 동일, 타 로봇 입력 거부 시험.
- 설계: [관측 기억 §4(b)](../../docs/design/2026-09-26-markerless-localization-and-memory.md),
  [arena-wall-map F](../2026-10-07-arena-wall-map/README.md#평가와-조건부-f-내보내기).
  과거 F의 품질 선행조건만 이번 사용자 결정으로 해제한다.

### B. 오프라인 쓸모 시험: 3쌍, 한 녹화의 회고적 재사용

탐색을 마친 **최종 지도**를 기억한 로봇이 위치를 잃은 상황을 모사해,
같은 녹화의 경과60/90/120초부터 끝180초까지 각각 재생한다.
PF RNG seed41001/41002/41003을 두 지도 조건에 동일하게 쓴다.
이미 지도에 쓰인 영상의 재사용이므로 **새 방문/독립 확증이 아니다**.
초기 pose·yaw는 각 지도 free 전체의 균등분포이며 저장된 현재 추정/GT pose,
출발 dock prior를 초기 입자에 넣지 않는다. 입력은 기존 자기 RGB에서 구한 실제
열 접점과 자기 명령뿐이다. 지도는 고정하고 재삽입/정합/새 검출을 하지 않는다.

1. **자기 지도:** 원본381점유칸/관측 free, 자기 시작 좌표.
2. **정답 정적 지도 기준선:** 녹화에 연결된 고정 벽/장애물 기하, 정적지도 좌표.
   사용자가 요청한 기준선 지도 입력만 허용한다. 실시간 GT pose/접촉은 평가 전용이다.
   두 조건은 같은 .1m 격자 표현이며 likelihood raster는 기존1cm 규약을 쓴다.
   자기 지도의 unknown은 초기 free 입자로 만들지 않는다. 지도 면적 차이를 보고한다.

기존 PR406 `2fa4bf9a0e8097bcd4d1e1933b7d04e4d54dd965`의 AMCL/KLD 핵심 함수를
읽기 전용으로 복사해 재사용한다(#406 파일 수정0): likelihood_field의 거리/우도,
augmented_start의 belief_report·Policy, kld_start의 sample_limit/assign/resample/Policy.
출처 파일·행·해시를 기록한다. S2 전체 Runtime을 이식했다고 주장하지 않는다.

- 원본 수치: KLD2000–100000입자, ε=.05/confidence=.99, bin .5m/.5m/10°;
  recovery αslow=.001/αfast=.1, ESS≤N/2; hit/random=.5/.5, σhit=.2m,
  max거리100m·거리장2m·60beam 정수 stride; 이동 관문 .25m/.2rad.
- 카메라 접점은 egomap34의 positive-depth/4m 검출 그대로. 명령 평균은rotL_v1,
  잡음은 기존 `rbpf_rejection.motion_variance`의 RGB 간격값. 모션 재적합0.
- 필요한 어댑터 차이: 벽 사각형 대신 자기 격자도 거리장 입력으로 받고,
  실제RGB열/명령을 녹화로 공급한다. 글로벌 재위치 진단 동안 KLD 정책을 유지한다
  (S2 운반 Runtime의 첫 base motion→고정2000 handoff/active pan 제어는 실행하지 않음).

#### 판정(결과 전 고정)

- 내부 수렴: 기존 `belief_report.resolved`가 연속5개 RGB(1초)에서 true.
  정답 수렴: 그5개가 모두 평가 XY≤.25m, |yaw|≤10°. 첫 시간/오차,
  거짓 내부 수렴, 종료·경로 오차와 σ를 모두 기록한다. GT로 필터를 멈추거나 수정하지 않는다.
- 재위치 쓸모: 정적 기준선 정답 수렴≥2/3이어야 비교가 유효하다. 자기 지도는
  수렴 건수 열세 없음, 공통 수렴 건의 XY 중앙오차≤정적의2배, 수렴시간 중앙값≤2배,
  거짓 수렴0. 공통 수렴0이면 비율은 미정이며 통과가 아니다.
- **감독11:2x 지시 반영(평가 전): 목표는 '탐색 중 본 B 바닥 구역으로 돌아가라'.**
  이전 커밋의 종료 칸 목표를 폐기한다. 자기 지도 목표는 기존 floor_color_v3의
  `own-controller.jsonl.goal`에서 **처음 locally_confirmed_region이 된 후보**의
  그 시각 중심을 사용하고 관측ID·시각·RGB해시를 연결한다(동률은후보ID순).
  기존 자기 카메라 검출을 재사용하며 GT 정렬로 자기 목표를 만드는 행위는 금지한다.
  정적 기준선 목표는 같은 개체 B의 정적지도 region 중심이다. 미관측이면
  '목표 미관측'으로 별도 집계하며 GT 위치로 채우지 않는다.
- 기존 public_ros_v8 NavFn/costmap으로 각 내부 수렴시 처음 목표 경로를 요청한다.
  허용 unknown을 유지하고, 경로의 실제 벽/footprint 충돌은 평가에서만 별도 센다.
  목표 선언은 자기 추정이 자기 조건의 목표≤.20m이고 내부 수렴할 때; 같은 시각
  GT 차체 중심이 정적 B region 안이면 '녹화상 올바른 도달 선언', 아니면 거짓 선언이다.
  부분 관측 중심과 정적 영역 중심 차이도 보고한다. 올바른 도달률 열세 없음·거짓0을 고정한다.
- **한계:** 녹화 명령은 두 조건 모두 같고 새 경로를 따라 움직이지 않는다.
  따라서 경로 있음/녹화상 선언은 반사실적 폐루프 목표 도달 성공이 아니다.
  실제 목표 도달률은 오프라인만으로 검증 불가로 남긴다. 둘 다0인 선언률을
  '열세 없음'만으로 쓸모 통과라 하지 않고 기준선 올바른 선언≥1/3을 요구한다.
  물리 제안은 재위치·녹화상 도달·경로 충돌0 조건이 모두 맞을 때만1회 추천,
  아니면 실패 원인에 맞는 다음 오프라인 점검만 제안한다. 이번 물리는 무조건0.

관측·입자 수,지도 free/occupied칸·면적, 기존 전체/영역 coverage 분모를 함께 보고한다.
각 예측을 먼저 봉인한 뒤 GT 궤적을 채점한다. 예측 API에는 GT 키/파일 인자 없음.

## 출처

- [Fox2001 KLD-Sampling 원문](https://papers.nips.cc/paper_files/paper/2001/hash/c5b2cebf15b205503560c4e8e6d1ea78-Abstract.html).
- Nav2 AMCL 원본 `235fc5ce55bdf94d9be360fdbca39d89dc0e4f74`의 pf.c 및
  likelihood_field_model.cpp, PR406의 기존 이식/라이선스/변경점 명시를 계승.
  웹 blob 열람은 cache miss였고 실제 재사용 코드는 위 고정 Git 객체에서 확인했다.
- 신뢰도: 기존 `harness/self_wall_evidence.py`의 Cartographer TSDF 관측 support(확률 아님).
- 경로: 기존 `harness/public_navigation_monitor.py`, `UnknownNavigator.plan_to`,
  NavFn C++와 ROS inflation. 새로운 제어기/경로 추종은 만들지 않는다.

## 구현 연결 (결과 전)

`harness.self_wall_memory_robust.SelfWallMemory(..., wall_export="segments_confidence_v1")`의
`export_wall_memory()`가 전체 로컬 JSON을 반환하고 `snapshot()`에는
`self_wall_export_text` 요약만 추가한다. 기존 자기 지도 옵션들은 그대로 필요하다.
`observe_wall(..., observation_id=..., frame_sha256=...)`로 실제 RGB 출처를 연결한다.
제공하지 않은 해시/std는 null이며 만들어내지 않는다. 선분 ID는 지도 revision별 ID라
관측이 바뀌었는데 같은 의미인 척하지 않는다. 원본 관측 ID는 유지된다.

저장 녹화에서는 `export_walls(grid, ledger, robot_id=..., wall_export=...,
observations=..., pose_covariance=..., now=...)`를 직접 사용한다. 기존 Hough 요약의
지지 셀과 현재 양의 점유칸 주변 반대각선 거리 안의 과거 ray endpoint를 출처로
연결한다. 이 근접 연결 자체가 참 벽 검증은 아니며 전부 명시적 후보이다.

PR406 원본 함수·행별 해시: [provenance.json](../../harness/own_map_amcl_vendor/provenance.json),
[이식 경계](../../harness/own_map_amcl_vendor/NOTICE.md). 새 외부 의존성/venv0.
기존14 기억 시험과 새8 시험(실제 비어 있지 않은 off snapshot/RNG·출처·peer 격리,
KLD 원본 정의/상수·이동 관문·균등 prior·B 관측 목표)만 실행한다.
