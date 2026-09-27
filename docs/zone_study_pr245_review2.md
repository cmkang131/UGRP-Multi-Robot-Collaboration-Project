# PR #245 재검토 P1 수정 — 2026-09-28

기준 HEAD는 `a1501c180ec82be93ee56e5d3c388e0f635fb918`이다. 이 문서는 미커밋 수정의
비물리 코드 회귀 기록이다. 모델 호출·물리 step·커밋·push·병합은 하지 않는다.
#240/v65 합성(P2)은 후속으로 유지한다.

## 원인과 수정

종전 코디네이터는 `call_start` queue에서 같은 시각의 공통 사건까지 찾아 제거하고,
v64의 `_deferred`를 호출 자격 검사 전에 꺼내 병합했다. 이 때문에 메시지가 없는 조건도
호출을 잃었고, report와 retry의 처리 순서에 따라 조건별 호출 수가 달라졌다.

- 공통 사건은 `EventScheduler._on_call_start`, `_defer`, `_retry`, `_resume_deferred`를
  공유한다. 같은 시각의 사건을 선제 병합하거나 공통 queue를 삭제하는 코드가 없다.
- 메시지 대기는 별도 사전과 세대 번호로 관리한다. 오래된 예약은 자기 메시지 세대가
  소비됐을 때만 무효화된다. 공통 시작·outstanding·최소 간격·재시도 상태에 쓰지 않는다.
- 공통 입력 snapshot이 실제 만들어지는 `_submit`에서 보류 메시지를 소비한다.
  공통 사건이 보류·거절되면 그대로 남으며, 전달 후의 메시지는 이전 snapshot에 추가하지 않는다.
- 같은 시각에는 공통 시작을 먼저 처리한다. 메시지끼리만 병합하고, 작업 중인 로봇은
  자기 작업 경계 또는 먼저 온 공통 호출을 기다린다. 공통 trigger가 없는 자기 종료 경계도
  메시지 대기만 깨운다.
- 메시지에서 유래한 호출·재시도에는 `cause=message`, `message_ids`, `retry_of`를 남긴다.
  공통 호출은 `cause=common`이다. 메시지 응답은 공통 re-ask 타이머를 예약하지 않는다.
- 메시지 호출 시작 뒤 예측하지 못한 공통 사건이 와도 시각을 지키기 위해 outstanding과
  최소 간격을 경로별로 분리했다. 각 경로의 outstanding 상한은 로봇당 1개다. 이미 시작한
  메시지 호출과 뒤의 공통 호출은 겹칠 수 있다. ledger·비용 정산·전송 예산은 공유한다.

공통 시각 대조는 동일한 공통 사건과 응답 비용, 충분한 공유 예산으로 스케줄러의 효과를
분리한다. 추가 호출도 유한 예산을 소비하며 기존 예산 차단은 유지한다. 메시지로 바뀐 실제
행동·종료 사건이나 예산 소진 이후까지 조건별 전체 궤적이 같다는 주장은 아니다.

## 독립 대조 소스와 두 반례

`tests/fixtures/zone_study_multiturn/v64/`는 기준
`97f91cb040bf382973ce84b24b1ca8399e64a6fb`의 scheduler·offline·integration 파일 원문이다.
`source.json`에 SHA-256을 기록했다. 테스트는 매번 해시를 확인하고 메모리에서 읽는다.
스케줄러·통합 알고리즘은 동결 소스를 사용하며, 가짜 전송 예외를 두 버전이 동일하게
인식하도록 CallReply/TransportFailure/NotSent의 자료형만 현재 모듈과 공유한다.
Git 이력이나 네트워크 없이 재실행할 수 있다.

| 반례 | v64와 수정본의 r1 호출 시작 | 의미 |
|---|---|---|
| 6.0초 오류 종료·메시지·타이머 | 0, 5.5, 7.5, 12.8 | 7.5는 원래 retry_of를 보존한 재시도, 12.8은 공통 타이머 |
| 65.3초 자기 작업 종료·타이머 | 0, 65.3, 70.6 | 두 공통 사건 유지 |

첫 반례에서 재검토 문서의 no_comm 3회는 당시 후보의 결과이며 v64의 결과가 아니다.
v64 원본을 실행하면 4회다. 새 회귀도 이를 기준으로 한다. 이전 후보의 호출 누락을
기준선으로 고정하지 않는다.

## 검증 범위

`tests/test_zone_study_multiturn_properties.py`는 시드 0–299, 생성기 seed 245000+seed를 쓴다.

- no_comm 300개 사건열: 전체 호출·입력 해시·실제 요청 해시·dispatch 직렬화 바이트·
  censored 기록을 동결 v64와 대조한다. idle/failure/blockage/timeout/retry/timer,
  동시각 사건, OSError/TimeoutError, 실제 재시도, claim/wait/continue와 자기 종료를 포함한다.
- 같은 300개 사건열의 통신 3조건: 공통 호출의 시각·횟수·순서·트리거·재시도 계보를
  no_comm과 대조한다. 추가 호출의 원인 ID는 해당 로봇이 시작 전 실제 수신한 ID여야 한다.
- 두 반례, 메시지 호출 중 뒤따르는 공통 사건, 메시지 재시도 계보·공통 snapshot 소비,
  공통 trigger 없는 자기 작업 경계를 별도로 회귀한다.
- 기존 통합·pair·입력 격리·비용·ledger·source pin 회귀를 함께 확인한다.

검증 결과는 다음과 같다. 서로 겹치는 재검사를 합산하지 않는다.

- [전체 property 실행](../experiments/2026-09-27-zone-study-multiturn/review2-properties.txt):
  **600 property cases 통과**. 그 뒤 첫 반례 테스트는 잘못 둔 3회 기대값으로 실패했다.
  v64 원본의 4회가 맞음을 별도 대조하고 기대값을 수정했다.
- [관련 회귀 실행](../experiments/2026-09-27-zone-study-multiturn/review2-related-regressions.txt):
  **555 passed, 3 failed, 600 deselected**. 실패 3건은 메시지 응답도 `arm_reask`를
  시도해서 skipped가 늘어난다는 과거 기대값이었다. 새 불변식대로 예약 시도 자체가
  없고 실제 메시지 원인이 기록되는지를 확인하도록 바꿨다. 소스 동작은 바꾸지 않았다.
- [최종 재검사](../experiments/2026-09-27-zone-study-multiturn/review2-final-targeted.txt):
  **48 passed**. 새 경계 회귀 20건, 기존 타이머 4조건, 최종 소스로 다시 실행한 property
  24건(시드 0–7, 73, 149, 239, 299의 두 property)을 포함한다. 초기 실패는 모두 해소됐다.
  전체 범위는 중복을 제외하면 property 600건과 관련 회귀 558건이다.
- [첫 진단 로그](../experiments/2026-09-27-zone-study-multiturn/review2-initial-regression.txt)의
  5건은 65.3초 공통 호출 병합 및 메시지 호출 뒤 공통 최소 간격 적용이라는 과거 기대값이다.
  두 기대값을 v64/새 불변식에 맞게 고친 뒤 위 관련 회귀에서 통과했다.
- [최종 소스 해시](../experiments/2026-09-27-zone-study-multiturn/review2-sources.json):
  runtime 3파일·테스트 3파일·동결 fixture 4파일·CI workflow 1파일의 SHA-256을 재확인했다.
  `git diff --check` 통과, `.pytest_tmp` 없음.

전체 property 명령:

```sh
OMP_NUM_THREADS=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest \
  tests/test_zone_study_multiturn_properties.py --basetemp=./.pytest_tmp -q
```

관련 회귀는 `test_zone_study_multiturn`, `integration`, `integration_pair`, `source_pinning`,
`integration_seams`, `pair_delay`, `zone_event_scheduler`, `zone_sim_cost`, `protocol`, `offline`,
`review_r7_transport`, `review_r8`, `review_r10`과 새 property 모듈의 경계 회귀를 사용했다.
전체 600건은 이미 확인했으므로 관련 실행에서는 두 무작위 property를 `-k`로 제외했다.

기존 offline CI의 20분 한도에 긴 property 검사를 더하지 않고, `.github/workflows/tests.yml`에
30분 한도의 `zone-multiturn-properties` 작업을 등록했다. YAML 파싱·스레드 설정은 로컬에서
확인했으며 GitHub CI는 실행하지 않았다.

pytest는 항상
`OMP_NUM_THREADS=1` 및 `--basetemp=./.pytest_tmp`를 사용하며, 종료 후 임시 디렉터리를 지운다.
네트워크와 MuJoCo import가 차단된 가짜 wire/시계 검사이며 새 물리·모델 코호트가 아니므로
TensorBoard 변환 대상은 없다. 로컬 기록을 원격 백업·CI·배포 완료로 표현하지 않는다.

## 원격 확인

`git fetch origin`은 공용 `.git/worktrees/codex-multiturn/FETCH_HEAD` 쓰기 제한으로 실패했고,
`gh pr list`는 네트워크 제한으로 실패했다. GitHub connector에서 이동된 실제 저장소
`cmkang131/UGRP-Multi-Robot-Collaboration-Project`의 열린 PR을 확인했다.
#245 원격 head는 `a1501c18`, base는 `ba0eb4f5`로 확인했다. 열린 #240의 v65/pair 변경은
이번 수정에 합치지 않았다. 사용자 요청대로 커밋하지 않고 작업 트리에 남긴다.
