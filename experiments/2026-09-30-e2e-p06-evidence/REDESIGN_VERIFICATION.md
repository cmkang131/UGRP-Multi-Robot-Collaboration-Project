# P06 증거 조인 재설계 검증 — 2026-09-30

PR #303, `codex/evidence-referee`. 시작 HEAD는
`114349e0adc6d934ceb9a990ee9589aa123b8543`다. 이전 두 BLOCK을 해소하기 위해
관계형 무결성·고정 계획 분모·입력 해시 재계산 방식으로 바꿨다.
방법의 원문과 적용 범위는 [README 참고 자료](README.md#참고-자료)에 적었다.

**최종: 440 passed, 0 failed, 0 errors, 0 skipped.** 생성 사례 12,000개와
registered-source 22개·source-pinning 33개를 포함한다. native TensorBoard event readback과
코호트 CLI도 통과했다. 최종 소스의 물리 실행은 없다.

## 발견 → 수정

| 발견 | 수정과 검증 |
|---|---|
| A303-1 / F303-1: 외부 identity만 맞으면 내부 calls/actions의 다른 시행·seed·조건을 수락 | 6열 복합키, 중복을 덮어쓰지 않는 인덱스, 논리 trial_id와 내부 run_id의 명시적 대응. 두 리뷰의 11개 반례를 테스트로 편입 |
| 요청·action·message·dispatch·원장의 고아나 중복이 dict/set 변환에서 사라질 수 있음 | 1:1 참조와 고유키 검사. 수신자별 메시지 반복은 `(message_id, recipient)` 교차 관계로 정규화하고 각 행의 발행 호출과 수신자를 검증 |
| 발견한 결과만 모으면 누락 시행이 분모에서 사라짐 | 실행 전 계획과 외부 SHA-256 pin 필수. 계획에서 모든 시행의 판정을 만들며 누락/INVALID는 비성공으로 포함. 중복 source·추가 고아도 기록 |
| 파일 해시를 다시 계산하면 값 복사나 연결 충돌을 놓침 | trial/referee 원본 바이트와 내부 JSON 행의 해시를 보존. 평가·개별 event·코호트 요약을 원본에서 재계산하고 게시 직전에 비교 |
| result 안에 복사한 심판 결과, JSON 중복 키, schema 우회 | 복제본과 별도 원본을 비교. 중복 JSON 키·비유한 수·키의 bool 타입·일반 변환기로의 우회 거절 |
| A303-2: 등록 runner 바이트 회귀 | 기존 runner와 등록 해시를 보존. 필수 registered-source 22개·source-pinning 33개 전체 포함 |
| A303-3: terminal 표식 생략 | 기존 terminal true·완전한 terminal 객체·boolean completeness 요구 유지. frozen plan/index도 필수이며 기존 raw를 자동 변환/재봉인하지 않음 |

## 실행 범위와 재현

기존 Python **3.12.13**, pytest **9.1.1**, TensorBoard **2.21.0**을 사용했다.
Hypothesis는 설치되어 있지 않아 고정 seed 생성기를 사용했다. 새 환경을 만들지 않았다.
MuJoCo·torch·물리 worker import를 막고 BLAS/OMP/MKL/VECLIB 스레드를 1개로 제한했다.
실제 모델·물리·렌더 실행이 없는 명시적 selector만 실행했다. referee 파일 전체를
실행하지 않았으며 필요한 순수 판정 테스트만 골랐다. 필수 소스 고정 파일 2개는 전체 실행했다.

처음에는 이 브랜치의 옛 CONTRIBUTING에 따라 공용 잠금을 기다렸으나, 테스트 시작 전에
최신 main의 [#328](https://github.com/kcm0127-dotcom/ugrp/pull/328) 병합과
오프라인 테스트의 기본 잠금 해제를 확인했다. 대기 드라이버만 중단하고 기존 실험 잠금은
변경하지 않았다. 이후 테스트는 새 규칙에 따라 잠금 없이 실행했다. wall 시간은 테스트
실행 시간이며 로봇·학습·추론 성능 수치가 아니다.

실제 사용한 selector는 [redesign_test_selectors.json](redesign_test_selectors.json)에,
같은 선택·환경·import 차단을 재현하는 드라이버는
[redesign_test_driver.py](redesign_test_driver.py)에 보존했다.

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  experiments/2026-09-30-e2e-p06-evidence/redesign_test_driver.py \
  --junitxml=/absolute/new-result.xml
```

생성 검사는 혼합·중복·삭제·재정렬 각 3,000회, **총 12,000개 사례**다.
seed는 `30320260930 + 연산번호(0..3)`이며 1–5개 시행·1–3개 주문과 성공/실패를 섞는다.
성공수/성공률 비증가, 키 충돌 시 시행 전체 INVALID, 고정 분모를 검사한다.
재정렬에서는 정규화된 요약 전체의 동일성도 요구한다. 12,000을 pytest 테스트 수에
더해 총량을 부풀리지 않는다.

실제 `EventAccumulator`로 개별/코호트 이벤트를 읽었으며, 예를 들어 성공 1개·실패 1개·
원본 누락 1개는 성공률 **1/3**, 분모 **3**, 누락 시행 성공 **0 / INVALID**다.
누락·손상·중복 시행이 함께 있는 5개 계획은 성공 **1/5**로 남는다.
계획만 있고 source가 하나도 없는 CLI 실행도 **0/2**, INVALID 2로 게시한다.
게시 중 raw가 바뀌면 완료 폴더/event를 노출하지 않는 반례도 포함했다.

## 이전 판독기의 음성 대조

두 번째 리뷰의 재현 파일은 `test_zone_study_evidence_review_f303.py`로 그대로 복사했다.
`114349e0`의 contract·zone-study adapter·exporter 3개만 임시 Python 모듈로 불러와
같은 테스트의 판독기를 교체했다. 저장소 파일은 되돌리거나 덮어쓰지 않았다.

결과는 **7 failed, 0 errors**다. 일곱 실패 모두 테스트 본문에서 실제
`evaluation/reported_success=1.0`을 읽은 뒤 실패했다. 수집 오류나 fixture 오류를 결함 검출로
세지 않았다. 재현 hook은 [redesign_negative_control.py](redesign_negative_control.py)에
보존했다. `/private/tmp/p06-evidence-redesign/old_{contract,study,export}.py`는 각각
시작 HEAD의 해당 소스를 `git show`로 추출한 파일이며 수정하지 않았다.

## 중간 실패도 보존

- 첫 좁은 묶음: **38 passed**, 생성 검사 4개는 이 묶음에서만 미선택.
- 첫 확장 묶음: **126 passed / 2 failed**. 잘못 쓴 fixture 조건 이름 `schema_comm`을
  실제 `structured`로 고쳤다. peer의 수신자별 message 참조를 1개짜리 message PK로
  오해한 부분은 교차 테이블로 정규화했다. 검사를 생략하거나 set으로 중복을 숨기지 않았다.
- 수정 뒤 정상 네 조건·내부 충돌: **8 passed**.
- 첫 관련 전체 묶음: **420 passed / 8 failed**. 모두 `test_ci_sharding.py`에서
  기존 압축 fixture 3개의 sparse 제외 때문에 preflight가 차단한 경우다. 안내된 정확한
  Git 경로의 v3/v4/v5 `example_trial_record.json.gz`를 복원했고 preflight 3/3을 확인했다.
  테스트나 검사 조건을 우회하지 않았다.
- 후속 경계 검사: **211 passed**, 생성 검사 4개는 이 좁은 묶음에서만 미선택.

최종 묶음의 개수·필수 파일별 결과·JUnit SHA-256·소스 해시는
`redesign_verification.json`과 `redesign_source_files.sha256`를 따른다.
최종 실행에는 생성 검사도 모두 포함한다.

원본 로그·JUnit은 `/Users/changmin/projects/ugrp/outputs/p06-evidence-redesign-20260930/`에
보존한다. 임시 synthetic JSON/JPEG/event는 OS 임시 디렉터리에만 생성했다.
작은 검증 요약·재현 코드·소스 해시만 GitHub에 올리며 로컬 raw 전체의 원격 백업을 주장하지 않는다.

## 남은 범위

새 writer의 실제 실행기 연결·실행 전 계획 봉인·물리 인수, 실제 provider 정산,
실제 연구 코호트의 snapshot 및 공용 TensorBoard 화면/영상 인수는 후속이다.
이번 작업에서는 물리·렌더·실제 모델 호출 0회, 공용 TensorBoard 서버/기존 snapshot과
Drive 변경 0회다. 기존 runner·등록 JSON과 `.github/workflows`도 변경하지 않았다.
이 검증은 E2E 또는 PHYSICAL 승인이나 독립 재검토 완료를 뜻하지 않는다.
