# PR #303 · 5차 검토 E303-1 수정

2026-10-01 KST. 대상은 `567038c2563d3d6fb4c653ebc7f797b7e35fe79f`,
독립 검토는 `f80a8f98a84d9d308e48ebca42994d489f121a80`의
`experiments/2026-09-30-e2e-readiness/REVIEW_303E.md`다.
요청대로 먼저 main `7e081d7047aa2df737cc1890c963b1d3a14302c0`을 병합한
`746b040b024fcb6bfd0d1f57b0db96305f4e7590`에서 수정했다.

## 원인과 수정

A의 성공 원본과 같은 A의 실패 사본이 함께 있으면 A는 중복으로 INVALID다.
실패 사본의 폴더 이름을 B의 run ID로 둔 뒤 정책·profile·events·summary 중 하나를
손상시키면, 이전 코드는 검사에 실패한 사본을 B에 배정했다. A의 중복이 집계에서
사라져 **성공 0/2 → 1/2**, TensorBoard 성공률 **0.0 → 0.5**가 됐다.
수정 전 원본 검토 테스트 8개를 `--runxfail`로 실행해 모두 이 assertion 실패를 재현했다.

- `harness/zone_evidence_key.py`에서 기존 여섯 열 키 검증을 공유한다.
  원시 심판 이벤트 v2는 첫 주문 이벤트부터 전체 시행 키를 복사해 보존한다.
  호출자가 나중에 키 객체를 바꾸거나 다른 키로 이어 쓰는 것을 허용하지 않는다.
  키 없는 기존 심판은 계산만 하며 게시 가능한 원시 이벤트를 만들지 않는다.
- 재생은 이벤트 키, 원본 파일의 키, 그 파일의 manifest `event_sources` 항목,
  외부 계획의 시행 키가 모두 같아야 한다. 해시를 다시 계산해도 다른 시행의 이벤트는
  사용할 수 없다. manifest 키의 누락·null·bool·주문 범위·다른 파일 경로도 거절한다.
- 코호트는 파일·envelope·원시 이벤트의 소유 선언을 검사 결과와 별개로 먼저 수집한다.
  거절된 원본의 선언과 관련 시행 키를 영수증에 보존하며, 그 원본은 원래 시행을
  INVALID/성공 0으로 분모에 남긴다. 서로 다른 소유 선언은 양쪽 시행 모두 INVALID다.
  알려지지 않은 키는 전체 코호트를 보수적으로 거절한다. 폴더 이름은 소유권이 아니다.
- 첫 봉인에서도 이미 선언된 키·계획 pin을 덮어쓰지 않는다. 기존 봉인 재작성 거부는
  유지한다. 다른 시행으로 옮긴 잘못된 원시 기록을 새 evidence로 고치지 않는다.

## 검사와 재현

기존 Python 3.12 환경을 재사용했다. driver는 MuJoCo·torch·물리 worker import를
차단하고 수치 라이브러리 스레드를 1개로 제한한다. 로컬 오프라인 검사는 host lock 없이
실행했다. 새 환경·추출 디렉터리를 만들지 않았으며 `/private/tmp` 추출본도 없다.

```sh
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
$PY experiments/2026-09-30-e2e-p06-evidence/redesign_test_driver.py --tb=short
$PY experiments/2026-09-30-e2e-p06-evidence/event_replay_mutations.py <변이명> --tb=short
```

**관련 검사 고유 671개 통과, 실패·error·skip·xfail 0개.** 최초 전체 묶음 665개에
기존 생성형 항목 8개(24,000 사례)가 포함된다. 마지막 manifest 키 타입 보강 뒤에는
영향받는 나머지 묶음 663개를 모두 재실행했다. 동일 항목의 재실행은 합산하지 않았다.
E303 원본 파일은 **68개 모두 통과**, 그중 기존 xfail 반례는 8개다. 원 검토의
assertion 16개를 AST로 대조해 그대로임을 확인했다. 등록 소스 검사는 각각 22개·34개 전체 통과다.
추가 순서·복제·이동 사례 192개를 포함한 총 생성 사례는 **24,192개**다.
변이 **12/12 검출**, pytest 수집 error·skip 0개다. 마지막 manifest 키 보강 뒤에는
해당 우회 변이도 다시 실행해 DID NOT RAISE 실패 1개로 검출했다.

최종 검사 집계·정확한 명령·파일 해시는 [review_e_verification.json](review_e_verification.json)에 있다.
기존 12,000개 관계 검사와 12,000개 이벤트 재생 검사를 유지했다.
추가 생성 검사는 원본 순서 변경·복제·이동 각 64개, **192개**이며 고정 분모와 성공 수
비증가, 기존 INVALID 유지, 정상 순열의 동일 판정을 확인한다. 생성 사례 수는 pytest
항목 수에 더하지 않는다. 검토 테스트는 생성 시 키 인자만 추가하고 xfail 8개를 제거했으며,
기존 assertion은 유지했다. 기존 C/D 및 fixture도 표본 생성 전에 키를 지정하도록만 바꿨다.

변이 12종은 cap 제거, 정책 pin 제거, 코드 pin 제거, 정착 창 단축, 요약 대조 제거,
즉시 TensorBoard import, 이벤트 키 검사 제거, 원본 키 검사 제거, 거절된 원본의 폴더명
재배정, 소유자 합집합 제거, manifest 키 대조 우회, 봉인 중 키 덮어쓰기다.
모두 해당 회귀의 실패로 검출하며 수집 오류를 검출로 세지 않는다. 즉시 import 변이는
선택 패키지 미설치 오류를 다시 도입하는 별도 대조다.

초기 구현 검사에는 지역 변수 이름 충돌로 정상 기록도 거절한 실패 51개가 있었다.
변수명을 분리한 뒤 같은 핵심 묶음은 173개 통과했다. 실패 로그도 보존했다.
추가 점검에서 개별 export의 null 출처 키가 순수 호출 기본값으로 해석되지 않도록
manifest 키 타입·일치를 명시적으로 검사하고 관련 5개 반례를 더했다.

## 보존과 범위

등록 runner SHA-256은 `85508cc58e1cba0f1fc11e3b7ef656c0c7648202ff1086c274c3dbaa64a99edd`로
그대로다. `f5566289`에 있던 prereg 관련 JSON 57개도 바이트가 같다.
등록 소스 두 테스트 파일 전체를 실행한다. `.github/workflows`는 origin/main과 같으며
새 필수 검사와 실제 event 읽기는 기존 테스트 파일·CI 목록으로 연결했다.

원본 로그·JUnit·음성 대조는 `/Users/changmin/projects/ugrp/outputs/p06-review-e-fix/`에
로컬 보존한다. 작은 보고서·소스·로그 해시만 Git으로 보존하며 전체 로그의 원격 백업을
주장하지 않는다. TensorBoard는 임시 합성 event를 실제 EventAccumulator로 읽었다.
공용 snapshot·서버·브라우저 UI와 기존 연구 raw는 변경하지 않았다.

이 결과는 오프라인 코드 계약 검사다. 물리·렌더·학습·실제 모델 호출은 0회다.
실제 실행기 연결, 새 실행의 출처 고정·배송, provider 정산, 실제 영상·공용 UI 인수와
독립 재검토는 남아 있다. PR #303은 draft로 유지하고 병합하지 않는다.
