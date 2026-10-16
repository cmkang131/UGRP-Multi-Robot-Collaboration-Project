# PR #299 / 299g-R1 수정 검증 — 2026-10-01

검토 `34242f27`의 시간 선후관계 P1을 공개·합성 기록만으로 수정했다.
시작 후보는 `3a136bc821f912af893f414ea2224db8742b880e`이며, 사용자 지시에 따라
`origin/main` `26bfcf8e2977e85132845d7704fe1070f277dd13`을 먼저 병합했다
(병합 커밋 `3c01a0a685922de435358633b49ed924bbcf2bdc`).
최종 수정 파일 hash는 `verification.json`에 기록한다. 이 기록을 포함하는 커밋이
수정 후보이며, PR 병합·판정기 봉인·블라인드 개봉을 수행했다는 뜻이 아니다.

## 원인과 변경

stage snapshot끼리와 로봇별 timeline끼리만 순서를 검사해 두 스트림 사이의
모순을 놓쳤다. 등록 recorder의 실제 필드로 `teacher.gt_after_lift.t ≤
gt_at_entry.t < submit_t < 각 로봇의 첫 carry 시작`을 검사한다.
각 로봇의 원 `chain_raw` 시작을 사용하며, 더 늦은 로봇의 derived 시작으로
먼저 시작한 로봇의 위반이 가려지지 않는다. 시작과 같아도 INVALID/null이다.
row/result의 제출 예약 시각은 모두 유한해야 하고 복사값은 1e-9초 이내로
일치해야 한다. 복사값 허용오차를 선후관계의 허용오차로 사용하지 않는다.

carry 전 HOST 부분 기록에는 미래 제출 시각을 요구하지 않으며 양성 하드
위반은 FAIL_HARD_LIMIT 우선순위를 유지한다. 실제 명령 접수 시각이나 없는
등록 receipt를 생성하지 않는다. `CLASSIFY_NOTES.md`에는 별도 드라이버,
실행 당시 미봉인 상태와 조정자가 prereg/seal에 연결할 남은 기록을 공개했다.

`tests/test_classify_review_299g.py`는 리뷰 커밋의 테스트를 가져와 현재 반례
5개에서만 xfail을 제거했고 직접 거부 사유까지 확인한다. 과거 `58dc07e7`
코드의 10개 strict xfail은 역사적 음성 대조로 유지한다. 실제 producer의
제출 필드를 표현하도록 **합성** run-manifest builder에 `.2` 예약 시각을
추가했다. 공개 raw·고정 projection·커밋 메타데이터는 수정하지 않았다.
새 리뷰 테스트를 기존 offline CI 목록에 추가했으며 workflow는 바꾸지 않았다.

## 검증

| 검사 | 확인 결과 | 기록 |
|---|---|---|
| 수정 전 현재 P1 | 5개 모두 판정 AssertionError | `before.txt` |
| 첫 관련 15파일 전체 | 592 passed / 10 historical xfailed; 10,000개 생성 검사 포함 | `related_tests.txt`, `related_command.json` |
| 최종 경계 보강 뒤 관련 15파일 재검사 | 595 passed / 10 historical xfailed / 1 deselected | `final_related_tests.txt`, `final_related_command.json` |
| 새 mutation | 6/6 검출, 생존 0 | `mutations_299g_final.json` |
| 이전 mutation | 299d 5/5, D1–D5 7/7 검출 | `mutations_299d_final.json`, `mutations_299c_final.json` |
| 공개 golden | 11/11 판정 유지: lag-on 10 PASS_CLEAN, lag-off 1 FAIL | `golden_final.json` |
| 과거 완료 자료 | 16코호트 308/308 개별 판정·집계 유지; cA/cB 각 24/24 | `published_count_checks_final.json` |
| 별도 부분 tX1 | 12 PASS / HOST 미분류 2 유지 | `published_summary_final.json` |
| 입력 보존 | 공개 acceptance 36파일과 과거 입력·분석 697파일 해시 동일 | `golden_final.json`, `published_summary_final.json` |

전체 묶음을 실행하는 중 제출 시각 두 사본의 미세한 차이가 strict 경계를
넘는 경우까지 보강했다. 그 뒤 모든 관련 검사를 다시 실행하되, 이미 진행
중이던 `test_ten_thousand_generated_evidence_chains` 하나만 중복 실행에서
제외했다. 이 검사는 recorder_context를 전달하지 않으므로 변경 함수에
진입하지 않는다. 함수별 AST 대조에서 마지막 변경은
`validate_recorder_chronology` 하나뿐이다(`final_scope_check.json`).
진행 중이던 전체 검사도 최종적으로 성공했으며 실패·skip은 없다.
재검사에는 최종 299g 테스트 52개 정상 통과와 역사적 xfail 10개가 포함된다.

최종 코드의 공개 golden·308건 재분류·mutation 18개를 다시 실행했고,
관련 명령/종료 코드는 `final_validation_commands.json`에 보존했다.
mutation은 메모리에서만 guard를 바꿔 정상 witness 통과와 판정 assertion의
실패를 대조한다. import/예상 밖 예외를 검출 성공으로 세지 않는다.

## 범위와 보존

모든 실행은 기존 Mac Python 환경의 로컬 오프라인 검사이며 host lock을
획득하지 않았다. 물리·렌더·모델 실행, 블라인드 raw의 열거/읽기, `.github/workflows`
편집, Drive 작업, PR 병합은 없다. 추출용 임시 디렉터리를 만들지 않았다.
새 실험 결과가 아니므로 TensorBoard 재변환·viewer 실행 없이 기존 snapshot을
보존했다. `published-final/`의 상세 재분류는
`/Users/changmin/projects/ugrp/outputs/review-299g-fix-20261001/` 아래 로컬에
보존하며 이 폴더의 작은 결과/해시만 Git에 추가한다. raw 전체의 원격 백업을
주장하지 않는다. 처음 수행한 검사와 중간 결과도 그대로 남겼다.

남은 일은 최종 수정 후보의 독립 재검토와 정상 PR CI 확인, 그리고 조정자의
실행 경로·봉인/개봉 순서·미봉인 입장 자격 기록이다. 이번 작업에서 확증 입장
승인이나 실제 블라인드 결과의 판정을 수행하지 않았다.
