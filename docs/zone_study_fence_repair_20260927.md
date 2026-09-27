# PR #194 실제 PREFLIGHT 펜스 회귀 수정 기록

작업 기준: `kiro/zone-study-core`, HEAD `1adfeff01884b308352918a4488c31258adaf478`.
변경은 미커밋이다. 실모델 호출·물리 실행·실제 budget 이관은 하지 않았다.
코디네이터가 main/열린 PR의 최댓값 v62를 확인해 지정한 v63을 사용했다.
이 환경에서는 `git fetch origin`이 공용 `.git` 쓰기 권한으로, `gh pr list`가 네트워크로
막혔다. GitHub 연결 도구의 PR 조회도 저장소 이동(301)으로 실패해 원격 상태는 갱신하지 않았다.

## 원본과 재현

- 읽기 전용 원본: `/Users/changmin/projects/ugrp/outputs/zone-study-adapter-pilot-r10/preflight-01/`.
  작업 전후 파일 6개의 경로·SHA-256이 모두 일치한다.
- wire 응답: `no_comm/wire/000001-call-0001-r1-response.json`, 568 bytes,
  SHA-256 `c54262648d695a7402b9981808d95e688b6ab68f64bae80c01b3ba3bb08ef359`.
  `tests/fixtures/zone_study_preflight_r10/`에 바이트 동일 응답과 출처를 보존했다.
- 수정 전: 기존 completion gate의 `json.loads(TEXT)`가 실패하고, 같은 원문을 넣은
  네 조건의 adapter 회귀 테스트도 모두 실패했다(4 failed, fixture 검증 1 passed).
- 수정 후: 기존 `three_robot_plan.parse` 재사용으로 네 조건 모두 채택한다.
  request_id·조건별 스키마·종료 이유 검사를 유지한다. 펜스 제거 bool이 호출 기록부터
  scheduler·archive·ledger·budget까지 이어지며 조건별/전체 집계에 반영된다.
  정확한 wire bytes와 펜스 포함 출력 토큰 비용은 보존된다.
- 반례: 밖의 설명, 복수/중첩/불완전 펜스, 잘린/연속 JSON, 다른 언어/대문자 표시,
  객체가 아닌 JSON을 거절한다. `length`의 유효한 fenced JSON도 채택하지 않는다.

## 실행 번들과 예산

- v62 JSON SHA-256: `6601192a6da7ac018dd3a7104364065bb9afb9dce0d61e79021f824648b07f69`.
  바이트 그대로 보존하고 은퇴 목록에 추가했다.
- v63 JSON SHA-256: `ef4fe391e57c145b6625ba052e651542745bfcb6244d8e25736827ee8122aa01`.
  소스 closure 174개를 고정했다. 물리·카메라·명령 effective 설정은 v62와 같다.
  `experimental_unqualified`이며 과거 성공을 승계하지 않는다.
- 실제 budget은 SQLite `mode=ro`로만 확인했다. 2 attempts/235,408 tokens 예약 차감,
  provider 보고 total 10,622 tokens, 기존 run은 `failed`다.
  원래 봉인 identity SHA-256은
  `0927ccba1cc2943205227a297227cb524845ede1dfc7688d18e7817ad294d45d`다.
- 실제 봉인과 새 소스를 읽기 전용 비교해 소스 이외 설정·비용 정책 및 bundle effective가
  같음을 확인했다. 직접 재개는 소스 불일치로 거절한다. 새 `--migrate-source`는 같은 파일에
  이전 봉인·신규 소스·사유·시각·SQL 원본 해시를 추가하고 기존 지출·한도를 보존한다.
  실패·미확인 예약도 환불하지 않는다. 구체적 명령과 receipt 복구는
  [파일럿 문서](zone_study_pilot.md#v63-단일-json-펜스와-예산-소스-이관)에 있다.
- 실제 원본은 `reconciliation_complete=false`다. 이관이 과금 대사를 대신하지 않는다.
  코디네이터의 소스 검토·커밋·실제 이관, 이전 요청의 terminal upstream 증거,
  새 소스의 4조건 PREFLIGHT가 남아 있다.

## 검증

모든 pytest 실행에 `OMP_NUM_THREADS=1`, `--basetemp=./.pytest_tmp`를 사용했다.

```sh
OMP_NUM_THREADS=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest \
  tests/test_zone_study_fenced_reply.py tests/test_zone_pilot_source_migration.py \
  tests/test_zone_study_review_r8.py tests/test_zone_study_review_r9.py \
  tests/test_zone_study_review_r10.py tests/test_zone_study_protocol.py \
  tests/test_zone_study_review_r7_transport.py tests/test_rgb_execution_bundle.py \
  tests/test_three_robot_plan.py tests/test_zone_dialogue_ko.py \
  --basetemp=./.pytest_tmp -q
# 472 passed

OMP_NUM_THREADS=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest \
  tests/test_zone_study_eval.py tests/test_zone_pilot_source_migration.py \
  --basetemp=./.pytest_tmp -q
# 88 passed (위 이관 테스트 17개 재검증 포함; 고유 테스트 총 543개)
```

같은 DB 재개 테스트는 최초 실패 1호출과 새 소스 4호출의 총 10 attempts 예약을 보존한다.
주입 wire와 합성 terminal 근거로 실행했으며 실제 provider/물리 검증이 아니다.
소진 한도 유지, 미해결 청구 재개 차단, 기존 preflight 거절, stale 소스 쓰기 차단,
원자적 롤백, DB 커밋 뒤 receipt 저장 실패와 `--reconcile-only` 감사 회수도 통과했다.

`verify-current --id rgb-standard-dispatch-v63`,
`verify-registry --base 1adfeff01884b308352918a4488c31258adaf478`, `git diff --check` 통과.
새 테스트 두 파일은 `scripts/run_ci_tests.py`에 등록하고 실제 선택 목록 포함을 확인했다.
검사 후 `.pytest_tmp` 제거를 확인했다. 저장소 HEAD는 작업 시작 값 그대로다.
