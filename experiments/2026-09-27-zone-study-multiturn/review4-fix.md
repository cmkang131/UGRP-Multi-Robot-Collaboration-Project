# PR #245 검토 4 P1 구조 수정 — 2026-09-28

기준 HEAD는 `6386472702a32d6758c920865469a5d4d77cb9b5`다. GitHub connector로
PR #245의 같은 원격 HEAD·draft·미병합 상태와 열린 PR을 확인했다. fetch는 공유
`.git/FETCH_HEAD` 쓰기 제한으로, gh는 네트워크 제한으로 실패했다. origin 설정은
변경하지 않았다. 모델 호출·물리 step·Git 커밋·push·병합은 모두 0회다.
P2(#240/v65 합성)는 요청대로 후속이다.

## 구조와 상한

`DecisionScheduler`의 `_message_waiting`·토큰·전용 `_push`, `_on_call_start`, `_submit`,
`_resume_deferred`를 제거했다. 이 클래스는 `received_event_cause='message'`, 자기 작업
경계의 가용 시각, 시행/외부 예산을 설정한다. 실제 수신 한 건은 코어의 `event()`를
통해 `EventInput` 한 개를 만들고 기존 `call_start` 사건 큐에 들어간다.

`EventInput`은 원인·출처 태그·가용 시각·snapshot 소비자를 가진 일반 사건 입력이다.
작업 경계가 미정이면 `available_at=inf`, 자기 완료/실패가 오면 그 시각으로 바꾼다.
공통 사건과 메시지 사건은 `_deferred`의 원인별 키로 구분한다. 메시지 사건은 공통
사건을 흡수하거나 공통 last-start를 변경하지 않는다. 같은 시각에는 공통 사건이 먼저다.
공통 snapshot은 이미 받은 메시지를 소비할 수 있지만 미래 메시지를 읽지 않는다.

호출이 0-send이면 코어의 유일한 환불 지점에서 **원래 입력 사건**을 복원한다.
submit 오류도 같은 `_resume_deferred`를 거친다. 별도 메시지 wake나 재개 토큰은 없다.
반복 0-send에는 최소 간격을 적용하고, 간격 0 설정에서도 최소 1 quantum 뒤에 예약해
동일 시각 무한 반복을 막는다. 취소·잘못된 반환형·emit 예외는 v64처럼 상위로 전파하며
자동으로 다음 일을 실행하지 않는다. reply 예외가 전파될 때 pending 회계 상태는 보존한다.

증가만 하는 `_calls_started`는 ID 생성에만 사용한다. 시행 상한은 `AttemptBudget`의
전송/예약 수로 제한하고 0-send는 전액 환불한다. 기본 실제 전송 상한은 로봇당 30,
시행당 90이며, 한 논리 호출의 여러 HTTP 전송도 각각 포함한다. v64 로봇별 논리 상한은
유지한다. 예산 차단·horizon·취소를 새로운 호출 허가로 바꾸지 않는다.

일반 `EventScheduler`에 `cause='operator_notice'` 사건을 넣어도 같은 보류→snapshot
실패→환불→재개를 통과하는 검사를 두었다. subclass의 생명주기 메서드가 부모 메서드와
동일한지도 검사한다. 이는 메시지 전용 상태 기계를 이름만 바꾸는 것을 방지한다.

## 재현·적대적 추적

- 요청 반례: 최초 r1 호출·재시도 실패 → 6.1초 수신 → snapshot 실패 → **8.1초 inbox 포함
  요청**. 통신 3조건 모두 통과한다. 수신이 먼저 존재하므로 실패 시 복원해야 하는 사건을
  실제로 검사한다.
- 기본 상한·반복 wait·600초 대조: 최초 준비 실패 1회와 2초 공통 사건 후 **90회 전송,
  각 로봇 30회**. 동결 v64와 호출·입력·명령·ledger·예약/사용 예산이 같다.
- 종료 표: **33개 경로 × 4상태 = 132셀**. 보류 없음 / 이전 수신 보류 / 도착 직후에
  호출 진행 중 도착도 추가했다. 정상, 실패 응답, submit/pending 0-send, snapshot,
  TransportFailure, ledger 모순, 잘못된 반환형, emit/action 예외, 예산 5종, 취소와 horizon을 포함한다.
- API·입력 거절 23셀은 실제 수신 사건을 보류한 채 실행하고, 부적합 입력을 거절한 뒤
  정상 자기 경계 4초에서 재개함을 확인한다. 생성 실패는 별도 인스턴스의 거절이며 기존
  보류 사건을 건드리지 않는지 확인한다.
- `EventScheduler`와 설정 subclass의 명시적 return·raise·except 64개와
  정상 암시적 반환 24개를 AST/실제 반환 opcode로 열거했다. **88개 지점 중 88개에 실행 근거**가 있다. 이는 모든 boolean 조합이나 외부 콜백 내부의
  예외까지 전부 검증했다는 뜻은 아니다. 정상/환불은 재개, 예산은 거절, 취소/치명적 예외와
  종료는 재시작 없음으로 구분한다.
- 메모리 변이 2개(입력 환불 복원 제거, 환불되지 않는 call-ID 상한 복원)가 모두 검출됐다.

[전체 표](review4-exit-table.md), [실행 추적·ledger·분기 인덱스](review4-exit-traces.json),
[재생 스크립트](audit_review4.py)를 함께 보존했다. JSON은 반복 관측 tick의 개수만
따로 기록하고 call·message·환불·예외·예산 사건은 보존한다. `executed_by`는 `rows`의
0부터 시작하는 인덱스다. 표의 시작 시각은 실패한 snapshot 시도도 포함하며 실제 send는
각 행의 ledger로 구분한다.

## 생성 검사와 검증 범위

새 기본 상한 생성기 1,000건은 실제 v64 스케줄러와 현재 스케줄러에 같은 seed의
사건열을 넣는다. 기본 30/90에서 각 시행이 실제 90회 전송에 도달해야 한다. 최초
준비(start), submit, snapshot, wire 직전 실패를 무작위로 주입하며 각 분류는 250개
seed에서 최초 실패로 강제한다. 호출·입력 digest·명령·ledger·전송 기록 전체를 비교한다.
이 검사는 커널의 가짜 입력이며, 기존 통합 생성 712건은 실제 study 입력 builder·보존
자기 RGB·가짜 wire를 사용해 no_comm v64 동등성과 통신 3조건의 공통 일정·추가성·liveness를 검사한다.
기존 생성기의 300/900 비구속 상한도 실제 기본 30/90으로 바꿨다.

조건 간 공통 일정 비교는 외생 사건·응답 비용을 고정하고 첫 예산 거절 전까지 수행한다.
no_comm의 호출·입력·명령·ledger 동등성은 끝까지 비교한다. fixture 명령의 이해나 실제
운반 성공을 측정한 검사가 아니며, 실제 provider·물리 파일럿 승인을 뜻하지 않는다.
CI 전용 multiturn job에도 1,000건 생성기를 추가했다.

초기 검증 중 새 실패 유형에 맞지 않던 gap 기대값을 바로잡았다. 6.0초 submit/snapshot
실패는 호출 시작 자체가 없으므로, 이후 처음 오는 6.1초 메시지를 즉시 처리하는 것이
v64 동작이다. pending 준비/저장 실패는 6.0초 시작 간격 때문에 8.0초 재개한다.
요청 반례의 **6.1초 메시지 이후** snapshot 실패와 혼동하지 않았다.
별도 cwd의 관련 검사에서는 상대 지도 경로가 없어 실패했다. 해당 cwd에서 원본 `maps`
디렉터리를 읽는 링크를 연결해 다시 검사한다. 제품 경로나 실패 기대값은 바꾸지 않았다.

이 작업은 단위 회귀이며 새 연구·학습·평가 결과가 아니므로 TensorBoard 변환 대상이 아니다.
Google Drive는 프로젝트 제외 지침에 따라 사용하지 않았다. 이전 raw·기록·v64 fixture는 보존했다.

## 최종 결과

**서로 다른 검사 3,012건 통과**, 실패·skip 0건. 반복 실행된 동일 node는 합산하지 않았다.
모든 pytest에 `OMP_NUM_THREADS=1`, `--basetemp=./.pytest_tmp`를 적용했다. 병렬 단위
검사는 자기 임시 cwd를 사용했고 해당 폴더와 프로젝트 `.pytest_tmp`를 종료 후 삭제했다.

| 검사 | 통과 | 근거 |
|---|---:|---|
| 관련 20개 모듈 + 생성 1,000 + 종료 표 당시 257 | 2,167 | [로그](review4-related.txt), [XML](review4-related.xml) |
| 최종 코어 + 생성 1,001 + 종료/API 259 | 1,295 | [로그](review4-final-core.txt), [XML](review4-final-core.xml) |
| 통합 no_comm·구속 예산 대조 | 400 (200+200) | [1](review4-nocomm-1.txt), [2](review4-nocomm-2.txt) |
| 통신 3조건 생성·gap·개별 반례 | 344 | [로그](review4-remaining-properties.txt), [수집 목록](review4-remaining-collected.txt) |
| 초기 검토 18개 finding의 기존 회귀 | 98 | [로그](review4-legacy.txt) |

최종 자체 점검에서 `max_outstanding_per_actor=2`의 한 자리가 비었을 때 재개가 늦어질
가능성을 확인하고, 원래 v64처럼 여유가 생기면 재개하도록 바꿨다. `[0.0, 0.1, 1.0]` 시작
시각을 동결 v64와 비교하는 검사를 추가했다. 기본 상한 1에서는 같은 조건식이며,
이 마지막 변경 후 코어·생성·종료 1,295건을 다시 실행했다. 검사 단계별 코어 해시와
최종 소스·로그 해시, 중복 제거 결과는 [검증 manifest](review4-validation.json)에 있다.

sparse checkout에서 빠진 과거 v3/v4/v5 fixture 3개는 HEAD blob을 임시 디렉터리에 읽고
기존 `raw_index.json`의 전체 SHA-256과 대조했다. 테스트 경로만 임시 자료로 연결했으며,
원본 내용·검사 기준·과거 기록은 바꾸지 않았다. 복사본도 검사 후 삭제했다.
AST와 CI YAML 파싱, `git diff --check`도 통과했다. HEAD는 기준 SHA 그대로다.
수정은 이 worktree에 미커밋으로 남겼고 원격 CI·병합·물리 준비 완료는 주장하지 않는다.
