판정: **MERGE** — 요청된 재검토 범위에서 R3 / P2를 닫는다. 새 P0/P1/P2 지적과
소스 수정 요구는 없다. 실제 병합은 필수 CI 통과와 draft 해제 이후이며, 이 검토에서는 병합하지 않았다.

대상은 `f476e61ff0bbfc264533aa01248314601a705118`이다. 이전
[REVIEW_352b.md](REVIEW_352b.md)의 `3a6070b30dd3e2608b7ffb6cf6ad95d460452a6c`와
[작성자 답변](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/352#issuecomment-5949492623)을 확인했다.
`git fetch origin`, 지정 구간 diff, 후보의 독립 `git archive` 추출본으로 한 번에 검증했다.

| 확인 항목 | 독립 재검증 결과 |
|---|---|
| R3 문서 반례 2개 | 이전 테스트 본문을 수정하지 않고 현재 후보 SHA로 호출했다. 과거 strict xfail 표시는 적용하지 않았고 두 지도 모두 통과했다. `PHYSICS_HANDOFF.md:67–82`는 이제 `scripts.run_final_pair_heldout`을 안내하며, 완전한 직접 계획 명령도 각각 v90을 반환하고 output을 만들지 않는다. |
| 두 표준 수집 명령 | `PHYSICS_HANDOFF.md:26–65`의 bash 구문과 실제 parser를 검사했다. 각 명령은 `agent_lock acquire`의 owner·branch·PID·10분, `ugrp_session`, `sim_cli workflow run zone-final-pair-heldout-v90`, `--check calibration-unloaded`, 지도 ID, `--seed 911`, expected source SHA, `--execute`, `--lock-owner codex`, 지도별 새 output을 포함한다. workflow 3.2.0 → heldout runner 연결 및 fake backend의 plan/bundle/사례·전체 result와 해시가 통과했다. |
| 거부 경계 | 두 지도 × fine/loaded × 계획/execute의 8개 경우가 host 판정·backend·output 생성 전에 거부됐다. 기존 CLI·bundle 거부 검사도 통과했다. 이미 존재하는 output을 준 두 경우는 표준 workflow 계획이 거부하며 기존 파일을 보존했다. |
| v88 보존 | 세 profile의 plan/bundle 전체 바이트 해시 6개가 원래 독립 검토의 고정 기대값과 일치했다. 각 bundle의 소스 239개는 실제 SHA-256과 `fa2119ca`, `6b1ba45b`, `f476e61f`의 Git blob 모두 일치한다. |
| 동결 파일·번호 | 이전 검토의 고정 파일 12개와 보정 실험 디렉터리 29개 파일이 그대로다. criterion B·validator 변경 없음. configs/harness/sim/scripts/maps/calibration 전체 diff가 비었으며 v90/3.2.0 및 기존 번들 번호도 그대로다. v90 두 bundle의 소스 247/248개도 세 SHA와 동일하다. |

`fa2119ca6926a66a317a455701cbc389d7d3fb58..6b1ba45bb4ded61161cab3891925526ff5c42b12`는
인계문, `tests/test_review_352.py`, `handoff_fix/` 검증 기록의 **11개 파일**만 바꾼다.
실제 수집 shell 블록과 기존 v88 이하 인계문은 바이트가 같다. `.github/workflows` 변경은 없다.
추가된 직접 계획 안내·회귀 테스트·검증 스크립트를 읽고 새 결함을 발견하지 않았다.

`6b1ba45b..f476e61f`는 main의 #354 병합이다. `.github/workflows/tests.yml`의
shard 제한 **15 → 25분**과 관련 주석, `CONTRIBUTING.md`의 같은 설명만 바뀐다.
검토자가 workflow를 수정한 것은 아니다. 후보 추적 파일 **9,128개**를 Git blob과 대조했고,
검사 종료 후에도 다시 일치했다. [보존 검사](review_352c/verify_static.py),
[해시·diff 범위](review_352c/static.json).

최종 검사는 **219 passed / 0 failed / 0 skipped / 0 xfail**이다.
기존 관련 검사 207개와 이번 재검토 검사 12개이며 전체 저장소 suite를 실행한 것은 아니다.
[로그](review_352c/related.log), [JUnit](review_352c/related.xml),
[검증 집계·파일 해시](review_352c/verification.json).

재실행할 때 후보를 scratch에 `git archive`로 추출하고 이 리뷰 브랜치의
`tests/test_review_352b.py`, `tests/test_review_352c.py`를 복사한다.
Python 3.12.13의 기존 `.venv-sim-worker-mac`과 후보의
`experiments/2026-10-01-calib-heldout-maps/review_fixes/guarded_pytest.py`를 사용했다.
`PYTHONDONTWRITEBYTECODE=1`, `-q -p no:cacheprovider`, scratch 내부 `--basetemp`로
집계 JSON에 적힌 7개 테스트 모듈/선택 항목을 실행한다. audit hook은 공용 outputs 접근을 차단했다.

CI는 [Actions 37014058679](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/37014058679)에서
확인 시점 **27 SUCCESS / 5 진행 중 / 관측된 실패 0**이었다. 필수 `offline-regressions`의
최종 통과는 아직 확인하지 못했다. PR은 draft이고 GitHub 표시는 BLOCKED다.
따라서 **MERGE는 이번 소스 재검토 판정이며 지금 병합 가능하다는 선언이 아니다.**
[조회 시각과 전체 check 상태](review_352c/ci.json).

fake host는 실제 source/disk/lock 판정을 대체했다. 위 통과는 명령·등록·저장 경로의 오프라인
검증이며 실제 호스트의 잠금 획득이나 물리 수집 완료를 입증하지 않는다. 물리·렌더·모델 호출,
실제 잠금·세션 생성, 공용 outputs 접근은 없었다. criterion B의 v90 미수용은 인계문에
명시된 기존 후속 과제이며 이번 수정으로 범위를 넓히지 않는다. 새 실험 코호트가 없어
TensorBoard/Drive 작업도 없다.

scratch `/private/tmp/ugrp-review-352c.rkt_wyeb`는 검사와 추적 파일 재대조가 끝난 뒤
삭제했다([정리 확인](review_352c/cleanup.json)). 리뷰 문서·테스트·근거만
`codex/review-352`에 남겼다. 후보 구현·workflow·기본 체크아웃은 변경하지 않았고 병합하지 않았다.
