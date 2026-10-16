# search7 — f932b02c 관문 2건의 접근 정지 복구

2026-10-15, PR #484, `claude/e2e18-grasp-rootcause`. 기준 소스는
`f932b02c5074a7727aab57af1907b69332699c33`이다. 후보 SHA는 커밋 뒤 만든
`outputs/e2e18-admin/vm3-queue/20261015-grasp-search-<SHA8>.json`에 고정한다.

## 원장으로 확인한 원인

회수한 GCP `n4-highcpu-64` 관문은 **완료 14/16 성공**, 계획40·시작16·미시작24,
실패2·중단0·HOST_ERROR0·핸드오프0이다. ≥38/40 관문은 미통과다.
`SUPERVISOR_STOP.json`의 두 독립 에피소드(12,15)는 사유 `episode_timeout`,
단계 `approach`/`ready`가 같아 `repeated_cause_v1` 감독 정지됐다.
과거 시작 필터는 원래40개 중1개(seed86004 r2,2.5%)를 제외했다.
[전체16개 요약·원본 위치·해시](search7-summary.json)에 성공14개도 포함했다.

- **ep012 / seed86012**: r1=청록, r2=파랑. r1은 탐색 뒤 +3.2초부터 접근했고
  **+18.0초까지 실제 발행 바퀴 명령이 있었다**. 이후 `approach`의 `_route`가
  `waypoint(...) is None`에서 `_hold`를 반복한다. 팔 완료·시야 확보·READY 허가를
  기다리는 분기가 아니다. **계획기437회, no_path0, blocked_goal0**이다.
  “계획기 호출 없이 5–7초부터 정지”라는 운영 관찰은 원장과 다르다.
  관측 밴드와 고정 빔 형상에서 추론한 자기 청록 끝의 반경20mm + 로봇130mm
  여유가 연결을 막는다. +20초 단면에서 차체는 여유 밖2.156mm에 있지만,
  5cm 격자 A*의 첫 점으로 가는 선분은 여유를9.766mm 침범한다. 나머지
  세 점으로 가는 선분도 모두 막혔다. A*의 격자 경로 존재가 연속 현재 자세에서
  연결 가능한 경로를 뜻하지 않는데, 실패한 같은 경로를 계속 다시 계산했다.
- **ep015 / seed86015**: r1=파랑, r2=청록(운영 관찰의 끝 색과 다름).
  r1은 +5.1초에 보이는 밴드를 얻은 뒤 `approach`, r2는 자기 끝에서 `ready`다.
  계획기55회 모두 `blocked_goal/no_path`. 차단 대상은 **관측된 `green_1` 화물**이며
  동료·자기 빔 끝·정적 벽이 아니다. 목표까지122.503mm인데 화물 보수 반경
  30.741mm + 패딩5mm + 로봇130mm =165.741mm이므로 **43.237mm 침범**이다.
  이 반경은 관측 모델의 보수 경계이고 실제 접촉/몸체 겹침을 증명하지 않는다.
  기존 nominal 핸드오프는 정적 지도만 검사하므로 이 동적 화물 여유를 처리하지 않는다.

직접 본 영상은 각 에피소드 **+0/5/10/20/30/45/59초 × overview/r1/r2 =21장**,
총42장이다. 처음·중간·끝을 모두 확인했다. 두 로봇이 같은 끝으로 가거나 서로
물리적으로 막는 양상은 보이지 않았고, ep12는 이동 후 자기 끝 부근에서 정지,
ep15는 먼 자기 끝을 본 채 접근을 시작하지 못했다.
[42장 경로·manifest 대조 SHA-256](search7-frame-review.json), 검토용 모음은
`outputs/e2e18-admin/search7/ep12-frames.jpg`, `ep15-frames.jpg`에 있다.
영상은 평가 전용이며 제어 재생에는 쓰지 않았다. 성공14개는 요약 JSON 수준으로만
비교했다: 완료26.0–42.0초, 로봇별 계획기0–32회, 일부 일시 blocked_goal1–7회도
성공했다. 단일 blocked_goal을 곧바로 실패로 바꾸지 않았다.

## 표준 방법과 적용 범위

2026-10-15 공식 문서의 관련 절을 열람했다.

1. [Nav2 SimpleProgressChecker](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/core_servers/controller_server/controller_server_plugins/simple_progress_checker/): 기준 위치로부터 최소 이동 거리와 허용 시간을 검사하는 방법.
2. [Nav2 상세 Behavior Tree 설명](https://docs.nav2.org/jazzy/getting_started/nav2_behavior_trees/detailed_behavior_tree_walkthrough/detailed_behavior_tree_walkthrough/): navigation 실패 뒤 contextual recovery와 유한한 재시도, recovery subtree의 순차 복구와 navigation 재시도.
3. [Nav2 RecoveryNode](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/core_servers/bt_plugins/controls/RecoveryNode/): 주 행동 실패 → 복구 행동 → 주 행동 재시도, 정해진 재시도 수를 넘으면 실패 반환.

거리·시간 진척 검사와 **복구1회 → 재시도 → 명시적 실패 반환** 구조를 따른다.
이 프로젝트에 필요한 차이는 좌표가 실시간 정답/TF가 아니라 자기 발행 명령을 적분한
기존 자세라는 점, 막힘 반환이 기존 `approach_blocked_handoff`라는 점이다.
기본 Nav2의0.5m/10초를 그대로 파지 근처에 쓰지 않고, 로컬 접근에10mm/3 SIM초를
선택했다. 이 값의 새 물리 관문 적합성은 아직 미검증이다. 관측 장애물을 지우는
clearing이나 blind backup은 구현하지 않았다. 캐시 **경로만** 버리고 허용된
현재 관측·기억과 기존 안전 검사를 그대로 써 재계획한다.

## 변경

기본 OFF `--approach-progress approach_progress_v1`을 추가했다. 접근 주행 중
10mm 넘는 순 위치 변화가3 SIM초 없으면 캐시 경로를 버리고 재계획1회, 다시
3초 동안 같은 정지면 바퀴0·집게 열림·pick 없이 명시적 지도 핸드오프를 낸다.
진척이 있으면 타이머/재시도를 초기화한다. READY의 GO/ACK 대기는 제외하며
정렬은 기존 오차 진척 검사에 맡긴다. search를 거쳐도 접근의 미해결 타이머는
지워지지 않는다. 실시간 정답·접촉·평가 성공/높이·측정 관절은 읽지 않는다.
지도 코드의 실제 재배치 실행은 이 변경에 포함하지 않는다.

교사/배치 CLI, 결과·resource-admission·관문 요약, 속도 재사용 및 학습 기록 허가의
모드 일치 검사까지 같은 토글을 연결했다. 기존 기준 모드는 계속 `off`다.
물리/카메라/접촉/IK/구동 포트/안전 여유는 바꾸지 않았으며 weld OFF다.

## 검증

- 변경 모듈 관련3파일 `test_grasp_act_progress.py`, `test_grasp_act_goal_set.py`,
  `test_grasp_act_batch.py`: **81 passed**. 실제 저장 정지 입력2개·토글 OFF·유한
  재계획/핸드오프·READY 제외·잘못된 profile 거부·하위 실행 전달·기록/속도 모드
  혼합 거부를 검사했다. 새 물리/렌더/모델/원격 실행은0회다.
- [원장 재생](search7-replay.json): 과거 성공6개(a4564520 원본)의 **4,664명령**을
  고정 기준 f932b02c와 후보 ON으로 모두 재생했다. 기준↔후보의 시각·바퀴·PWM·펄스
  길이·단계·done이 정확히 동일하다. 저장 GCP↔Mac 펄스 길이만 libm 차이≤1e-12초를
  허용하며 다른 필드는 정확히 일치한다. seed78113에서 재계획1회가 있었으나
  발행 명령은 모두 동일했다. 나머지5개는 복구에 진입하지 않았다.
- 실패2개도 최초 입력부터 전체를 재생해 기준 명령을 검증했다. 후보는 ep12 **+24.0초**,
  ep15 **+11.1초**에 깨끗한 핸드오프를 냈다. 그 시점까지 양쪽 전체 명령은 기준과
  정확히 같고, 두 로봇 모두 바퀴0·집게 열림·pick 없음, 기존 peer 핸드오프 정리도
  통과했다. 핸드오프를 물리 파지 성공으로 세지 않는다.
- 재생 원본40파일의 저장/압축 해시와 decoded 해시, 검토 JPEG42장의 manifest 해시,
  관문/감독 정지/로그의 회수 SHA256SUMS를 대조했다. 원본은 수정하지 않았다.
  재생 입력에서 평가 truth를 먼저 버려 **invisible_measurements=0,
  held_world_reads=0**이다. 이 수치는 simulator/World가 없는 오프라인 재생 범위이며
  새 GCP 실행의 입력 감사까지 완료했다는 뜻이 아니다.

재현 명령:

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q tests/test_grasp_act_progress.py tests/test_grasp_act_goal_set.py tests/test_grasp_act_batch.py
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m scripts.replay_grasp_act_progress --normal-run /Users/changmin/projects/ugrp/outputs/gcp1-runs/grasp-search-diagnostic-gcp-a4564520 --failed-run /Users/changmin/projects/ugrp/outputs/gcp1-runs/grasp-search-gate-gcp-f932b02c --out experiments/2026-10-14-e2e18-grasp-rootcause/search7-replay.json
```

## 다음 대기열과 미검증

기존7개+실패2개 시작 조건 그대로인 [진단9 계획](teacher-search7-diagnostic-plan.json),
새 **87000–87039** [관문40 계획](teacher-search7-gate-plan.json)을 따로 봉인했다.
로컬 기존 대기열/기록에서 이 정수 시드 범위의 예약 충돌을 찾지 못했으며 운영자가
원격 실행 예약을 제출 직전에 다시 확인해야 한다. 새 시드 원래40개에서 정적 목표
차단2/40(5%,87014 r2·87023 r1)을 제외했다. 생성 시 nominal 검사43제안 중3거절,
수용40이다. 과거86000대의1/40 제외와 합치지 않는다. 결과 기반 재선택은 없다.

순서는 **진단9 → 같은 SHA/토글 속도16 → 관문40**이다. 정상0–5는6/6 물리 성공,
기존 어려운6은 깨끗한 nominal 핸드오프, 새7–8은 실제 성공 또는 깨끗한 명시적
접근 핸드오프를 요구한다. 진단9개 전부 완료·회수·영상 검토 후 속도16의
wall/SIM 중앙≤3.5를 새로 잰다. 그 뒤 **조정자 승인 전 관문40 제출 금지**다.
`gate_promotion_authorized_if_all_conditions_pass=false`이고 과거 승인은 승계하지 않는다.
새 관문은≥38/40 성공이며 모든 핸드오프는 분모에 남고 성공에서 제외한다.
이전 f932 대기열은 superseded·ready=false로 바꾼다.

GCP의 실제 진단9·속도16·새 관문40, 실제 지도 재배치 후 재접근/파지 회복,
이전 관문 성공14개의 전체 명령 재생은 미검증이다. 새 후보의 물리 성공률은0/0이며
실패 해결을 파지 성공으로 확정하지 않는다. 요청 범위대로 커밋·push·대기열·PR 댓글만
남기고 원격 접속/제출/감시와 Mac 물리·렌더는 하지 않는다.
