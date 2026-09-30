# 분류기 v4 봉인 입력 계약

조정자 소유 봉인 파일과 **독립적으로 고정한 해시**를 읽는 평가 계약이다.
실행·봉인·승인을 만들지 않는다. 실제 등록 recorder의 필드만 소비하는 어댑터는
[CLASSIFY_NOTES.md](CLASSIFY_NOTES.md)의 R1–R5를 따른다.

## 등록된 producer 형식

`--sealed-manifest <파일> --sealed-manifest-sha256 <해시>`는 다음 두 schema를 명시적으로 구분한다.

| schema | 입장 명부·provenance | raw 기록 |
|---|---|---|
| `ugrp.zone_pair_v6h_confirmatory.DRAFT.v1`, `sealed=true` | #292 builder의 `runs`, `cases`, `placements`, `v6_contract.source_sha256`, `execution_bundle_id`, `registration_sha256` | 등록 native `manifest.source`·`registration`, runtime plan `{labels,cases}`, case `registration_run_id`·receipt |
| `ugrp.v6h_confirmatory.v1`, `state=sealed` | 기존 synthetic/평가 봉인의 `execution_identity`, `placements_file`, `plan_file`, `cases[].attempts` | 해당 형식에 실제 저장된 identity·coverage·canonical receipt |

첫 번째 schema를 두 번째 형태의 raw로 소급 고치지 않는다. 등록 `registration_sha256`는
원 payload에서 `registration_sha256`, `execution_authorization`만 제외한 canonical JSON
해시다. 배치 파일 바이트 해시와 60+12 run/case 관계를 별도로 검사한다.
`execution_source_sha`가 있으면 manifest와 일치해야 하며, authorization의 source SHA도
존재할 때 사용한다. case/manifest receipt의 실행 SHA·등록 해시·run id와 봉인의 worker
설정 전체를 대조한다. recorder가 덧붙이는 `labels`만 설정 대조에서 제외한다.

등록 recorder 파일 SHA-256은
`531c420696ccb4c7d53fbfd17d1b96f3851730fd1f6881951b3c0892edc97c63`으로 고정한다.
이 값이 다른 producer를 이름만으로 같은 형식으로 허용하지 않는다.

`adjudicate_attempt(..., confirmatory=True, recorder_context={"manifest": ..., "case": ...,
"registration": ...})`가 메모리의 등록 형식 증거를 소비한다. 반환값의 `recorder_contract`에
출처와 **관측된** trace 창/행 수를 남긴다. 등록이 없는 공개 acceptance context는
`public_format_validation_only`로 표시되어 새 확증 코호트 입장 자격이 되지 않는다.

기존 두 번째 schema는 평가 프로토콜 전체가 `EVALUATION_PROTOCOL`과 같아야 한다.
배치·prior·설정·실행 파일 목록·원본/재시도 case 파일 해시를 대조한다.
그 형식의 canonical receipt는 row/result/trace를 묶으며 result에서는 receipt 자체만
제외한다. **첫 번째 producer에는 이 필드를 요구하지 않는다.**

## 판정과 불완전 자료

- 941 주 시드 60개와 943 보조 12개 슬롯을 먼저 만들고 누락을 미분류로 채운다.
  주 시드 성공·실패·미분류를 구분하며 분모는 60이다.
- 원본 → 같은 배치·시드·설정의 최대 1회 HOST 재실행 순으로 전이한다. 원본 FAIL,
  HARD, 모순된/불완전한 증거는 정상 재시도로 지워지지 않는다.
- `result.host_error`가 HOST 신호다. recorder의 예외 경로에서 termination이 없거나
  cleanup 이전 정상 종료가 남은 형식은 row와 일관되면 허용한다. 미해결 HOST와
  누락/손상은 `class=null`; FAIL 대치와 분모 제외를 하지 않는다.
- 원본/재시도/거부 시도의 하드 위반은 모두 보존한다. 기울기 >15° 또는 관통 >5 mm는
  FAIL_HARD_LIMIT, 정확히 문턱인 값은 하드 위반이 아니다.
- 완료된 leg·handover 실패는 HOST 표지와 무관하게 평가한다. 아직 도달하지 않은
  handover는 실패로 추정하지 않는다.
- raw endpoint와 derived leg는 같은 source 시각에서 lift/jaws/tilt를 대조한다.
  다른 시각의 관측도 안전 합집합에는 남긴다.
- 실제 trace t/tilt/lift/jaws·주기·관측창, teacher/entry 시각, 종료 경계와 PF를 검사한다.
  제공된 coverage는 자기 창과 count/period/gap가 일관돼야 한다. 등록 producer의
  wall_contact에는 episodes와 양성 접촉 steps만 있으므로 총 표본수/주기는 `not_recorded`다.

입력은 전후 바이트 해시를 대조하며 raw 안으로의 CLI 출력은 거부한다. 해시는 바이트
보존 검사이며 source/derived 논리 검사·작성자 인증·미측정 구간의 증명을 대신하지 않는다.
알려진 위반 없이 입력을 평가할 수 없으면 `NOT_EVALUABLE`; 알려진 하드 위반 또는
평가 가능한 기준 불충족은 `FAIL_A_B_SAFETY`; 모든 요구가 충족돼야 `PASS_A_B_SAFETY`다.

공개 acceptance 11건은 형식·golden 회귀 시험이고 새 확증 60+12 표본이 아니다.
이 패치에서 실제 blinded raw·봉인을 조회하거나 물리·렌더를 실행하지 않았다.
