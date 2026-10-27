# Arm C/S D0·D1·D2 CPU 진단 — 2026-10-27

**D1은 완료했고 D2는 저장된 라벨·명령·기하의 관계를 정량했다. D0는 접근 가능한 교사 P5 궤적 부재로 재채점 직전에 중단했다.** 교사 정렬 통과 수·마진은 `null`(미기록/이번 산출 불가)이며 0으로 채우지 않았다. D2의 원래 정답 stage 기반 지표와 READY 확률은 필요한 기록이 없어 산출 불가다.

이번 작업의 GPU 사용 0, VM 기동 0, 새 arm 0, 학습 0, 물리 step/렌더/모델 추론 0, 판정 임계값 변경 0이다. 이미 켜져 있는 현재 서버 CPU에서 기존 보존본을 읽었다. 원본 시뮬레이션 백엔드는 MJWarp이며, 이 산술 재계수를 CPU 시뮬레이션 코호트로 취급하지 않는다. 기존 원본·동결 문서·학생 결과는 수정하지 않았다.

## 자료와 검증 범위

- 기준 검토: [MiniMax 최종 판정](/home/ubuntu/UGRP/outputs/reports/2026-10-27-arm-cs-interpretation-minimax-review.md), [Codex 교차 검토](/home/ubuntu/UGRP/outputs/reports/2026-10-27-arm-cs-interpretation-codex-review.md).
- C/S 실제 읽은 경로: `/home/ubuntu/ugrp-archive/runs/baseline-resume-20261027T1936Z-tokyo-c/arm-{c,s}/world-000`–`world-019/raw/`의 `plan.json`, `eval-only.jsonl.zst`, `student-eval.jsonl.zst`, `result.json.zst`(총 160파일). 각 arm 20개, seed 8342000–8342019. 두 arm의 같은 20 seeds를 40개의 독립 표본으로 합산하지 않는다.
- 실행 당시 원본 경로: `/home/ugrp/ugrp-sim/runs/baseline-resume-20261027T1936Z/arm-{c,s}/world-NNN/raw/`. 실행 호스트는 gcp6 Tokyo `asia-northeast1-c`, VM ID `2102818194467198298`.
- 보존본 이력: [기존 전체 파일 보존 검증](/home/ubuntu/UGRP/outputs/reports/2026-10-27-baseline-resume-evidence/study-archive-verification.json). 이번에는 분석에 쓴 160 원본 파일의 bytes/SHA-256을 당시 C/S 원본 manifest와 다시 대조했다. [source-manifest.json](/home/ubuntu/UGRP/outputs/reports/2026-10-27-d0d1d2-diagnostic-evidence/source-manifest.json)에 현재 경로·크기·해시를 남겼다.
- 원본 `t`를 정확히 일치시켜 C 34,963 + S 34,481 = 69,444프레임을 결합했다. 시각 반올림·최근접 프레임 결합은 없다. 277,776개의 기하/기록 플래그 대조가 일치했고, 40개 에피소드의 stage·발행 명령·hold 계수도 원본 요약과 일치했다.
- 원래 [recount.py의 geometry()](/home/ubuntu/UGRP/outputs/reports/2026-10-26-round2-recount-evidence/recount.py:61) 함수 AST만 추출해 실행했다(모델·시뮬레이터 import 없음). 역할별 목표·경계·yaw wrap을 포함한 알려진 자세 6건을 확인했다. 이것은 수치 구현 점검이며 교사 양성 대조를 대신하지 않는다.
- 별도 산술 검증: 69,444프레임에서 식을 다시 계산하고 40개 최소값/시각, 집계 계수 24개, 사용 파일 167개의 해시를 재확인해 PASS. [verification.json](/home/ubuntu/UGRP/outputs/reports/2026-10-27-d0d1d2-diagnostic-evidence/verification.json).

| 학생 종료 (절차 완료와 임무 성공 구별) | C | S |
| --- | --- | --- |
| 정상 기록 완료 | 20/20 | 20/20 |
| cap_end | 18/20 | 17/20 |
| learned_finished_early | 2/20 | 3/20 |
| HOST_ERROR | 0/20 | 0/20 |
| 기록된 물리 성공 | 0/20 | 0/20 |

조기 종료 5건의 원시 `end_reason=teacher_terminal`은 실행기 공통 표기다. `student_eval.finished_t`를 확인해 `learned_finished_early`로 구분했으며 원시 값도 보존했다.

## D0 — 교사 P5 양성 대조: 원본 접근 불가에서 중단

확인 대상은 `/home/ugrp/ugrp-sim/runs/pairact-p5-eval-20261025/p5-teacher/world-000`–`world-019/raw/{plan.json,eval-only.jsonl.zst}`이다. 현재 호스트에는 `/home/ugrp` 자체가 없다. `/home/ubuntu/ugrp-sim/runs/…`와 `/home/ubuntu/ugrp-archive/runs/…`의 동일 실행명 경로도 없다.

`ugrp-archive`, `ugrp-sim`, `ugrp-audit`, `UGRP/outputs`, `ugrp-recovery`를 숨김·ignore 제외 없이 파일명 검색했으나 해당 P5 원본은 발견하지 못했다. 무관한 과거 `.incoming-*` 자료에 접근 거부 43행이 있어 전 디스크 부재로 단정하지 않는다. [data-discovery.json](/home/ubuntu/UGRP/outputs/reports/2026-10-27-d0d1d2-diagnostic-evidence/data-discovery.json), [data-search.stderr](/home/ubuntu/UGRP/outputs/reports/2026-10-27-d0d1d2-diagnostic-evidence/data-search.stderr). 과거 source manifest에서 확인되는 교사 plan/truth 40개 경로·해시는 [teacher-expected-originals.json](/home/ubuntu/UGRP/outputs/reports/2026-10-27-d0d1d2-diagnostic-evidence/teacher-expected-originals.json)에 남겼다. 해시 목록은 궤적 원본의 대체물이나 백업이 아니다.

조회 전용 GCP 목록에서 Seoul 원래 gcp6와 Tokyo 복원 gcp6 모두 `TERMINATED`임을 확인했다. 원격 디스크를 기동·마운트·복사하지 않았다. [vm-status-readonly.json](/home/ubuntu/UGRP/outputs/reports/2026-10-27-d0d1d2-diagnostic-evidence/vm-status-readonly.json). 원본이 삭제되었다는 뜻이 아니라, 이번에 허용된 접근 경로로 읽지 못했다는 뜻이다.

| 교사 항목 | 값 | 이번 검증 범위 |
| --- | --- | --- |
| 원래 approach/alignment/READY/grasp 지표 | 미기록 (`null`) | 원래 기록의 누락을 유지 |
| 이번 geometry() 정렬 통과 /20 | 산출 불가 (`null`) | plan/truth를 읽기 전 중단 |
| 이번 정렬 마진 분포 | 산출 불가 (`null`) | 기존 교사 성공률로 추정하지 않음 |
| 과거 교사 임무 성공 | 19/20 | 과거 재계수 요약 인용; 이번 독립 재검증 아님 |
| 과거 엄밀한 접촉·높이·기울기 3초 유지 | 19/20 | 과거 요약값; runner hold 플래그 20/20과 구별 |

교사 참조 파일은 [기존 result-v2/recount.json](/home/ubuntu/UGRP/outputs/reports/2026-10-26-round2-recount-evidence/result-v2/recount.json)이다. 교사 성공과 학생 성공을 합산하지 않았다. **중단 지점:** 기존 P5 plan/truth 확보 → geometry() 적용 → 20월드 통과·마진 계산 중 첫 단계에서 멈췄다. 따라서 정렬 기준의 교사 궤적 적합도는 여전히 미검증이다. 별도 교사·다른 시드·새 실행으로 대체하지 않았다. [d0.json](/home/ubuntu/UGRP/outputs/reports/2026-10-27-d0d1d2-diagnostic-evidence/d0.json).

## D1 — 같은 프레임의 공동 여유 분포

`d_r(t)`는 빔 끝에서 해당 역할 방향의 0.203m 뒤 스탠션까지의 **로봇 베이스 XY 오차**, `Δθ_r(t)`는 빔 yaw(blue 역할은 +π)와 로봇 yaw의 wrapped 차이다. 집게 거리나 높이·기울기 오차가 아니다. 원래 평가 기준 0.03m·0.06rad·0.203m를 그대로 썼다.

```text
m_xy(t) = max_r d_r(t)/0.03 - 1
m_yaw(t) = max_r |Δθ_r(t)|/0.06 - 1
m(t) = max(m_xy(t), m_yaw(t))
t* = argmin_t m(t)   # 같은 프레임의 양쪽 로봇·두 성분을 먼저 결합
```

`m≤0`이 공동 정렬이다. 성분별 독립 최소값은 별도 JSON 필드로만 보존했고 공동 정렬 판정에 합치지 않았다. 아래 `t*` 성분은 모두 공동 최소 프레임에서 측정했다. 분위수는 정렬 후 `(n-1)q` 선형 보간이며 새 통과 기준이 아니다.

| arm | 공동 정렬 에피소드 | 공동 정렬 프레임 | 에피소드 최소 m: min / P25 / P50 / P75 / max | t* 제한 성분 XY / yaw |
| --- | --- | --- | --- | --- |
| C | 0/20 | 0/34,963 | 0.2816 / 1.4883 / 2.1298 / 3.8288 / 16.3185 | 8/20 · 12/20 |
| S | 1/20 | 665/34,481 | -0.3159 / 1.3846 / 2.0057 / 4.7294 / 10.3728 | 11/20 · 9/20 |

에피소드 20개가 단위인 위 표와, 아래 모든 시각을 합친 기술 분포는 다르다. 프레임을 독립 시행으로 해석하거나 긴 실행에 더 큰 통계적 가중치를 주지 않는다.

| arm | 모든 프레임 m P05 / P50 / P95 | m_xy P05 / P50 / P95 | m_yaw P05 / P50 / P95 |
| --- | --- | --- | --- |
| C | 1.4037 / 21.0445 / 46.8038 | 0.2307 / 10.4400 / 29.7538 | 0.9392 / 18.4453 / 46.8038 |
| S | 1.1405 / 22.1891 / 47.3800 | -0.3480 / 11.3709 / 29.6596 | 0.7720 / 19.4376 / 47.3800 |

| arm | t* 최대 XY 오차 min / P50 / P95 (mm) | t* 최대 yaw 오차 min / P50 / P95 (rad) |
| --- | --- | --- |
| C | 9.908 / 73.712 / 178.889 | 0.02724 / 0.17173 / 0.38825 |
| S | 11.176 / 77.981 / 326.008 | 0.01961 / 0.13368 / 0.43814 |

| arm | XY만 미달 | yaw만 미달 | 둘 다 미달 | 둘 다 통과 |
| --- | --- | --- | --- | --- |
| C | 588 | 1497 | 32878 | 0 |
| S | 494 | 1739 | 31583 | 665 |

C의 가장 가까운 실패는 world 7, t=150.5s: 최대 XY 38.4493mm, 최대 yaw 0.027244rad, m=0.281642로 위치 성분이 남는다. S의 가장 가까운 실패는 world 15, t=182.1s: 최대 XY 19.5748mm, 최대 yaw 0.107444rad, m=0.790740으로 요 성분이 남는다. S world 9는 t=128.7s에 m=-0.315907이다. 이 결과에서 임계값 완화를 정당화하거나 새 기준을 도출하지 않았다.

기존 퍼널의 접근 프레임 C 25,047·S 23,928은 **한번 관문에 도달한 뒤의 누적 유지 계수**다(`audit.frame_definition`). 이번 동일 시각 조건으로 접근 자체가 참인 프레임은 C 23,968·S 23,606이다. 분모/시간 정의가 달라 두 계수를 바꿔 쓰지 않는다. 정렬 0·665는 이번 자료에서 두 정의가 일치한다.

### 에피소드별 동일 프레임 최소값

시각은 원본 절대 SIM초다(각 시작 t=2.2s). r1/r2의 개별 오차·역할·라벨도 같은 시각으로 [episodes.json](/home/ubuntu/UGRP/outputs/reports/2026-10-27-d0d1d2-diagnostic-evidence/episodes.json)의 `min_joint_margin_frame.robots`에 전부 보존했다.

| arm | world (seed=8342000+world) | t* (s) | min m | m_xy(t*) | m_yaw(t*) | max XY (mm) | max yaw (rad) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C | 0 | 138.7 | 1.519551 | 1.519551 | 1.515249 | 75.587 | 0.150915 |
| C | 1 | 105.6 | 16.318535 | 16.014779 | 16.318535 | 510.443 | 1.039112 |
| C | 2 | 169.5 | 3.954178 | 3.115735 | 3.954178 | 123.472 | 0.297251 |
| C | 3 | 123.4 | 2.210983 | 0.752161 | 2.210983 | 52.565 | 0.192659 |
| C | 4 | 147.4 | 2.035801 | 1.127549 | 2.035801 | 63.826 | 0.182148 |
| C | 5 | 149.4 | 0.536508 | 0.491916 | 0.536508 | 44.757 | 0.092191 |
| C | 6 | 66.8 | 4.899963 | 4.348869 | 4.899963 | 160.466 | 0.353998 |
| C | 7 | 150.5 | 0.281642 | 0.281642 | -0.545933 | 38.449 | 0.027244 |
| C | 8 | 137.9 | 4.381297 | 4.381297 | 1.988915 | 161.439 | 0.179335 |
| C | 9 | 156.1 | 2.188300 | 1.892225 | 2.188300 | 86.767 | 0.191298 |
| C | 10 | 114.3 | 1.604282 | 1.604282 | 1.571584 | 78.128 | 0.154295 |
| C | 11 | 112.6 | 2.071368 | 2.071368 | 1.373159 | 92.141 | 0.142390 |
| C | 12 | 121.3 | 1.394602 | 1.394602 | 1.394015 | 71.838 | 0.143641 |
| C | 13 | 95.9 | 4.055650 | 0.280699 | 4.055650 | 38.421 | 0.303339 |
| C | 14 | 175.8 | 1.735539 | 0.431706 | 1.735539 | 42.951 | 0.164132 |
| C | 15 | 147.6 | 0.591513 | -0.068861 | 0.591513 | 27.934 | 0.095491 |
| C | 16 | 137.2 | 2.620247 | 2.620247 | 1.062028 | 108.607 | 0.123722 |
| C | 17 | 121.4 | 2.679608 | 2.679608 | 2.300217 | 110.388 | 0.198013 |
| C | 18 | 113.2 | 3.787031 | -0.488244 | 3.787031 | 15.353 | 0.287222 |
| C | 19 | 182.1 | 0.809989 | -0.669736 | 0.809989 | 9.908 | 0.108599 |
| S | 0 | 70.0 | 1.921240 | 1.594021 | 1.921240 | 77.821 | 0.175274 |
| S | 1 | 123.9 | 8.983025 | 8.983025 | 6.121353 | 299.491 | 0.427281 |
| S | 2 | 118.5 | 1.019008 | -0.627452 | 1.019008 | 11.176 | 0.121140 |
| S | 3 | 128.3 | 7.201427 | 7.201427 | 0.109380 | 246.043 | 0.066563 |
| S | 4 | 147.3 | 9.840304 | 9.840304 | 9.742197 | 325.209 | 0.644532 |
| S | 5 | 131.8 | 1.042091 | 1.042091 | -0.255735 | 61.263 | 0.044656 |
| S | 6 | 159.6 | 3.975671 | 2.164293 | 3.975671 | 94.929 | 0.298540 |
| S | 7 | 88.6 | 2.870350 | 2.870350 | 1.093581 | 116.110 | 0.125615 |
| S | 8 | 135.0 | 3.529689 | 3.529689 | 2.885944 | 135.891 | 0.233157 |
| S | 9 | 128.7 | -0.315907 | -0.598933 | -0.315907 | 12.032 | 0.041046 |
| S | 10 | 174.0 | 6.990758 | 6.990758 | -0.673234 | 239.723 | 0.019606 |
| S | 11 | 166.7 | 10.372825 | 10.372825 | 4.368243 | 341.185 | 0.322095 |
| S | 12 | 101.9 | 3.758765 | 1.345946 | 3.758765 | 70.378 | 0.285526 |
| S | 13 | 141.7 | 1.792798 | 1.792798 | 1.237737 | 83.784 | 0.134264 |
| S | 14 | 113.7 | 1.604688 | 1.604688 | 0.780993 | 78.141 | 0.106860 |
| S | 15 | 182.1 | 0.790740 | -0.347505 | 0.790740 | 19.575 | 0.107444 |
| S | 16 | 156.7 | 1.440001 | 0.951651 | 1.440001 | 58.550 | 0.146400 |
| S | 17 | 123.0 | 1.589271 | 1.589271 | 0.778656 | 77.678 | 0.106719 |
| S | 18 | 115.0 | 1.218405 | 0.736959 | 1.218405 | 52.109 | 0.133104 |
| S | 19 | 121.4 | 2.090097 | 0.006218 | 2.090097 | 30.187 | 0.185406 |

## D2 — READY 조건부 분포·전이·기하와의 시간 관계

`policy READY`는 현재 발행 기록의 `stage == ready`, `protocol READY`는 원본 `ready[rid]` 불리언이다. S의 프로토콜은 pending 제안을 포함하므로 두 정의를 분리했다. READY 출현의 경험적 빈도를 계산했으며, 저장되지 않은 logits/확률을 추정하지 않았다.

| 항목 | C | S |
| --- | --- | --- |
| READY 라벨 robot-tick | 877/69,926 (1.254%) | 1,674/68,962 (2.427%) |
| 한 로봇 이상 READY인 에피소드 | 16/20 | 7/20 |
| 양쪽이 각각 한번 이상 READY | 5/20 | 4/20 |
| 그중 동시 READY가 전혀 없는 에피소드 | 5/5 (world 0·2·13·14·18) | 3/4 (world 5·12·17) |
| 동시 정책 READY | 0/34,963 (0.000%) | 8/34,481 (0.023%) |
| 동시 프로토콜 READY | 0/34,963 (0.000%) | 410/34,481 (1.189%) |
| 정책/프로토콜 동시 READY 불일치 | 0프레임 | 402프레임 (S world 5) |
| 정책/프로토콜 개별 READY 불일치 | 0 robot-tick | 2,768 robot-tick |
| READY 연속 구간 수 / 최대 표본 수 | 302 / 128 | 55 / 289 |

C의 protocol READY는 진단용이며 행동 허가를 강제하지 않는다. S의 410프레임을 정책 동시 READY 8프레임에 합산하지 않는다. 원본 `eval_passed.READY`는 protocol READY와 일치하므로, 이번 stage-head 진단에서는 `issued.stage`를 직접 읽었다. 예: S world 5 t=142.0s는 stage `execute/ready`, protocol READY `true/true`다.

### 기하와 READY의 2×2 분할 (프레임)

| arm | 기하 X · 동시 READY X | 기하 X · 동시 READY O | 기하 O · 동시 READY X | 기하 O · 동시 READY O |
| --- | --- | --- | --- | --- |
| C | 34963 | 0 | 0 | 0 |
| S | 33808 | 8 | 665 | 0 |

| 에피소드 기하 분담 | C /20 | S /20 |
| --- | --- | --- |
| 두 로봇 모두 한번도 개별 정렬하지 못함 | 14 | 16 |
| 한 로봇만 개별 정렬 | 6 | 3 |
| 각자 정렬했으나 시점이 겹치지 않음 | 0 | 0 |
| 공동 정렬은 있으나 동시 READY와 겹치지 않음 | 0 | 1 |

따라서 이번 실패 자료에서 **개별 기하 달성 시점만 서로 어긋나 공동 정렬을 놓친 사례는 0건**이다. C는 전부, S는 19/20에서 기하 자체가 부족하고, S 나머지 1건은 기하가 존재하는 창에서 동시 READY가 없다. 이는 관측 상태 분할이며, 정책·실행기·감독 피드백의 인과적 기여율이 아니다. READY 시점 불일치도 별도로 존재하지만 그것만 고치면 물리 성공한다는 근거는 없다.

### premature_ready: 원래 지표와 기하 대리지표

동결 `pairact_r1.offline_metrics`의 원래 `premature_ready`는 **정답 stage가 approach/alignment/recover인 행 중 ready 예측 비율**이다. 학생 방문 상태에는 해당 정답 stage가 없으므로 원래 지표와 정답 전이 recall/혼동행렬은 `null`이다. 원래 2% 관문과 아래 수치를 비교하지 않는다.

대신 같은 기존 기하 조건으로 `premature_ready_geometry_proxy = #ready∧¬자기정렬 / #¬자기정렬`을 계산했다. READY 중 미정렬 비율은 분모가 다른 별도 값이다.

| 지표 (robot-tick) | C | S |
| --- | --- | --- |
| P(ready \| 자기 정렬 X) | 868/66,450 (1.306%) | 1,358/65,199 (2.083%) |
| P(ready \| 자기 정렬 O) | 9/3,476 (0.259%) | 316/3,763 (8.398%) |
| P(자기 정렬 X \| ready) | 868/877 (98.974%) | 1,358/1,674 (81.123%) |
| P(ready \| 공동 정렬 O) | 적격 0; 미정의 | 109/1,330 (8.195%) |

행별 stage 오분류의 정답이 없는 상태에서 이 대리지표를 정답 정확도·원래 premature_ready로 명명하지 않는다.

### 자기 입력·역할에 따른 READY 출현

| 조건 (겹치는 분류; 서로 합산 금지) | C: ready/N | S: ready/N |
| --- | --- | --- |
| 로봇 r1 | 247/34,963 (0.706%) | 1,349/34,481 (3.912%) |
| 로봇 r2 | 630/34,963 (1.802%) | 325/34,481 (0.943%) |
| 역할 blue | 814/34,963 (2.328%) | 1,350/34,481 (3.915%) |
| 역할 teal | 63/34,963 (0.180%) | 324/34,481 (0.940%) |
| 직전 발행 wheel 전부 0 | 877/54,553 (1.608%) | 1,674/53,215 (3.146%) |
| 직전 발행 wheel 하나 이상 비영 | 0/15,373 (0.000%) | 0/15,747 (0.000%) |
| 이력16 wheel 전부 0 | 876/45,297 (1.934%) | 1,671/44,626 (3.744%) |
| 이력16 wheel 비영 존재 | 1/24,629 (0.004%) | 3/24,336 (0.012%) |
| 직전 집게 PWM delta=0 | 66/7,063 (0.934%) | 1,629/16,441 (9.908%) |
| 직전 집게 PWM delta>0 | 463/31,177 (1.485%) | 27/26,057 (0.104%) |
| 직전 집게 PWM delta<0 | 348/31,686 (1.098%) | 18/26,464 (0.068%) |
| 목적지 token none | 1/48,485 (0.002%) | 549/63,518 (0.864%) |
| 목적지 token B | 876/21,441 (4.086%) | 1,125/5,444 (20.665%) |
| 직전과 최신 자기 RGB sha 같음 | 0/21 (0.000%) | 64/394 (16.244%) |
| 직전과 최신 자기 RGB sha 다름 | 877/69,865 (1.255%) | 1,610/68,528 (2.349%) |
| 평가 전용: 배정 끝 visible=true | 876/24,880 (3.521%) | 1,672/26,181 (6.386%) |
| 평가 전용: 배정 끝 visible=false | 1/45,046 (0.002%) | 2/42,781 (0.005%) |

자기 입력 조건은 기록된 자기 발행 이력·RGB 참조·고정 역할/token에서만 구했다. RGB sha는 영상의 반복 여부이며 내용 분류가 아니다. 반복 비교의 첫 관측은 미정의이므로 각 arm 40 robot-tick(20에피소드×2로봇)은 RGB 반복/비반복 두 행에서 제외했다. 끝 visible 플래그는 **평가 전용 truth의 기존 렌더 가시성 기록**이며 정책이 읽은 추가 관측이 아니다. 이 조건부 빈도로 이미지의 특정 의미·원인 또는 P(READY | 전체 RGB,전체 이력)를 식별할 수 없다. 이번에 영상 내용 검토나 새 시각 분류기를 실행하지 않았다.

발행 명령과의 결합: 현재 READY 라벨인데 wheel이 비영인 경우는 C 0/877, S 0/1,674다. S의 READY 1,674 중 1,671틱은 software_hold와 겹친다. 이 결합은 프로토콜이 행동을 선택한 결과도 포함하므로 stage-head가 멈춤의 단일 원인이라는 뜻이 아니다. 실제 이동 성공을 발행 wheel/PWM으로 대체하지 않았다. 세부 계수는 [verification.json](/home/ubuntu/UGRP/outputs/reports/2026-10-27-d0d1d2-diagnostic-evidence/verification.json)의 `extras.issued_command_conditionals`에 있다.

### stage 전이 및 기하 상태와의 교차표

아래 전이 표는 **같은 로봇의 t−1 예측 → t 예측** 중 라벨이 바뀐 횟수다(에피소드 경계 제외, 대각은 생략하여 0). 정답 전이와 예측의 혼동행렬은 아니며 정확도/전이 recall로 보고하지 않는다. recover/complete 라벨과 그 전이는 두 arm 모두 0회다. 자기 전이를 포함한 8-stage 희소 행렬(0빈도 항목 생략)은 [summary.json](/home/ubuntu/UGRP/outputs/reports/2026-10-27-d0d1d2-diagnostic-evidence/summary.json)에 보존했다.

| arm | 이전 → 다음 | approach | alignment | ready | execute | carry | place |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C | approach | 0 | 130 | 0 | 45 | 1 | 0 |
| C | alignment | 92 | 0 | 297 | 16 | 0 | 0 |
| C | ready | 1 | 282 | 0 | 17 | 0 | 0 |
| C | execute | 49 | 7 | 5 | 0 | 48 | 51 |
| C | carry | 0 | 0 | 0 | 47 | 0 | 3 |
| C | place | 1 | 0 | 0 | 52 | 1 | 0 |
| S | approach | 0 | 99 | 0 | 6 | 0 | 0 |
| S | alignment | 67 | 0 | 44 | 21 | 0 | 0 |
| S | ready | 0 | 46 | 0 | 8 | 0 | 0 |
| S | execute | 4 | 11 | 11 | 0 | 0 | 6 |
| S | carry | 0 | 0 | 0 | 0 | 0 | 0 |
| S | place | 0 | 0 | 0 | 4 | 0 | 0 |

평가 기하 상태 × 정책 stage 교차표는 기존 위치·yaw 기준을 썼다. GT stage 표적의 혼동행렬과 구별한다.

| arm | 자기 기하 | approach | alignment | ready | execute | carry | place |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C | XY X, yaw X | 39001 | 8733 | 721 | 7725 | 42 | 26 |
| C | XY X, yaw O | 1528 | 2567 | 117 | 1747 | 0 | 41 |
| C | XY O, yaw X | 37 | 1516 | 30 | 2403 | 210 | 6 |
| C | XY O, yaw O | 1 | 1589 | 9 | 1877 | 0 | 0 |
| S | XY X, yaw X | 39730 | 7356 | 1144 | 3788 | 0 | 582 |
| S | XY X, yaw O | 1110 | 3634 | 214 | 1860 | 0 | 0 |
| S | XY O, yaw X | 3 | 5778 | 0 | 0 | 0 | 0 |
| S | XY O, yaw O | 0 | 2227 | 316 | 1220 | 0 | 0 |

carry/place 라벨은 물리 단계 성취를 뜻하지 않는다. 위 후속 라벨을 파지·운반 성공으로 세지 않았다.

### 동시 READY와 기하의 시간 관계

S world 9(seed 8342009)의 공동 정렬은 t=115.7–182.1s에 665프레임 연속이다. 첫/마지막 표본 간 관측 시간폭은 **66.4s**, 10Hz 표본 점유시간은 **66.5s**다. 표본 사이의 연속 물리 상태까지 관측한 것은 아니다. 이 창에서 r1은 alignment 100·execute 456·ready 109, r2는 alignment 67·execute 598·ready 0이다. r1 첫 ready는 t=167.8s(공동 정렬 시작 52.1s 뒤), r2 ready는 끝까지 없다. 동시 정책/프로토콜 READY 모두 0이다.

S world 9의 t*=128.7s에서 r1 `(d,yaw)=(0.012032004m,0.041045586rad)`, r2 `(0.003310158m,0.019328668rad)`이며 둘 다 execute 라벨이다. 기하 여유가 실제 존재하는 상태에서 READY가 맞지 않은 사례이지만, 기하가 안 맞은 나머지 에피소드의 실패까지 설명하지 않는다.

S의 동시 정책 READY 8틱은 전부 world 0: t=92.1, 94.1, 96.6, 99.3, 99.5, 99.9, 100.0, 100.1s다. 해당 시각 m은 1.979656–1.984311로 모두 정렬 미달이다. world 0은 전체 실행 중 개별 정렬도 두 로봇 모두 0회다. S world 5의 추가 동시 protocol READY 402틱도 공동 기하가 없으며, 이것을 정책 READY의 기하 정합 성공으로 해석하지 않는다.

## 해석 한계와 남은 중단 지점

- **D0 미완료:** 정렬 기준이 실제 교사 P5 성공 궤적을 포괄하는지 검증하지 못했다. 원본을 VM 기동 없이 읽을 수 있게 되기 전까지 교사 마진·학생 대비 정밀도 캘리브레이션은 보류한다.
- **D2의 정답·확률 자료 부재:** 학생 상태의 true stage, stage logits/READY score, 동일 입력에서의 teacher-forced 예측이 기록되지 않았다. 원래 premature_ready·정답 stage 전이 혼동·전이 recall·확률 trace는 산출 불가다. 이번 결과는 저장된 라벨과 기존 기하·자기 이력의 기술 진단이다.
- 같은 정책·기존 보류 seeds를 다시 본 사후 분석이며 새 검증 코호트가 아니다. 프레임의 시간 상관, C/S 처치 차이, 관측·발행 이력 피드백 때문에 이 수치를 원인별 인과 기여율이나 두 arm의 우열로 해석하지 않는다.
- 0.203m·0.03m·0.06rad는 기존 코드 출처를 재사용했을 뿐 실기 사양·성공 교사 분포로 정당화한 것은 아니다. 임계값 변경·새 arm·학습으로 이어가지 않았다.
- 파지 이후 누적 관문의 적격 대상이 없다는 사실은 그 능력의 독립 실패율이 아니다. 학생 물리 성공 기록 C/S 각각 0/20과 교사의 과거 성공 19/20은 별도다. 모든 성과는 시뮬레이션 자료이며 실제 로봇 성과를 주장하지 않는다.
- 이번에 영상 내용은 직접 검토하지 않았다. 특정 물체 방해·같은 끝 접근·시야 상실 등 물리 실패 원인을 선택하지 않는다. 막은 물체는 미관측, 최소 틈은 미측정이며 기하/READY 분할은 공간 장애 원장 대신이 아니다.

## 재현·산출물

```bash
cd /home/ubuntu/UGRP
CUDA_VISIBLE_DEVICES= PYTHONDONTWRITEBYTECODE=1 python3 outputs/reports/2026-10-27-d0d1d2-diagnostic-evidence/analyze.py
CUDA_VISIBLE_DEVICES= PYTHONDONTWRITEBYTECODE=1 python3 outputs/reports/2026-10-27-d0d1d2-diagnostic-evidence/verify.py
```

재현은 같은 보존본과 `zstd`가 필요하다. 현재 스크립트는 P5 원본 부재를 명시적으로 확인하고 D0 중단을 기록한다. 나중에 교사 원본이 생겨도 자동으로 다른 코호트로 대체하지 않는다. 실행 시 증거 디렉터리의 계산 산출물만 갱신하므로 현재 결과 보존이 필요하면 새 경로에 사본을 두고 실행한다.

- 전체 요약/원본 연결: [summary.json](/home/ubuntu/UGRP/outputs/reports/2026-10-27-d0d1d2-diagnostic-evidence/summary.json), 에피소드별 수치·동일 프레임 성분/구간: [episodes.json](/home/ubuntu/UGRP/outputs/reports/2026-10-27-d0d1d2-diagnostic-evidence/episodes.json).
- 69,444프레임의 거리·yaw·margin·stage·READY·허가/hold: [frame-metrics.csv.gz](/home/ubuntu/UGRP/outputs/reports/2026-10-27-d0d1d2-diagnostic-evidence/frame-metrics.csv.gz).
- 교사 중단 기록/경로: [d0.json](/home/ubuntu/UGRP/outputs/reports/2026-10-27-d0d1d2-diagnostic-evidence/d0.json), [teacher-expected-originals.json](/home/ubuntu/UGRP/outputs/reports/2026-10-27-d0d1d2-diagnostic-evidence/teacher-expected-originals.json), [data-discovery.json](/home/ubuntu/UGRP/outputs/reports/2026-10-27-d0d1d2-diagnostic-evidence/data-discovery.json).
- 분석/검증 소스 및 로그: [analyze.py](/home/ubuntu/UGRP/outputs/reports/2026-10-27-d0d1d2-diagnostic-evidence/analyze.py), [verify.py](/home/ubuntu/UGRP/outputs/reports/2026-10-27-d0d1d2-diagnostic-evidence/verify.py), [analysis-run.log](/home/ubuntu/UGRP/outputs/reports/2026-10-27-d0d1d2-diagnostic-evidence/analysis-run.log); 최종 stderr는 비어 있다. 앞선 CPU 분석 2회는 각각 과거 JSON 키 구조 가정과 policy/protocol READY 동일성 가정으로 중단했고, 로그(`analysis-attempt1/2.*`)를 보존했다. 3회차 계산 성공 후 조기 종료 표기를 원시 값과 분리해 4회차로 재생성했다. 이는 새 시뮬레이션 실패가 아니다.
- 순차 통과·거부/이유: [funnel.json](/home/ubuntu/UGRP/outputs/reports/2026-10-27-d0d1d2-diagnostic-evidence/funnel.json). 새 대기열은 만들지 않았고 원래 처치의 관문을 재승인하지 않았다.
- 증거 파일 크기·SHA-256: [artifact-sha256.json](/home/ubuntu/UGRP/outputs/reports/2026-10-27-d0d1d2-diagnostic-evidence/artifact-sha256.json); 사용 원본 해시는 별도 `source-manifest.json`에 있다.

완료 시각(KST): 2026-10-27 11:10:48 KST (D1·저장 라벨 D2 계산/검증 및 보고서 작성 완료; D0와 기록 없는 D2 항목은 위 중단 상태).
