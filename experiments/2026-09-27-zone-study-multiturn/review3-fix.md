# PR #245 검토 3 P1 수정 (2026-09-28)

기준 HEAD: `0acdaf0d543e6535d61ff80f2c49d031beee04d7`.
이 기록은 미커밋 소스의 단위 회귀이며 실제 모델 호출·물리 step은 0회다.
Git 커밋·push·병합은 하지 않는다. fetch는 공유 Git 디렉터리 쓰기 제한,
원격 PR 조회는 네트워크 제한으로 실패했다. 지정된 검토 파일과 로컬 HEAD를 대조했다.

## 원인과 수정

`DecisionScheduler`의 메시지 wake가 `_on_call_done`에만 있었다. 반면
`EventScheduler._release_unsent`는 wire 전 실패를 환불한 뒤 `_resume_deferred`로
공통 대기만 재개했다. 그래서 호출 도중 도착한 메시지는 inbox에 남아도 다시 호출하지 않았다.

메시지 wake를 `_resume_deferred` override로 옮겼다. 부모의 v64 공통 wake를 먼저
실행한 뒤 메시지를 깨운다. 공통 시작·타이머·재시도·최소 간격·정산 구현은 그대로 공유한다.
메시지는 자기 작업 경계·진행 중 호출·최소 간격·공유 예산을 다시 검사하는 추가 호출이다.

## 종료 경로 표

구현된 테스트 표는 `tests/test_zone_study_multiturn_exits.py:EXIT_CASES`다.
공통만 / 메시지만 / 둘 다의 대기를 검증한다. 아래 항목을 세분한 24개 경로를 포함한다.

| 종료 경로 | 공통 대기와 메시지 대기의 처리 | 검사 |
|---|---|---|
| 정상 `call_done` | 둘 다 자격 재검사; 동시에 있으면 공통 snapshot이 메시지를 소비 | 시작 시각, 원인, inbox, 중복 없음 |
| invalid / error / timeout / send 뒤 submit 오류 | 비용 정산 뒤 둘 다 재개; 실패 행동은 실행하지 않음 | ledger·send 수·행동 배제 |
| 재시도 소진 / 모순된 NotSent | 추가 retry 없이 둘 다 재개 | retry root·exhausted 기록·공통 일정 |
| pending 0-send: 입력 생성 / NotSent / 요청 저장 / wire 예산 거절 | 환불 뒤 둘 다 재개 | 0 send·hold 해제·2초 최소 간격 |
| submit 0-send: 일반 오류 / NotSent | pending·hold·대기를 만들기 전 거절; 후속 사건은 정상 처리 | 예약 환불·NotSent 전파·후속 두 종류 사건 |
| actor 논리 / actor HTTP / 시행 HTTP / 시행 논리 / 외부 예산 거절 | 두 종류 사건 모두 wire 전에 거절; 새 호출·예약 없음 | 거절 횟수·추가 전송 0 |
| pending 동안 예산 소진 | 모든 재개 경로에서 두 대기 모두 자격을 다시 확인하고 거절 | 각 wake 행 × 예산 허용/차단 |
| submit 취소(전송 전/후) / reply 취소 | 예외 전파로 중단; 둘 다 추가 실행 없음; 예약 보존 | 예외·ledger·send 수 |
| 에피소드 종료: pending / SIM 비용 대기 / 0-send | censor 또는 환불만 수행; 종료 처리 중 후속 호출 없음 | 정산·예약 해제·추가 전송 0 |

취소를 성공 완료로 바꾸거나 horizon 이후 자동 재시작하는 API는 추가하지 않았다.
submit의 동기 실패에는 도중 수신 대기가 생기지 않으므로, 이 두 행은 후속 사건의
정상 처리를 별도로 검사한다. 이 표는 기존 종료 의미를 유지하며 두 대기의 누락을 확인한다.

## 반례와 생성 검사

- 6.0초 공통 호출 → 6.1초 메시지 → pending 0-send. 입력 생성 실패와 요청 저장 실패를
  각각 4조건으로 검사한다. 수정 전 통신 6건 모두 8.0초 요청이 누락됐다.
  v64는 8.0초 inbox 포함 요청을 만들었고 no_comm 2건은 원래도 동일했다.
  [수정 전 실패 로그](review3-before.txt).
- 기존 600개 생성 검사의 비구속 예산 비교를 유지하고 wire 오류·timeout·입력 생성 실패·
  요청 저장 실패를 주입했다. no_comm은 동결 v64의 호출·입력 해시·명령·censor·0-send·
  ledger·예산 사용/예약을 비교한다. 통신 3조건은 공통 일정과 추가 호출의 메시지 근거를 검사한다.
  추가 메시지 호출의 fixture 행동은 `continue`로 고정하고 응답 비용은 유지한다. 초기
  seed 287에서는 추가 응답의 `wait`가 hold를 새로 만들어 31.3초 자기 완료 사건까지
  달라졌다([진단](review3-seed287-diagnosis.txt)). 이는 외부 사건을 고정한 일정 비교의
  전제 위반이므로 fixture를 고쳤다. 실제 wait/hold 정책은 전용 90초 v64 회귀로 유지한다.
- 예산 차단 생성 100건을 더했다. no_comm은 유한 예산에서도 v64와 전체 결과가 같아야 한다.
  통신 조건은 실제 예산 거절 전 공통 일정과 전송 상한을 검사한다. 추가 메시지 호출이
  유한 공유 예산을 먼저 소진할 수 있으므로 거절 이후 일정까지 동일하다고 주장하지 않는다.
  최초 실행은 거절 진단 목록까지 동일하다고 가정해 HTTP 예산 사례가 실패했다. 기존 v66은
  소진 뒤 재질문 타이머를 더 만들지 않고, v64는 타이머를 만든 뒤 거절하므로 목록 길이가
  다르다. 호출·입력·명령·사용/예약 예산은 같았다. 비교 범위를 이 불변식으로 명시하고
  예산 거절의 실제 발생과 전송 상한은 따로 검사한다. 제품의 타이머 정책은 바꾸지 않았다.
- 확률적 실패 주입만으로는 다른 공통 사건이 누락된 메시지 wake를 대신해 기존 오류를
  가릴 수 있었다([초기 변이 검사](review3-mutation.txt)). 그래서 6.0–8.0초 사이 후속
  공통 사건이 없는 간격을 생성하는 12건을 더해 **총 712개 생성 검사**로 만들었다.
  이 간격에서도 후반의 사건은 seed별로 생성한다. 메시지 대기가 자격을 갖춘 채 남으면
  즉시 실패하는 liveness 검사도 있다.
- 원래 `_on_call_done` 전용 wake를 메모리에서 복원한 변이는 준비/저장 실패 × 통신
  3조건 모두 생성 검사에서 `('r1', 8.0, 6.0)`으로 검출됐다.
  [변이 검출 로그](review3-gap-mutation.txt). 소스 파일에 변이를 쓰지 않았다.

## 최종 검증

**서로 다른 검사 총 1,751건 통과.** Python 3.12.13 / pytest 9.1.1,
기존 `.venv-sim-worker-mac`을 사용했다. 모든 pytest에 `OMP_NUM_THREADS=1`과
`--basetemp=./.pytest_tmp`를 적용했고 종료 후 작업 트리와 분할 실행 폴더의 임시
디렉터리를 모두 삭제했다. HEAD는 기준 SHA 그대로이며 커밋·push·병합은 0회다.

| 검사 | 최종 결과 | 근거 |
|---|---:|---|
| 생성 property 712 + 개별 반례 28 + 종료 표 101 | 841 passed (281 + 280 + 280) | [1](review3-final-properties-1.txt), [2](review3-final-properties-2.txt), [3](review3-final-properties-3.txt) |
| 기존 관련 20개 모듈 | 907 passed, 과거 fixture 부재 3건 | [로그](review3-final-related.txt) |
| 누락 fixture 3건 재검증 | 3 passed | [로그](review3-final-frozen-records.txt), [원본 해시](review3-frozen-retrieval.json) |

누락 파일은 sparse checkout에서 제외된 v3/v4/v5의 `example_trial_record.json.gz`다.
현재 HEAD의 Git blob을 임시 폴더에 읽고 기존 `raw_index.json`의 SHA-256과 대조한 뒤,
해당 테스트의 fixture 경로만 임시 복사본으로 연결했다. 파일 내용과 감사 로직은 바꾸지
않았으며 복사본도 검사 후 삭제했다. 검증 완료에 필요한 원본은 Git에 그대로 있다.

새 841건은 같은 소스를 참조하는 독립 pytest 3개로 분할했고 각 프로세스의 임시 폴더를
분리했다. [수집 목록](review3-collected.txt), [실제 명령](review3-test-commands.json),
[최종 소스/로그 해시·결과](review3-validation.json)를 보존한다. 재현 대상은 다음과 같다.

```sh
OMP_NUM_THREADS=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest \
  tests/test_zone_study_multiturn_properties.py tests/test_zone_study_multiturn_exits.py \
  --basetemp=./.pytest_tmp -q
```

초기 확장 검사 [로그](review3-properties.txt)의 67건 실패는 위에 설명한 거절 진단
비교 66건과 외부 사건을 바꾼 fixture 1건이다. 최종 소스로 712개 생성 검사를 모두 다시
실행했다. CI YAML의 새 검사 포함·스레드 제한·항상 임시 폴더 정리는 파싱으로 확인했다.
원격 PR 최신 상태와 GitHub CI는 접속 제한 때문에 확인하지 못했다.

이 작업은 새 연구·학습·평가 코호트가 아니므로 TensorBoard 변환 대상이 아니다.
원본 v64 fixture와 이전 실험 기록은 그대로 보존한다.
