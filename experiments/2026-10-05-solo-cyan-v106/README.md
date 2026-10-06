# S2 단독 cyan 최종 v3 운반 후보 — v106

**DEV 실행 기록은 맨 아래 "실행 기록" 절. 최종 환경 성공 0회인 상태는 그대로다(DEV 기하 판정만 있음).**
S2 계획(#389)의 첫 실행 후보이며, S2 졸업(6개 slot 파지·단독 6회·3대 동시 6회)을 뜻하지 않는다.
원본·결과는 로컬 `outputs/`에 보존한다. Google Drive는 사용하지 않는다.

- 작업 브랜치: `claude/solo-cyan`, 시작 SHA `ee12e84fbde2320fadd8364b3820e9f2fd09f1a1` (#388 위).
- 계획: main의 `experiments/2026-10-05-scenario-e2e-gap/README.md` S2. 시나리오 v4(#390)는 별도 작업이다.
- 새 번들: `zone-solo-cyan-v106`, 표준 workflow `3.13.0`. main/열린 PR 전체의 `RUNNABLE_ID` 및 별도 번들 상수를 확인했다. 기존 RGB 레지스트리 최고 v86, v98 DEV 라벨 최고 v105 → v106. 조회한 ref 목록은 `configs/zone_solo_cyan_v106.json`에 저장했다.
- 실행 SHA는 커밋 후 PR과 인계 기록에 적고, 실행 전 `--expected-source-sha`와 깨끗한 트리를 검사한다. 실행마다 `bundle.json`에 코드 닫힘(303개 이상 파일), 지도·보정·명령/카메라 프로필의 해시를 만든다. 과거 번들은 수정하지 않는다.

## 조사와 선택

| 기존 경로 | 확인한 동작 | 이번 재사용 |
|---|---|---|
| `vision_pose_source_highpose.py`, `opencv_wall_observation.py` | 자기 RGB 벽 경계 열 → 정적 지도 예상 경계와 비교 → 입자 필터. 명령으로 이동 예측. 고정 v3 카메라 키만 사용 | 실제 `PartialFixHighPoseSource`를 생성한다. 표식 제공자·분할 모델 없음. 0.16초 관측 지연도 그대로 |
| `zone_pair_highpose_partial_fix.py` | 정보 행렬에서 두 방향 이상 강하면 부분 보정 영수증. 벽에 평행한 약한 방향을 완전히 관측했다고 주장하지 않음 | 동일 설치 경로와 기록. covariance·last_fix_t를 출력 |
| `zone_pair_highpose_blind_close.py` | 호버에서 서로 다른 두 프레임 확인 → 기체 고정·팬 고정·고정 팔 경로 하강 → 유한 시간 안에 blind close. 경로 밖 명령이면 취소 | 같은 v3 호버/하강 자세, 프레임 수, `off_window`, 거리/시간 한도 사용. 빔 패치 대신 cyan cuboid/부분 패치 확인 |
| `zone_pair_highpose_own_load_occlusion.py` (#388) | 자기 단계+자기 close 명령 영수증이 있는 하중 구간의 저대비 영상은 무관측. 낡거나 잘못된 프레임은 오류 | 같은 `OwnLoadOcclusion` 객체. 가린 RGB는 PF에 `None` 전달. 명령 예측만 하고 관측 영수증을 만들지 않음 |
| `zone_final_pair_vision.py`, `zone_pair_highpose.py` | v3 실제 집게 중심의 고정 IK, 낮은 호버→HIGH→내리기 | 같은 유한 경로·안정화 시간. cyan 32 mm 상자에 24 mm 파지 높이가 충분한지는 물리 미확인 |
| `sim.session_scenes.Scene` → `FinalV3Scene` | 표식 없는 0.40 m 벽, v3 로봇, 표준 reset·접촉 적용 | 그대로 상속. `cargo_noslip_v1`, weld OFF, `arena_default`, 근거리 절단면/정수 시간 v98 재사용 |

예전 단독 `ZoneOwnExecutor.deliver`/wrist v9의 표식 위치 추정과 v2 카메라 기하는 사용하지 않는다.
새 `Runtime`이 명시적 v3 소비자 검사를 통과하고, 향후 S3 호스트가 사용할 자기 입력/명령 경계를 가진다.
기존 일반 호스트의 `deliver` dispatch까지 연결한 것은 아니다(S3 통합은 남음).
단독 이동은 기존 정적 지도 A*와 v3 명령 기하를 사용한다. 통로를 `door_1`로 지정하며 첫 door를 암묵 선택하지 않는다.
복도·두 문 지도는 명시적으로 거절한다.

## 구현과 입력 경계

1. 공개 시작 줄 전체에 넓은 prior를 놓고 LOOK_P20 팬 관측으로 위치를 추정한다. seed별 로봇-줄 배정은 전달하지 않는다.
2. 주문의 거친 slot 근처로 이동하고 자기 RGB cyan을 찾는다. 기존 색 임계값·바닥 cuboid fit에 **v98 실측 카메라 행렬**만 사적으로 바인딩한다. 색은 종류만 식별하고 두 후보 이상이면 집지 않는다.
3. 자기 영상의 상대 위치로 고정 파지점에 정렬한다. 호버 두 장이 지지하는 마지막 표적에 한해 blind descent/close를 허용한다. 호버 이후 기체/팬/팔 경로가 어긋나거나 시간이 지나면 거절한다. 이 짧은 blind 구간의 저대비 프레임도 무관측이며 오래된/깨진 입력은 항상 오류다.
4. 발행한 close를 기록하고 v98 HIGH 경로로 든다. 문 앞·문 뒤·목적 구역의 경로를 추정 위치로 따라간다. 문 앞/뒤에서 HIGH를 유지하며 관측한다. 내려놓기·열기·팔 회수 후 `place_sequence_complete`를 남긴다. 이 이벤트는 물리 성공이 아니다.
5. 정답·관절·접촉은 물리 소유자의 `eval_only/` 출력에만 둔다. 종료 후 잠정 기하 판정은 상승 이력, 상자 전체의 구역 내부 포함, 바닥 안정 2초를 검사한다. 정답 판정이 제어기를 움직이거나 끝내지 않는다.

실행 고정물은 cyan 하나를 선택 slot 중심에 놓고 세 로봇의 표준 시작을 유지한다. 선택 로봇만 움직이고 다른 둘은 유휴다.
이는 S1 혼합 화물 또는 연구 시나리오를 대신하지 않는다. 실제 색/물체 위치는 제어 입력에 없다.

**보정 한계:** v98의 300 g 두 로봇 빔 이동 보정을 cyan 단독에 적용하지 않았다. 새 provider는 loaded 상태에서도
측정된 v101 **무하중 단독 이동 모델을 대용값**으로 쓴다. 쌍 이동/빔 yaw 입력은 끈다. loaded HIGH 카메라 행렬은
부모의 빔 하중 보정이므로 cyan에서 처짐 차이를 확인해야 한다. 이 조합은 `MOTION_PROXY`로 기록하고 DEV만 허용한다.
(2026-10-06: 이 대용값은 저장된 실행으로 반증되어 v102 HIGH 운반 측정 프로필로 바꿨다. 아래 "실행 3" 참고.)

DEV light의 위치 불확실·정적 충돌 거절은 `dev_light_would_stop`으로 기록하고 계속한다. 표적 영상 없음, blind 경로 이탈,
깨진 입력, 실행 오류와 900 SIM초 상한은 종료한다. **낙하·기울기·집게 이탈은 실행 중 감지하지 못한다.**
부모 스택의 이 한계를 유지하며 `in_run_drop_tilt_contact_detection: false`를 번들/결과/학생 기록에 명시한다.

## 검증

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
  tests/test_solo_cyan_v106.py tests/test_solo_cyan_v106_runner.py
```

26 passed (최종 재검사 11.39초, 속도 측정 아님). 실제 위치 제공자 생성/partial-fix 설치/지연/무관측 예측, 실측 v3 카메라의 합성 cuboid 세 자세,
호버 두 프레임·중복 프레임·blind 명령 이탈/만료, 자기 하중 가림, 낡은/외부 로봇/해시 오류 입력,
실제 팔 명령 큐 전체 단계(가짜 영상·위치/이동 도착), 정적 A*·원시 명령 계약, 실제 provider의 v98-exact-v6 설치/해제,
장면 해석·지도/소비자/번들/표준 workflow 등록, 가짜 backend의 유한 종료·평가/다른 로봇 명령 분리·ENOSPC 기록을 검사했다.
도착 좌표에서 방향만 남아 A* 다음 점이 없는 경우도 검사했다. 선택 stage·speedups는 번들 해시에 포함한다.

첫 시험의 실패도 기록한다: 이동 명령에 `duration`을 썼지만 원시 포트/PF는 `duration_s`를 요구했고,
무하중 보정에는 빔용 `deadband` 필드가 없었다. 실제 포트 계약과 보정 형식대로 고쳤고 위 재검사에서 통과했다.
넓은 로컬 suite는 돌리지 않았다. 새 두 시험은 `scripts/run_ci_tests.py`에 등록했다.

`sim_cli workflow plan` 등록 확인, `git diff --check`, `/bin/zsh -o NO_BG_NICE -n launch_dev.zsh` 정적 검사도 통과했다.
시뮬레이션/렌더/실제 모델 호출은 0회. 새 실험 결과가 없으므로 TensorBoard 변환·서버 시작도 하지 않았다.
조정자가 실행을 회수하면 실패를 포함해 `docs/tensorboard.md`에 따라 공유 root에 별도 snapshot으로 등록해야 한다.

## 조정자 실행

`launch_dev.zsh FULL_SHA ABSOLUTE_NEW_OUTPUT [pick|door|place]`는 소스/우선순위를 확인하고,
자기 셸 PID로 배타 잠금을 잡은 뒤 표준 `sim_cli workflow run`을 호출한다. 900 SIM초/10800 wall초 상한,
v98-exact-v6 기본, nice 0, watchdog(PID·파일 읽기 전용)과 자기 자식 정리를 포함한다. 실제 실행은 조정자만 한다.

```zsh
setopt NO_BG_NICE
# SOURCE_SHA는 PR에 적힌 40자리 실행 커밋으로 설정한다.
RUN_OUT=/Users/changmin/projects/ugrp/outputs/solo-cyan-v106-${SOURCE_SHA[1,8]}-s911-P1-2-place
nohup nice -n 0 /bin/zsh \
  /Users/changmin/projects/ugrp-wt/solo-cyan/experiments/2026-10-05-solo-cyan-v106/launch_dev.zsh \
  "$SOURCE_SHA" "$RUN_OUT" place >"${RUN_OUT}-console.log" 2>&1 </dev/null &
```

watchdog는 `/Users/changmin/projects/ugrp/outputs/v98-probe-tools/sim_watchdog.py`를 사용한다.
상한을 넘기거나 결과 파일이 없는 종료도 실패로 보존한다. `pick`은 실제 시작→파지→HIGH까지,
`door`는 같은 실제 시작에서 문 뒤까지다. 순간이동/교사 파지로 중간 상태를 만들지 않는다.
각 단계는 새 출력 폴더로 실행한다. 이번 인계는 첫 P1-2 후보이며, 나머지 5 slot과 seed, 연속 주문, 3대 동시·혼합 호스트는 남아 있다.

## 참고 자료

확인일 2026-10-05. **확인(verified)**은 아래에 적은 범위만 뜻한다. 수치/코드를 이 환경에서 재현했다는 뜻이 아니다.

- **확인: 논문 첫 부분/방법** — Fox, Burgard, Dellaert, Thrun (1999), [Monte Carlo Localization](https://www.cs.cmu.edu/~thrun/papers/fox.aaai99.pdf).
  이동 예측과 관측 가중치 갱신을 분리한 입자 분포. 새 알고리즘을 만들지 않고 이미 사용 중인 PF를 재사용한다.
- **확인: 저자 페이지 초록; 본문 미확인(unverified)** — Zhang, Kaess, Singh (2016), [On Degeneracy of Optimization-based State Estimation Problems](https://www.cs.cmu.edu/~kaess/pub/Zhang16icra.html).
  관측 가능한 방향과 약한 방향을 분리한다. 기존 partial-fix가 적용한 방식을 그대로 쓰며 단일 벽 영상을 완전한 위치 보정으로 해석하지 않는다.
- **확인: 튜토리얼 기본 제어식** — Chaumette & Hutchinson (2006), [Visual Servo Control, Part I](https://web.mit.edu/amcp/OldFiles/drg/Chaumette_Part_I.pdf).
  보이는 표적의 오차로 폐루프 접근한다. 이 문헌이 우리 고정 blind 구간의 안전을 입증한다는 주장은 하지 않는다.
- **확인: 공식 공개 소스의 문서** — [robot_localization, sensor_timeout](https://raw.githubusercontent.com/cra-ros-pkg/robot_localization/ros2/doc/state_estimation_nodes.rst).
  관측이 없으면 보정 없이 예측을 수행하는 관례를 확인했다. cyan 가림을 성공 또는 새로운 위치 보정으로 바꾸지 않는다.
- **확인: 최신 수정판(v2) 초록; 본문·공개 구현 재현 미확인** — Gupta, Sathua, Gupta (2025), [Precise Mobile Manipulation of Small Everyday Objects / SVM](https://arxiv.org/abs/2502.13964).
  손에 의한 가림이 폐루프 표적 추정의 문제임을 다루며 out-painting을 사용한다. RGB-D/vision model 추론 경로는 이번 own RGB/고정 보정/무모델 범위에 채택하지 않았다.
- **미확인** — SVM 프로젝트 웹페이지 접근 실패, 구현 미열람. #388이 인용한 EyeRobot 2.0/FingerViP의 내용은 이번에 재확인하지 않았고 새 구현의 근거로 사용하지 않는다.

저장소에서 직접 확인한 구현 출처: `zone_pair_highpose_partial_fix.py`, `vision_pose_source_highpose.py`,
`zone_pair_highpose_blind_close.py`, `zone_pair_highpose_own_load_occlusion.py`, `zone_pair_highpose.py`,
`zone_final_pair_vision.py`, `zone_color_boxes.py`, `zone_robot_model_runtime.py`, `sim/zone_final_v3_scene.py`.
과거 pair DEV 성공을 이번 단독 후보의 성공 표본에 합산하지 않는다.

## 실행 기록 (DEV, seed 911, r3, P1-2, B, door_1, v98-exact-v6, FUNCTIONAL_DEV)

판정은 사후 `eval_only` 기하 판정(`PROVISIONAL_GEOMETRIC_JUDGE`)이며 `physical_success=null`, `research_result=false`다.
제어기는 정답 좌표를 쓰지 않는다. 아래 위치 오차는 저장된 `poses`와 `eval_only/trajectory.jsonl`을 사후 대조한 값이다.

| # | 실행 SHA | 결과 | 출력 |
|---|---|---|---|
| 1 | `457aeccc5315c53a88f84e15917a750518585514` | STAGE_FAILED / CYAN_ALIGN_VIEW_LOST, lifted=false (SIM 50.3 s) | `/Users/changmin/projects/ugrp/outputs/solo-cyan-v106-457aeccc-s911-P1-2-place` |
| 2 | `25638624704fb8c2d348894b40e6d3b69e1ecc52` | STAGE_REACHED_UNQUALIFIED, lifted=true / inside=false (SIM 179.8 s, 명령 3794) | `/Users/changmin/projects/ugrp/outputs/solo-cyan-v106-25638624-s911-P1-2-place` |
| 3 | `ee40923ca165dc4fbf8092ba85aeeaa618ce8838` | STAGE_REACHED_UNQUALIFIED, lifted=true / inside=false (SIM 363.2 s, 명령 12000) | `/Users/changmin/projects/ugrp/outputs/solo-cyan-v106-ee40923c-s911-P1-2-place` |
| 4 | `d18600598b25b45f7b99a47e6b08e1d0afe7366e` | STAGE_REACHED_UNQUALIFIED, **lifted=true / inside=true / success=true(잠정 기하 판정)** (SIM 366.2 s, 명령 12030) | `/Users/changmin/projects/ugrp/outputs/solo-cyan-v106-d1860059-s911-P1-2-place` |

실행 1: 정렬 중 작은 cuboid가 p45 영상 아래쪽으로 벗어났다 → 25638624에서 아래쪽 행 440 근처에서 한 단계 낮은 시점으로 내리도록 고쳤다.
실행 2: 집기·운반·놓기를 끝까지 했지만 cyan이 목적 구역 B 밖(마지막 위치 (2.283,-0.185), B 중심과 xy로 3.006 m)에 놓였다.

### 실행 2 진단 (사후, 새 시뮬레이션 없음)

| 시점 | 추정과 실제 xy 거리 |
|---|---:|
| 집기 직후 carry 시작 82.7 s | 0.090 m |
| 문 앞 체크포인트 102.8 s | 0.241 m |
| 문 뒤라고 판단한 체크포인트 122.8 s | 0.642 m |
| 최종 lower 시작 159.7 s | 약 2.98 m |

- 마지막 PF fix는 37.75 s(집기 전)였다. 운반 중에는 명령 예측만으로 이동했고, 문 앞에서 이미 0.24 m 틀렸다.
- 차체 x 최댓값은 2.103 m로 칸막이(x=2.2)를 넘지 못했다. 틀린 추정으로 문이 아닌 벽 쪽으로 간 정황이다. 어떤 접촉 때문인지는 검증하지 않았다.
- carry 구간 cyan 중심 z는 0.1413–0.1417 m로 일정했다(낙하 증거 없음).
- **fix가 끊긴 원인:** HIGH 운반 자세에서 든 cyan이 자기 카메라 화면 전체를 채운다(82.7 s, 159.7 s 원본 JPEG를 직접 확인; 화면 전체가 균일한 cyan).
  Codex가 hash를 확인한 8개 운반 영상(82.7/90/102.8/110/122.8/130/140/159.7 s)을 기존 OpenCV 관측기에 넣으면 유효 벽 열이 모두 0개였다(최소 6개 필요).
  `zone_pair_own_load_occlusion_v1_v98` 규칙이 처리한 프레임은 0개였다(포화 cyan이 저대비 CONTENT_ONLY 규칙에 걸리지 않음).
  따라서 HIGH에서 8초 정지하는 기존 체크포인트는 시야를 회복하지 못한다. 대기 시간을 늘리는 방식은 채택하지 않았다.

### 수정: 문 앞·문 뒤·목적지 체크포인트에서 내려놓고 빈 카메라로 재관측한 뒤 재집기 (`solo-cyan-v106-v98-stack-dev-setdown-relook-v1`)

각 정적 경로 체크포인트(3개)에 도착하면 기존 v98 `lower` → 놓기·열기·팔 회수 → `LOOK_P20` 팬 스캔(빈 자기 카메라) → 자기 RGB로 cyan 재탐색 → 기존 호버/blind/close/raise를 거친다.
`begin_relocalization`은 예측 분포를 유지하고 오래된 fix 영수증만 무효화한다. 체크포인트당 한 번만 시도하므로 유한하다. 재관측 뒤 경로를 새 추정으로 다시 계산한다.
마지막 체크포인트에서는 재관측한 추정이 체크포인트에 있으면(3 cm, 0.025 rad) 그 자리에 놓은 채 완료하고, 멀면 다시 집어 옮긴다. 완료 이벤트는 물리 성공이 아니다.

- 입력 경계: 자기 RGB·정적 지도·자기 명령 이력·자기 PF 추정만 쓴다. 재집기에는 원래 pickup slot 위치를 강요하지 않고 자기 RGB에서 보이는 cyan이 정확히 하나일 때만 집는다(둘 이상이면 `CYAN_REGRASP_NOT_UNIQUELY_VISIBLE`로 종료, 기존 표적 영상 없음 실패와 같은 분류).
- dev_light: fix를 못 얻으면 `REOBSERVATION_NO_FIX`를 기록만 하고 계속한다. 기존 종료(표적 영상 없음, 입력 오류, 시간 상한)는 유지한다.
- 과거 hash 고정 모듈은 수정하지 않았다. 카메라 위치·FOV·로봇 외관·모델·지도·물리는 그대로다.
- Codex 후보(미적용 패치)에서 한 가지를 줄였다: 집은 직후(index -1)의 재관측을 뺐다. 그때 오차는 0.09 m로 문 앞 재관측이 어차피 고치고, 재집기 한 번이 늘수록 파지 실패 위험만 커진다(체크포인트 3회 + 목적지 완료).
- **카메라 pan/자세 변경 대안은 채택하지 않았다.** 카메라는 `r*__gripper` 본체에 고정되어 있고 pan(서보 6)은 팔 전체를 돌리므로, 든 cyan이 항상 렌즈 앞에 남는다. 카메라 배치/FOV는 바꾸지 않는다(AGENTS.md).
- 한계: 단독 하중 모델은 여전히 무하중 대용값이고, 낙하·기울기·집게 이탈은 실행 중 감지하지 못한다.

시험: `tests/test_solo_cyan_v106.py`에 체크포인트 진입, 원래 slot 밖 단일 cyan 재집기/다중 후보 거절, 오래된 fix의 기록 후 계속, 마지막 체크포인트 분기 시험을 추가했다. `tests/test_solo_cyan_v106.py tests/test_solo_cyan_v106_runner.py` 31 passed (로컬 11.3초, 속도 측정 아님).

### 참고 자료 (2026-10-06 조사)

- **확인: 저자 초록(전체 본문 미확인)** — Fox, Burgard, Thrun (1998), [Active Markov Localization for Mobile Robots](https://www.cs.cmu.edu/~dfox/abstracts/active-ras-special.abstract.html).
  이동 방향과 센서 방향을 위치 불확실성이 줄도록 고른다는 원리. 우리는 센서 방향 대신 "들고 있는 물체가 시야를 가리지 않도록 내려놓는" 동작을 고정 일정으로 쓴다.
- **확인: 공식 문서** — [robot_localization sensor_timeout](https://raw.githubusercontent.com/cra-ros-pkg/robot_localization/ros2/doc/state_estimation_nodes.rst). 관측이 없으면 보정 없이 예측만 한다. 가림을 fix로 바꾸지 않는다.
- **확인: 공식 공개 코드(해당 부분만)** — [Nav2 AMCL amcl_node.cpp](https://raw.githubusercontent.com/ros-navigation/navigation2/main/nav2_amcl/src/amcl_node.cpp) `nomotionUpdateCallback`의 `force_update_`. 정지 중 갱신을 강제해도 실제 측정(스캔)이 있어야 필터가 갱신된다 → 우리도 새 fix 영수증이 있어야 체크포인트를 통과로 인정한다.
- **확인: 저장소 구현** — `harness/zone_pair_highpose_refix.py`의 v98 set-down 재관측·재집기 순서, `harness/zone_study_pose_delay_p03.py`·`vision_pose_source_p03.py`의 `begin_relocalization`(분포 보존, 영수증 무효화).
- **채택하지 않음(미확인 포함)** — Di Giammarino et al. (ECCV 2024, Learning Where to Look), rvp-group actloc_benchmark, Bajpai et al. (ECMR 2025): 학습·SfM·VLM 경로라서 무모델 조건에 맞지 않는다. 본문/구현은 이번에 확인하지 않았다(미확인).
- 외부 논문의 성공 수치를 이 후보의 성공 근거로 합산하지 않는다. 이 문서의 진단 초안은 Codex(2026-10-06 오프라인 감사, `/Users/changmin/projects/ugrp/outputs/solo-cyan-v106-pr391-20261006-codex-audit/`)가 작성했다.

### 실행 3 — `ee40923ca165dc4fbf8092ba85aeeaa618ce8838` (set-down 재관측 v1, 체크포인트 3개)

출력: `/Users/changmin/projects/ugrp/outputs/solo-cyan-v106-ee40923c-s911-P1-2-place`
결과: STAGE_REACHED_UNQUALIFIED, **lifted=true / inside=false** (SIM 363.2 s, 명령 12000, 모델 호출 0, `physical_success=null`).
`dev_light_would_stop`: ARM_COLLISION_GUARD 3, POSE_UNCERTAIN 400, REOBSERVATION_NO_FIX 2(둘 다 마지막 스캔: 스캔 종료 시점과 재관측 결과 시점). 실제 물리 실패 없음.

- 재관측은 동작했다. 문 앞(130.35 s)·문 뒤(207.35 s) 스캔은 새 fix를 얻었고, 세 번 모두 빈 카메라로 cyan을 다시 찾아 집었다. 문(`door_1`)을 통과했다(실행 2는 x=2.10에서 칸막이에 막힘).
- 마지막 스캔(목적지, 301–311 s)은 fix가 없었다. cyan은 최종 (4.306,-2.173)에 놓였고 B 구역 x 범위 4.3–4.9의 서쪽 경계를 약 1.1 cm 벗어났다(상자 x 반폭 0.017). 마지막 추정과 실제의 xy 거리는 0.29 m였다.
- 추정-실제 오차(사후 채점): 문 앞 0.241→재관측 뒤 0.113, 문 뒤 0.301→0.206, 마지막 이동 뒤 0.321.

**남은 오차의 원인 — 운반 중 이동량 과대 예측.** 세 운반 구간에서 실제 이동/예측 이동 비가 x방향 0.925·0.883·0.888이었다(저장된 명령으로 같은 PF를 오프라인 재생하면 같은 편향이 나온다).
원인은 이번 모듈의 대용값이었다. `build_provider`가 loaded 프로필을 무하중 프로필의 복사본으로 덮어써, 실제 로봇이 갖는 하중 구간의 affine 불감대(v102 측정)가 PF에 없었다.
동일 명령을 v102 HIGH 운반 측정 프로필(`motion_loaded` 그대로)로 재생하면 같은 세 구간의 비가 1.021·0.969·1.009로, 오차가 0.12–0.20 m/구간에서 0.01–0.03 m/구간(x)이 된다. y 방향은 0.02–0.13 m 남는다(요 오차의 옆 이동; 재관측이 보정한다).
재생 스크립트와 방법: `dr_replay_motion_profiles.py`(시뮬레이션·프레임·fix 없음; GT는 채점에만 사용). 이 비교는 s911 한 번의 실행에서 기존 측정 프로필 두 개를 고른 것이며 새 상수를 맞춘 것이 아니다. 다른 seed/slot에서 확인된 것은 아니다(탐색 자료).
참고: 불감대에서는 낮은 명령일수록 상대 손실이 크다(정렬 구간 act/model 0.66). 이 구간은 위치 fix가 흡수하므로 이번에는 건드리지 않았다.
출처: Thrun, Burgard, Fox, *Probabilistic Robotics* (2005) ch. 5(속도/오도메트리 운동 모델과 잡음 모델, 모델 밖 편향은 추정 분산에 반영되지 않으면 과신으로 이어진다) — 일반 서적 지식, 이번에 본문 재확인 없음(미확인).
Borenstein & Feng (1996, UMBmark)의 체계적 오도메트리 오차 보정 원칙(체계 오차는 측정해 보정) — 이번에 본문 재확인 없음(미확인).

### 수정 2 — loaded 이동 프로필 (`solo-cyan-v106-v98-stack-dev-setdown-relook-v2`)

`build_provider`에서 `motion_loaded` 덮어쓰기를 제거했다. `MOTION_PROXY=cyan30g_loaded_uses_v102_pair_high_carry_profile_UNQUALIFIED`.
빔 파트너 입력·pair plan은 계속 끈다(`pair_plan=None`, `carry_yaw_fallback=None`). 30 g cyan에 대한 하중 이동 모델은 여전히 미측정이다(HIGH 자세에서 측정된 프로필의 대용값).

### 실행 4 — `d18600598b25b45f7b99a47e6b08e1d0afe7366e` (loaded 이동 프로필 교체, 재관측 v1 유지)

출력: `/Users/changmin/projects/ugrp/outputs/solo-cyan-v106-d1860059-s911-P1-2-place` (콘솔 로그와 watchdog 로그는 같은 이름에 `-console.log`/`-watchdog.log`).
결과: STAGE_REACHED_UNQUALIFIED, 사후 잠정 기하 판정 **lifted=true, inside=true, floor=true, stable=true(2.0 s), success=true**. SIM 366.2 s, 명령 12030, 모델 호출 0.
`physical_success=null`, `research_result=false`, 실행 중 낙하·기울기 감지 없음은 그대로다. `dev_light_would_stop`: ARM_COLLISION_GUARD 3, REOBSERVATION_NO_FIX 2(마지막 스캔), POSE_UNCERTAIN 1. 실제 물리 실패 없음. 부하 평균(시작→끝) 3.19→2.54.
최종 cyan (4.797,-1.692) — B 구역(x 4.3–4.9, y -2.8~-0.7) 안, 동쪽 경계와 x로 약 8.6 cm(상자 반폭 제외) 여유.

| 시점 | 추정-실제 xy 거리 | 마지막 fix |
|---|---:|---|
| 문 앞 도착 104.7 s | 0.067 m | 37.75 s |
| 문 앞 재관측 뒤 133.9 s | 0.057 m | 132.35 s (새 fix) |
| 문 뒤 도착 187.3 s | 0.069 m | 132.35 s |
| 문 뒤 재관측 뒤 216.4 s | 0.086 m | 216.2 s (새 fix) |
| 목적지 도착 286.5 s | 0.408 m | 218.15 s |
| 목적지 재관측 뒤 315.8 s (fix 없음) | 0.390 m | 없음 |

- 이동 프로필 교체로 문 앞·문 뒤 단계의 오차가 실행 3의 0.24/0.30 m에서 0.07/0.07 m로 줄었다(재관측 전 기준).
- **취약한 점(남은 문제):** 마지막 구간(문 뒤 → 목적지)에서 오차가 0.09 → 0.41 m로 커졌다. 추정이 가고 실제는 x로 +0.27 m 더 가고 y로 0.29 m 덜 갔다. 이동 방향이 추정 대비 약 8° 돌아간 것과 맞는다(헤딩 오차 의심; 실제 요는 저장되지 않아 확인하지 못했다, 미확인).
  목적지 재관측은 fix를 얻지 못했다(실행 3과 같은 현상). 통과는 여유 약 8.6 cm로 이루어졌다. 이 성공은 s911/P1-2/B 한 번의 DEV 판정이며 재현·일반화·확증이 아니다.
  같은 seed에서 모델을 고쳐가며 얻은 결과이므로 탐색 자료다. 다른 seed/slot과 반복 실행으로 확인해야 한다.
- 이번 실행에서 확정한 것: (1) 운반 중 HIGH 시야는 든 cyan으로 가득 차 fix가 불가능하다 → 내려놓고 빈 카메라로 재관측한다. (2) 재관측 후 재집기는 세 번 모두 성공했다. (3) 무하중 프로필 대용값은 하중 구간 이동량을 과대 예측했다.
  확인하지 못한 것: 목적지 스캔에서 fix가 없는 이유(PF 거부 사유 미조사), 마지막 구간의 요 오차, 30 g cyan 하중에 대한 실측 이동 모델.
- 실행 3→4에서 바뀐 것은 `motion_loaded` 프로필 한 가지다(재관측 로직은 동일). 실행 3의 결과가 같은 원인으로 두 번 막힌 것이 아니므로 중단 조건은 충족하지 않았다.
