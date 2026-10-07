# 탐색 평가 어댑터 v3 — 진행 감시·장애물 유지·접촉 회복

## 구현 전 사전 등록

PR #409 `6ae4c5a7`에서 이어간다. [explore4](../2026-10-07-mapfree-navigation-recovery/README.md)의
기존 실패10건 B0/10, 유효6건 중 정지/회복 소진4·맹점 접촉2를 보존한다. 새 `navigation=public_ros_v3`,
기본 off, v1/v2 소스·결과·B v3·센서 오류 통계·v7 명령 평균/잡음은 보존한다. MuJoCo·모델 호출·렌더 없음.

[줄 단위 원본 대조](REFERENCES.md)에 따라 explore_lite의 frontier 진행 timeout/ABORTED→blacklist→즉시
다음 목표, Nav2 SimpleProgressChecker와 RecoveryNode/RoundRobin의 성공/실패 처리, obstacle marking/clearing을
이식한다. 새 알고리즘을 임의로 덧붙이거나 실패 후 파라미터를 조정하지 않는다. C++ frontier/NavFn 원본은 그대로다.

설정: 기존 0.1 m 격자/사각 footprint+padding/경로 추종/900 modeled s·40 m·300관측은 그대로.
explore_lite progress_timeout30 s, Nav2 이동 반경0.5 m·검사시간10 **FollowPath active seconds**를 사용한다.
2 s 카메라 정착 정지는 명시적 제어 중단이므로 checker의 active clock에서 제외(약30 modeled s),
행동 중 예측 충돌로 정지한 시간은 포함한다. 목표/FollowPath 재시작 때만 baseline을 reset한다.
planner contextual clear1회·전체 성공 회복≤6, clear/spin1.57/wait5/backup.30 m at.15 m/s 순서.
고정 Nav2 revision의 RoundRobin 기본 `wrap_around=false`도 보존한다(기존 v2의 무조건 순환과 다름).

관측 장애물은 별도 persistent own layer에 저장한다. 일반 갱신은 clear-before-mark, 새 free ray가 입증한
셀만 지우며 시야 밖이라는 이유로 지우지 않는다. **Nav2 원본에는 explicit reset/footprint clearing 예외가 있다.**
사용자의 이번 '지우기는 raytrace로만' 요구에 따라 recovery clear는 파생 costmap을 초기화한 뒤 자기 관측 층을
재적용한다. 현재 footprint의 임시 비용 제거는 원본처럼 수행하지만 관측 메모리/정적 벽을 삭제하지 않는다.
카메라 floor endpoint 사이의 미관측 바닥을 lidar처럼 free로 꾸미지 않고, raytrace clearing은 관측된 floor
support와 hit 전방에만 적용한다. 이 camera adapter 차이를 코드/출처에 명시한다.

사용자가 이번에 명시한 **접촉/정지 감지**는 2D 평가의 별도 binary bumper sensor(t, pressed)로 구현한다.
Kobuki safety controller의 stop/reverse와 bumper2pc의 고정 몸체 기하 투영을 참고한다. 실제 물체 ID/좌표/법선·
GT pose를 actor에 전달하지 않는다. 접촉 때 환경은 침투 전 마지막 위치에서 정지하고 사건을 집계하며,
actor는 자기 발행 명령을 정지한 뒤 Nav2의 .30 m BackUp 회복을 요청한다. DR는 GT로 고치지 않는다.
카메라-only 조건과 새 bumper 조건을 동일 입력이라고 주장하지 않는다. 실물 MasterPi 센서 탑재/성공은 미검증이다.
후진 충돌 예측도 유지한다. 접촉을 숨기거나 원 안전 기준의 충돌0을 통과로 바꾸지 않는다.

## 판정 순서와 중단

1. **기존 실패10건만 개발 재생**: 원 ID/좌표/seed를 그대로 유지한다. s1/H·s4/H의 시작 겹침4건은
   `HOST_SETUP_ERROR` 거부가 맞는 결과이며 B 성공으로 세지 않는다. 나머지 유효6건 모두 참 B 확인·거짓0,
   무한 정지/회복 소진0, 접촉 뒤 후진/재계획 처리가 확인되어야 다음 단계로 간다. 초기 접촉도 충돌 수에 남긴다.
   안전 단위시험(관측 장애물 시야 밖 유지/새 free ray 삭제/blacklist 전환/접촉 역주행)을 함께 통과해야 한다.
2. 통과한 경우에만 소스·설정을 동결하고 **이미 등록된 미개봉 I/J×5701/5702 32쌍**으로 oracle static1회.
   [원 cohort](../2026-10-07-mapfree-navigation-recovery/cohort.json)의 bytes/hash/생성 규칙을 변경하지 않는다.
3. **참 B≥30/32·거짓0** 통과 시에만 frontier oracle, 그 완료 뒤 현실 잡음 static/frontier. 기존5기준
   (B≥80%, 거짓0, 시간/거리≤2, coverage≥40%, 충돌/잘못된 문0·실제 문 시도≥1, 입력/off 검사)은 그대로다.
4. 개발 실패/관문 실패는 원인과 함께 중단, 신규32 개봉이나 재튜닝으로 덮지 않는다. HOST_ERROR/ENOSPC 보존.

시험은 변경 모듈1–3파일만, 시험 통과 후 커밋·push. 모든 commit Codex trailer, 강제 push/reset 없음.
raw는 `/Users/changmin/projects/ugrp/outputs/mapfree-navigation-persistence-v3/`, 덮어쓰기/삭제 없음.
속도 비교가 아니므로 timing lock 불필요. 다른 worktree·PR #405 수정 없음. DRAFT 유지·병합 없음.
TensorBoard/Drive는 이전 사용자 결정대로 생략한다.
