# Solo 구역 운반 2차 수정 — top 카메라 제어 입력 금지

PR #505 / `claude/map-carry-zone`, 기준 `fc874c145680f515450f4f221a77eef3ad318521`.
실행 소스는 이 기록을 포함한 커밋이며, push 뒤 생성하는
`outputs/e2e18-admin/vm3-queue/20261015-solo-carry-<SHA8>.json`의 `sha`에 전체 SHA를 고정한다.

## 결정과 보존

[이슈 #366](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/366)의
2026-10-03 결정: “공용(위) 카메라는 쓰지 않는다. 지도 만들기나 위치 추정에 쓰지 않는다.”
이 결정과 이번 사용자 지시가 이전 AGENTS.md 문구보다 우선한다.
`chassis_candidates`, `RGBCommandPose`, `CarryToZone.observe(tops, ...)`는 과거 소스를
보존하지만 실행 시 ValueError로 거부한다. runner의 top 이미지 소비는 `review-top` 평가 저장만 남겼다.
기존 carry1·계획·요약·거부 대기열은 변경하지 않았다.
거부 대기열 SHA-256: `4164c4a83dc65386f7b1cdcc37004868d298cced0c3b6eb12d290859ec667ef3`.

## 먼저 확인한 기존 방식과 재사용

- #461 관련 `harness/e2e_own_inputs.py`, `scripts/run_e2e_ownmap_live.py`,
  `harness/e2e_setdown_relook.py`: 자기 시작 프레임과 명령/RGB 추정, 실제 자기 RGB 재관측 후 보정.
  **자기 시작 프레임의 (0,0,0)은 정적 세계 지도의 초기 위치가 아니다.**
- `harness/owncam_bootstrap_v6b.py:dock_prior`: 정적 작업 시작 prior를 관측 fix와 구분하는 원칙.
  현 v3 지도에는 `start_dock`이 없으므로 도크 좌표나 로봇별 줄을 꾸며내지 않았다.
- #480 `origin/codex/e2e18-pose-diagnosis:harness/e2e_static_rgb_localizer.py`:
  정적 자유 공간 전역 초기화. 현재 carry에 이 미인수 경로를 복사하지 않았다.
- #507 `map-amcl`의 `harness/map_amcl.py`를 읽기만 했다(확인 HEAD `87d62f67`).
  그 worktree는 수정하지 않았고 구현·의존성도 가져오지 않았다.
- 실제 재사용: `grasp_act_visible_world.command_delta`, `active_lookaround.OwnPose`,
  `plan_path`/`waypoint`, 기존 목적 바닥 HSV/FK/가림 마스크,
  `SoloLookaround` → `LookaroundLocalizer`의 정적 벽 바닥선·문·구역 경계 관측/격자 보정.

## 초기값의 근거와 달라진 진단 조건

새 `diagnostic-plan-v2.json`은 고정 작업 설명을 명시한다:
**정적 pickup 구역 서쪽 경계에서 0.25 m 서쪽, 그 구역의 y 중앙에서 동쪽을 보고 시작.**
두 사용 지도에서 명목값은 (-0.70 m, -0.85 m, 0 rad)이다.
제어기는 `task_start(static_map)`만 읽고, 초기 불확실성은 개발 가정 5 cm / 3°다.
명목값은 RGB 측정으로 세지 않으며 `last_rgb_fix_t=null`로 시작한다.

장면 생성기가 이 작업 조건으로 r1을 배치하면서 x/y 각각 ±2 cm, yaw ±2°의 별도
고정 난수 오차를 준다. 데이터 흐름은 **고정 작업 설명 → 장면 배치**이며,
spawn/화물 정답 → 자기 위치 초기화가 아니다. 제어기는 이 오차를 읽지 않는다.
기존 화물 주변 무작위 출발과 조건이 달라진 새 진단이며, E2E #461의 동일 실행 조건이나
기존 solo 성공률로 취급하지 않는다. 8개 계획 모두 정적 26 cm 여유 검사 통과,
주차된 다른 로봇과 최소 2.07 m(계획 파일의 설정 검사만, 물리 검증 아님).

## 제어·평가 경계와 한계

명령 추측항법은 접근부터 운반·후퇴·둘러보기까지 누적한다. RGB 프레임을 받았다는 사실과
목적 바닥 색 확인은 위치 fix가 아니다. 명령 시각 지연과 추정 불확실성을 기록하고
개발 한도(시각 0.2초, xy sigma 0.5 m, yaw sigma 20°)를 넘으면 운반을 멈춘다.
이 한도·분산은 물리 오차 보증이나 안전 인증이 아니다.

내려놓은 뒤에는 같은 명령 추정 belief에서 주변 지형지물을 볼 방향을 선택한다.
명령을 이중 적분하지 않으며 실제 자기 RGB의 격자 보정이 있을 때만 fix 횟수/시각을 갱신한다.
정답과 오차 비교는 평가 출력에만 쓴다. held 정답 차단·구역 전체 발자국·무낙하·접촉 해제·안정
평가와 운반/근거리 학습 표본 구분은 유지했다. 운반 토글 기본 off, 학습 RGB off, gate 승격 off다.

**현재 기본 경로가 충분하다고 입증하지 못했다.** 운반 중에는 명령 누적 오차가 남고,
바닥 색만으로 방향·구역 내 정확한 위치·전체 화물 발자국을 증명할 수 없다.
목적지에서 놓은 후의 보정은 이미 발생한 경로 이탈이나 낙하를 복구하지 않는다.
동적 장애물 회피·loaded 주행·실제 재관측 수/오차 개선·새 시작점의 대상 탐색도 미검증이다.
원격 진단에서 이 한계를 측정하기 위한 준비이며 성공 관문/학생 데이터 승인 근거가 아니다.

AMCL 연결 자리는 `CommandPose(..., amcl_option='report_v1').accept_amcl(report, now)`뿐이며
기본은 off다. own RGB 출처·로봇·지도 해시·pose·xy/yaw sigma·시각·나이를 요구하고,
다른 출처, 추가 top/truth 필드, 재사용·과거 시각·과도한 불확실성을 거부한다.
이 포트는 현 명령 시각까지 외삽한 report(age_s=0)를 요구한다. 실제 AMCL 공급자/runner 연결은
아직 없으며 이번 계획에서도 켤 수 없다. 공유 belief 참조는 보정 뒤에도 유지한다.

## 검증과 제출 범위

관련 오프라인 5파일만 실행했다. 명령과 최종 통과 줄은 `offline-tests-carry2.txt`,
파일 해시와 8개 미실행 상태는 `summary-carry2.json`에 기록한다.
회귀 범위는 top 경로 거부, 실제 runner의 top 평가 바이트가 perception에 들어오면 실패,
자기 RGB 입력, 시작 prior/명령 적분, AMCL off/시각/출처, 보정 belief 공유,
held 입력 차단, 구역 발자국·무낙하·접촉 해제 평가다. 실제 runner 검사는 가짜 backend다.
Mac 시뮬레이션·렌더, 원격 실행·모델 호출·학습은 모두 0회다.
새 대기열은 승인 false·전체 실행 off다. 원격 seed 미사용·예산·저장 공간·속도·첫 영상
점검 및 정확한 새 SHA 승인은 조정자에게 남는다. 기존 거부 대기열은 보존한다.
