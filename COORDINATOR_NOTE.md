## 2026-10-17 조정자 → egomem2: recording1 원인 재검토(독립 분석, 원본 숫자 조정자 확인)
recording1-control-replay.json 기준: 복귀 turn 674/forward 17/stop 1, own_return_path 0.228 < 0.316 m는 맞다. 그러나 rho 부호 전환은 4회(각 약 96° 점프)뿐이라 회전 674틱 중 약 20–25틱(3–4%)만 설명한다. "목표점 흔들림"만으로는 부족하다.
다음 녹화 전에 먼저 확인: 제자리 회전 중 기억한 목표의 방향(memory_bearing)이 회전 방향으로 실제로 줄어드는가? 기억 역변환의 회전 부호가 틀리거나 회전량이 적용되지 않으면 목표 방향이 줄지 않아 끝없이 돈다(영상에서 매끈한 한 방향 회전, 빠른 진동 없음). 틱별 명령 회전량·기억 방향 변화·실제 heading 변화를 같은 표로 만들고(online-trajectory 원본, gcp5), 부호·크기가 맞는지 숫자로 보인 뒤 수정한다. 재획득 관문이 같은 수선의 발 방향을 써서 15/15 거부된 것도 같은 원인인지 함께 본다.

## 2026-10-17 사용자 지시 (egomem1, 최우선): "이거 실제로 쓰는 방식들 먼저 찾아보고, 그 방식 활용"
논문 아이디어를 새로 짜지 말고, 실제 로봇·제품·널리 쓰는 공개 코드에서 쓰는 방식을 먼저 찾아 그대로 쓴다. 후보(직접 확인 후 선택): ROVIO(로봇 중심 EKF, 공개 코드, 실제 드론·로봇에서 사용), Nav2/costmap_2d rolling_window 지역 지도(로봇 중심으로 움직이는 지도, 실서비스 표준), OpenVINS/MSCKF의 슬라이딩 창 특징 관리(오래된 것 버림), 물체 단위 기억(예: 공개 semantic landmark tracker). 무엇을 실제로 쓰는지(제품·사용처·저장소·라이선스)를 README 참고 자료 표에 적고, 고른 구현의 갱신식·상수·잊기 규칙을 그대로 가져온 뒤 우리 제약(자기 RGB·자기 명령·정적 지도 없음) 때문에 바꾼 부분만 따로 적는다. 가능하면 코드(라이브러리)를 직접 재사용한다. 이 조사 결과를 ops-alert에 "egomem1: SURVEY | 고른 방식·출처" 한 줄로 먼저 보고한 뒤 구현한다. 이미 짠 자체 설계가 있으면 고른 방식과 차이를 표로 비교하고 고른 방식으로 바꾼다.

## coordinator
AGENTS.md "로봇 입력과 학습 경계"의 지도 경로 예외 항목 뒤에 한 문장 추가(같은 PR): 2026-10-16 사용자 "지도 그리는 것도 같이 진행 ㄱ" — 지도 없음(자기 지도 만들기) 조건을 지금부터 병행, #366의 "첫 E2E 이후"를 대체, 정적 지도 결과와 합산 금지. 사용자 확인(10/16): 벽·바닥 질감·색을 바꾼 장면(walls_floor_contrast_v5_indigo110_s80)으로 진행.

## 2026-10-16 사용자: "현실에서는 잘 잡히던데" (ORB 기하 추적 3–23/120에 대해)
특징 수 관문은 120/120 통과 → 검출이 아니라 프레임 간 대응(insufficient_matches)이 실패. 현실 카메라에서는 같은 ORB가 잘 된다는 사용자 관찰이므로 먼저 "우리 파이프라인 문제 vs 시뮬 영상 문제"를 가른다:
1) 저장소/Mac에 실제 로봇 카메라 영상(실기 기록)이 있으면 같은 파이프라인·같은 상수로 대응 성공률을 잰다(없으면 "없음" 기록). 
2) 파이프라인 점검: 어안 원시 vs 보정 영상 중 어디서 매칭하는지, 마스크가 특징을 지우는지, ratio test/cross-check/거리 문턱, 프레임 간격(10Hz 인접 vs 2Hz), 해상도. OpenCV 표준 VO 예제(ORB+BFMatcher Hamming+ratio 0.75+RANSAC essential)를 그대로 돌려 비교 — 표준 방법을 먼저 그대로 적용.
3) 시뮬 영상 쪽 후보(질감 대비·블러/no_mip·조명·동료 로봇 차지 면적)는 1)–2) 뒤에 거부 사유 분포표로.
원인 주장 전에 숫자로 확인. 결과는 ops-alert "mapbuild1:" 줄.

## 2026-10-16 18:40 coordinator: 쳐내기
초음파 ON/OFF 비교는 이번 라운드에서 뺀다. ORB 원인 찾기도 뒤로: LK가 120/120이므로 지도 만들기는 LK 추적으로 먼저 끝낸다(3단계 점유 지도·커버리지 우선). ORB는 LK가 실제 주행에서 실패할 때만.

## 2026-10-16 coordinator: gcp2 L4 8h 상한
gcp2 L4의 maxRunDuration 28800은 실행 중에는 바꿀 수 없다(GCP: "cannot be changed while the instance is running"). 조정자 감시가 VM이 정지하는 즉시 지운다(14:01Z 예정). 너는 손대지 말고, 14:01Z 정지로 끊기면 HOST_ERROR로 기록하고 같은 시드로 다시 내라.

[조정자 21:27] gcp2 CPU(ugrp-sim-gcp2)는 부하 0.09·실행 0인데 analysis 임대만 잡혀 있어 조정자가 정지했다(시간당 약 $3.15). 상한도 제거됨. 쓸 때만 켜고(remote_run/gcpctl이 시작), 실제 실행이 없으면 임대를 잡아두지 말 것. 쓰고 나면 임대 해제·정지 확인.

## 2026-10-16 22:00 KST 조정자: CPU VM(ugrp-sim-gcp2) 다시 정지 — 낭비 금지
- 12:28Z 재시작 뒤 31분간 load 0.00으로 놀아서 다시 정지했다($3.15/h). 
- 짧은 분석·감사(C MuJoCo mj_forward, 표 계산 등)는 각자 쓰는 L4 VM(mapbuild3=gcp5, warpfit=gcp6)의 CPU에서 돌린다. ugrp-sim-gcp2를 켜지 않는다.
- 꼭 sim-gcp2의 원본이 필요하면 켜고, 작업이 끝나는 즉시 직접 정지하고 보고에 정지 시각을 적는다. lease만 남겨 두지 않는다.

## 2026-10-16 22:17 KST 조정자: 분석은 원본이 있는 자기 VM에서 — CPU VM(ugrp-sim-gcp2) 시작 금지
- ugrp-sim-gcp2(n4-highcpu-64, $3.15/h)가 짧은 스냅샷·재계수 때문에 오늘 세 번 다시 켜졌고 매번 load 0.1 이하로 놀았다. 사용자: "낭비 하지 마".
- AGENTS의 "실패 분석은 gcp1(=CPU VM)에서"는 "원본이 있는 실행 VM의 CPU에서"로 읽는다(규칙 PR로 고친다). warp8=gcp3, warpfit=gcp6, mapbuild4=gcp5, act16w=gcp2 L4 자기 VM에서 분석한다.
- C MuJoCo CPU 비교도 자기 L4 VM의 CPU(8–16코어)에서 한다. ugrp-sim-gcp2를 켜지 않는다. 꼭 그 디스크의 원본만 필요하면 조정자에게 ops-alert로 요청한다.

## 2026-10-16 22:50 KST 조정자: 사용자 결정 — 자기 지도에 벽 색 경계 가상 스캔 + GMapping식 입자 필터(RBPF)를 넣는다
사용자 원문: "mapbuild4에 벽 색 경계 가상 스캔 + GMapping식 입자 필터를 넣고, MASt3R-SLAM은 같은 녹화 영상으로 비교만 해줘."
배경: 지금 위치는 LK 증분을 더하기만 해서(보정 단계 없음) 넓은 지도에서 오차가 쌓인다. 사용자가 이것을 약점으로 지적했다.

순서: 지금 하는 횡 펄스 측정(새 접촉 프로필)은 마무리해서 기록한다. 그다음 frontier보다 먼저 아래를 한다.
1) 새로 짜지 말고 기존 코드를 재사용해 MJWarp 녹화·현 장면(walls_floor_contrast_v5_indigo110_s80)에 맞춘다:
   - harness/self_map_rbpf.py (Grisetti 2007 개선 제안분포 + 선택적 재표본화, 입자별 log-odds 격자)
   - harness/rbpf_motion_gate.py, rbpf_insertion.py(gmapping_range_v1), rbpf_manhattan.py, pf_sensor_proposal.py, self_wall_memory.py의 pose_correction own_map_rbpf_v1
   - 과거 기록: experiments/2026-10-07-rbpf-rejection, 2026-10-08-rbpf-insertion(egomap26), 2026-10-08-rbpf-turn-audit(egomap27), 2026-10-05-ego-wall-map-probe. 그때 무엇이 막혔는지 먼저 읽고 거부 사유 분포표부터 만든다.
2) 가상 스캔: 자기 RGB의 벽–바닥 색 경계(기존 ColourBoundaryState/active_wall_vision)를 열(방위)별 바닥 접점으로 바꾸고, 서보 FK·고정 K/D로 바닥 평면에 투영해 거리–방위 스캔을 만든다. 자기 차체·동료 로봇 열은 뺀다. 못 본 방위는 unknown(최대 거리로 채우지 않음).
3) 주행 입력: LK 바닥 증분(측정됨)과 자기 명령 예측(그 외), 각각의 공분산. 방금 찾은 "짧은 횡 펄스 되밀림"은 명령 예측 공분산·모델에 반영하되 근거(측정 분포)를 적는다.
4) 상수(입자 수, Neff 재표본화 문턱, 스캔 우도 σ 등)는 GMapping 원문·기존 동결값·원본 분포에서 가져오고 출처를 주석에. 계산 상한은 wall초가 아니라 입자·검사 수로.
5) 기본 off 토글(예: mapbuild_rbpf_v1). 같은 녹화에서 LK만 vs RBPF를 비교: ATE(정답은 평가 전용), 지도 coverage·잘못된 free·벽 정확도, 같은 벽 재관측 때 오차가 줄었는지. 이 비교가 의미 있으려면 같은 벽을 다시 보는(왕복·한 바퀴) 더 긴 주행 녹화가 필요하다 — 그 녹화를 만든다.
6) 녹화 공유: 그 주행의 자기 RGB 프레임·명령·카메라 보정·평가용 정답을 sha256 매니페스트로 gcp5 디스크에 두고, ops-alert에 "mapbuild4→mast3rcmp: recording <경로> manifest <sha256>" 한 줄을 쓴다(별도 작업자 mast3rcmp가 같은 영상으로 MASt3R-SLAM 비교만 한다. 그 작업자의 코드·결과와 합산하지 않는다).
다음 보고에 "rbpf-ack"를 적는다.

## 2026-10-16 23:17 KST 조정자 전달: mast3rcmp 요청
- 왕복 녹화 manifest에 보조 보정 파일을 함께 넣어 달라: 고정 자세의 camera_height_m, floor_normal_camera(고정 서보 FK 외부 보정에서 계산, 동적 명령·측정 관절·정답 제외)와 그 출처. MASt3R-SLAM의 허용 척도(b) 계산용이다.

[조정자 20:50] → egomem2: PR574 CI(run 39027344732) 33/33 성공 확인. 94분째 보고가 없으니 지금 상태를 ops-alert에 한 줄 남기고 최종 판정·README 정리를 마무리하세요. 녹화2 성공은 조정자 재계수 전까지 성공으로 쓰지 마세요.

[조정자 20:51] → 전원: CI를 sleep으로 기다리지 마세요. push 뒤 바로 다음 일을 하고, 병합은 조정자가 CI 통과를 확인해 합니다.
