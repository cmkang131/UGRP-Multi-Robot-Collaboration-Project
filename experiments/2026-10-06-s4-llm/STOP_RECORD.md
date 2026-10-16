# S4 중단 기록 — 2026-10-06

> 재개 전 시점의 기록이다. 사용자 재개 지시 뒤의 수정·최종 결과는 [RESUME_RECORD](RESUME_RECORD.md)에 보존한다. 아래 당시 상태·실패 이력은 바꾸지 않았다.

## 현재 범위

- 시작 전에 기본 checkout AGENTS.md, README, current_status, CONTRIBUTING, S4 계획을 읽었다. 기준 main `da92d91dbf4af193d3aa3559de9efe55653ec5c0`.
- 원격/로컬 HEAD `5fa2210030ce738aaf6ed8dc99ff17c24be0c089`는 **초기 claim 라우팅과 시험 7개만** 포함한다. `Co-Authored-By: Codex <noreply@openai.com>` 포함. [DRAFT #395](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/395).
- 후속 `harness/s4_llm_host.py`, `harness/s4_llm_inputs.py`, 저장된 합성 응답 fixture와 호스트 시험은 **로컬 미커밋**이다. 기존 `pair_llm_dispatch.py`에는 로봇 목록/실행기 선택 함수의 선택 인자만 추가(기본값 보존). 초기 cyan role의 잘못된 `solo`를 기존 카탈로그 `west`로 고친 것도 미커밋이다.
- 한 호스트의 IntegratedTrial + DecisionScheduler + PairLiveLedger(MainStudySendLedger), #371의 응답 검증/이미지 비용/StopAdapter를 재사용했다. claim: r3 cyan → deliver, r1/r2 beam → pair_carry. rule은 모델 어댑터를 받지 않는다. no_comm/peer_nl만 기존 어댑터를 주입한다.
- 새 실제 실행 CLI·runnable bundle·workflow 없음. 실제 호출을 자동으로 시작하는 코드 없음. S3가 auto-claim을 끄고 자기 RobotLink와 자기 executor를 주입해야 한다.
- [S3 #394](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/394)는 마지막 확인에도 `2669eee28b56cd54f655c285a5e57d0916a895c9`, 계획 파일 1개뿐이다. API 제안은 두 PR 코멘트로 남겼고 S3 브랜치/파일을 수정하지 않았다. S3 실행기와의 실제 연결 검증은 남았다.
- 이번 에이전트의 로컬 시뮬레이션·MuJoCo compile/reset/render·물리 실행·실제 모델 호출 **0회**. 수동 프록시 시작/조회, 잠금 획득/해제, 다른 프로세스 변경 없음. PR 생성에 따른 GitHub 자동 CI는 로컬 시험과 별개다.
- fixture 응답은 손으로 만든 합성 JSON이다. 과거 실제 모델 응답으로 표현하지 않는다. wire에서 request_id만 해당 요청 ID로 연결한다. 시각은 stub의 논리 스케줄러 시각이며 물리 SIM 측정이 아니다.

## 실행한 시험 (항상 한 프로세스, 변경 모듈의 파일 3개만)

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest \
  tests/test_pair_llm_s4_host.py tests/test_pair_llm_s4_routing.py \
  tests/test_pair_llm_decisions.py -q --maxfail=1
```

| 차수 | 결과 | 원인·처리 |
|---|---|---|
| 초기 | routing 7 passed in 0.47s | 이 통과 뒤에만 초기 커밋·push·DRAFT PR 생성 |
| 1 | 1 failed, 3 passed in 0.82s | 시험이 archive_request의 `user` 대신 wire 형식의 `messages`를 기대. 기존 저장 함수 확인 후 시험을 수정 |
| 2 | 1 failed, 11 passed in 0.97s | 정지 판단 stub에 진행 중 pair job이 없어 기존 idle 재질문 2회가 추가됨. 실제 정지 상태처럼 stub의 자기 job을 설정 |
| 3 | **36 passed in 1.03s** | 이 시점의 연결/기록/429 시험 통과. 아직 커밋하지 않음 |
| 4 | 1 failed, 13 passed in 0.95s | 추가한 입력 거절 시험에서 예외가 밖으로 재발생한다고 잘못 가정. 스케줄러는 미전송을 환불/기록하고 동료 로봇을 계속 처리함 |
| 5, 최종 | **1 failed, 13 passed in 1.01s** | 같은 입력 거절 경계에서 종료된 ledger 행의 `unsent`를 읽어 KeyError. 오류는 종료 때 `unsent_calls`로 옮겨짐. 두 번의 스케줄러 오류 계약 오해로 사용자 규칙에 따라 수정·시험 중단 |

통과 수는 합산하지 않는다. `--maxfail=1` 뒤 나머지는 실행되지 않았으므로 최종 트리의 전체 통과를 주장하지 않는다.

최종 실패 전까지 확인한 것: 세 조건의 단독/짝 claim 선택, 같은 scheduler/원장 소유, 실제 직렬화한 요청/응답 원문과 해시, 자기 영상+정적 지도 해시,
호출·제공자 형식 토큰·wall latency·SQLite 원장 정합, peer_nl의 r3→r1 전달/no_comm 발화 거절,
첫/둘째/셋째 POST의 429 모두 RATE_LIMIT 고정·후속 POST/행동/finish 재시도 차단·오류 본문/Retry-After 보존,
비정상 finish_reason의 비용 보존/행동 차단, 정지 창 바뀜/만료 거절, 두 종류 정지 판단의 정상 적용.

## 두 번째 실패의 정확한 원인 (중단 후 읽기만 수행)

- 실패 시험: `tests/test_pair_llm_s4_host.py:332`, `r['unsent']['error']`에서 `KeyError: 'unsent'`.
- 앞선 assertion 두 개는 통과: 잘못된 이미지 해시를 가진 r1의 실행기 호출 0, 전송 원장의 actor 집합은 r2/r3뿐.
- `harness/zone_event_scheduler.py:1008` 근처 `_reply_of`가 임시 `entry['unsent']`를 설정한다.
- **`harness/zone_event_scheduler.py:1098`** `_release_unsent`가 `pop('unsent', ...)` 한 뒤 ledger를 `status='not_sent'`, `attempts=0`로 바꾼다.
- **같은 파일 1100–1103**이 오류의 정식 보관 장소 `scheduler.unsent_calls`에 call_id/actor/stage/error를 추가한다. `transport_errors`에도 원인이 기록된다.
- 따라서 현재 증거는 **시험의 오류 기록 조회가 잘못됨**이다. 입력 누출이나 스케줄러 결함이 검증된 것이 아니다.
- 다음 수정 후보: 임시 dict 키가 아니라 `not_sent` 상태 + wire ledger 0회 + 실행기 0회 + `unsent_calls`의 동일 call_id/error를 함께 검사. `Host.save`에도 `unsent_calls`, `transport_errors`, 최종 scheduler ledger를 보존할지 검토할 것. 이번 중단 뒤에는 이를 수정하거나 다시 시험하지 않았다.

## 고전·표준·최근 방법 조사

1. **고전: Martin Fowler, Event Sourcing (2005)** — [원문](https://martinfowler.com/eaaDev/EventSourcing.html)의 상태/이벤트 로그 구분과 외부 호출을 gateway에서 격리하는 절을 읽었다. 적용 방향(우리 판단): 처리 중 사라지는 필드 대신 정식 사건 기록으로 오류와 실제 전송 여부를 검증하고, 재생 중 외부 전송은 stub으로 격리한다. 저장소 전체를 event-sourcing으로 재작성할 필요는 없다.
2. **표준: pytest monkeypatch** — [공식 문서](https://docs.pytest.org/en/stable/how-to/monkeypatch.html)의 외부 호출 대체, 명시적 의존성 주입과 자동 원복을 확인했다. wire/실행기만 주입하고 실제 parser/scheduler/ledger는 사용한다. 시험에서 socket 및 MuJoCo·worker 진입을 차단했다.
3. **최근 상위/하위 계층: Hi Robot, ICML 2025** — [논문 초록](https://arxiv.org/abs/2502.19417), [저자 설명](https://www.pi.website/research/hirobot)을 확인했다. 상위 의미 판단과 하위 실행을 분리한다. 이것은 S4 연결 구조의 참고이며 Python 기록 형식의 증거는 아니다. 논문 전체/성능 재현은 미확인.
4. **최근 공개 구현: RoCo, ICRA 2024** — [논문 초록](https://arxiv.org/abs/2307.04738), [dialog_prompter.py](https://github.com/MandiZhao/robot-collab/blob/main/prompting/dialog_prompter.py)의 `prompt_one_round`를 읽었다. 파싱 실패, 실행 가능 여부, 피드백 기록을 각각 보관하고 실행 허가를 구분한다. 우리에게 필요한 점은 거절과 실행을 별도 기록/검증하는 부분이다. RoCo의 정답 환경 피드백·자동 재계획/재호출은 UGRP 입력/재시도 제약과 달라 도입하지 않는다.

참고 문헌이 이번 구현의 성공이나 물리 성능을 입증하지는 않는다. 정확한 오류 원인은 위 저장소 코드에서 확인했다.

## 남은 작업과 보존

입력 거절 시험·미전송 오류 저장 점검 → 같은 세 파일만 재검사 → 통과 뒤 후속 커밋/일반 push → S3 실제 API 연결 검증 순서가 남았다.
사용자의 중단 규칙 때문에 여기서 실행하지 않는다. 최신 변경은 원격에 없으며 초기 PR의 CI를 최신 구현 검증으로 해석하지 않는다.
소스·실패 요약·SHA manifest는 기본 checkout의 새 `outputs/s4-llm-offline-stop-20261006/`에도 복사했다. 로컬 보관이며 원격 백업이 아니다.
완료한 실험/훈련/평가가 없어 TensorBoard snapshot 없음. Drive 조회/업로드 없음. raw 삭제/덮어쓰기·강제 push/reset·병합 없음.
