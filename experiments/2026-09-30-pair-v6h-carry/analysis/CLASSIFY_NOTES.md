# v6h 판정기 — 등록 recorder 계약 반영 v6

PR #299 세 번째 독립 검토(`d1c64f85`, 검토 대상 `f32d5fd9`)의 R1–R5와
조정자의 D1–D5 결정을 반영한다. v3의 **새 필드 소급 필수화와 INVALID→FAIL 대치**를
폐기한다. 과거 검증 기록은 그대로 보존한다. 이 수정은 제어기·recorder·물리·등록 봉인을
바꾸지 않으며, 공개 인수 자료의 형식 검증을 새 확증 표본으로 세지 않는다.

4차 검토(`a0903178`, 검토 대상 `58dc07e7`)의 두 P1도 같은 D1–D5 안에서
보완했다. 등록 recorder가 실제로 저장하는 원 좌표·시작 기록·시각 순서를
거리/경계 요약과 대조한다. 없는 계측값을 새로 요구하지 않는다.

후속 검토 `34242f27`의 299g-R1(대상 `3a136bc8`)은 실행 전 entry·제출 예약과
운반 시작 사이의 누락된 순서를 보완한다. 반례 5개의 현재 후보 xfail을 해제하고
공개/합성 자료만으로 수정했다. 이 변경은 블라인드 결과를 보거나 admission을
승인한 기록이 아니다.

## R1 / D1: 실제 생산자와 소비자의 계약

등록 생산자는 #292 `4c6b439f3f7c9a147c901f8b260a1e214d4eb396`의
`scripts/run_pair_stage_probes.py`다. 공개 acceptance 소스
`3c4fe30e2197518443b195392212b0341507ac59`와 바이트가 같으며 파일 SHA-256은
`531c420696ccb4c7d53fbfd17d1b96f3851730fd1f6881951b3c0892edc97c63`이다.
`recorder_v4c6b.py`는 이 fingerprint를 확인하는 읽기 전용 어댑터다.

| 입력 | 판정기에 제공하는 값 | 제공하지 않는 값 |
|---|---|---|
| native manifest `source.source_sha`, `source.execution_tree.files` | 저장된 실행 SHA·파일 해시 | 런타임에 없던 `execution_identity` 객체 |
| 공개 인수 wrapper `source_sha`, `source_fingerprint.files` | 같은 recorder 형식인지 확인 | 봉인·확증 입장 자격 |
| 봉인 `execution_source_sha` 또는 authorization SHA, `v6_contract.source_sha256`, `execution_bundle_id` | 저장 출처와의 일치 검사, 등록 번들 | case에 없던 `source_sha`, `bundle_id`, `prior_id` |
| case `registration_run_id`, `registration` receipt | run·등록 해시·실행 SHA 및 manifest 사본 대조 | 임의 실행이나 새 retry의 승인 |
| trace t·길이 | 관측된 시작/끝·행 수·최대 관측 공백 | 실제 collector 시작/끝을 새로 측정했다는 주장 |
| wall_contact episodes·steps | 에피소드 수·양성 접촉 step 수 | 전체 표본 수·수집 시작/끝·주기·최대 공백 |

측정하지 않은 항목은 **`not_recorded`**다. `steps`는 접촉한 step 수이지 전체
수집 표본 수가 아니다. 저장 당시 `evidence_sha256`도 없으므로 만들거나 요구하지 않는다.
어댑터 출력은 판정 결과의 `recorder_contract`에만 남고 입력 객체·raw를 수정하지 않는다.
기존 synthetic receipt 형식도 명시적으로 지원하되, 그 형식의 해시·coverage 검사는 유지한다.
등록 형식에 추가 receipt/coverage가 실제 존재하면 모순을 묵인하지 않는다.

### 2026-10-01: 블라인드 실행의 별도 run manifest

72건(941×60곳 + 943×첫 12곳)의 기록은 표준 `run_pair_stage_probes`의
상위 드라이버가 아니라 **같은 worker 진입점을 호출하는 thin custom driver**에서
생성됐다. 실행 source는 `4c6b439f3f7c9a147c901f8b260a1e214d4eb396`이다.
커밋 `e78ef70fb5004fed1dfef1866aaf99bbf0bdda41`의
`experiments/2026-10-01-v6h1-confirm-blinded/RUN_MANIFEST.json`과 `plan.json`만
읽고 `tests/fixtures/v6h_blinded_run_metadata/`에 바이트 그대로 복사했다.
블라인드 raw 경로를 열거하거나 결과·trace·명령 본문을 읽지 않았다.

전달 설명의 `v6h1-confirm-blinded.run.v1`과 달리, 커밋된 `RUN_MANIFEST.json`의
실제 schema는 **`v6h1-confirm-blinded.manifest.v1`**, 계획은
`v6h1-confirm-blinded.plan.v1`이다. 이 두 형식만 명시적으로 읽는다.
열지 않은 raw `manifest.json`의 형식을 추측하거나 표준 러너 형식으로 위장하지 않는다.

| 별도 드라이버의 기록 | 소비자 검사/표시 |
|---|---|
| `source.head_sha`, 시작 clean·종료 clean·`source_changed_during_run=false` | 알려진 `4c6b439f…` worker 소스와 무변경 기록 확인 |
| `raw.driver_py_sha256` | `7a35229e…` 고정 driver 식별; worker fingerprint는 기존 `531c4206…` 유지 |
| `raw.plan_json_sha256` | 실제 계획 파일 전체 바이트의 SHA-256 `d627f9cd…`와 대조 |
| `plan.cases` | 모든 작업 설정·case ID·C01…C60×941/C01…C12×943의 72개 식별 목록 |
| `cases[].commands_json_sha256` | 해당 case의 실제 `commands.json` 바이트와 대조; 경로는 case ID에서 제한적으로 계산 |
| `raw.cases_jsonl_sha256` | 케이스 목록 파일의 전체 바이트 해시 대조 |
| `admission=unsealed_stage_probe` | 그대로 유지; 등록 receipt·bundle ID·`registration_run_id`를 새로 만들지 않음 |

`--recorded-run-manifest`와 `--recorded-run-manifest-sha256`를 **함께** 지정해
해당 커밋 메타데이터를 입력한다(원 manifest 해시 `99723de36d20a55f348ea5b25ca203cf1db910dd9a620d3a8c4a17f27407f210`).
입력한 raw 디렉터리의 `plan.json`, `cases.jsonl`, 각 case의
`case.json`·`commands.json`·`result.json`·`eval_only/trace.jsonl`을 검사한다.
메타데이터 안의 절대 raw 경로를 자동으로 따라가지 않는다. 검증 후 재해시에도
외부 manifest와 계획·명령을 포함한다. 이번에는 합성 디렉터리에서만 이 경로를 실행했다.

케이스 설정은 계획과 `labels`를 제외하고 정확히 같아야 한다. 같은 worker가 만든
공개 golden 11건의 **기존 per-case 계약을 그대로** 적용하므로 시작/끝 GT, 거리·시각,
handover, 종료 창, PF, 양성 안전 위반, HOST 처리와 선택 순서는 바꾸지 않는다.
72개 식별 목록 중 기록이 없으면 그 슬롯은 미분류로 남고 60곳의 분모를 줄이지 않는다.
manifest의 `finished`는 파일 완료 메타데이터이며 과제 성공 증거가 아니다.

이 입력 경로는 실행 당시 미봉인 상태를 등록 실행으로 소급 승격하지 않는다.
per-case 증거 검사는 엄격한 모드로 수행하지만 전체 A/B 확증 판정은
`NOT_EVALUABLE`로 유지하고, `--sealed-manifest`와의 혼용은 거부한다.

### 2026-10-01: 별도 드라이버·미봉인 입장 상태의 공개 기록

검토 `REVIEW_299g_astra.md`(커밋 `34242f27`)가 요구한 공개 내용이다.
등록 계획의 `scripts.run_pair_stage_probes --prereg` 대신 별도 드라이버가
worker를 호출한 실행 경로와 등록 시점의 차이를 명시한다. 같은 worker라는
설명만으로 이 차이를 생략하지 않는다. 아래 내용은 **커밋 메타데이터의 진술과
소비자 연결 검사**이며, 드라이버 본문·실제 블라인드 명령 동등성 검증이 아니다.

- 실제 실행 source는 `4c6b439f3f7c9a147c901f8b260a1e214d4eb396`이다.
  드라이버는 표준 runner의 `--prereg` 입장 경로를 거치지 않고 같은 모듈의
  worker를 호출했다고 기록됐다. driver 전체 SHA-256은
  `7a35229e431409904dffec27b5e9572f290cd900f0595c8e0babc5ef92cf3e56`이다.
  로컬 보존 위치는 manifest의 `raw.path`를 고정 참조하되 그 경로를 따라가지
  않았다. 정확한 driver 파일 위치·호출 진입점·표준 runner 대비 역할 차이와
  실제 파일 해시는 조정자가 봉인/개봉 전에 별도 확인·기록해야 한다.
- 실행 당시 **`--prereg` 없음, `prereg_v6h.json` 미봉인,
  계획에서 `registration_run_id` 제외, `unsealed_stage_probe`**였다.
  메타데이터상 실행은 2026-09-30 23:06:29–2026-10-01 00:55:10 KST이고,
  메타데이터 커밋 `e78ef70f`는 2026-10-01 00:56:00 KST다.
  판정기 봉인·개봉의 실제 시각과 선후관계는 후속 prereg/seal 변경 기록에
  남겨야 한다. 이 수정에서 두 절차를 수행하지 않았다. 새 봉인은 과거 실행에
  registration receipt나 사전 등록 이력을 소급 생성하지 않는다. 향후 입장 자격은
  이 실행 경로와 한계를 포함한 별도 결정이며, 분류기 병합과 구분한다.
- 전체 72개 case ID·case별 command hash의 고정 참조는 위 커밋의
  `experiments/2026-10-01-v6h1-confirm-blinded/RUN_MANIFEST.json`이다.
  전체 manifest SHA-256은
  `99723de36d20a55f348ea5b25ca203cf1db910dd9a620d3a8c4a17f27407f210`,
  같은 위치 `plan.json` 전체 SHA-256은
  `d627f9cda827d07bab5b86c04f9e45ffceb474e97a8dda566c4956372d5fb026`이다.
  주 시드 941×60곳·보조 943×첫 12곳·재실행 0은 기록된 메타데이터이며,
  허용된 HOST 재시도 규칙을 실제로 사용했다는 뜻이 아니다. 누락은 미분류,
  모순·계획 밖 기록은 INVALID로 처리하고 60곳/72슬롯 분모를 유지한다.
- 기록된 설정은 b-v6h1/axial lag ON, teacher-held 진입의 chain L0–L1 종료,
  SIM, weld OFF, 모델 호출 0, floor_light_v1, PF/contact ON,
  800 SIM초/1500 wall초 예산, workers 4/OMP 1과 plan의 개별 설정이다.
  이 경로의 검사를 E2E 또는 실물 성공으로 확대하지 않는다.
- 최종 classifier/adapter의 봉인 SHA·파일 hash와 고정 D1–D5 규칙을
  후속 prereg/seal에 연결해야 한다. 이번 수정의 코드 hash·공개 acceptance·
  과거 탐색 대조는 `review_299g_fix_validation/`에 별도로 기록한다.
  이 수정·검토에 블라인드 결과는 사용하지 않았으며, 공개 11건·과거 308건의
  재분류는 새로운 확증 자료가 아니다.

이 공개 기록은 조정자의 prereg/seal 변경 기록을 대신하지 않는다. 봉인·개봉과
미봉인 실행의 향후 입장 자격 결정은 이번 PR 수정 범위 밖의 남은 일이다.
판정기 정의의 봉인과 실행의 사전 등록은 별개다. 기존 표준 러너의 등록 입력 경로는 유지한다.
새 테스트는 두 메타데이터 fixture와 새로 생성한 가짜 per-case 기록만 사용한다.
공개 11건·과거 308건 대조와 실제 블라인드 코호트 판정은 별도 작업이다.

등록 builder의 `ugrp.zone_pair_v6h_confirmatory.DRAFT.v1` + `sealed=true`를
별도로 읽는다. `runs/cases`의 C01…C60×941 + C01…C12×943, 등록 payload 해시,
배치 파일 해시와 실행 source contract를 확인한다. 기존 synthetic 평가 봉인
`ugrp.v6h_confirmatory.v1`의 이름으로 덮어쓰지 않는다. 실제 봉인 파일은 열거나 바꾸지 않았다.

`verify_recorder_contract.py`가 허용된 공개 acceptance 11건의 전체 원본을 직접
소비하고, 원본 36파일 해시를 리뷰의 고정 감사 목록 및 검사 후 해시와 대조한다.
기대값은 조정자가 정한 **lag-on 10 PASS_CLEAN + lag-off sanity 1 FAIL**로 고정했다.
`tests/fixtures/v6h_recorder_v4c6b/`는 필요한 필드만 복사한 CI용 projection이다.
시각·값을 반올림하거나 새 필드를 채우지 않으며 전체 원본과 projection의 판정 객체가
동일한지도 확인한다. fixture 자동 갱신은 없고 기존 디렉터리 덮어쓰기도 거부한다.

형식/출처 연결에 실패하면 `state=INVALID`, `class=null`,
`classification_status=UNCLASSIFIABLE`, `UNCLASSIFIABLE_RECORDER_FORMAT` 사유다.
물리적 과제 실패로 세지 않는다. 알려진 하드 위반은 이 경우에도 우선 보존한다.

## R2 / D2: HOST_ERROR와 누락의 집계

등록 PREREG_DRAFT(#285 167–168, 191–193; #292 148–150)의 규칙을 따른다.
HOST_ERROR·ENOSPC·주 시드 누락·증거 INVALID는 **미분류**로 남는다.
`class=null`, 사유, 원 시도와 파일 해시를 보존하고 완료/성공 선언을 막는다.
60개 입장 분모는 유지하며 FAIL 개수에는 대치하지 않는다. 주 시드에 미분류가 있으면
Wilson 구간도 출력하지 않는다. 주 시드 성공과 보조 943 성공은 합치지 않는다.

실제 `result.host_error`를 HOST 신호로 읽는다. 실제 except 경로는 termination을
남기지 않을 수 있고, cleanup 오류에서는 STUDY_LAYER_DONE이 남을 수도 있다.
row의 HOST 표지와 result의 HOST 기록이 일치하면 이런 형식을 허용한다.
완전한 관측창에서 알려진 과제 실패·하드 위반이 없는 HOST 시도만 `HOST_SAFE` 사건으로
재시도 선택이 가능하다. 같은 배치·시드·설정의 재실행은 최대 1회다.
불완전한 원본의 재실행 자체를 금지하는 것은 아니지만, 확인할 수 없는 원본 안전 증거를
재실행의 정상값으로 대체해 전체 성공을 선언하지 않는다.

EOF의 미해결 HOST는 `state=INVALID`, `class=null`이다. 전이표는 완전하며
FAIL/HARD/INVALID는 후속 PASS로 복구되지 않는다. 모든 시도의 양성 하드 위반은
선택 여부·손상 여부와 관계없이 합집합으로 남는다.

| 현재 상태 | PASS | FAIL | HARD | INVALID | HOST_SAFE |
|---|---|---|---|---|---|
| NEW | PASS | FAIL | HARD | INVALID | RETRY |
| RETRY | PASS | FAIL | HARD | INVALID | INVALID |
| PASS | INVALID | INVALID | HARD | INVALID | INVALID |
| FAIL | FAIL | FAIL | HARD | FAIL | FAIL |
| INVALID | INVALID | INVALID | HARD | INVALID | INVALID |
| HARD | HARD | HARD | HARD | HARD | HARD |

`INVALID`는 실패 class가 아니라 증거 상태다. 성공 요건을 평가할 수 없으면
`full_verdict=NOT_EVALUABLE`; 관측된 하드 위반이나 평가 가능한 기준 불충족은
`FAIL_A_B_SAFETY`다. 어느 쪽도 성공 선언을 허용하지 않는다.

## R3 / D3: 관측된 과제 실패의 보존

HOST 표지를 검사하기 전에 완료 끝점·controller 실패와 이미 도달한 handover를 검사한다.
L0 끝→L1 시작 창이 실제 trace로 덮인 경우 rest_release/regrasp_lift 실패를 확정한다.
L1 시작 뒤 HOST가 발생해 L1 끝점이 없어도 이미 도달한 handover 판정은 유지한다.
`restaging_between_legs=true`도 양성 실패 증거다. 이 뒤 cleanup HOST나 정상 retry가
와도 성공으로 바뀌지 않는다. HOST 중단으로 아직 도달하지 않은 미래 handover와,
trace가 빠져 실패를 확정할 수 없는 창은 실패로 추정하지 않는다.

## R4 / D4: source→derived 모순 검사

- result.host_error가 있는데 row가 정상이라고 하면 INVALID다. row HOST + 실제
  result HOST + 이전 정상 termination은 recorder의 합법적인 cleanup 형태다.
- `pair_chain_probe.chain_legs()`는 나중에 도착한 robot endpoint의 GT를 반올림 없이
  row에 복사한다. 그 동일 시각의 `lift_m`, `tilt_deg`, `jaws`와 derived leg 값을
  대조한다. 수치 직렬화 허용오차는 1e-9이며 0.05초 trace 간격과 혼동하지 않는다.
  두 source 끝점이 있으면 row 끝 시각도 더 늦은 source 시각과 같아야 한다.
- 다른 시각의 robot GT 값은 같은 순간의 값처럼 비교하지 않는다. 안전 관측의
  합집합에는 계속 포함한다. SHA 일치는 논리적 일치를 대신하지 않는다.
- 등록 형식의 각 recorded leg에는 r1/r2의 `leg_start`와 `leg_end` 및 유한한
  원 `beam_xyz`가 모두 있어야 한다. 양쪽 시작·끝 기록 중 각각 더 늦은 시각을
  선택하며 동시각은 producer처럼 정렬된 로봇 ID 순서로 고른다. XY 원 좌표와
  case의 정적 route에서 `end_error_m`, `leg_error_m`, `planned_length_m`,
  `travel_m`, `step_error_m`, `along_error_m`, `cross_track_m`를 재계산한다.
  `pair_chain_probe`의 `math.dist`/`math.hypot` 식과 반올림 없는 값을 사용한다.
  요약과 1e-9 m보다 큰 차이 또는 필수 수치 누락은 INVALID다. 100 mm 과제
  판정 문턱은 그대로이며 요약값을 덮어쓰거나 모순을 과제 FAIL로 대치하지 않는다.

## R5 / D5: 관측창과 coverage의 자체 일관성

trace 시각은 음수가 아니며 엄격 증가, 공백 ≤0.051 SIM초다.
제공된 coverage는 end>start, count·period·자기 창 길이·최대 공백이 일치해야 한다.
wall 창을 evaluation 창 길이만으로 검사하지 않는다.
`include_teacher=true`일 때 저장된 `teacher.gt_after_lift.t`와 `gt_at_entry.t`는
실제 기록창 안에 있어야 한다. 등록 형식에는 관측된 trace 창을 사용한다.
원 recorder에 없는 전체 접촉 coverage를 지어 넣어 통과시키지 않는다.

등록 형식에서는 로봇별 `timeline` 배열 순서와 leg 번호에 따른 시작→끝 경계,
교사→entry→stop→end GT 시각을 각각 검사한다. 각 스트림은 음수가 없고
비감소해야 한다. raw 시작/끝은 그 로봇 timeline의 첫 해당 상태와 연결하고,
요약 시작/끝은 양쪽 raw의 최댓값과 연결한다. 같은 경계의 `gt.t`/`sim_s`와
원 stop/row stop의 허용오차는 1e-9초다. snapshot은 관측 trace 창에서
한 표본 간격(0.051초) 이내, termination이 있으면 그 시각+1e-9초 이내여야 한다.
이 차이는 실제 cleanup GT가 마지막 trace보다 약 0.05초 늦게 기록되기 때문이다.
로봇 간 비동기 시각, 동시각 상태 전이, robot/경계 dict와 요약 leg 배열 순서
변경은 허용한다. 기존 trace의 엄격 증가·공백 조건은 바꾸지 않는다.
HOST except 경로의 termination 부재와 아직 시작하지 않은 leg도 계속 허용한다.

등록 recorder의 `gt_at_entry.t`와 `result.submit_t`/`row.submit_t`도 각 로봇의
**원 `chain_raw[robot].leg_start[*].sim_s` 중 최초 시각보다 엄격히 앞서야** 한다.
교사 시각 ≤ entry < submit < 각 로봇의 첫 carry 시작이며, entry/submit이 시작과
같아도 INVALID/null이다. `submit_t`는 producer가 저장한 SIM 제출 예약 시각이며
별도의 명령 접수·완료 시각을 만들어 넣지 않는다. row/result 제출 시각의 일치에는
기존 직렬화 허용오차 1e-9초를 쓰지만 선후관계에는 그 오차를 쓰지 않는다.
두 제출 시각 사본의 차이가 1e-9초 이내여도 어느 하나가 entry/carry 경계를
넘거나 경계와 같으면 INVALID다.
한 로봇이 먼저 시작했는데 더 늦은 로봇의 요약 시작 시각으로 위반이 가려지는 것도
거부한다. carry가 기록된 경우 entry/submit은 유한한 필수 시각이고, 아직 carry를
시작하지 못한 HOST 부분 기록에는 미래 제출·경계를 소급 요구하지 않는다.
양성 하드 위반은 이 모순이 있어도 FAIL_HARD_LIMIT 우선순위를 유지한다.

## 검증과 범위

- 3차 리뷰 27개 시험에서 13개 strict-xfail을 모두 해제한다. R1의 네 시험은
  없는 필드 생성을 요구하는 대신 실제 producer 형식을 소비하도록 뒤집는다.
- 이전 리뷰 반례와 10,000개 생성 사례를 유지한다. 바꾼 기대는 D2의 INVALID→FAIL
  대치 제거와 `NOT_EVALUABLE` 구분뿐이며, 안전/실패의 성공 승격 금지는 유지한다.
  분모 불변식은 `분류된 수 + 미분류 수 = 입장 수`로 검사한다.
- `check_299c_mutations.py`는 소스 파일을 쓰지 않고 메모리에서 D1–D5 guard를
  제거한다. 정상 witness 통과 후 mutant의 AssertionError만 제거 검출로 센다.
  import 오류나 예상 밖 예외를 검출 성공으로 세지 않는다.
- 공개 16코호트 308건 및 부분 tX1은 `revalidate_published.py`로 별도 대조한다.
  cA/cB 각 24/24 유지와 모든 raw 입력 해시를 확인한다. tX1의 HOST 두 건은 다시
  미분류로 돌아가며, 완료 308건과 합치지 않는다.
- 최종 로그·해시·명령은 `review_299c_fix_validation/`에 남긴다. blinded confirmatory
  raw의 열거/읽기, 물리·SIM step·렌더·모델 호출은 하지 않는다. 새 실험 결과가 아닌
  오프라인 판정기 회귀이므로 기존 TensorBoard snapshot을 보존하고 재변환하지 않는다.
  원 raw는 로컬이며 테스트 fixture의 GitHub 보존을 raw 원격 백업이라고 표현하지 않는다.
- 4차 검토의 10개 strict-xfail을 모두 제거했다. 같은 파일에 거리 7항목,
  raw 좌표 누락/손상, 시간 역전, 비동기/동시각 양성 대조 등을 더해 57개를
  정상 offline CI에 포함했다. `check_299d_mutations.py`의 거리·시각·start
  어댑터 계약 삭제 5개와 기존 D1–D5 삭제 7개를 각각 검사한다. start 어댑터
  mutation은 어댑터 자체의 필수 필드 계약을 검사하고, 나머지는 최종 판정으로
  검사한다. 결과·명령·파일 해시는 `review_299d_fix_validation/`에 남긴다.

## 참고 자료

- [Pact: How Pact works](https://docs.pact.io/getting_started/how_pact_works),
  [provider verification](https://docs.pact.io/implementation_guides/javascript/docs/provider).
  소비자가 요구하는 계약을 실제 생산자의 출력에 대해 검증하는 원칙을 적용했다.
  이 파일 기반 검증은 Pact 방식의 contract test이며 Pact 서버/브로커를 도입하지 않았다.
- [ApprovalTests: approval testing / golden master](https://approvaltestscpp.readthedocs.io/en/latest/generated_docs/ApprovalTestingConcept.html).
  고정한 입력·검토된 기대 결과의 변화 감지에 적용했다. 여기서는 조정자가 지정한
  11건의 기대 판정과 공개 원본 해시가 golden 기준이며 성공률을 새로 추정하지 않는다.
- [ICH E9(R1), 2019-11-20 final](https://database.ich.org/sites/default/files/E9-R1_Step4_Guideline_2019_1203.pdf), A.1/A.3/A.5.
  중간 사건과 누락 자료, 목표 평가량을 구분하고 사전 정의된 처리 전략을 지키는 원칙을
  참조했다. HOST_ERROR 처리의 실제 규칙은 이 프로젝트 PREREG_DRAFT다.
  ICH가 로봇 실험의 특정 미분류/실패 대치를 요구한다고 주장하지 않는다.
