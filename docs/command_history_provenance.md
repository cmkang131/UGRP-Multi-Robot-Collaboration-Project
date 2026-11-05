# 발행 이력 출처 sidecar 계약 (ugrp.command_history.provenance.v2)

- 작성: UGRP-Pair, 2026-11-05
- 브랜치: `ugrp/issued-provenance-20261105T1902Z` (base `3cd3897d55a50ec02d9415d295072d9702dd0d4b`)
- 코드: `harness/command_history_provenance.py`, 시험 `tests/test_command_history_provenance.py`
- 성격: 비물리·오프라인 계약. GPU·모델 forward·SIM·물리·네트워크·설치 0.

## 1. 왜 별도 문서인가

기본 관측은 자기 RGB와 **자기 발행 명령 이력**이다. 발행 이력에는 서로 다른 사실이 섞여 들어간다.

| 사실 | 발행 명령인가 | 이 모듈의 대우 |
|---|---|---|
| 정책이 스스로 내린 정지(policy stop) | 예 | 발행 사실로 그대로 보존 |
| 프로토콜/GO-ACK 장벽이 기계적으로 낸 hold | 예 | 발행 사실로 그대로 보존 |
| 초기 16슬롯 중립 채움(padding) | 아니오 | sidecar 유효성 표시에만 기록 |

policy stop과 protocol_hold는 **둘 다 실제 발행 사실**이며, 이 둘을 동의어(실제 hold ↔ synthetic padding)로 쓰지 않는다. padding은 발행 명령이라고 주장하지 않고 유효성 마스크/출처 sidecar에만 표시하며, 이 메타데이터는 **모델 관측 dict에 주입하지 않는다**.

## 2. API

```python
from harness import command_history_provenance as p

sidecar = p.describe(raw_issued_window, origins=[...], padding_valid=[...])
p.validate_sidecar(raw_issued_window, sidecar)   # 라벨/길이/원시 일치 확인
p.resolve_prior(raw_issued_window, prior_command, origin='policy') # 과거 prior만 허용
p.fingerprint(raw_issued_window)                 # 원시 값 SHA256
p.copy_commands(raw_issued_window)               # alias 없는 독립 사본
```

- `origins`: 슬롯별 라벨. `'policy'`, `'protocol_hold'`, `'padding'`, `'unknown'`. 라벨이 없거나 `None`이면 `'unknown'`.
- `padding_valid`: 슬롯별 boolean. **`'padding'` 슬롯에만 참을 쓸 수 있다.** 미지정 시 전부 False(유효성 미주장).
- `describe`는 라벨·카운트·원시 해시만 담은 dict를 반환하고 **명령 객체를 담지 않는다**. 관측 스키마·rollout·기본 실행 경로는 건드리지 않는다.

### 반환 sidecar 필드

| 필드 | 뜻 |
|---|---|
| `schema` | `'ugrp.command_history.provenance.v2'` |
| `length` | 창 길이 |
| `origins` | 슬롯별 출처 라벨 |
| `issued` | 슬롯별 tri-state. 제공된 라벨 기준 주장(인증 아님). `True`=policy/protocol_hold, `False`=padding 및 padding_valid=True, `None`=unknown 또는 유효성 미주장 padding |
| `padding_valid` | 슬롯별 padding 유효성 주장 |
| `raw_sha256` | 원시 JSON 표기 SHA256 (일관성 비교용, 출처 인증 아님) |
| `counts` | 라벨별 개수 |

## 3. 계약 규칙

1. **원시 불변**: `describe`·`validate_sidecar`·`resolve_prior`는 호출자의 명령 목록과 각 dict를 변경하지 않는다. 검증은 `c.command()`로 계약 적합성만 확인하고, **정규화 객체로 원본을 대체하지 않는다.**
2. **정지·hold 보존**: 정지와 hold는 지우지도, 이동으로 바꾸지도, 라벨을 바꾸지도 않는다. `restore`류 복구 기능이 이 모듈에 없다.
3. **padding 분리**: padding은 `padding_valid=True`인 중립 슬롯에만 `issued=False`로 표시하고, 유효성 미주장이면 `issued=None`으로 남긴다. 원시 행은 창에 그대로 남고, 유효성은 sidecar에만 있다.
4. **unknown 유지**: 값·시각·반복만으로 라벨을 추정하지 않는다. 중립 바퀴라는 사실만으로 padding·policy 어느 쪽도 되지 않는다. `issued=None`은 미확인이며 False가 아니다.
5. **prior 경계**: `prior['t']`가 창 시작보다 크면 거부(`ProvenanceError`). 과거 또는 창 시작과 같은 시각의 prior는 허용되고, **그 prior가 실제 정지(바퀴 0)여도 정상 발행 명령으로 받아들인다.** 경계는 창 시작(`commands[0]['t']`) 기준이며 역순 창을 거부하고 같은 시각은 허용한다. 미래 prior 허용 오차는 없으며 `prior.t <= window_start`를 그대로 검사한다.
6. **sidecar 불일치 거부**: 저장 배열은 정확한 list, length와 counts는 bool이 아닌 int, counts는 정확한 키 집합·재계수 일치를 요구한다. 검증 성공 시 새 sidecar를 반환한다. padding_valid=True 슬롯의 바퀴·펄스폭이 모두 0이 아니면 거부한다.  라벨 목록·issued 목록·padding_valid 목록의 길이가 창 길이와 다르면 거부, 알 수 없는 라벨은 거부, padding이 아닌 슬롯의 `padding_valid=True`는 거부, 필드 화이트리스트 위반은 거부, `raw_sha256`가 다른 창은 거부.
7. **alias 방지**: sidecar는 명령 객체를 담지 않고, `copy_commands`는 독립 사본을 반환해 호출자가 원본을 바꿀 수 없게 한다.

## 4. 하지 않는 것 (범위 밖)

- 이력 수리·재라벨·치환 (기존 v1/v2 후보의 복제 아님).
- 관측 스키마(`harness/grasp_act_contract.py`), `grasp_act_rollout.py`, `beamact*`, 기존 rollout·기본 실행 경로 수정.
- 모델 입력 교체. 입력 변경은 다음 단계에서 **계약 버전·검토 대상**이며 이 모듈의 암묵적 동작이 아니다.
- 원격 병합·release·배포. 배포된 경로·시점·채택 여부는 별도 검토 대상.

## 5. 최소 비물리 검사 (실행 결과)

```
cd <worktree> && PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 \
  python3 -m unittest tests.test_command_history_provenance -v
```

- 종료 코드 0, `Ran 39 tests ... OK` (2026-11-05, worktree 경로 고정).
- 커버: policy stop 보존, protocol_hold 보존, padding sidecar 분리·유효성 미주장, unknown 유지, prior 경계(미래 거부·과거 정지 허용·창 시작 동일 허용), sidecar 길이/라벨/필드 불일치 거부, 원시 값·해시 불변, alias 방지.

## 6. 미확인

- `origins`/`padding_valid`를 **실제로 누가 어떤 시점에 채우는지**는 이 후보에서 정하지 않았다. 관측 기록자·runner 배치는 다음 단계다.
- 실제 issued 명령에 붙는 라벨 분포(정지/hold/padding 실제 비율)는 관측 기록이 없어 미확인. 이 문서는 코드 계약이며 실험 결과가 아니다.
- 본 문서의 검사는 합성·단위시험이며 실제 운반 성공·물리·모델 성능을 주장하지 않는다. 과거 GPU 0/4 실패의 원인으로 일반화하지 않는다.


## 7. 독립 감사 반영 — Ugrp, 2026-11-05

- `validate_sidecar`는 저장된 `origins`/`issued`/`padding_valid`에 정확한 list와 고정 길이를 요구한다. origins는 명시적 문자열만 허용한다. `None` 기본값은 `describe` 입력에만 허용되며 저장된 배열을 대신하지 않는다.
- `length`와 counts 값은 bool/float가 아닌 int다. counts는 정확한 키 집합과 배열에서 다시 센 값이 일치해야 한다. 추가 명령 객체나 집계 불일치는 거부한다. 검증 성공 시 모든 가변 필드가 분리된 새 sidecar를 반환한다.
- 원시 이력 시간은 비감소 순서여야 한다. 같은 시각의 초기 padding은 허용하지만 역순 창은 거부한다. prior 경계는 최초 슬롯이며 미래 허용 오차를 두지 않는다.
- `resolve_prior(..., origin='unknown')`은 기본적으로 명령 형식과 시간 경계만 검사한다. **실제 발행 인증이 아니다.** 명시적으로 padding인 prior는 거부한다. policy/protocol_hold 출처는 실제 기록 생산자가 확인해야 한다.
- SHA256은 원시 JSON 값/표기의 비교용 digest다. `0`과 `0.0`은 다른 원시 표기이므로 해시도 다르다. 정규화된 사본을 원본으로 주장하지 않는다. 서명이나 출처 인증이 아니며 숫자 정규화 해시로 대체하지 않는다.

### 감사에서 채택하지 않은 제안과 남은 생산자 계약

출처를 명령값으로 추론하는 규칙은 추가하지 않았다. 실제 정지와 초기 padding은 값이 같을 수 있으며, sidecar에 `padding`이라고 적는 것만으로 과거 발행 사실이 검증되지는 않는다. `issued`는 **제공된 라벨의 주장에 따른 삼상태**이며 출처가 없으면 unknown을 유지한다. 이 모듈은 라벨을 스스로 바꾸거나 독립적으로 인증하지 않는다. 따라서 모순 없는 sidecar를 만들 수 있다는 사실이 참된 출처의 증거는 아니다.

다음 연결 단계에서는 초기화·실제 발행·프로토콜 hold 사건을 생산 시점에 기록하고, 이력과 동일한 인덱스로 결합해야 한다. 이미 저장한 출처를 사후 덮어쓰는 경로를 막고 실행/관측 ID 및 원시 해시와 묶는다. 이 생산자 기록 없이 padding 라벨을 근거로 실제 issued를 제거하거나 모델 입력을 치환해서는 안 된다. 단순히 0인 바퀴를 검사하거나 새로운 source 문자열을 받는 것은 이 증거를 대체하지 못한다.

검토서의 int/float 해시 동일화 제안은 원시 표기 보존과 충돌하여 채택하지 않았다. sidecar의 일관성 검증과 발행 사실 인증을 구분하며, 실제 생산자 연결은 아직 미구현이다.

### 수정 후 한정 검사

Ugrp가 기존 24개와 감사 회귀 12개, 총 **36 tests / OK / exit 0**을 실행했다. 집계값 위조·객체 삽입, 반환 sidecar 변경 후 원본 불변, 저장 배열/정수 타입, 역순 창, 동일 시각 창, 미래 prior, 원시 표기 해시, padding prior 거부를 포함한다. 기존 4개 조정자 probe도 모두 `ProvenanceError`로 바뀌었다. 이 결과는 합성 CPU 검사이며 수정 후 독립 재검토는 별도다.

## 8. 패딩 일관성 보완 (v2)

36개 검사 수정본은 Verify가 독립 실행·45항목 프로브로 조건부 수용했다. 이어 권고 F2a를 반영했다. v2는 유효 padding 주장에 중립 바퀴·펄스폭을 요구하고, padding 라벨만 있고 유효성 미주장인 슬롯은 issued=None으로 남긴다. 값으로 출처를 새로 추론하지 않으며 PWM 중립값은 정하지 않는다. 삼상태 의미가 바뀌므로 sidecar schema를 v2로 올렸다. 모델 관측 schema·값에는 변화가 없다.

기존 36 + 패딩 회귀3 = 39 tests. 이전 독립 수용은 43d0d8c84의 36개 검사 버전에만 적용하며, 이 v2 보완본의 별도 독립 재검토는 아직 미수행이다. 생산자 연결 시 실행/관측 ID 및 이벤트 순번·창 오프셋 검증을 추가해야 한다.
