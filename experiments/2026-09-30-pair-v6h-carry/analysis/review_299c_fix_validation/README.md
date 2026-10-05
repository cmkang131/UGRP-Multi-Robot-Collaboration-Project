# PR #299 R1–R5 수정 검증

2026-10-01 KST. 검토 대상 `f32d5fd9`, 3차 검토 `d1c64f85`, 먼저 병합한
main `6a57435e`(#328), 검증 당시 기반 HEAD `e85e00a213c52b06655a65162c80a55bc0684c3a`.
수정 소스·테스트·fixture의 정확한 SHA-256은 `provenance.json`에 기록했다.
최종 묶음 전체가 끝날 때까지 코드/테스트를 고정했고 전후 해시가 모두 같다.
최종 수정 commit은 이 기록을 포함하는 commit이며 PR 댓글에서 전체 SHA를 연결한다.

## 결과

| 검사 | 확인 결과 |
|---|---|
| 관련 테스트 10파일 | 386 passed, failed/skip/xfail 0 (648.95초; 성능 측정 아님) |
| 생성 속성검사 | 10,000건, seed 202609300299, 사례별 5개 불변식 |
| 공개 producer 계약 | 11건 전체 원본: lag-on 10 PASS_CLEAN, lag-off sanity 1 FAIL |
| 원본 보존 | acceptance 36파일의 고정 감사/검사 전/후 SHA-256 일치 |
| projection 계약 | 전체 원본과 CI용 필드 projection의 판정 객체 일치 |
| D1–D5 mutation | 정상 witness 통과 후 guard 삭제 7개 모두 AssertionError로 검출 |
| 공개 완료 코호트 | 16코호트 308건, 공개 기대값 전부 일치; cA/cB 각각 24/24 |
| 부분 tX1 | 14건 중 PASS 12, HOST 미분류 2; 배치 7, 분류된 주 시드 6 |
| 과거 원본 | 17코호트 cases.jsonl 해시 불변; 전체 읽은 입력 해시는 대조 기록에 포함 |
| CI fixture preflight | frozen fixture 3개 확인 |

3차 리뷰의 strict-xfail 13건을 제거했다. R1 네 건은 실제 producer가 기록하지 않은
필드를 요구하지 않고 공개 출력 11건을 소비하도록 전환했다. 기존 안전/실패 반례를
유지하며, D2에 반하는 INVALID→FAIL/완료 판정 기대값과 분모 불변식만 새 계약에 맞췄다.
기존 27건 외에 L1 도중 HOST가 나도 이미 도달한 handover 실패를 보존하는 3건을 추가했다.
등록 builder schema와 native 단일 실행 형식은 synthetic 입장 명부와 공개 worker 형식으로
검사했다. 72슬롯 중 자료 없는 71슬롯은 그대로 미분류로 남는다.

## 재현 및 기록

`provenance.json`의 `commands`에 정확한 Python·명령·종료 코드가 있다.
`related_tests.txt`, `properties.json`, `acceptance.json`, `mutations.json`,
`published_count_checks.json`은 최종 실행의 바이트 그대로 복사했다.
`artifact_index.json`은 원본 위치·파일 해시·개발 중 실패/중단 실행의 상태를 연결한다.
개발 중 첫 묶음은 D2 기대값 등의 실패를 확인했고 두 긴 실행은 최종 코드 수정 때문에
중단했다. 이 실행들은 통과로 세지 않았고 원 로그는 로컬에 보존했다.
최종 실행 원본과 17개 전체 판정 JSON은 `/Users/changmin/projects/ugrp/outputs/v6h-classifier-299c-fix/final-v4`에 있다.

CI fixture 누락은 기존 frozen 파일 3개를 sparse checkout에 포함해 해결했다.
`.github/workflows`는 별도 수정하지 않았다. 정상 push 이후 GitHub CI의 정확한
head·상태는 PR 댓글에서 별도로 보고한다. 이 기록은 로컬 검사 통과 근거다.

## 범위

오프라인 JSON/수치 회귀와 허용된 공개 기록 대조다. blinded confirmatory raw와
실제 봉인은 열거·조회하지 않았다. 물리·렌더·모델 실행은 없고 새 확증 성공률을 주장하지 않는다.
새 실험을 만들거나 새 결과를 회수한 것이 아니므로 TensorBoard를 재변환/재개방하지 않았고
기존 snapshot을 보존했다. raw 원본은 로컬이며 GitHub fixture 보존은 전체 raw 백업이 아니다.
PR 병합은 하지 않는다. 설계/참고 자료는 [CLASSIFY_NOTES.md](../CLASSIFY_NOTES.md)를 따른다.
