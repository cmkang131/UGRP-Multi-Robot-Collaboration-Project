# release6 — 놓기 교사의 관측 소진 뒤 지도 기반 다음 시점 (2026-10-15)

기준 `e96386d319fee37cbf109867f55a1b9aefac4229`, GCP 진단 **6/7**.
실행 소스 브랜치는 `claude/grasp-act-probes`다. PR #491 head인 `claude/grasp-act-release`는 별도다.
이 문서는 저장 증거 감사와 기본 off 후보 기록이며 새 물리 성공 기록이 아니다.

## 원장·영상으로 확인한 원인

74940 원본: `/Users/changmin/projects/ugrp/outputs/gcp1-runs/release5-diagnostic-02-e96386d3/`.
65.9 SIM초에 `active_observation_exhausted`, 빔 중심 거리 0.328748 m로 끝났다.
원본 7건의 result·plan·명령 원장을 직접 해시 검증했다. 회수 결과와 운영 요약을 합산하지 않는다.
새 복구를 계산할 때 실행별 `plan.map_id`를 읽고 원본 `scene.static_map_sha256`과 대조했다.
74940 지도는 `zone_wide_door_geometry_v3`, SHA-256 `2302d273bcd30a9cc9d3166c753f2d40fcf3f03654369d23cd00324b4ca4688d`다.
일곱 진단에는 이 지도 5개와 `zone_wide_two_doors_final_v3` 2개가 섞여 있다.

| 시각 | 로봇 | 누적/사용 시야 | 사용 벽 점·구역선·문 | 선/가설/합의 선 | rank·score gap | 원본 결정과 재생 |
|---|---|---|---|---|---|---|
|21.7|r1|3/3|212·7·0|10/87/3|2·약 0|모호함, gap < 0.75|
|21.7|r2|3/3|152·9·0|10/43/3|2·0.51591|모호함, gap < 0.75|
|33.8|r1|13/13|894·20·0|32/1098/13|2·3.89340|수락|
|33.8|r2|13/13|699·26·0|40/939/13|1·3.32614|평행선 합의, rank=1이라 거절|
|45.9|r2|23/18|1025·25·0|50/1791/11|1·0.01571|반복 스윕으로도 rank=1·모호함|
|63.4|r2|33/18|743·11·0|28/1174/8|2·0.82359|다른 지도 위치를 수락한 뒤 내려놓기 축 검사에서 거절|

벽 점/선은 반복 관측 합계이며 고유 지형지물 수가 아니다. 각 가설·지형지물 group·잔차는
[재생 상세](release6-replay-detail.json.zst)에 있다. 해당 지도 재생은 원본 수락/거절과 일치한다.
비선형 풀이의 플랫폼 부동소수점 차이는 있기에 초기 동률 가설 순서를 바이트 동일이라고 하지 않는다.

**r1이 다음 후퇴/몸 회전으로 가지 않은 이유는 예산이나 상태 전이 결함이 아니다.**
33.8초 수락 뒤 35.4초 `localized_margin`(축 0.644674 m, 옆 0.048286 m)을 보고했다.
`pending`은 유효 margin이 없는 로봇만 고르므로 r2만 다음 단계에 들어갔다.
r1 관측 단계는 1이며 후속 빈 ScriptRunner의 로그는 0개다. 새 관측 없이 같은 결정을 다시 쓰고 기다렸다.

r2의 35.5초 후퇴는 안전 검사 때문에 생략됐다. 그때 자기 합의 후보는
`[4.70964, 1.09329, -1.44004]`이며 0.10 m 뒤의 추정 y는 약 1.19244 m다.
북쪽 벽 y=1.45, 반두께 0.025, 기존 차체 반경 0.18 + 불확실성 여유 0.15에서는
중심 y≤1.095가 필요하므로 후퇴 경로가 안전하지 않다. 생략 뒤 같은 자리 스윕은 새로운 기하를 만들지 않았다.
47.6초의 기존 +45° 회전은 당시 살아 있는 두 가설에서 안전해 실행됐다.
마지막 18시야 제한으로 초기 관측이 빠졌고, 마지막 10시야 중 4개는 검출 0이었다.
마지막 수락 위치 `[2.89794,-2.44752,-3.00188]`는 평가 전용 실제 위치와 **4.07790 m/91.484°** 차이가 났다.
이는 제어 후 평가에만 결합한 값이다. 실제 종료 보고는 `release_axis_unaligned`였다.
따라서 운영 요약의 “위치 합의가 수락되지 않았다”는 마지막 상태를 정확히 설명하지 않는다.
65.2초 r2 단계 3을 보고 기존 `any(stage>=3)` 상한이 종료를 선택했다. 전체 180초 상한에 닿은 것이 아니다.

처음(prefix 첫 프레임)·중간·끝, release 15.1/22.1/33.1/44.1/54.1/65.1초에
개요·r1·r2 **21장**을 직접 보았다. 두 로봇은 반대 끝이며 본 프레임에서 서로 막지 않았다.
r1의 뒤쪽 반복 프레임과 r2 회전 중 벽만 보이는 시야를 확인했다. 프레임 경로·해시는 상세에,
검토 접촉 시트는 로컬 `outputs/release6-review/74940-contact-sheet.jpg`에 보존했다.

## 참고 자료와 적용한 표준 방법

기존 [참고 기록](release-localization-reference-first.md)을 이어서 수정 전에 원문을 확인했다.

- Fox, Burgard, Thrun (1998), [Active Markov Localization](https://biorobotics.ri.cmu.edu/papers/sbp_papers/integrated4/fox_active_loc.pdf),
  §4.1 식 (3)–(8), §4.2 식 (9)–(11): belief를 상대 이동으로 예측하고 관측 후 기대 entropy 감소에서
  실행 비용을 빼 다음 이동/센서 방향을 고른다. 장애물 확률도 위치 가설들에 걸쳐 계산한다.
- Zhang, Scaramuzza (2019), [Beyond Point Clouds: Fisher Information Field for Active Visual Localization](https://www.ifi.uzh.ch/dam/jcr:5a26a3b4-ce01-4647-8cf6-f6a24e579a85/ICRA19_Zhang.pdf),
  §II 식 (2)–(4): 보이는 지형지물의 `Jᵀ R⁻¹ J`와 FOV로 후보 위치/방향의 정보량을 평가하고
  이동·충돌 비용과 함께 선택한다. [저자 공개 구현](https://github.com/uzh-rpg/rpg_information_field)도 확인했다.

위 식의 **선형 Gaussian 관측 근사**를 기존 `active_lookaround.information/gain`, 카메라 FK와
`visible_fn_for`에 적용했다. 후보별 own-command 이동 잡음을 먼저 전파한다.
`0.5(logdet P_before − logdet P_after_observation)`를 자기 가설들에 균등 평균하고 실행 비용을 뺀다.
합의 점수는 확률이 아니므로 softmax로 posterior라고 부르지 않는다. 지도 전체 Markov 격자와 관측 likelihood
적분을 그대로 구현했다는 주장은 하지 않는다. 가설 사이의 이산 entropy는 이 근사에 포함되지 않는다.
실제 영상 가림·검출 오류를 예상 정보량이 보증하지도 않는다.

## 바꾼 것·검증

`--active-recovery map_nbv_v1`, 기본 **off**. 기존 3단계가 종료할 지점에서만 최대 3회,
각 최대 3시야를 추가한다. 기존 180초 상한과 모든 수락/내려놓기 임계값은 그대로다.
선택지는 제자리, 0.10 m 후퇴, 0/±45/±90/180° 몸 방향, ±90° 범위 15° 간격 팬과 기존 두 팔 관측 자세다.
자기 RGB가 만든 대안 가설 전체에 기존 0.18+0.15 m 정적 여유를 적용해 이동 후보를 거른다.
지형지물의 보일 방향·FOV·벽 가림은 정적 지도와 각 자기 가설에서 계산한다. 한 물리 선당 두 표본으로
중복 벽 점을 독립 정보로 과장하지 않고, 추정기가 쓰지 않는 문 검출은 예상 정보에서 제외한다.
이미 찍은 명령 좌표계 시점은 다시 고르지 않는다. 팬 slew+settle 뒤 실제 자기 JPEG를 받고,
회전했으면 원래 방향으로 돌아온 뒤 원래 수락 검사로 재추정한다.
각 교사는 독립적으로 계획하며 상대 위치/영상/지형지물 공유는 추가하지 않았다.

74940 저장 상태에서는 대안 가설 하나가 벽 여유를 만족하지 않아 이동을 생략하고,
surroundings 팬 **−15/−75/+75°**의 새 시야를 고른다(예상 Gaussian 정보 이득 약 3.15836 nats).
새 JPEG가 없으므로 새 위치 합의나 성공을 오프라인에서 만들지 않았다.

- [재생 요약](release6-replay.json): 원본 공동 결정 **27/27 정확히 재생**, 성공 **6개 불변**,
  실패 74940의 마지막 종료만 추가 관측으로 바뀐다. 원본 7건 `invisible_measurements=0`, `held_world_reads=0`.
- 이전 80장면을 기존 고정 참고 지도 조건으로 다시 재생해 **77/80(96.25%)**;
  각 실행 plan의 실제 지도/scene 해시로 따로 재생해도 **77/80**이다(모호함 2, no_consensus 1).
  두 분모를 합치지 않는다. 추정기 소스·수락 임계값은 기준 e96386d3와 바이트 동일하다.
- 시험은 `tests/test_global_landmark_localization.py`, `tests/test_release_nbv_observation.py`,
  `tests/test_grasp_act_release_run.py` 3파일. 수식, 모든 가설의 안전 여유, 반복 시점 제외,
  예산, 대기 로봇, 실제 스케줄러의 새 RGB→거절, 회전 복귀, 정답 기반 Eyes 차단을 확인했다.
  [최종 오프라인 결과](release6-offline-summary.json)에 최종 개수·시간·소스/원본 해시를 기록한다.

## 대기열·미검증

[진단 계획](release6-diagnostic-plan.json): 새 74950–74956 7개와 이전 74940 시작·역할·배치를 그대로 재현한 1개.
재현(index 7)을 먼저 짧게 확인하고 첫 30 SIM초 원본 검토 뒤 새 7개를 연다.
[시드 점검](release6-seed-reservation.json)은 main·열린 PR·probes 등 20개 원격 추적 ref와 로컬 회수 plan을 확인했다.
숫자가 같은 파일 바이트 수는 예약 시드가 아니어서 제외했다. 원격 실행 이력 확인은 조정자에게 남는다.
[관문 계획](release6-gate-plan.json)은 기존 미실행 예약 74200–74239 40개를 승계하며 학습 RGB는 off다.

커밋·push와 원격 SHA 일치를 확인한 뒤 `register_release6_queue.py`로
`outputs/e2e18-admin/vm3-queue/20261015-release-gate-<SHA8>.json`을 만든다.
**ready=false**, 진단/관문 stage_ready=false, `gate_promotion_authorized_if_all_conditions_pass=false`.
이전 e96386d3 큐는 원본 백업을 보존하고 superseded·ready=false로 연결한다.
관문 40은 진단 8/8·영상·입력 검토를 모두 통과해도 **조정자 별도 명시 승인**이 필요하다.
대기열 등록은 실행 제출이 아니다.

미검증: 새 시점에서의 실제 검출/합의·재파지·내려놓기 성공, GCP 진단 8개/관문 40개,
새 입력 감사와 실제 이동/회전, 실제 동시 부하·서버 CI·원격 시드 미실행 확인.
Mac 물리·시뮬레이터 렌더·원격 접속·모델 호출은 하지 않았다. weld off를 유지한다.
