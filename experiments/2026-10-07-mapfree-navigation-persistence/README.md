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

## 구현과 실행 계약

| 옵션 | 기본 | 동작 |
|---|---|---|
| `navigation=off` | 기본 | 기존 출력 객체/bytes를 그대로 반환, v1/v2 파일·원 cohort bytes 검사 |
| `navigation=public_ros_v3` | 명시 opt-in | 진행 감시/회복 포트, 영속 자기 장애물, binary bumper stop/backup |

`harness/public_navigation_persistent.py`는 자기 관측·명령 DR·(t,pressed)만 받는다.
정적 baseline만 기존 authored 정적 지도/B를 받고, 물체 배치 정답은 전달하지 않는다.
`code/contact_world.py`는 충돌 직전 substep을 거부하는 2D 평가기다. 막힌 발행 명령의 DR 오차는 남긴다.
`code/run_persistent.py`는 개발 관문/새32 관문 원본 episode bytes와 source hash를 확인하며 다음 단계를 막는다.

실행 전 관련3파일 시험30개 통과. 초기 시험의 중복 frame/time fixture와 sparse checkout에서 빠진
기존 `sensor-errors.npz`는 수정·Git 원본 SHA256 검증 후 재검사했다. 임계값 변경 없음.
신규 venv/설치 없음. binary contact 추가 조건을 camera-only 이전 결과와 같은 관측이라고 합산하지 않는다.

```sh
PYTHONPATH=outputs/self-map-plot-deps /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest tests/test_navigation_persistent.py tests/test_navigation_recovery.py tests/test_public_navigation.py -q
PYTHONPATH=outputs/self-map-plot-deps /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python experiments/2026-10-07-mapfree-navigation-persistence/code/run_persistent.py --navigation public_ros_v3 --cohort diagnostic --stage a --output /Users/changmin/projects/ugrp/outputs/mapfree-navigation-persistence-v3/diagnostic
```

## 결과 — 개발 관문 실패, 새 확인 미개봉

사전 등록 `3eb966f7` → 시험30개 통과 → 구현 `0ccdf972` 커밋·push → 기존 실패10을 **1회** 재생했다.
[10건 개별 전후 표](results/tables.md), [원 수치/이벤트 분석](results/failure-comparison.json),
[중단 판정](results/summary.json)을 남긴다. oracle 두 seed는 동일 궤적이며 독립 표본으로 합산하지 않는다.

| 기존 실패 묶음 / 각2seed | v2 → v3 B | 종료/확인 modeled s | v3 coverage | v3 주행 접촉 |
|---|---:|---:|---:|---:|
| s1/H·s4/H (총4건) | 0 → 0 | 0; 시작 겹침 `HOST_SETUP_ERROR` 유지 | 0% | 0 |
| s4/G | 0 → 0 | 161 → 125; 회복 소진 | 39.5% | 0 |
| s5/G | 0 → 0 | 131 → 104; 회복 소진 | 70.2% | 0 |
| s8/H | 0 → 2 | 2.7 접촉 종료 → 74 B 확인 | 46.5% | 각2회, 총4회 |

**B 0/10 → 2/10, 유효6건 중2, 거짓0. 개발 사전 기준6/6 미달.** 과거 성공22건과 더해 새24/32라고
보고하지 않는다. 새 I/J32는 실행0, freeze 생성0, oracle static ≥30/32 관문·frontier oracle·현실 잡음
모두 미평가다. 기존5개 성공 기준도 변경하지 않았다. 같은 정지/회복 소진이 재발하여 추가 수정·튜닝·재실행을 중단했다.

- **s4:** follow6·spin1회가 footprint projection에서 거부됐다. backup은122.4s에 성공했으나 고정 원본
  RoundRobin의 마지막 child 종료 분기가 `round_robin_exhausted`를 반환했다. 125s는 최종 관측 시각이다.
  따라서 s4의 후진 후 도달 가능성은 이번 결과로 판단하지 않는다. 원본 분기를 결과 뒤에 고치지 않았다.
- **s5:** follow6·spin1·backup1회가 예측 충돌로 거부됐다. B5/5 가시·검출에도 동일 track의3-view 병진은
  **0.000026585 m**로 .05m 확인 기준 미달이다. .094m 앞선 이동은 다른 B track이어서 합치지 않았다.
- **s8:** 처음 보지 못한 `can_1` 접촉을2.7s에 binary bumper로 받았다. 2.70·2.85s에 실제 기하 접촉2회가
  각 실행에 기록됐다. 발행 stop/후진 뒤에도 v7 관성 상태가 즉시0이 되지 않아 회복 초기에 두 번째 접촉이 있다.
  입력의 상승 에지는1회, 후진 완료/재계획은11s에1회이고 **완료 뒤 재접촉0**이다. 74s/1.477m에 참 B 확인,
  종료 DR 오차0.027822m다. 관성·DR를 정답으로 보정하지 않았다. 총 충돌4회는 그대로 남겨 **충돌0 기준 미달**이다.
- 개발 gate는 현재 `contact_replan` 수를 기하 contact event 수와도 비교하므로 s8의1회 bumper burst/2회
  접촉에 보수적으로 실패한다. 감지 에지와 기하 접촉은 다른 단위임을 공개한다. 이 집계와 관계없이 유효 B2/6으로
  관문은 실패이며, 결과를 본 뒤 gate를 완화하지 않았다.

장애물 시야 밖 유지/clear 뒤 재적용/free ray 삭제/hit 우선·frontier ABORTED/timeout 다음 목표는 단위시험에서
검증했다. **frontier 실험 성공은 아직 검증하지 않았다.** 정적 목표 B는 도달 불가 frontier처럼 다른 목표로
대체하지 않는다. 원 native 탐색/계획 코어·B v3·벽/운동 잡음·원 cohort·v1/v2 bytes는 그대로다.

원시93파일 **7,963,176bytes**는 [artifacts.json](results/artifacts.json)의 절대 경로·SHA256으로 로컬 보존한다.
이는 raw 원격 백업이 아니다. 결과/출처/검증은 Git에 보존한다. runtime hash·이전 v2 모든 source hash·사용자
미추적4파일 해시 불변, 실제 실패 자료의 `DEVELOPMENT_GATE_FAILED_STOP_CONFIRMATION` 차단을 검증했다.
[검증 기록](results/verification.json). MuJoCo/렌더/모델 호출0, 실행 session은 종료됐다. PR #409 DRAFT 유지.

## 후속 s4·s5 정지 기하 진단 (explore6)

[진단·그림2장·v4 결과](../2026-10-07-mapfree-stop-geometry/README.md).
통로0.50m > padding 포함 최대 회전폭0.3688m. s4/s5 첫 거부 투영은 연속 기하에서 양의 여유가
있으나 raster 벽과 겹쳤다. filled footprint와 Nav2 원본 외곽 검사 차이만 기본-off `public_ros_v4`로
분리했다. 동일 개발10에서 s5 두 건은101s B 확인·접촉0, s4 두 건은125s 동일 회복 소진이었다.
유효 참 B2/6→4/6·거짓0, 관문 미달. s4의 원본 RoundRobin 종료 및 정적 B 임무를 바꾸지 않고
추가 튜닝 중단, 미개봉 I/J32 실행0. v3 코드/결과는 바이트 그대로 보존했다.
