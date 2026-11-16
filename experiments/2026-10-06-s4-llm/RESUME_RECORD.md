# S4 재개와 오프라인 검증 — 2026-10-06

사용자가 STOP_RECORD의 시험 조회 위치 오류와 조사를 확인하고 재개를 지시했다.
시뮬레이션·MuJoCo compile/reset/render·물리 실행·실제 모델 호출 없이, 변경 모듈의 같은 시험 파일 3개만 한 pytest 프로세스로 실행했다. 공용 잠금·다른 worktree/프로세스는 변경하지 않았다.

## 변경과 확인 범위

- 일반 claim과 짝 `carry_decision`/`post_look_decision`이 같은 3대 scheduler/channel/PairLiveLedger(MainStudySendLedger)를 사용한다. 기존 #371의 검증·StopAdapter·과금·429 검사를 재사용한다. 기존 PairTrial의 로봇/계획기 기본값은 보존한다.
- r3 cyan/west → `deliver(order-1, A)`, r1/end_neg·r2/end_pos → `pair_carry(order-5, B, partner)`. rule은 모델 어댑터를 받지 않고, no_comm/peer_nl은 주입한 어댑터를 사용한다.
- 잘못된 자기 이미지 해시, 일반 belief에 정답 필드, 짝 own_belief에 타 로봇 pose를 넣는 세 경우 모두: `not_sent`, attempts 0, wire ledger 0, 해당 실행기 호출/정지 결정 0, `scheduler.unsent_calls`와 `transport_errors`의 같은 call_id와 비어 있지 않은 동일 error를 함께 확인했다. 정상 동료 r2/r3는 처리된다.
- `Host.save`에 `scheduler_ledger.json`, `unsent_calls.json`, `transport_errors.json`을 추가했다. 정상 종료·입력 거절·429 실패 시 현재 최종 원장과 오류가 그대로 저장되는지 검사한다. save는 pending 호출을 처리하거나 모델을 재호출하지 않는다. 실패 상태의 원장은 outstanding 행을 포함할 수 있고 `scheduler_settled=false`로 표시한다.
- 요청/응답 실제 직렬화 원문, 본문·자기 이미지/지도 SHA-256, 호출 수·제공자 형식 토큰·wall latency·SQLite 과금 원장, peer_nl 메시지/무통신 거절, 첫/둘째/셋째 POST의 429 RATE_LIMIT 고정·추가 전송/행동 차단, 비정상 finish_reason 과금/행동 차단, 정지 창의 같은 ID/만료/교체 거절을 시험했다.
- 모델 응답 fixture는 손으로 만든 저장된 합성 JSON이다. 실제 모델의 저장 응답이나 실제 제공자 사용량 측정이 아니다. stub 시각은 논리 스케줄러 시각이며 로봇 운동/물리 SIM 결과가 아니다.

## S3 공개 API와 남은 연결

읽은 #394 소스: `e4b72aaffb0d756560397b7f0a30995da12da89f`. `harness/zone_s3_host.py`를 git object로 읽었으며 S3 브랜치/파일은 수정하지 않았다.
S4의 `S3Link`는 `OwnLink`의 다음 계약을 맞춘다.

- 짝 호출의 네 번째 고정 role 인자를 추가한다. S3 내부 cargoX 별칭은 ACK 원문에 남고 모델 명령 이력에는 공개 order-5를 쓴다.
- S3 절대 시각을 S4의 시작 이후 시각으로 바꾸고, 정지 판단은 자기 실행기의 절대 시각으로 되돌린다. nonzero 시작 시각 1.3초를 stub으로 검사했다.
- r3의 축약 ACK에 명령 시각/인자/ID를 채운다. r3 원시 pose dict를 닫힌 연구 belief에 넣지 않고 unknown skeleton으로 유지한다.
- S3가 아직 공개하지 않은 abort/hold/look_around는 실행기 호출 없이 `S3_API_UNAVAILABLE`로 거절한다. 두 정지 판단은 별도 #371 StopAdapter로 전달한다.

단, S3 `IntegratedTrial.begin`의 r3 자동 claim과 `Runtime._pair_claim → trial.claim`의 짝 자동 제출을 끄는 인계 API는 아직 없다. S4를 S3 Runtime.trial에 바로 대입해서 실행할 수 있다는 뜻이 아니다. 후속 통합은 자동 claim OFF, 최초 자기 frame 이후 Host.begin, 자기 executor와 자기 event의 전달이 필요하다. S3와 S4의 실행 책임은 그대로 분리한다. [S3 경계 코멘트](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/394#issuecomment-6009838255)에 공유했다.

`S3Link(s3.links[rid], condition=condition, executor=s3.pair.actors[rid] if rid in ('r1', 'r2') else None, origin_s=origin)`가 준비된 어댑터 경계다. 시험은 공개 OwnLink 계약을 흉내 낸 stub을 사용하며, 실제 S3 Runtime/provider/physics를 만들지 않는다. 새 CLI·실행 번들·workflow는 등록하지 않았다.

## 시험과 보존

세 번 모두 아래 세 파일을 끝까지 실행했다. `--maxfail` 옵션 없음.

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest \
  tests/test_pair_llm_s4_host.py tests/test_pair_llm_s4_routing.py \
  tests/test_pair_llm_decisions.py -q --junitxml=<각 새 출력 경로>/pytest.xml
```

| 재개 후 차수 | 결과 | 원인/범위 | 로컬 원본 (기본 checkout outputs 아래) |
|---|---|---|---|
| 1 | 7 failed, 34 passed in 1.39s | 요청한 미전송 검사는 통과. 새 JSON 저장 비교가 tuple/list 차이를 고려하지 않아 실패 | `s4-llm-offline-resume-20261006T141442/` |
| 2 | 41 passed in 1.26s | JSON 표준 변환에 맞춰 저장 상태 비교를 고침 | `s4-llm-offline-resume-20261006T141516/` |
| 3, 최종 | **45 passed in 1.38s**, exit 0 | 새로 올라온 S3 API 어댑터와 네 가지 추가 사례 포함 | `s4-llm-offline-resume-20261006T141809/` |

각 폴더의 pytest.log/pytest.xml/test_run.json 및 tmp 아래 합성 요청/응답·해시·원장을 보존한다. 통과 수는 차수끼리 합산하지 않는다. 마지막 시험 뒤 기능 코드를 바꾸지 않고 문서만 정리한다. 검증된 파일의 바이트 해시는 `offline_validation.json`에 기록한다. 커밋에는 Codex co-author trailer를 넣고 일반 push 뒤 해당 SHA의 CI를 확인한다. PR #395는 DRAFT 유지하며 병합하지 않는다.

## 참고 자료와 적용

재개 전 고전·최근 방법 조사는 [STOP_RECORD](STOP_RECORD.md#고전표준최근-방법-조사)에 보존한다: [Fowler Event Sourcing (2005)](https://martinfowler.com/eaaDev/EventSourcing.html)의 상태/사건 기록 구분, [pytest monkeypatch](https://docs.pytest.org/en/stable/how-to/monkeypatch.html)의 외부 경계 대체, [Hi Robot (2025)](https://arxiv.org/abs/2502.19417)의 상위/하위 판단 분리, [RoCo 공개 코드](https://github.com/MandiZhao/robot-collab/blob/main/prompting/dialog_prompter.py)의 거절/실행 허가 기록 분리를 따른다. 논문 성능 재현은 하지 않았다.
이번 JSON 비교 실패는 [Python json 공식 문서](https://docs.python.org/3/library/json.html)의 변환 예를 추가 확인했다(2026-10-06): tuple은 JSON array로 쓰이고 읽을 때 list가 된다. 메모리 원장은 변경하지 않고 기대값을 같은 JSON 데이터 형식으로 정규화해 비교했다.

새 실험·훈련·평가 결과가 없어 TensorBoard snapshot/서버를 만들지 않았다. UGRP 제외 규칙에 따라 Drive 사용 없음. 원본 삭제/덮어쓰기·강제 push/reset·병합 없음. S3 실제 연결, 실제 모델 no_comm 3 seed, 물리 완주와 S4 졸업은 남아 있다.
