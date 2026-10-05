# 연구 관리 시간 측정 — 2026-09-30

**가장 큰 직접 근거는 AI 추론 속도보다 공용 소스 봉인과 반복 검증이다.** #256은 현재 트리 봉인 때문에 최소 4시간 30분 동안 병합 보류 상태였고, 같은 이유가 v6b에서 다시 나타났다. CI 8분할은 이미 전체 workflow 중앙값을 20.2분에서 7.9분으로 낮췄다. 다음 단계는 분할 수 확대보다 중복 실행 제거와 변경 범위에 맞는 검증이다. 다만 관찰 자료이므로 아래 시간들을 더해 “몇 시간 절약”으로 주장하지 않는다.

이 작업은 **프로세스 측정과 제안만** 한다. 제어기·사전 등록·CI 정책을 바꾸지 않았고 새 물리·시뮬레이션·모델 호출을 하지 않았다. 저장된 결과를 새 과학적 증거로 합산하지 않는다. PR은 draft로 남기며 병합하지 않는다.

## 범위와 계산법

- PR **#256–#294, 39개 전수**. 시작은 9/28 04:30:38 UTC(대상 PR의 첫 커밋), 관찰 종료는 **9/30 09:49:03 UTC = 18:49:03 KST**. 약 53.3시간이다. GitHub 수집은 09:51:07 UTC까지 이어져 원자적 스냅샷은 아니다. 추가 페이지는 동일 HEAD를 확인했다.
- 저장소 코드 기준은 `a8094cc14e098a55483f53a3c49bf6a0b116043d`. 열린 #292의 v6h 자료는 **`3afc61b00f2c127ac3fbe2be5e7bb57da989b15a`**를 따로 읽었다. 이후 변경은 포함하지 않는다.
- PR 생성→병합은 `mergedAt - createdAt`. 미병합 3개는 결측으로 두고 관찰 종료까지의 나이를 따로 기록한다. 첫 커밋→결과는 **작업 시간**이 아니라 대기·병렬 작업까지 포함한 경과 시간이다.
- CI 152개 run 중 대상 PR과 **head branch가 일치하는 95개**를 분석한다. main push와 범위 밖 PR은 57개이며 PR별 비용에 섞지 않는다. 실제 재실행은 `run_attempt - 1`, 새 커밋에 따른 새 run은 별도로 센다. 모든 attempt의 job 시간은 보존했다.
- 완료 CI의 끝은 `updated_at` 대신 **마지막 job의 `completed_at`**이다. 전체 workflow, required check, 개별 pytest step, 병렬 job 합계는 다른 측정량이다. 취소·실패·실행 중 run도 CSV에 남기되 성공 실행 중앙값에서는 제외한다. 재실행 run의 생성→끝에는 이전 attempt와 재실행 대기가 포함된다.
- 상위 10% 경계(p90)는 nearest-rank. 검토 횟수는 **문서에 드러난 검토→수정 묶음의 하한**이다. 승인 리뷰가 없다고 독립 검토가 없었던 것으로 세지 않는다. 댓글 시각도 실제 검토 시작 시각과 다르다.
- 출처: [수집 시각·SHA](data/metadata.json), [PR 원자료](data/prs.json), [CI run 원자료](data/runs.json), [PR별 CSV](derived/prs.csv), [CI별 CSV](derived/ci_runs.csv), [job별 CSV](derived/ci_jobs.csv), [집계](derived/summary.json). UTC 원자료를 보존했다.

## 1. PR 대기와 검토 반복

| 측정량 | 결과 | 해석 |
|---|---:|---|
| 생성→병합, 병합된 36개 | 중앙 **77.0분**, p90 **396.7분**, 최대 **920.9분** | #290·#294는 feature branch로 병합됨. main 병합은 34개, 중앙 83.2분 |
| 첫 비병합 커밋→병합, 같은 36개 | 중앙 **96.3분**, p90 **532.9분** | 최초 구현 이전의 조사·모델 응답 시간은 빠져 있음 |
| 정식 GitHub review 객체 | **0개** | 검토는 댓글·실험 문서·커밋에 기록됨 |
| 확인 가능한 검토→수정 묶음 | **12개 PR에서 최소 16회** | #261, #263은 각각 3회. 나머지 27개는 “없음”이 아니라 계측되지 않음 |
| 첫 검토 관찰 뒤 커밋 | **41개** | 실제 review 댓글이 5개 PR, 수정 커밋/응답 시각 대용이 7개 PR. 모두 수정 커밋은 아니며 병합·문서 커밋 포함 |
| #278의 PR 생성 전 구간 | **10시간 5분**, 전체 **37커밋** | PR 생성→병합은 81.9분에 불과해 개발·측정 시간을 대변하지 못함 |

근거: [검토 수동 판독 규칙과 항목별 출처](review_annotations.json), [PR CSV](derived/prs.csv). #265의 독립 검토자 두 명은 한 번의 병렬 검토 묶음으로 센다. #285·#292·#293은 일부 수정은 끝났어도 남은 지적이 있는 열린 PR이다. “16회”는 최종 승인 16회가 아니다.

#256의 보류 댓글은 **9/28 12:37:11 UTC**, #262 병합 뒤 해제 댓글은 **17:08:02 UTC**다. 두 시각 간 **4시간 30분 51초**는 봉인 충돌이 공개적으로 유지된 구간이다. 그 동안 다른 작업도 했으므로 전부 유휴 시간은 아니다. 18:41:57에는 v6b 봉인 때문에 다시 보류했고 18:46:22에 이력 감사 전환을 결정했다. [첫 보류](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/256#issuecomment-5869959567), [해제](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/256#issuecomment-5874843362), [두 번째 보류](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/256#issuecomment-5876271735), [결정](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/256#issuecomment-5876338090).

아래 `후속`은 첫 검토 댓글 또는 표기한 대용 시각 **이후**의 커밋 수다. `≥`는 첫 수정/응답 시각밖에 없어 실제 첫 검토 뒤 커밋 수의 하한이다. `—`는 관찰 근거 없음이며 0회로 해석하지 않는다. run 수에는 취소·실행 중도 포함된다.

| PR | 생성→병합(분) | 커밋 | 검토 수정 하한 | 후속 | CI run / 재실행 |
|---|---:|---:|---:|---:|---:|
| [#256](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/256) | 886.9 | 6 | 1 | 5 | 5 / 2 |
| [#257](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/257) | 920.9 | 5 | 1 | 3 | 5 / 0 |
| [#258](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/258) | 532.7 | 2 | — | — | 3 / 1 |
| [#259](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/259) | 175.9 | 3 | — | — | 1 / 0 |
| [#260](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/260) | 292.9 | 10 | — | — | 6 / 0 |
| [#261](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/261) | 396.6 | 12 | 3 | ≥9 | 6 / 0 |
| [#262](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/262) | 58.9 | 2 | 1 | ≥0 | 2 / 1 |
| [#263](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/263) | 301.3 | 10 | 3 | ≥5 | 2 / 0 |
| [#264](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/264) | 170.8 | 1 | — | — | 1 / 0 |
| [#265](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/265) | 94.7 | 8 | 1 | 2 | 2 / 0 |
| [#266](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/266) | 35.8 | 12 | — | — | 1 / 0 |
| [#267](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/267) | 56.8 | 2 | — | — | 2 / 0 |
| [#268](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/268) | 31.7 | 1 | — | — | 1 / 0 |
| [#269](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/269) | 88.1 | 1 | — | — | 1 / 0 |
| [#270](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/270) | 84.6 | 2 | — | — | 1 / 0 |
| [#271](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/271) | 98.8 | 4 | — | — | 2 / 0 |
| [#272](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/272) | 27.4 | 8 | — | — | 2 / 0 |
| [#273](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/273) | 60.6 | 2 | — | — | 2 / 0 |
| [#274](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/274) | 89.4 | 4 | — | — | 8 / 0 |
| [#275](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/275) | 15.8 | 2 | — | — | 2 / 0 |
| [#276](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/276) | 27.1 | 1 | — | — | 1 / 0 |
| [#277](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/277) | 89.8 | 1 | — | — | 1 / 0 |
| [#278](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/278) | 81.8 | 37 | 1 | 2 | 3 / 0 |
| [#279](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/279) | 35.4 | 4 | — | — | 2 / 0 |
| [#280](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/280) | 20.1 | 7 | — | — | 2 / 0 |
| [#281](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/281) | 205.7 | 6 | 1 | ≥2 | 3 / 0 |
| [#282](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/282) | 72.2 | 5 | — | — | 1 / 0 |
| [#283](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/283) | 25.9 | 11 | 1 | ≥1 | 2 / 0 |
| [#284](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/284) | 213.1 | 1 | — | — | 1 / 0 |
| [#285](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/285) | 열림 | 18 | 1 | 10 | 5 / 0 |
| [#286](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/286) | 89.6 | 1 | — | — | 1 / 0 |
| [#287](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/287) | 27.6 | 1 | — | — | 1 / 0 |
| [#288](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/288) | 60.5 | 1 | — | — | 1 / 0 |
| [#289](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/289) | 59.6 | 1 | — | — | 1 / 0 |
| [#290](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/290) | 33.5 | 1 | — | — | 2 / 0 |
| [#291](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/291) | 19.8 | 1 | — | — | 1 / 0 |
| [#292](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/292) | 열림 | 3 | 1 | ≥1 | 6 / 0 |
| [#293](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/293) | 열림 | 2 | 1 | ≥1 | 4 / 0 |
| [#294](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/294) | 27.8 | 1 | — | — | 2 / 0 |

## 2. CI와 테스트에 실제로 든 시간

| 비교 | n | 중앙값 | p90 | 출처 |
|---|---:|---:|---:|---|
| 대상 PR의 성공 workflow 전체 | 66 | **8.5분** | 21.0분 | [ci_runs.csv](derived/ci_runs.csv) |
| 8분할 도입 전 형태 | 20 | **20.2분** | 23.8분 | 같은 CSV, `offline_sharded=false` |
| 8분할 형태 | 46 | **7.9분** | 10.2분 | 같은 CSV, `offline_sharded=true` |
| `offline-regressions` 완료까지, 분할 전→후 | 20 / 46 | **20.2→4.9분** | 집계 JSON 참조 | [required_gate.csv](derived/required_gate.csv) |
| 실제 pytest 최장 step, 분할 전→후 | 20 / 46 | **19.1→3.6분** | 집계 JSON 참조 | 같은 CSV |
| 생성→첫 job 시작 | 66 | **4초** | 55초 | 러너 대기열이 이 표본의 주 병목이라는 근거는 약함 |

이 전후 비교는 #267의 시점 전후에 코드·머신 부하도 달라진 **관찰 비교**다. 동일 커밋의 속도 실험은 아니다. 이미 구현된 8분할을 새 제안의 절감 효과로 다시 세면 안 된다. [#267](https://github.com/kcm0127-dotcom/ugrp/pull/267), [현재 실행기](../../scripts/run_ci_tests.py), [workflow](../../.github/workflows/tests.yml).

- 95 run = 성공 **66**, 실패 **8**, 취소 **17**, 수집 시작 때 미완료 **4**. 명시적 재실행은 **4회**: #256 두 번, #258·#262 각 한 번. 새 HEAD 실행과 중복 trigger를 재실행이라고 뭉뚱그리지 않았다.
- **동일 workflow·head SHA의 push/PR 중복 13쌍**. push 쪽 실제 job 점유 합계는 **60,151초 = 16.71 runner-hours**다. 이는 제거 대상으로 식별한 계산량이고 **16.71시간의 연구 지연**이 아니다. PR의 merge-ref 검사와 main push는 유지하면서 PR이 있는 feature branch의 push를 억제하는 것이 최소 변경이다. [대상 run ID](derived/duplicate_ci.json).
- 분할 후 마지막에 끝난 job은 `ubuntu-simulation-runtime` **32/46**, `ubuntu-simulation-scenarios` **10/46**, `offline-regressions` **4/46**이다. 앞의 두 job 중앙 실행 시간은 454초·389.5초다. 오프라인 shard를 더 늘려도 42/46에서는 workflow 끝 시각을 직접 당기지 못한다. 변경 경로에 따른 선택과 설치 캐시를 이 job들에서 먼저 검토해야 한다. [job CSV](derived/ci_jobs.csv), [집계](derived/summary.json).
- 순수 Markdown 변경 #269·#287·#289도 전체 workflow를 실행했다. 각각 **450·490·613초**, 총 **25분 53초**다. PR 생성→병합은 각각 88.1·27.6·59.6분이므로 CI를 빼도 전부 사라지지 않는다. 과학 판정·사전 등록 문서는 Markdown이라는 이유만으로 검토를 면제하면 안 된다.
- 현재 정적 목록은 **328개 파일, 8개 shard, 각 41개**, 파일 중복·누락 0이다. 목록 확인만 실행했고 테스트·공용 잠금을 시작하지 않았다. 성공한 분할 run의 가장 긴/짧은 job 비율 중앙값은 **2.72배**다. `--durations-json` 기능과 JUnit artifact가 **이미 있으므로**, 별도 분할기를 만들기보다 이 자료를 연결하는 작은 변경이 맞다. [목록](data/current_shards.txt), [불균형](derived/shard_balance.csv).
- 로컬 전체 검사도 비용이 있다. #265 기록은 **853초와 831초, 합계 28분 4초**, 각각 6252 passed / 16 skipped / **같은 sparse checkout 원인 3 failed**다. `.gz` fixture가 없어서 재실행으로 해결되지 않았다. 동일 결과를 다시 측정하지 않았다. [당시 README 247–250행](https://github.com/kcm0127-dotcom/ugrp/blob/a8094cc14e098a55483f53a3c49bf6a0b116043d/experiments/2026-09-29-pair-v6d-align/README.md#L247). 최소 변경은 sparse 규칙의 작은 필수 fixture 예외와 시험 시작 전 존재 검사다. 실패를 그냥 무시하는 fast path는 제안하지 않는다.

## 3. 소스 고정→결과: 요청한 다섯 정책의 실제 상태

**다섯 이름을 전부 “등록·봉인 후 확증을 마친 제어기”로 볼 수 없다.** v6c/d는 개발 단계 probe, b-v6e는 등록 전 개발 후보, b-v6g는 `revision=v6e`로 결과 뒤 DRAFT 등록, b-v6h1은 관찰 종료 때 미봉인이다. 따라서 **최종 봉인→동일 봉인의 확증 결과 완료 시간은 이 자료에서 다섯 정책 모두 산출할 수 없다**. 아래는 구할 수 있는 대체 지표다.

| 정책·측정 범위 | 소스 커밋 시각 (KST) → 결과 문서 커밋 | 경과 | 실제 저장된 실행 시간 | 봉인과의 관계 |
|---|---|---:|---|---|
| b-v6c 초기 개발 | `b5234b7a` 9/29 01:39:18 → `099f4466` 03:51:18 | **132.0분** | 초기 align 25건 24.6분; 후속 bound 46건 12.3분 | 그 사이 검토 수정 발생. 최종 재봉인 `be95f8b0` 07:40:54는 결과 문서보다 뒤, 그 소스로 재실행 없음 |
| b-v6d 실행 트리 | `052e3eba` 06:19:22 → `29d30234` 09:16:48 | **177.4분** | 정렬 두 shard 38.6/34.9분; 병합 트리 subset 19.7분·bound 18.9분 | 최종 봉인 `48f9872a` 10:13:08는 보고 뒤. 25셀 전체를 v80에서 반복하지 않음 |
| b-v6e yaw 첫 후보 | `86cdefc9` 14:51:06 → `b16f7987` 16:05:52 | **74.8분** | cal 40건 **41.1분** | 등록 전 소스 고정. 수정 뒤 후보와 별도 결과 |
| b-v6e yaw 검토 수정 | `4fac772d` 16:12:38 → `eb5232c7` 17:03:38 | **51.0분** | cal 40건 **35.2분** | hA 4/10 등 미달 포함. 최종 봉인된 확증 아님 |
| b-v6g 첫 보류 배치 | `f844a373` 18:54:08 → `6a07fd8a` 19:20:35 | **26.5분** | 같은 소스에서 hB/C/D 단계 시험 | hB 8/10, hC 5/10, hD 7/10; 실패를 보존 |
| b-v6g 후속 hR2 | `f844a373` 18:54:08 → `3c91decd` 20:58:36 | **124.5분** | hR2 70건 **30.5분** | 제어기·적합은 같지만 staging·표본 규칙은 바뀜. `e510779d` 21:19:17에서 v81 / revision v6e DRAFT 등록 |
| b-v6h / b-v6h1 | #285 탐색과 #292 등록 구현은 별개 | **확증 결과 없음** | 새 실행 안 함 | #292 `3afc61b0`: 268개 소스 preview, `sealed=false`, 독립 검토 지적·인수 재생·봉인 남음 |

출처: [git 타임라인과 전체 SHA](derived/timeline.json), [로컬 manifest 메타데이터·SHA](derived/local_manifest_receipts.json), [v6c](../2026-09-29-pair-v6c/README.md), [v6d](../2026-09-29-pair-v6d-align/README.md), [v6e/g](../2026-09-29-pair-v6e-carry/README.md), [v6h 등록 계획](https://github.com/kcm0127-dotcom/ugrp/blob/3afc61b00f2c127ac3fbe2be5e7bb57da989b15a/experiments/2026-09-30-pair-v6h-carry/REGISTRATION_PLAN.md).

한계: 선택한 manifest에는 UTC 시작·끝 필드가 없고 `wall_s`만 있다. **결과 커밋 시각은 완료 시각의 상한**이며 실행 시작 전 준비·결과 작성도 포함한다. 서로 다른 실행의 wall 시간을 더해 경과 시간에서 빼지 않았다(병렬 실행·다른 소스·일부 실행만 수집). 로컬 wall 값은 당시 부하의 관찰치이며 제어기 속도 비교 근거가 아니다.

b-v6g는 첫 스모크 1/4, hB/C/D 미달, hR 44/70 뒤 hR2 56/70을 얻었다. README가 정정하듯 hR2는 네 번째 보류 묶음 시도이고 서로 다른 출발 조건은 6개다. **관리 비용을 줄이더라도 이 결과를 새 확증으로 소급 재분류하지 않는다.** 다음 확증에서는 대상 분포·분모·주장·중단 규칙을 새 자료를 보기 전에 잠근다.

## 4. 봉인 규모, 재봉인, 번호

아래는 전체 실행 트리 해시와 구분한 **`v6_contract.source_sha256`의 파일 수**다. `변경`은 앞 행과 공통으로 있는 경로의 해시 변경, `추가`는 새 경로다. 이것이 전부 제어 로직 수정이라는 뜻은 아니다.

| 개정 / 정책 | 소스 수 | 기존 중 변경 | 추가 | 기존 중 불변 | prereg JSON 줄 수 | Git에 남은 서로 다른 pin 파일 버전 |
|---|---:|---:|---:|---:|---:|---:|
| v6b (비교 시작점) | 73 | — | — | — | 581 | 5 |
| v6c / b-v6c | **77** | **12** | 4 | 61 | 603 | **5** |
| v6d / b-v6d | **80** | **8** | 3 | 69 | 636 | **2** |
| v6e / b-v6g | **85** | **12** | 5 | 68 | 675 | **1** |
| v6h 초기 미봉인 preview `52264828` | **104** | **12** | 19 | 73 | 봉인 없음 | 해당 없음 |
| v6h 검토 수정 preview `3afc61b0` | **268** | **12** | 183 | 73 | 봉인 없음 | 해당 없음 |

출처: [경로별 차이](derived/pins.json), [pin 변경 커밋과 해시](derived/pin_history.json). 마지막 두 행은 모두 v6e 85개를 기준으로 비교했다. v6c/d/e는 각각 최종 pin의 20.8% / 13.8% / 20.0% 경로가 변경 또는 추가됐다. v6h의 104→268은 검토에서 명령 생성 의존성 누락을 보완한 것으로, 소스 수만 줄이는 접근이 안전하지 않음을 보여준다. manifest의 넓은 실행 트리는 예를 들어 v6d **951/974개**를 다루므로 “프로젝트 봉인은 104개”라는 단일 수는 맞지 않는다.

해시를 계산하는 CPU 시간 자체는 이번에 측정하지 않았다. 직접 확인된 비용은 해시 불일치가 다른 PR·검증을 막는 결합이며, 파일 수만 많다고 느리다고 단정하지 않는다.

`pin 파일 버전 수 - 1`은 생성 뒤 기록된 갱신 횟수이지 **모두 불필요한 재봉인**이라는 뜻은 아니다. v6c는 검토 수정까지 포함해 4번, v6d는 1번 갱신됐다. 원인이 문서에 명시된 최종 재봉인은 **v6c의 main 재동기화 1회, v6d의 검토 반영 1회**다. #256은 기존 v6와 v6b를 각각 이력 감사로 바꿔 두 번의 교차 PR 충돌을 풀었다. 이전 봉인을 덮어쓰는 해결은 하지 않았다.

| 번호 | 이 구간에서의 의미 | 재번호인지 |
|---|---|---|
| v76 | #263 b-v6c; v77–v79가 먼저 병합된 뒤 재동기화 | 번호 유지, 소스 재봉인·workflow 2.12.0 |
| v77 | #256 B7 | **후보 v72→v77**, workflow 2.9.0 |
| v78 | #257 심판 | **후보 v73→v78**, workflow 2.10.0 |
| v79 | #249 MasterPi v3 | 후보 v74→v79, workflow 2.11.0. **PR 번호는 조사 범위 밖**, v6c 재동기화 의존성으로만 포함 |
| v80 | #265 b-v6d | 새 후보, 2.13.0 |
| v81 | #278 b-v6g / revision v6e | 새 후보, 2.14.0 |
| v82 | v6f가 v6e로 합쳐져 사용하지 않음 | **건너뛴 예약**. 실패 실행/은퇴 실행으로 세지 않음 |
| v83 | #292 b-v6h1 / revision v6h | 2.16.0 예약·구현, **미봉인** |

대상 PR에서 확인한 합류 재번호는 **#256·#257 두 건**(그 밖의 #249 포함 시 세 건). 번호 하나가 늘었다고 재번호 한 번으로 세지 않았다. snapshot의 integration `RETIRED_BUNDLE_IDS`는 총 **15개**, 그중 v76–v80은 5개다. 전체 RGB 역사 번들 수와 혼동하면 안 된다. [은퇴 목록](derived/retired_bundles.json), [상수·변경 이유](https://github.com/kcm0127-dotcom/ugrp/blob/a8094cc14e098a55483f53a3c49bf6a0b116043d/harness/zone_study_integration.py#L79).

## 5. 문서·분기·작업 디렉터리 규모

| 실험 폴더 | README 줄 | 사전 등록 문서/JSON 줄 | 폴더 안 Python 줄 | 주의 |
|---|---:|---:|---:|---|
| pair-v6c | 270 | 603 | 341 | Python은 주로 등록 생성·분석 도구이며 제어기 전체가 아님 |
| pair-v6c-carry | 341 | 0 | 181 | stage probe 진단 |
| pair-v6d-align | 282 | 636 | 923 | 문서에 개발·병합 후·재검토 기록이 함께 있음 |
| pair-v6e-carry | **1026** | **675** | 2352 | v6e→v6g, 여러 계획·실패·재측정이 한 README에 누적 |
| pair-v6h-carry (#292 SHA) | 79 | 162 | 231 | 등록 구현 branch만. #285 탐색 폴더 전체와 다름 |

조사 PR diff 누적은 Markdown **8,266 추가 / 81 삭제**, Python **35,514 추가 / 777 삭제**다. Markdown/Python 변경 줄 비율은 **0.230**이다. 기타 파일은 309,542 추가 / 27 삭제로 결과 JSON/CSV/로그 등이 크게 차지한다. PR 간 상속·중복이 있으므로 고유 코드 증가량도, 집필 시간도 아니다. “문서가 코드보다 많다”는 전 저장소 주장은 이 수치로 뒷받침되지 않는다. 그러나 1026줄 README에서 현재 계획과 폐기 계획을 사람이 구분하는 비용은 별도 계측할 가치가 있다. [실험별 전수 줄 수](derived/docs_volume.csv), [diff 분류](derived/diff_volume.json).

- 작업 디렉터리(worktree) **80개**, HEAD가 snapshot main의 조상인 것은 **69개**. 마지막 HEAD 커밋이 7일보다 오래된 것은 **0개**다. 69개를 “지워도 되는 디렉터리”라고 판단하지 않았다. 실행 중 프로세스·수정 파일·무시된 raw는 별도 검사 대상이다.
- 로컬 branch **223개**: main에 포함된 HEAD **198개**, HEAD 커밋이 7일보다 오래된 것 **49개**. origin 추적 branch **161개**: main 포함 **125개**, 7일 초과 **42개**. `origin/HEAD`는 제외했다. **원격 서버의 실제 branch 목록이 아니라 fetch 뒤 로컬 추적 목록**이다.
- 관찰 종료까지 생성된 저장소 전체 PR은 **251개**(병합 238, 미병합 종료 10, 열림 3)다. [전체 생성·종료 시각](data/all_prs.json). 열린 PR **3개(#285·#292·#293)**, 마지막 GitHub 갱신이 48시간보다 오래된 것은 **0개**. 오래된 branch와 열린 PR 적체를 같은 현상으로 볼 수 없다.
- 여기서 오래됨(stale)은 위 시간 기준일 뿐 폐기 여부가 아니다. 수정 시각·현재 작업 유무를 조사하지 않았고 정리도 실행하지 않았다. [원목록](data/inventory.json), [worktree CSV](derived/worktrees.csv), [branch CSV](derived/refs.csv).

## 6. AI 지연에서 확인할 수 있는 것과 없는 것

허용된 로컬 Claude JSONL을 읽기 전용으로 처리해 **본문·프롬프트·도구 인자·개별 세션 ID를 저장하지 않고 집계만** 만들었다. 같은 관찰 구간에 자료가 있는 상위 세션은 3개, 중복을 제거한 assistant message ID는 **875개**다. metadata의 effort는 high 732, xhigh 140, 미기록 3이다. 이 표본은 모든 Codex·Sonnet·검토 작업자의 로그를 포함하지 않는다.

사용자/도구 응답→첫 assistant event 간격은 high 중앙 3.57초, xhigh 2.73초다. 이는 streaming·대기·네트워크·재시도 등이 섞인 **기록 간격**이며 전체 답변 생성 시간이나 모델 추론 지연이 아니다. 따라서 xhigh가 더 빠르다는 결론도, 이번 지연의 주범이라는 결론도 내릴 수 없다. 기록된 재시도 지연 35건의 설정 합은 283.5초지만 실제 기다린 시간을 확인한 값은 아니다. 비동기 Agent tool의 즉시 반환 시간도 하위 작업 완료 시간으로 세지 않았다. [집계와 한계](data/transcript_aggregate.json), [내용을 내보내지 않는 집계기](transcript_metrics.py).

모델 effort를 줄여 절약할 시간을 입증하려면 다음 작업부터 `request_started`, `first_token`, `response_finished`, 도구/검토 완료 시각을 같은 작업 ID로 기록해야 한다. 이 측정에서는 추가 모델을 호출하지 않았다.

## 7. 상위 5개 개선: 예상 절감/위험 순서

정량적인 절감/위험 비율을 계산할 실험은 없으므로 **낮은 변경 위험과 확인된 반복 비용을 우선한 판단 순서**다. “대상 비용”은 제거 가능성을 시험할 범위이며 약속하는 절감량이 아니다.

| 순위·병목 | 관찰 근거·대상 비용 | 대부분을 줄일 최소 변경 | 위험·정직성 유지 조건 |
|---|---|---|---|
| **1. 같은 변경의 중복 CI와 무관한 전체 job** | 동일 SHA 13쌍, push 쪽 16.71 runner-hours. 순수 문서 3건도 7.5–10.2분/회. 분할 후 42/46은 Ubuntu simulation job이 끝을 결정 | PR이 있는 feature branch의 push CI 억제. required check 이름은 유지하고, 변경 경로 판정 job이 순수 안내 문서는 정적 검사만 선택. scene/physics/runner/lockfile 변경은 기존 전체 실행 | 낮음~중간. PR merge-ref 검사는 유지. 누락/알 수 없는 경로는 전체 검사. 사전 등록·판정 문서는 별도 검토 유지. wall 절감은 문서 경로에서 먼저 측정; runner-hours를 wall로 바꾸지 않음 |
| **2. 로컬 전체 검사의 같은 환경 실패 반복** | #265는 853+831초를 쓰고 같은 누락 fixture 3건이 반복 | sparse checkout에서 필수 작은 `.gz` fixture를 포함하고 실행 전 존재 검사. 로컬은 변경 의존성 시험, 전체 검증은 맞는 환경의 CI 결과 재사용 | 낮음. fixture 누락을 pass/skip으로 바꾸지 않음. 캐시는 SHA·의존성·테스트·환경 키가 일치할 때만 사용. 28.1분 전체가 불필요했다고 단정하지 않음 |
| **3. 공용 카탈로그가 실행 봉인을 깨는 결합** | #256 보류 구간 270.9분, v6b에서 재발. v6c/d/e는 대부분 기존 source hash가 불변 | 과거 봉인은 특정 Git tree의 불변 manifest로 검증. 현재 실행 후보는 **제어/입력/물리/평가/실행기 의존성 묶음별 digest**와 전체 파일 명세를 기계 생성·비교. 공용 카탈로그는 선택한 entry의 실행 유효값을 별도로 고정 | 중간. 파일/전이 의존성을 빼자는 제안 아님. 동적 import·모델·지도·평가 코드까지 영향 범위 불명확하면 전체 무효화. 환경/실행 의미가 바뀌면 새 후보·새 검증. 과거 결과 승계 금지 |
| **4. 검토→수정→다시 검토의 뒤늦은 반복** | #261·#263 각 3회, 전체 확인된 최소 16묶음·후속 41커밋. #285는 통계 주장·분모·분류기 지적이 구현 뒤 발견됨 | 구현 전 한 장의 관측 경계·분모·주장·중단 규칙을 먼저 확정. 제어/통계 담당 검토를 같은 후보 SHA에서 병렬로 받고 지적을 한 묶음으로 수정. 재검토는 달라진 범위와 불변 검사 결과를 함께 전달 | 중간. 제어·평가·prereg는 독립 검토 유지. 단순 링크/표기·생성 자료는 검증 후 기계 병합 후보로 분리. 실제 반복 검토가 잡은 안전/통계 결함을 불필요한 비용으로 세지 않음. 절감 시간 미계측 |
| **5. 수동 등록 번호·중복 상태 문서·흩어진 작업 상태** | 대상 합류 재번호 2건, v6c pin 5버전, README 1026줄+prereg 675줄, worktree 80개. 다만 집필·탐색 시간은 미계측 | 내용 digest를 후보 식별자로 쓰고 사람이 읽는 bundle/workflow 번호는 원자적 예약 도구로 발급. 한 JSON manifest에서 차이표·현재 상태·실행 명령·결과표 생성. 실패·폐기 계획은 불변 event 기록으로 보존 | 낮음~중간. 코드 버전과 과학 prereg 버전은 따로 표현. 과거 ID·원문·raw를 변경/삭제하지 않음. worktree 정리는 현행 보존 검사 도구로만 별도 수행. 절감량은 다음 작업에서 확인 |

우선 **1·2를 작은 독립 PR로 적용**하고 동일 코드/CI 조건의 다음 10개 변경에서 확인하는 것이 가장 싸다. 3은 실행 의미의 경계를 검토하는 별도 계약 변경이다. 지금처럼 README나 번호만 바뀌었는데 제어기 재시험이 필요한 구조를 줄이되, 실제 제어·판정 의존성 변화에는 검증을 계속 요구한다. 이 보고서 자체는 어느 정책도 적용하지 않았다.

연구 절차는 두 흐름으로 분명히 한다. 탐색에서는 작은 변경마다 자동 후보 해시·입력·판정·raw 위치만 남겨 빠르게 실패를 찾는다. 후보를 선택한 뒤 **한 번** 독립 검토·인수 재생·전체 출처 봉인을 묶어 새 확증 자료를 열고, 결과를 본 뒤 소스/분모/주장/중단 규칙을 바꾸면 새 연구 단위로 시작한다. 사전에 허용한 재적합·중단 규칙은 그대로 남긴다. 반복해서 본 보류 자료의 이름만 바꿔 새 확증으로 쓰지 않는다.

다음 측정에 필요한 최소 event 필드는 `task_id`, `candidate_digest`, `stage`, `started_at_utc`, `finished_at_utc`, `blocking_dependency`, `source_sha`, `result_ref`, `cohort_kind`다. 단계는 구현/로컬 시험/CI/검토/수정/인수/봉인/실행/분석으로 구분한다. 동시에 진행한 구간은 합계가 아니라 임계 경로(critical path)로 계산한다. 새 자동화나 감시 작업은 만들지 않았다.

## 재현과 검증

Python 표준 라이브러리·git·gh만 필요하다. 기존 snapshot을 덮어쓰지 않도록 수집기는 빈 새 디렉터리만 받는다. `collect.py`는 GitHub 조회와 git 읽기만 수행하며 테스트·시뮬레이터를 시작하지 않는다.

```sh
# 현재 상태를 다시 수집: 원래 스냅샷과 시각/HEAD가 달라질 수 있다.
git fetch origin
python3 experiments/2026-09-30-process-review/collect.py --out /tmp/ugrp-process-NEW

# 보존한 원자료에서 수치 재계산(네트워크 없음)
python3 experiments/2026-09-30-process-review/analyze.py --out /tmp/ugrp-process-analysis-NEW
python3 experiments/2026-09-30-process-review/git_metrics.py --out /tmp/ugrp-process-git-NEW

# 로컬 raw가 있는 경우에만 선택 manifest 메타데이터를 확인한다.
python3 experiments/2026-09-30-process-review/git_metrics.py --out /tmp/ugrp-process-git-local-NEW --local-outputs /Users/changmin/projects/ugrp/outputs

# 선택 사항: 허용된 로컬 로그의 집계. 본문은 내보내지 않는다.
python3 experiments/2026-09-30-process-review/transcript_metrics.py --root /Users/changmin/.claude/projects/-Users-changmin-projects-ugrp --end 2026-09-30T09:49:03.434086+00:00 --out /tmp/ugrp-process-transcript-NEW.json
```

Git 객체는 snapshot SHA와 #292 HEAD를 포함해야 한다. 오래된 PR ref가 로컬에 없으면 해당 PR ref를 fetch한 뒤 실행한다. git 기반 표는 고정 SHA에서 읽으므로 작업 트리 변경에 영향받지 않는다. 로컬 manifest와 비공개 세션 로그는 새 clone에 없을 수 있다. 그 두 보조 자료의 재수집 제한을 GitHub/git 측정의 재현성과 구분한다.

수집 검증에서 GitHub의 제한 두 가지를 발견했다. #285의 `gh pr view files`는 첫 100개만 주어 REST 페이지로 **113개 전체**를 받았다. 그 뒤에도 큰 diff 후반 **19개 파일의 줄 수가 0**으로 돌아와, 같은 base/head의 `git diff --numstat`로 보완했다(누락 12,233 추가 줄). API 원값과 `git_file_stats`를 함께 남겼고, **39개 PR 모두 파일별 추가/삭제 합이 PR 총합과 일치**하는지 확인한다. 저장 자료를 그럴듯한 숫자로 맞추기 위해 조용히 교체하지 않았다.

검증 범위와 결과는 [VALIDATION.md](VALIDATION.md)에 기록한다. 새 로봇 실험·학습·평가 결과가 아니므로 TensorBoard 재변환·서버 시작·화면 재개방을 하지 않았다. 기존 결과·snapshot·원본은 보존했다. Google Drive는 프로젝트 예외에 따라 사용하지 않았다.

## 참고 자료

- [AGENTS.md](../../AGENTS.md), [CONTRIBUTING.md](../../CONTRIBUTING.md), [실행 버전 관리](../../docs/execution_versioning.md), [문서 색인](../../docs/README.md): 현재 규칙과 과거 기록의 구분.
- [PR #256](https://github.com/kcm0127-dotcom/ugrp/pull/256), [#257](https://github.com/kcm0127-dotcom/ugrp/pull/257), [#261](https://github.com/kcm0127-dotcom/ugrp/pull/261), [#263](https://github.com/kcm0127-dotcom/ugrp/pull/263), [#265](https://github.com/kcm0127-dotcom/ugrp/pull/265), [#267](https://github.com/kcm0127-dotcom/ugrp/pull/267), [#278](https://github.com/kcm0127-dotcom/ugrp/pull/278), [#285](https://github.com/kcm0127-dotcom/ugrp/pull/285), [#292](https://github.com/kcm0127-dotcom/ugrp/pull/292): 조사에서 인용한 주요 원자료. 나머지 전수 URL은 PR CSV에 있다.
- 위의 실험 README·봉인 JSON·현재 workflow, GitHub job start/end·test-step 기록. 외부 연구 일반론으로 프로젝트의 실제 지연을 대체하지 않았다.
