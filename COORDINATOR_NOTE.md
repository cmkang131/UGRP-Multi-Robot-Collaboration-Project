## 2026-10-16 19:00 coordinator
gcp6의 첫 용도를 act16w 학습에서 beamact3 C2 학습으로 바꾼다. 따라서 beamact3 학습 환경(gcp2 /home/ugrp/ugrp-rl1b-act-env, train_shared.py 의존성)과 beamact3 데이터(/home/ugrp/ugrp-sim/ops-reviews/actdiag/infer-final-v1/dataset-view가 가리키는 원본)를 SHA 확인 뒤 준비하고 50 step smoke까지. 최대한 빨리.

[조정자 20:04] 충돌 방지 규칙(필수): /Users/changmin/projects/ugrp/outputs/e2e18-admin/agent-ownership.md 를 읽고 따를 것. 자기 VM·자기 파일 범위 밖은 건드리지 말 것. 다음 ops-alert 보고 줄 끝에 'ownership-ack' 를 붙일 것.

[조정자 20:23] 범위 추가(필수, 다음 보고에 'scope2-ack'): 혼자 옮기기 MJWarp 장면이 nv228–246·nbody~160·ngeom~1390이다(experiments/2026-10-16-warp3/model-groups.json, ugrp-wt/warp4). MJWarp 문서는 60 DoF 넘으면 성능 저하라고 한다. noslip 프로필과 함께 'MJWarp용 모델 변형'을 기본 off 토글로 설계·측정할 것(Menagerie의 mjx_*.xml 방식 참고, 출처 기록): (1) 그 작업에 관여하지 않는 화물·물체는 free joint 제거(정적·같은 외관 유지, 카메라 화면 동일 — 렌더 비교로 확인), (2) 충돌용 기하는 원시 도형으로·필요 없는 충돌 쌍 contype/conaffinity로 끄기(시각 기하 불변), (3) 정적화된 물체와 로봇 접촉이 생기면 이벤트로 기록하고 그 실행은 무효 표시. 표에 nv·ngeom·ncon·물리시간/step·파지 유지·주행 변위를 기존 대비로. 기존 장면 파일은 수정 금지, 새 모듈에서 모델 로드 시 변형.

[조정자 21:27] gcp2 CPU(ugrp-sim-gcp2)는 부하 0.09·실행 0인데 analysis 임대만 잡혀 있어 조정자가 정지했다(시간당 약 $3.15). 상한도 제거됨. 쓸 때만 켜고(remote_run/gcpctl이 시작), 실제 실행이 없으면 임대를 잡아두지 말 것. 쓰고 나면 임대 해제·정지 확인.

## 2026-10-16 22:00 KST 조정자: CPU VM(ugrp-sim-gcp2) 다시 정지 — 낭비 금지
- 12:28Z 재시작 뒤 31분간 load 0.00으로 놀아서 다시 정지했다($3.15/h). 
- 짧은 분석·감사(C MuJoCo mj_forward, 표 계산 등)는 각자 쓰는 L4 VM(mapbuild3=gcp5, warpfit=gcp6)의 CPU에서 돌린다. ugrp-sim-gcp2를 켜지 않는다.
- 꼭 sim-gcp2의 원본이 필요하면 켜고, 작업이 끝나는 즉시 직접 정지하고 보고에 정지 시각을 적는다. lease만 남겨 두지 않는다.

## 2026-10-16 22:17 KST 조정자: 분석은 원본이 있는 자기 VM에서 — CPU VM(ugrp-sim-gcp2) 시작 금지
- ugrp-sim-gcp2(n4-highcpu-64, $3.15/h)가 짧은 스냅샷·재계수 때문에 오늘 세 번 다시 켜졌고 매번 load 0.1 이하로 놀았다. 사용자: "낭비 하지 마".
- AGENTS의 "실패 분석은 gcp1(=CPU VM)에서"는 "원본이 있는 실행 VM의 CPU에서"로 읽는다(규칙 PR로 고친다). warp8=gcp3, warpfit=gcp6, mapbuild4=gcp5, act16w=gcp2 L4 자기 VM에서 분석한다.
- C MuJoCo CPU 비교도 자기 L4 VM의 CPU(8–16코어)에서 한다. ugrp-sim-gcp2를 켜지 않는다. 꼭 그 디스크의 원본만 필요하면 조정자에게 ops-alert로 요청한다.

## 2026-10-16 22:2x KST 조정자 전달: mapbuild4 → warpfit 요청
- mapbuild4: 깨끗한 시작에서 좌60ms 횡이동 MJWarp FOLDED 7.036mm/HIGH 7.512mm, C3.16 CPU 7.696/7.729mm(400ms 약48mm). mapbuild3의 0.090mm는 "전진 펄스 뒤" 횡이동이라 상태(롤러 위상·접촉) 의존 의심.
- 요청: 후보 접촉 프로필 평가에 "전진 뒤 횡 60/400ms" 구간을 포함하고, 쓸 수 있는 최신 프로필 SHA를 ops-alert에 "warpfit→mapbuild4: ..." 한 줄로 알려 달라. 프로필 모듈은 warpfit 소유 그대로.
