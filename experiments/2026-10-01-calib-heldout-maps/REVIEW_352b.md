# PR #352 독립 재검토

판정: **MERGE AFTER FIXES**. 이전 P1·P2는 닫혔다. 인계문의 직접 계획 안내 한 곳을
수정하고, 실패한 필수 CI를 통과시킨 뒤 병합할 수 있다. 이 검토에서는 병합하지 않았다.

- 대상: `fa2119ca6926a66a317a455701cbc389d7d3fb58`.
- 기준 main: `11e9aa26954d3f1ce58c5116ddd14ec2b2738037`.
- 이전 검토: `f5eb5636343525f41728ce6c4932c25e6ec3a273`, [REVIEW_352.md](REVIEW_352.md).
- [작성자 답변](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/352#issuecomment-5948484619)을 읽고,
  fetch/diff 및 후보의 `git archive` 추출본으로 재검증했다. 검사 종료 직전에도 PR head와 main은 위 SHA였다.

## 닫힌 지적과 재현성 확인

| 항목 | 독립 확인 결과 |
|---|---|
| R1 / P1, v88 전체 바이트 | 이전 기준 해시 여섯 개를 바꾸지 않고 세 profile의 plan/bundle 전체 JSON 바이트가 일치했다. 기존 strict xfail 6개가 필수 통과했다. 각 bundle 소스 239개도 원래 base `25232698`, 최신 main, 후보 Git blob 및 실제 SHA-256과 동일했다. 해시 필드를 삭제하지 않았다. |
| R2 / P2, 표기 변조 미탐지 | 이전 TRAINING 반례가 이제 기존 plan 검사의 실패를 확인하며 통과했다. 역할·`training_eligible`·`teacher_only`를 생산 상수와 분리한 리터럴로 검사한다. 원래 strict xfail 총 7개가 모두 통과했다. |
| 인접 표기 변이 | 두 지도에서 코드 상수+등록 JSON의 세 필드를 각각 바꾼 6개 변이, plan/전체 result/사례 result/전체 result 내부 사례만 바꾼 12개 변이를 모두 탐지했다. 성공·HOST_ERROR 양쪽의 저장 파일과 사례 hash도 검사했다. |
| 허용 범위 | 두 지도에서 seed -1, 0, 910, 912, 2147483647을 CLI·run_case·직접 backend 진입점에서 거부했다. fine/loaded는 CLI뿐 아니라 measurement/case를 동반한 위조 bundle도 출력 생성·backend 생성 전에 거부했다. 기존 interlock/시작점/NaN/부분 자료 보존 회귀도 통과했다. |
| 번호·버전 | main 및 열린 PR #353/#352/#351/#339/#309/#293의 실제 원격 SHA를 조회했다. 다른 브랜치 최대 bundle v89, 공용 RGB RUNNABLE_ID v63. `zone-final-pair-v90` / `zone-final-pair-heldout-v90` 3.2.0은 #352에만 있고 충돌하지 않는다. |
| 동결 자료·병합 | 기존 설정·일정·workflow·criterion B/validator 12개가 원래 해시와 동일하다. 동결 보정 실험 디렉터리 29개 파일도 main과 동일하다. `.github/workflows` 변경 없음. v90의 소스 247/248개 hash도 실제 파일과 일치한다. |
| CI 시간표 | **371/409 = 90.709%**, 90% 기준 충족. 8개 shard 합집합/중복 없음 확인. frozen fixture 3개 존재. 이 coverage는 아래 실제 CI 성공을 뜻하지 않는다. |

기존 리뷰 반례의 후보 내 이식본을 원본과 diff로 대조했다. 기대 해시는 그대로이며,
v90 호출을 분리된 API로 연결하고 strict xfail을 제거한 변경이다.
전체 archive의 후보 추적 파일 **9,119개**를 Git blob과 대조했다.
근거: [static.json](review_352b/static.json), [검증 집계](review_352b/verification.json).

## 새 지적 — R3 / P2

**`PHYSICS_HANDOFF.md:67-68`의 직접 계획 안내가 PR head에서 실행되지 않는다.**

본문은 `run_final_pair_v3 --check calibration-unloaded --map-id <위 두 지도>`도 v90을
표시한다고 설명한다. 그러나 P1 수정으로 v88 진입점은 다시 두 문 전용이며,
두 held-out 지도 모두 `ValueError: v88 motion identification requires the registered two-door collection map`으로 거부한다.
따라서 문서대로 직접 계획을 점검하는 담당자는 정상적인 v90 후보에서도 실패한다.

예를 들어 후보 archive에서 다음은 물리 실행 없이 실패한다.

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  -m scripts.run_final_pair_v3 --check calibration-unloaded \
  --map-id zone_wide_corridor_final_v3 --seed 911 \
  --expected-source-sha fa2119ca6926a66a317a455701cbc389d7d3fb58 \
  --output /private/tmp/review-352b-unused
```

직접 계획 예시는 `scripts.run_final_pair_heldout`으로 고치거나 삭제해야 한다.
반례: `tests/test_review_352b.py::test_documented_direct_preview_actually_accepts_both_maps`
— 두 지도 **2 strict xfail**로 보존했다. 이 실패는 닫힌 R1/R2의 재발이 아니다.

한편 **본문 첫 bash 블록의 두 정식 workflow 명령은 통과했다**. bash 문법,
소유자/branch/PID/10분 잠금 인자, seed 911, unloaded, source SHA, 지도별 output,
workflow 3.2.0 → `scripts.run_final_pair_heldout` 연결을 확인했다.
문서에서 추출한 인자를 그대로 사용하고 output만 임시 경로로 옮겨, 두 지도 모두
fake backend의 저장된 plan/bundle/사례·전체 result까지 검사했다.
실제 source/디스크/잠금 상태는 fake host로 대체했으며 실제 수집 명령을 실행한 것은 아니다.

## 필수 CI 미통과

해당 SHA의 [Actions 실행 36986081433](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36986081433)은
검토 중 실패로 끝났다. `offline-regression-shard (3/8)`은 2026-10-02
08:48:39–09:03:55 UTC에 실행됐고, GitHub annotation이 **15분 최대 실행시간 초과**를 명시한다.
shard는 CANCELLED, 필수 집계 `offline-regressions`는 FAILURE, 나머지 31개는 SUCCESS다.
해당 shard의 JUnit artifact도 만들어지지 않았다.

이는 테스트 assertion 실패가 입증됐다는 뜻은 아니다. 시간초과 원인은 이 범위에서
확정하지 않았으며, 원인 확인·조치 후 필수 CI 전체 통과를 확인해야 한다.
검토자는 workflow 수정이나 CI 재실행을 하지 않았다.
근거: [현재 check 상태](review_352b/ci.json), [job 상태](review_352b/ci-shard3.json),
[GitHub annotations](review_352b/ci-shard3-annotations.json).

## 검사·보존 범위

중복을 제거한 최종 결과는 **241 passed / 0 unresolved failed / 2 strict xfail**이다.
기존 관련 검사 204개, 추가 재검토 검사 37개가 통과했고 xfail 2개는 R3 문서 반례다.
18개 의도적 표기 변이는 모두 검사에 잡혔다. 전체 저장소 suite를 로컬에서 실행하지 않았다.

첫 추가 검사에서 리뷰 하네스가 HOST_ERROR의 `main()` 반환값을 2로 잘못 기대했다.
실제 API는 `int(failed)`인 1을 반환한다. 이 기대값을 바로잡아 성공·실패 네 사례를 모두
재검사했고 통과했다. 초기 두 실패 로그도 보존하며 후보 결함으로 계산하지 않았다.
로그: [기존 회귀](review_352b/related.log), [초기 추가 검사](review_352b/variants.log),
[수정된 하네스·인계 검사](review_352b/corrected.log); 각 JUnit XML을 함께 보존했다.

재실행은 후보를 임시 디렉터리에 archive한 뒤 새 반례 파일을 그 `tests/`에 복사하고,
후보의 `experiments/2026-10-01-calib-heldout-maps/review_fixes/guarded_pytest.py`로 실행한다.
`PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`, 임시 `--basetemp`를 사용했다.
이 runner의 audit hook은 공용 outputs 파일 접근을 차단한다.

물리·렌더·모델 호출, 공용 outputs 접근, 실제 잠금·세션 생성은 하지 않았다.
새 실험 코호트가 없어 TensorBoard/Drive 작업도 없다. 구현·workflow는 변경하지 않고
리뷰 문서·테스트·근거만 리뷰 브랜치에 남겼다. 실제 안전·수집 완료·MEASURED_SIM·criterion B
통과·학생/실물 성공은 승인 범위 밖이다. 동결 criterion B의 v90 미수용은 기존에 공개된 후속 과제다.

사용한 scratch는 `/private/tmp/ugrp-review-352b.gMhh6q`이며 추적 파일 일치를 마지막으로
다시 확인한 뒤 삭제했다([정리 확인](review_352b/cleanup.json)). 기본 체크아웃은 갱신하지 않았다.
