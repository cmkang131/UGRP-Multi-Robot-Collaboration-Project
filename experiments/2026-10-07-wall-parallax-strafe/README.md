# egomap15 — 동결 시차 검출기의 횡이동 자료 진단

## 실행 전 사전 등록 (2026-10-07)

PR #405, 시작 `35a74081`. 사용자 요청으로 마지막 자료 변경만 허용한다.
탐색 PR #409의 public_ros_v6 개발 관문 실패(0/32)는 보고·동결되어 있다.
기존 8건은 개발 이력이며 아래 새 2건과 합산하지 않는다.

### 변경하지 않는 것

`../2026-10-07-wall-parallax/freeze.json`의 17개 파일·설정·관문을 바이트 그대로 유지한다.
`wall_detector=parallax_v1`, 기본 off, 기존 M1 명령 DR + v7 구조 잡음 사전,
무하중 21자세 보정, history10, 매2frame, 추적/시차/ROI/불확실성 조건 모두 그대로다.
GT는 예측 봉인 뒤 평가만 한다. 관문 실패 시 전체 자기 지도 트랙을 중단하며 추가
튜닝·녹화·RBPF/pose_graph 지도 재생을 하지 않는다. 2건 모두 통과한 경우에만 지도 재생한다.

### 사전 고정 취득 계획 (모델 호출 0)

현행 final v3 two-door Scene, v7 native mesh roller, camera v3, floor_light_v1/nearclip을 쓴다.
PR #406 `6bd861fb8800d9ee0ece56dad81480c0c3142b95`의 필요한 물리/카메라/명령 모듈만
그대로 복사하고 출처·해시를 남긴다. 다른 worktree 수정 없음. **freeze 옵션 사용 0**,
다른 로봇의 접촉·물리 유지, 벽/바닥/조명·카메라 장착·FOV 변경 0.
셋업만 아래처럼 지정하고, 로봇이 자율적으로 그곳에 도착한 증거로 주장하지 않는다.

|ID|seed|r3 시작 x,y,yaw (m,rad)|처음 횡이동 방향|관측 대상|
|---|---:|---|---|---|
|strafe-north|15101|3.25, .75, pi|left +.65|분리벽 북쪽 끝과 문틀|
|strafe-south|15102|3.25, -.70, pi|left -.65|분리벽 남쪽 면과 문틀|

원본 `RealPrimitivePort(min_wheel_cmd=real_v1)`의 횡이동 **±.65, .65 s** 명령을 쓴다.
기본 포트의 ±.1은 v7 출발 문턱 .325 미만이라 쓰지 않는다. 이 선택은 검출기/DR 보정이 아니다.
리셋 후 팔 {1:2000,3:740,4:2320,5:1320,6:1500}(무하중 HIGH) 명령, 5 s 정착.
각 run: 정착 5 s → t=5,6,7,8 s에 같은 방향 4펄스 → 정지 →
t=11,12,13,14 s에 반대 방향 4펄스 → 정지; 총 18 s, RGB 10 Hz, 평가 로그 10 Hz.
명령은 시간표만 읽으며 RGB/GT/실제 이동에 따라 크기·기간·방향을 조정하지 않는다.
팔은 발행 명령만 알고, 측정 관절/접촉/카메라 pose는 eval_only에만 저장한다.
벽 접촉·10도 차체 기울기·비유한 상태·weld 발생은 외부 안전 중단만 허용한다.
기술적 HOST_ERROR도 그대로 기록; 같은 원인 두 번이면 중단. 자료 부족을 이유로 재실행하지 않는다.

`agent_lock status=null` 확인 후 자신 PID로 acquire→`ugrp_session`/등록 workflow에서
한 번에 한 run만 실행→finally close/release. 실제 코드는 시험·commit·push 후 실행한다.
총 예산 2회×18 SIM s(+각 reset≤5 s), raw≤100 MiB, 예기치 않은 장기 실행은 기록·중단.
raw는 `/Users/changmin/projects/ugrp/outputs/wall-parallax-strafe-v1/` 새 경로, 원본 보존.
디스크 확인 후 시작, ENOSPC=HOST_ERROR. wall 시간은 운영 기록이며 속도 비교 아님.

### 평가 및 변경 없는 관문

각 run의 eligible 프레임 목록에서 중앙 6분위 프레임을 선택한다.
예측 보기 전에 own RGB만 보고 기존 96열 접점 주석 규칙으로 수동 주석하고 해시/commit한다.
동결 replay를 새 episode/cohort 경로로만 연결한다. 모든 예측을 봉인한 뒤 GT body와 벽을 읽는다.
전체 점 precision≥90%, 주석 precision≥90%/recall≥70%, 거리오차 중앙≤.10 m/P90≤.25 m,
동일-frame 기존 바닥 투영 precision 비감소, 가시 주석≥50열·주석 TP≥30열:
**기존 egomap14 기준을 새 2건 각각에 그대로 적용**한다. off bytes/own-only/양의 깊이도 필수.
빈 출력은 P/거리오차 NA, recall0. 거리별·같은 픽셀·DR 출발 정렬 오차는 각각 분리한다.
GT 경로는 횡방향 실제 이동량·명령 DR 차이의 사후 진단에만 사용한다.
특징 수·시차 부족/추적/재투영 거부율을 구 녹화와 나란히 보고하며 합산하지 않는다.

### 텍스처와 종료

실행 XML에서 벽 재질·texture 유무를 감사하고 보존된 실물 RGB와 비교한다.
일치하는 실물 경기장 벽 자료가 없다면 불명으로 기록한다. 텍스처 변경은 구현하지 않는다.
실패하면 바닥 투영/FK/S2/소실점/기존 및 새 시차 결과와 실물 측정 필요 항목을 한 표로 남긴다.
시험은 변경 모듈과 기존 parallax/off golden만. 의존성 설치 0. PR DRAFT·병합 금지.
TensorBoard 기존 사용자 면제 및 UGRP Drive 예외 유지.

## 취득 어댑터 인수 기록

`90c21ed3` 첫 north 호출은 `build_world` 필수 keyword `drive_profile` 누락으로
생성자 호출 전에 HOST_ERROR. 물리 step/RGB 0, 잠금 해제, 원본 디렉터리 보존.
검출/취득 설정 변경 없이 인자를 연결하고 signature 검사를 추가한다. 북쪽 출력만
`strafe-north-host-retry1`에 재개한다(원래 run에 robots 자료가 없을 때만 허용).
CLI 준비 단계의 잘못된 disk_report section/모듈 진입점/축약 SHA도 수정했고
실행 전 여유46.19 GiB, sim slot0, lock null, 전체 SHA admission 통과를 확인했다.
