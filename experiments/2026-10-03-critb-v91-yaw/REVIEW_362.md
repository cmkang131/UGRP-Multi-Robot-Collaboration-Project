# PR #362 독립 검토 — MERGE

2026-10-03, Codex 독립 검토. **수정이 필요한 P0/P1/P2 지적 없음.**
판정은 아래 SHA의 오프라인 채점 구현에 한정한다. 실제 held-out 결과나 물리 성공 판정은 아니다.

- 대상: `edcb4d3c0a001b4c5fa7bf5c61a7ae6be3177bb2` (`codex/critb-v91-yaw`).
- 최신 main / #356 병합본: `36a7dfceb767437f29f469fc860fc02f8a349654`.
- 작업: `codex/review-362`. 시작 시 `git fetch origin`, 열린 PR, 기본 checkout의 origin/main/청결 상태와 지침을 확인했다.
- 검토용 로컬 병합 `25a55c005dca661a34c788da42a242b7bba7ded7`의 tree는 대상 PR tree와 같다. 작성자 브랜치와 구현은 수정하지 않았다.

## 요청한 다섯 항목

| 항목 | 검증과 결론 |
|---|---|
| 1. 고정 부록·r5·공개 약속 | `scripts/validate_consumer_criterion_b_v91.py:102`의 `prepare_rotation`이 스냅샷 전체 해시, 댓글 ID/URL, 생성=수정 시각, 본문 해시, 공개된 두 해시와 실제 파일 바이트를 확인한다. manifest도 부록/r5의 해시와 대조한다. runtime 진입 및 변조/누락 거부를 합성 검사했다. |
| 2. 시간 순서의 정직한 구분 | 같은 파일 `:357`, `:400`, `:422`, `:447`에서 yaw는 `PRE_SCORING_AND_READING_NOT_PRE_COLLECTION`, `pre_collection_claim=false`이며, 기존 B의 수집 전 검사는 유지된다. yaw는 `commitment < 이번 호출의 raw 읽기 <= yaw 채점`이다. v91 수집이 yaw 약속보다 앞섰다는 사용자 지정 사실과 동결 기록을 그대로 표기하며, 실제 raw의 시각을 이번 검토에서 열어 검증한 것은 아니다. 과거 미열람 선언과 시계 동기화의 한계도 명시돼 있다. |
| 3. forward/left 동일성과 yaw 수치 | **실제 #356 병합 커밋에서 검증기를 로드**해 forward/left의 통과·실패·지원 누락·훈련 사례 8개와 두 지도 합성 raw의 전체 원래 보고서를 JSON 직렬화 바이트로 대조했다. 옵션 OFF/ON 모두 동일하다. yaw는 `:167`에서 동결 `evaluate_axis(case, 2, profile, B)`를 호출하며, 동일 수치·성분·시간·집계 규칙을 사용한다. 아래 독립 경계 사례도 통과했다. |
| 4. 고정 파일 보존 | 기존 preservation 목록 **64개 전부**를 현재 바이트, #356 병합본 Git blob, 대상 PR Git blob, 저장된 SHA-256과 교차 확인했다. B/r4/기존 검증기/부록/r5/manifest와 등록 파일이 모두 동일하다. |
| 5. main 병합 가능성 | `git merge-tree --write-tree <main> <head>` 종료 0, 충돌 없음. 결과 tree `57ed868379152950ad17790104ef7fee9ce2c802`는 대상 PR tree와 같다. 검토 브랜치에서 실제 로컬 병합도 성공했다. GitHub `MERGEABLE`을 확인했다. PR head가 main의 병합 커밋 자체를 조상으로 포함하지는 않지만, 해당 내용을 병합할 때 추가 코드 변경은 생기지 않는다. |

확인한 SHA-256:

```text
consumer_criterion_B_rotation.json
6129f144c840510535de053ffcce325ef934e8192c6adf777b2df8d976f5da08
calibration_candidate_r5_yaw.json
978727fcacc5e368efe2a0fdf6d9d8dc3756573c41e896e06ba11d78cf86fb97
yaw commitment.json
cad257ab12c41b786e36a1688ef522ee512551460ec91dc8e1b44a162fe450ca
```

2026-10-03T06:34:03Z에 검증기의 실제 재조회 경로로
[yaw 댓글 5966135675](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/219#issuecomment-5966135675)와
[B 댓글 5958329647](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/219#issuecomment-5958329647)의
id·URL·본문·생성/수정 시각 일치를 확인했다. yaw 생성/수정 시각은 모두
`2026-10-03T05:56:19Z`. 기본 실행은 고정 스냅샷 검증이며, 요청한 재조회가 실패/불일치하면
해당 경로는 `INELIGIBLE`, `pass=null`이다.

## 수치 반례와 실행 결과

독립 검사 [review_362_checks.py](review_362_checks.py)는 기존 수치 함수를 호출하지 않고
순수 yaw의 속도 응답과 끝 속도 Euler 적분으로 pose를 만들고, 각 tick의
`((noise_rel * abs(velocity) + noise_abs) * 0.05)^2`를 합쳐 yaw 분산을 계산했다.
동결 채점기와의 p95 차이는 `2e-12` 이내였다. 이 검사에는 적합이나 실제 raw가 없다.

| 합성 사례 | 관측한 판정 |
|---|---|
| 모든 그룹 최대 yaw p95 ≈ `1.9999998`, 두 지도 | `true` |
| 같은 자료에서 최대 yaw p95 ≈ `2.0000002`, 두 지도 | `false` |
| 100개 잔차가 정확히 2σ | 경계 포함, `true` |
| 2σ 초과 9/10/11개 | 포함률 91%/90%/89%; p95도 초과하므로 모두 `false` |
| 지도 누락 / 후보·±계단·±PRBS·시간 지원 누락 | 실패가 없으면 `null`; 관측한 실패는 `false`로 유지 |
| 부록·r5·manifest·스냅샷 변조, 훈련 pose 재사용, 잘못된 명령 lease/시계 | `INELIGIBLE` 또는 해당 축 `null`; 통과로 승격하지 않음 |
| yaw 계산 중 raw/B 증거 변경 | 원래 B와 yaw 모두 무효화 |

예측 시간 `0.2/0.5/1/2/3/3.2 s`, 전진 m·측면 m·yaw rad 세 성분, 계단/PRBS와 coast,
모든 완전한 0.05초 시작 창을 유지한다. 각 지도·split·시간·성분에
`p95(abs(error)/sigma) <= 2`와 `coverage_2sigma >= 0.90`를 동시에 적용한다.
평균은 `scripts/fit_unloaded_consumer.py:190`의 r4 끝 속도 Euler,
공분산은 같은 파일 `:202`의 r4 모델이며 rest noise ON, scale OFF다.
원래 B/r4의 rotate는 계속 null이며, 실패가 없는 경우 전체 pass도 null이다. 실패가 있으면 원래 규칙대로 false다. 새 요약은 별도 필드에만 있다.

**306 passed in 45.94s**: 관련 기존 검사 289개 + 독립 검사 17개.
작성자의 기존 로그를 새 실행 결과에 합산하지 않았다.
[실행 로그](review_362_tests.txt), [JUnit](review_362_tests.xml),
[해시·환경·명령·공개 기록 대조](review_362_evidence.json)를 함께 저장했다.
재현 시 evidence의 명령에서 `/private/tmp/ugrp-review-362-safety` 대신
`experiments/2026-10-03-critb-v91-yaw/review_362_safety`를 사용하면 동일한
[접근 가드](review_362_safety/sitecustomize.py)가 적용된다.

## 범위와 남은 절차

- 실제 `/Users/changmin/projects/ugrp/outputs/final-pair-v91-heldout-*`는 **열람·해시·채점 모두 0회**. 허용된 identity 필드도 필요 없어 읽지 않았다. 훈련 원본도 열지 않았다.
- 렌더링·물리 실행·모델 호출·기존 실행 프로세스 조작 0회. 합성 회귀검사에는 held-out 파일 열기, 네트워크 연결, 물리/모델 모듈 import를 거부하는 가드를 적용했다. 공개 댓글 조회는 별도 read-only GitHub 호출이다.
- 06:34 UTC에는 원격 CI 일부가 실행 중이었으나, 최종 재조회에서 동일 head의 **33개 검사 모두 SUCCESS**와 필수 `offline-regressions` 성공을 확인했다. 상세 시각·검사 URL은 evidence의 `final_github_check`에 저장했다. 코드 검토 판정은 `MERGE`; 실제 PR 병합은 코디네이터에게 인계한다.
- 실제 v91의 한 번 채점과 그 결과·TensorBoard 등록은 코디네이터의 후속 작업이다. 이번 결과는 합성 코드 검증이므로 TensorBoard 변환·뷰어 실행은 하지 않았다. 프로젝트 지침에 따라 Drive는 사용하지 않았다.

이 한 묶음의 검토로 요청한 다섯 항목을 모두 확인했다. 새 코드가 올라오면 변경 범위는 다시 검토해야 한다.
