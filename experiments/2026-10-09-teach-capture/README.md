# egomap53 — teach 단계의 연속 keyframe 기록

## 참고 자료 — 코드 변경 전 확인

- [Furgale & Barfoot 2010 JFR, DOI10.1002/rob.20342](https://onlinelibrary.wiley.com/doi/10.1002/rob.20342), [저자 프로젝트 원문 설명](https://asrl.utias.utoronto.ca/~ptf/JFR_VTnR/): teach에서 스테레오 영상을 기록해 서로 겹치는 지역 지도를 연결하고 repeat에서 지역 지도에 위치를 맞춘다. 전역 일관 지도를 요구하지 않는다. 이번에 출판사 원문 초록/저자 설명은 확인했지만 전문 PDF 링크는401/404라 본문 전체 검증은 미완료다. 아래 구현 수치/분기는 논문에 임의 귀속하지 않고 직접 확인한 공개 소스에서 가져온다.
- VT&R3 **`bdb40d8ad22f02094507cc0924af8622e1ed796c`**, Apache-2.0(라이선스/파일SHA는 references에 보존). [카메라 설정](https://github.com/utiasASRL/vtr3/blob/bdb40d8ad22f02094507cc0924af8622e1ed796c/config/bumblebee_grizzly_default.yaml#L300-L309): min_distance .05m, min_creation .30m, max_creation2m, rotation min3°/max20°, stereo inlier min50/fail15. 헤더 기본(.2m/2°/1m)과 실행 YAML(.3m/3°/2m)이 다름을 구분하고 **카메라 YAML**을 고정한다.
- [SimpleVertexTestModule](https://github.com/utiasASRL/vtr3/blob/bdb40d8ad22f02094507cc0924af8622e1ed796c/main/src/vtr_vision/src/modules/odometry/simple_vertex_test_module.cpp#L50-L150): 첫 프레임 vertex; 상대 SE(3) log 이동/회전량, 작은 이동은 candidate, 큰 불연속은 odometry failure, 거리/회전/특징 수 조건으로 vertex. [StereoPipeline](https://github.com/utiasASRL/vtr3/blob/bdb40d8ad22f02094507cc0924af8622e1ed796c/main/src/vtr_vision/src/pipeline.cpp#L88-L119): 실패 시 prior로 되돌리고 보관 candidate를 keyframe으로 승격. [Tactic](https://github.com/utiasASRL/vtr3/blob/bdb40d8ad22f02094507cc0924af8622e1ed796c/main/src/vtr_tactic/src/tactic.cpp#L985-L1008): 새 vertex와 직전 vertex 사이 temporal edge를 저장.
- 반복 실패: [Tactic](https://github.com/utiasASRL/vtr3/blob/bdb40d8ad22f02094507cc0924af8622e1ed796c/main/src/vtr_tactic/src/tactic.cpp#L963-L967)는 정합 실패 시 graph/chain 갱신을 하지 않는다. [BaseMPCPathTracker](https://github.com/utiasASRL/vtr3/blob/bdb40d8ad22f02094507cc0924af8622e1ed796c/main/src/vtr_path_planning/src/mpc/base_mpc_path_tracker.cpp#L130-L136)는 isLocalized=false면 zero command, [BasePathPlanner](https://github.com/utiasASRL/vtr3/blob/bdb40d8ad22f02094507cc0924af8622e1ed796c/main/src/vtr_path_planning/src/base_path_planner.cpp#L97-L102)는 odometry failure에도 zero command. 성공한 관측 뒤만 path tracking 재개. 회복을 위해360° 돌라는 규칙은 아니다.

### 우리 제약에 필요한 변경만

단안 wrist RGB+기존 own-submap CSM/명령 오도메트리를 쓰므로 stereo feature/VO를 새로 이식하지 않는다. stereo inlier50/15는 벽 끝점 수와 단위가 달라 적용하지 않고, 기존 CSM 최소6점·수락 판정은 그대로 쓴다. keyframe 생성은 위 **SE(2) log 거리/회전 분기**를 사용한다. 원본은 VO failure에서 candidate로 복구하지만 사용자는 복구 구간 기록을 버리지 말라고 했으므로, 그 candidate와 현재 프레임을 보존하고 temporal edge를 `uncertain`으로 표시한다. 실패를 성공 제약으로 바꾸지 않는다.

일반 복구/후진/회전 상태에서도 recent 지역 관측과 연속 엣지를 끊지 않는다. 엣지에는 구간의 자기 상태·공분산·중간 자세를 보존; GT 접촉으로 연결을 고르지 않는다. 같은 장소라는 추측으로 지름길/루프를 새로 연결하지 않고 **실제 시간순 기록 엣지만** 따라간다. 로컬 CSM은 eg52 nearest5/기존 판정을 재사용하고, 실패 시 새 회전 없이 현재 RGB로 재시도하며 zero command. 정상 teach 중에는 추가 정지/회전0, 기존 frontier 명령을 바꾸지 않는다. 기존360° sensor_sweep을 추가하지 않는다.

## 실행 전 사전등록

- 옵션 **`teach_capture=vtr_keyframes_v1`**, 기본off. off는 기존 객체/trace/입자/RNG 바이트 동일. eg51/52 보존. 기존 eg49/47 탐색+eg48 가속·벽 검출 eg34·tape·SEARCH·real_v1·rotL·RBPF100/graph/switchable·360초 탐색 동결. 귀환은 시간순 traversal graph의 forward-only 추종, 실패 정합에 pose/공분산 보정0; B blacklist0.
- 키프레임: 자기 RGB 원본 참조(frame ID/SHA), 16×12 요약, 자기 추정 pose/covariance, 최근15초/12스캔 지역 patch와 관측 출처. 각 tentative B 후보의 **첫 관측 프레임을 강제 keyframe으로 고정**, 기존 floor_color_v3가 확인한 첫 B 후보에만 귀환 목표를 연결. 확인 전 tentative를 도착 목표로 쓰지 않는다. 마지막 teach 프레임도 저장. 미래 관측을 과거 patch에 넣지 않음.
- 물리 DEV **1단계 seed49001,49002 각1회**:360SIM초 탐색→기존 unknown-start(100000입자/우도.5/자기 snapshot)→최대270초 재위치/귀환. seed는 eg49 비교용으로 재사용, 새 확증 아님. 이 두 회차 모두 다음3개를 충족할 때만 **2단계49003–49006 각1회**. 미달이면 추가 물리/재튜닝0으로 종료. 미실행4건은 실패4건으로 합산하지 않음.
- 관문(결과 전 고정): **B가 자기 관측/확인됐고 loss시 마지막 노드→고정 B노드 경로 존재**, **첫 return 프레임 CSM 수락**, **기존 도착 선언+GT B안 도착**을 두 회차 각각 만족. 거짓 선언0. 접촉/회전 비율은 숨기지 않고 보고하며 추후 문턱 추가0. 엣지가 불확실한 연결 존재와 실제 통과/도착을 구분한다.
- 도착은 eg43/49 그대로 resolved5연속+추정B거리≤.20m(+traversal B노드 국소화); GT 차체 중심이 실제 B 안이어야 채점 성공. GT는 실행 후 별도 평가만, 도착 선언/경로/정합에 금지. 접촉/실제 물리 실패와 기존60분HOST상한 유지. ENOSPC=HOST_ERROR, 실행된 슬롯 재시도0. 시작 전 잠금 거부는 미시작으로 기록하고 대기.
- 표: 도착/실행수(eg49 0/6과 별도 조건), B연결, 첫정합, uncertain엣지/노드, 회전시간비(실제 발행 회전 명령 지속시간/유효 명령시간; explore/return 분리), 벽/로봇 접촉episode, 귀환소요, 종료오차/σ. 탐색 명령 byte동일 오프라인 시험으로 추가 회전0 확인; 물리 동역학 차이로 비율이 달라지면 그대로 보고.
- 한 번에 한 물리, agent_lock null일 때만 acquire·ugrp_session·dev_light·NI0/NO_BG_NICE. s2v58/hardmaps 사용 중이면 대기. 처음2회 최대2시간+대기, 통과 시 추가 최대4시간. raw6GiB 예산/여유10GiB 확인. 벽 검출/문턱 재튜닝·freeze·모델·유료/원격 자원0. PR405 DRAFT, #406/다른worktree수정0.
- raw `/Users/changmin/projects/ugrp/outputs/teach-capture-v1/seed<seed>`, 성과/실패와 미실행 사유 모두 기록. 등록 순서 첫 완료 실행을4배속 손목RGB|자기지도/teach그래프로 저장(성공/실패 명시). 성공 만들기 위한 추가 실행0. TensorBoard 생략 유지.
