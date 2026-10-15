# search20 — 승인/유지 분리와 정렬 정지 보완 (기본 OFF)

2026-10-15, PR #484, 기준 search19 `06558d64a2fd1bd34e59cfea7e0b40045b6dab77`.
**OFFLINE_CHECKED / PHYSICAL_NOT_READY**. 실제 search19 GCP 첫 2회는 **0/2**이며 그대로 보존한다.
새 물리 실행·Mac MuJoCo 시뮬레이션/렌더·모델 호출·원격 호스트 접속·학습은 하지 않았다.
최종 커밋은 아래 큐의 `sha`와 소스 파일 해시로 고정한다.

## 실제 원장과 정렬 원인

원본은 `/Users/changmin/projects/ugrp/outputs/gcp1-runs/grasp-search19-repro4-gcp-06558d64/diagnostic/episode-{000,001}/raw/`.
`eval-only.jsonl`에서 **visible_measurements만** 관측기에 전달하고 실제 applied_command, 시계, GO/ACK를 재구성했다.
8311709 **354/354틱**, 315709 **640/640틱**의 원래 명령·PWM·기간(허용 오차 1e-12)·done·phase가 일치한다.
이하 16.4 등은 원장 `t`이며, 영상 표시는 에피소드 경과 시간이다.

- **8311709:** 막은 것은 tile_1 하나다. 활성화 3틱 해소, 실제 접근 15.4초까지 진행 후 추정 흔들림으로 재차단했다.
  새 자세의 차체 여유는 5.7초 15.5 mm, 15.4초 16.7 mm, 16.4초 5.3 mm, 17.4–19.4초 2.3 mm였다.
  원래 5 mm 자세 검사 / 7 mm 구간 검사가 16.4초 퇴로를 거부했고, 이후 5 mm 목표 검사도 거부했다.
- **315709:** 접근은 통과해 22.3초 정렬에 들어갔지만 `alignment_no_progress`로 끝났다. 상대는 기다리다 에피소드가 종료됐다.
  정렬 말기 추정 로컬 잔차는 약 x −49.5 mm / y −35.1 mm / yaw +0.0066 rad다.
  기존 yaw→y→x 우선순위가 빔 쪽 횡이동을 계속 고른다. 빔 끝 원판과 차체 원판의 현재 여유가 약 **0.60 mm**여서
  이 펄스는 사후 검사에서 hold로 바뀌었다. 같은 상태의 **후진 축은 두 발행 모델 모두 통과**했다.
  상대 위치는 이 차단의 직접 원인이 아니다.

개요·r1·r2 저장 JPEG를 0/6/12/19/25/31초에 각각 검토했다(**18장**, 처음·중간·끝 포함).
마지막 정렬에서는 r1이 파랑, r2가 청록의 반대 끝을 보고 있다. 같은 끝 경쟁이나 상대 차체의 직접 차단으로 분류하지 않는다.
초기 최근접 끝이 배정과 다른 관계는 과거 search19 기록과 구분한다.
프레임 경로·SHA-256은 [오차/프레임 원장](search20-error-distribution.json)의 `reviewed_frames`에 있다.
기존 montage: `/Users/changmin/projects/ugrp/outputs/e2e18-admin/gcp-reports/search19-06558d64-ops/grasp-search19-repro4-gcp-06558d64-episode-000-montage.jpg`.

## 새 토글과 여유의 근거

`--search20 search20_v1`은 기본 off이며 기존 두 search19 토글을 요구한다.
search18의 65 mm 상수와 search19 off 경로는 바꾸지 않는다. 새 모드는 몸체 대체의 새 자세 승인에 **140 mm**,
이미 승인한 자세 계열의 계속 검증에 **2 mm**를 쓴다. 목표·퇴로·경로·발행 펄스는 같은 문턱을 사용한다.
2 mm는 겹침 부근의 샘플링 여유이며 위치 오차 보증이 아니다. 구간 샘플 간 차체점 이동은 0.8 mm 미만이다.

실제 저장 search18 16회 + search19 2회의 평가 전용 오차를 최초 로봇 좌표계에 맞춰 다시 계산했다.
화물 상대 벡터 오차에 차체의 yaw 오차 변위를 더한 상계(5,287개, 기억된 화물 포함)는 다음과 같다.

| 오차 상계 | p50 | p90 | p95 | p99 | 최대 |
|---|---:|---:|---:|---:|---:|
| 상대 화물/차체, mm | 9.28 | 50.31 | 71.36 | 111.86 | 135.87 |

최대값을 5 mm 단위로 **올림한 140 mm**를 승인 여유로 쓴다. 기존 화물 원판의 별도 5 mm 패딩도 유지한다.
65 mm는 이 분포의 p95도 덮지 못한다. 성공 수를 늘리려고 5 mm로 내리지 않는다.
같은 코호트의 반복 틱이며 이미 살펴본 실패도 포함하므로, 독립 보정 자료나 새 조건의 확률적 안전 보증은 아니다.
평가 정답은 이 오프라인 표에만 쓰고 교사는 이 표·정답 좌표를 읽지 않는다.

이미 접근 중이면 `(배정 끝, offset, distance)` 계열을 고정하고 새 영상의 끝/각도로 목표를 갱신한다.
이전 목표 1 mm 일치를 요구하지 않으며, 남은 경로·새 끝 연결·퇴로·가시성·집게·IK·팔 sweep을 다시 검사한다.
일시 거부/예산 소진/무진행 재계획에서도 이전 경로는 **검증 안 된 제안**으로만 남긴다.
검사 실패 틱은 hold이고, 재검증 전에는 그 경로로 움직이지 않는다. 실제 겹침 및 기존 3초 인계·진행 시한은 유지한다.

정렬에서는 원래 명령이 거부될 때만 다른 활성 축(후진 포함)을 시험한다.
두 발행 모델과 기존 팔 검사를 통과하고 현재 보이는 목표/각도 오차를 줄여야 한다.
이미 승인된 정렬 펄스·준비 기준·IK·집기 순서는 유지한다. ACT 학생의 대체 경로를 추가하지 않았다.

## 계산 예산과 저장 재생 결과

몸체 대체/유지 판단은 틱당 **32,768 검사, A* 512 노드, 경과 1.0초**의 협력적 상한을 둔다.
경계 검사 사이의 한 기본 연산과 OS 스케줄링까지 즉시 중단하는 실시간 보증은 아니다.
초과하면 부분 결과를 실행하지 않고 PWM을 복원해 hold한다.
정확한 장면·자세·방향·여유를 키로 하는 LRU는 4,096개, 완료된 팔 sweep 캐시는 4개로 제한한다.
매 틱 teacher 원장 `planning_compute`에 총 시간, 몸체 판단 시간, 검사 수, 캐시 hit/크기, 예산 초과를 남긴다.

최종 저장 입력 재생: **18회·9,144틱 기준 불일치 0**, 성공 12건의 검사상 악화 **0/12**.
8/12에는 명령 변화가 있으므로 명령 동등성이나 새 물리 성공 12/12를 주장하지 않는다.
새 모드 off는 실제 search18 8,150틱과 search19 994틱을 각각 재현했다.
입력 감사는 모든 실행에서 `invisible_measurements=0`, `held_world_reads=0`이다.
진짜 겹침 후보는 8311709 **54/118**, 8311723 **77/118** 모두 계속 거부한다.
관련 7개 시험 파일 **88 통과**. [전체 요약·실행별 원본 해시](search20-replay-summary.json).

| 실제 마지막 유효 상태(15.4초)에서 이어받은 재생 | 16.4 | 17.4 | 18.4 | 19.4 |
|---|---|---|---|---|
| 기존 search19 | blocked_retreat | blocked_goal | blocked_goal | blocked_goal → 인계 |
| search20, 같은 계열·새 목표 재검증 | 유지 | 유지 | 유지 | 유지, 인계 없음 |

16.4초 새 목표 이동은 **21.58 mm**이며, 기존 경로 끝 1 mm 검사로는 유지할 수 없던 경우다.
이는 15.4초 실제 상태에서 시작한 이어받기 진단이다. 새 명령 뒤에도 실제 원장의 미래 영상/발행 명령을 사용하므로 새 궤적이 아니다.
원래 상태에서 매 틱 독립 분기하면 17.4초 이후에는 이미 경로가 사라져 있어 그 자체로 복구되지 않는다.
**처음부터 켠 새 실행은 5.7초의 15.5 mm 자세를 140 mm 승인 기준으로 거부한다.**
따라서 이 표를 8311709의 실제 접근/들기 성공 개선으로 보고하지 않는다.

최종 재생의 몸체 판단 최대는 약 **0.822초**, 8311709 원래 상태 한 틱 분기에서 검사 수 상한에 따른 hold 1회가 있다.
315709 몸체 판단 최대는 약 0.052초다. 기존 비몸체 경로 계산은 전체 틱 최대 **3.790초**가 남는다.
이 상한은 모든 기존 계획기의 계산을 제한하지 않는다. GCP 새 wall/SIM과 물리 성공은 미측정이다.

## 장면과 비교 큐

실제 두 GCP 원본은 `s1_normal_mixed_v4`, `grasp_act_scene_v1`, `grasp_act_teal_blue_v1`,
`teacher_profile=visible_only`, `self_pose_source=issued`, `search18_footprint=off`, 두 search19 토글 on이다.
원본 v4 시나리오 해시는 `004c61f7324eac530c81dcf226ad47582e8ad9032089c30d24878e2fba855ac6`다.
타일/캔이 남은 이유는 계획 파일의 `scenario_id`가 v4에 고정됐기 때문이다.

권고는 **v4를 재현 대조군으로 보존하고 사용자 결정의 v6를 별도 비교**하는 것이다.
큐의 두 번째 후보만 계획 토글 `cargo_scene=cargo_v6`와 별도 v6 시나리오 ID/해시를 쓴다.
v6 파일의 tile/can 부재와 해시를 실행 전 검증한다. 같은 시드·빔·로봇 배치·pan으로 비교하며 합산하지 않는다.
현재 기본 장면을 바꾸거나 v6가 성공할 것이라고 판정하지 않는다.

새 큐: `/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/20261015-grasp-search20-<sha8>-diag.json`.
한 큐에 후보 2개(`search20` / `search20+cargo_v6`), 후보마다 재현 315709/8311709/8311711/8311723 + 신규 8312200–8312211,
총 32개 진단을 준비했다. 승인·실행·관문·기록·학습·승격 관련 플래그는 전부 false다.
로컬 355개 파일에서 신규 충돌 0을 확인했다. 원격 재고·예약은 미확인이며 제출하지 않았다.
기존 큐는 수정하지 않고 SHA-256으로 연결한다. 비용·유휴·기간 가드는 그대로 요구한다.
독립 재검토, 운영 승인, 같은 GCP 머신 종류의 실제 진단이 남는다.

## 재현 명령

```sh
PYTHONPATH=. /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m scripts.replay_grasp_act_search20 --cohorts search18 search19 --out /tmp/search20-replay
PYTHONPATH=. /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m scripts.analyze_grasp_act_search20 --out /tmp/search20-audit
PYTHONPATH=. /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q tests/test_grasp_act_search20.py tests/test_grasp_act_search19.py tests/test_grasp_act_search18.py tests/test_grasp_act_batch.py tests/test_grasp_act_admission.py tests/test_grasp_act_visible_only.py tests/test_grasp_act_search15.py
```

최종 raw 재생 산출물: `/Users/changmin/projects/ugrp/outputs/e2e18-admin/analysis/search20/replay-verified/`.
앞선 `replay-v1`, `replay-final`, `replay-retained`, `replay-release`는 중간 탐색이며 최종 근거와 합산하지 않는다.
새 큐를 만드는 명령은 커밋 뒤 `python -m scripts.prepare_grasp_act_search20_queue --sha "$(git rev-parse HEAD)"`다.
이는 로컬 JSON만 만들며 기존 큐가 있으면 덮어쓰지 않는다. raw는 로컬 보존이며 별도 외부 백업 완료를 뜻하지 않는다.

## 참고 자료

- [실제 GCP 보고](../../outputs/e2e18-admin/gcp-reports/search19-06558d64.json) 및 위 원본 경로:
  0/2, wall/SIM 5.71 경고, 원본 재생과 프레임 검토의 일차 근거. worktree의 outputs 링크가 없으면 위 절대 경로를 사용한다.
- [평가 전용 오차 분포와 18장 프레임 해시](search20-error-distribution.json), [재생 요약](search20-replay-summary.json),
  [과거 search17 오도메트리 측정](search17-odometry.json). 과거 65 mm 문턱을 성공률에 맞춰 내리지 않았다.
- [Nav2 공식 footprint collision checker 본문](https://raw.githubusercontent.com/ros-navigation/navigation2/main/nav2_costmap_2d/src/footprint_collision_checker.cpp):
  2026-10-15 본문 열람. 자세별 형상 변환 원칙을 참고한다. Nav2의 격자 구현·안전 보증을 이식한 것은 아니다.
- [Fox·Burgard·Thrun, DWA (1997), 저자 초록](https://www.cs.cmu.edu/~dfox/abstracts/colli-ieee.abstract.html):
  2026-10-15 열람. 허용 명령과 목표 진행을 함께 확인하는 원칙이다. 여기서는 발행 명령 운동학만 쓰며 제동/실물 보증은 아니다.
