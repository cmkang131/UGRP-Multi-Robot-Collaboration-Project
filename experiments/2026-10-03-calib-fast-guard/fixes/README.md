# PR #355 리뷰 수정 — DRAFT 유지

대상 구현 `54d5e28b3439a4ba3624d7fee01d02b083ac33ae`, 독립 검토
`fd1e82d2025097729b52efea8ff0dfaae3239f9c`의 P1a/R1·P1b/R2를 한 묶음으로 수정했다.
[원 검토](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/fd1e82d2025097729b52efea8ff0dfaae3239f9c/experiments/2026-10-03-calib-fast-guard/REVIEW_355.md).
이 기록의 파일별 해시는 커밋 전 통과한 소스를 식별하며, 실행 SHA는 이를 포함하는 최종 fixing commit이다.
PR은 draft로 유지하며 병합·새 수집을 수행하지 않는다.

## P1a / R1: 실제 legacy 바이트 복구

- `scripts/agent_lock.py`를 main `6f8460ad61ed858025a9e1d5d6ce77d7b92d9b1f`와 바이트 동일하게 복구했다.
  SHA-256: `709db3d87e4d2369171aba10ce3c64b7c8be254e2de7115ae608a022b1783dce`.
- `historical_lock_receipt`, heldout 테스트의 해시 치환, v84/v87 보존 검사의 lock 예외와
  `tests/agent_lock_successor.py`를 제거했다. 테스트 4개 파일도 main 바이트로 복구했다.
- v91 전용 `scripts/agent_sim_slots.py`는 v91 runner에서만 사용한다. 옛 lock 파일에 새 import가 없다.
- 리뷰의 `base-hashes.json`에서 출처·원본 해시를 명시한 fixture를 만들었다. v88 7개 + v90 2개 조합의
  **모든 source_sha256 항목**, bundle/plan writer 전체 바이트 해시와 파생 digest가 그대로인지 검사한다.
  필드를 무시하거나 해시를 치환하지 않는다. 새 모듈은 legacy closure에 없고 v91 closure에는 있다.

## P1b / R2: 옛 도구에서도 보이는 coordinator 소유권

- 첫 슬롯이 비어 있는 기존 `physics` 디렉터리를 legacy `acquire()`의 원자적 mkdir로 예약한다.
  기본 acquire와 timing-sensitive acquire 모두 슬롯이 먼저 들어간 경우에도 기존 도구에서 거부된다.
- 이미 physics 잠금이 있으면 **같은 owner·살아 있는 같은 coordinator PID·non-timing**이어야 한다.
  다른 owner와 시간측정 잠금은 거부한다. 허용 범위는 해당 owner의 비시간측정 SIM-time 작업뿐이다.
- coordinator는 모든 지도 자식이 끝날 때까지 살아 있고 physics를 유지해야 한다. 문서의 단일 bash
  coordinator가 두 슬롯/자식을 시작하고 모두 wait한 뒤 슬롯을 해제한다. 첫 슬롯 종료 시 잠금은 유지하고,
  마지막 슬롯만 자동 생성한 physics를 해제한다. 기존 잠금을 빌렸거나 소유권이 바뀌었으면 해제하지 않는다.
- live stale 해제, dead/incomplete/orphan 슬롯의 새 입장, 잘못된 PID·branch와 교체된 coordinator를 거부한다.
  실행 중 legacy release/--stale로 physics를 지우지 않는다. coordinator가 죽으면 자식 종료 확인 뒤
  새 모듈의 명시적 stale 해제로 복구한다. 기존 도구 자체는 바이트 보존 때문에 슬롯 정책을 알지 못한다.
- 현재 API 양쪽 획득 순서와 main SHA의 옛 timing acquire를 포함해 리뷰의 18개 실패 반례를
  xfail 없이 이식했다. 같은 owner의 두 슬롯·마지막 해제·borrowed lock 보존·경쟁·stale 검사를 추가했다.

## 보존·검증 범위

[검증 원값](verification.json), [보존 해시](preservation.json), [번호 확인](reservation.json),
[raw 재생](raw-equivalence.json)을 함께 보존한다. v91 / 3.3.0은 main과 열린 다른 PR에 충돌이 없다.
`.github/workflows` 변경은 없다. 관련 337 + CI 102 + workflow 3 = **442 passed**, 실패·skip·xfail 0이다.
초기 86개 검사는 최종 검사와 중복되어 합산하지 않는다. CI durations는 로컬 JUnit의 새 리뷰/슬롯
측정값만 반영했으며 **414/417 = 99.28%**다. 8 shard의 누락·중복 없는 배정도 확인했다.

완료 raw 두 개의 14,802행에서 가드 판정·최소 간격·abort·hold·eval_only 기록과 이전 좌표 바이트가
전부 일치했다. 원본은 읽기만 했고 guard/backend/verifier 소스는 리뷰 대상과 바이트 동일하다.
50 ms 순차 비교의 파일당 7,286개 변위 abort도 동일하다. 이는 0.25 ms 궤적 복원이 아닌 합성 검사다.
기존 CPU 측정 기록은 보존하고 새 속도 측정은 하지 않았다.

렌더링·모델 호출·새 코호트·공용 잠금 쓰기·기존 프로세스 조작은 하지 않았다.
raw·기존 실험 기록·workflow 파일은 보존했다. `/private/tmp` extraction 디렉터리는 만들지 않았고
이 작업 관련 extraction 잔여도 없음을 확인했다. 테스트 JUnit과 작은 JSON은 이 디렉터리에 보존한다.
코드 회귀/완료 raw 비교이므로 새 TensorBoard 변환·서버·화면은 만들지 않았다. Drive도 사용하지 않았다.

실제 두 지도 동시 수집, 처리율, criterion B 연결, 학생/실물 성공은 미검증이다.
동결 B의 v90/v91 거부와 #351/B의 파일별 source hash 대조 부재는 이번 잠금 수정 범위 밖이며 그대로다.
수정 후 독립 재검토가 필요하다. 실행 명령은 [PHYSICS_HANDOFF의 마지막 v91 절](../../../PHYSICS_HANDOFF.md)을 따른다.
