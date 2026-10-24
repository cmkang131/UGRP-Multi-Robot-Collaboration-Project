# OFFLINE_GATE 개정 (2026-10-25) — G4 전이 계측 정합화

원본 `OFFLINE_GATE.md`는 변경하지 않는다. 이 문서는 G4 전이 재현율의 **계측 정의**만을
등록 정의에 맞게 정합화하는 개정 기록이다. 통과 기준값은 일절 바꾸지 않는다.

## 배경

- 2026-10-24~25 오프라인 게이트 실행 결과: validation 체크포인트 20개 전부 탈락,
  `selection.json` verdict `NOT_READY_NO_CHECKPOINT_PASSES`, `selected_step=null`.
- 전 체크포인트에서 G4의 `ready→execute` 전이가 `total=0`으로 기록됐다. 측정값이
  없으면 실패로 보는 등록 규칙에 따라, 이 항목 하나만으로 탈락한 체크포인트가
  6개(step 7000·9000·11000·13000·15000·19000, macro 정확도 0.93–0.97, 나머지 전
  항목 통과) 있었다.

## 근본 원인 (실측 확정)

- 등록 정의(G4)는 "validation의 실제 전이 뒤 10행 안에 도착 단계를 예측한 비율"이며
  '같은 segment 안의 전이만 센다'는 조건이 없다. 그러나 하네스 구현
  `transition_recall`은 인접 행의 segment id가 다르면 전이를 건너뛰었다.
- ready 구간은 에피소드당 1행뿐이고(validation 전체 25행), ready→execute 경계에는
  GO 대기 시간 간격이 항상 존재한다(실측 예: ready 행 t=11.8s → execute 첫 행
  t=19.9s, 약 8.1초). segment는 제어 주기와 어긋나는 시간 간격에서 끊기므로
  execute 첫 행은 항상 새 segment가 되고, 실제 전이 24건이 전부 미계수됐다.
- validation 실측(24 에피소드, 22,374행): GT 인접 전이는 alignment→ready 25,
  ready→execute 24, carry→place 24, place→complete 24건 존재한다. segment 조건을
  적용하면 ready→execute만 total=0이 되고, 나머지 3종은 조건 유무와 무관하게
  동일하다.

## 결정

- 2026-10-25 사용자 결정으로 계측 정합화 개정을 채택했다. 재학습·기준 변경이
  아니라, 구현을 등록 정의에 맞추는 정정이다.

## 개정 내용

- 개정은 실행기 `scripts/pairact_r1_offline.py`에만 들어간다. 하네스
  `harness/pairact_r1.py`는 **바이트 단위로 동결본 그대로**다(sha256
  `8a986924…`). 모든 체크포인트의 `adapter.json`이 이 파일의 sha256을 묶고 있어
  (`PairActActor.load`가 불일치 시 로드를 거부한다), 하네스를 고치는 구현은
  체크포인트를 아예 불러올 수 없었다 — 실제로 첫 구현이 이 검사에 걸려, 개정
  위치를 실행기로 옮겼다.
- 실행기에 `transition_recall_registered`를 추가했다: 전이 판정은 인접 행의
  **에피소드 동일성**(데이터셋 샤드 id; 샤드=에피소드임은 아래 감사로 확인)으로
  한다. `evaluate()`는 동결 하네스의 `offline_metrics`로 나머지 지표를 전부
  계산한 뒤 `transitions` 항목만 이 함수 결과로 교체한다.
- hit 판정 규칙은 기존과 동일하게 유지한다: 도착 행부터 10행까지(도착 행 포함
  0–10 오프셋) 창 안에서, 도착 행과 같은 segment인 행만 본다. 이 segment 제한은
  등록 문구를 무제한으로 읽는 것보다 좁은 셈이라 hit를 억제할 수는 있어도
  부풀리지는 않으며, 이번 개정이 새로 도입한 것이 아니다.
- 에피소드 경계(샤드 경계)의 단계 변화는 세지 않는다.

## 바꾸지 않은 것

- GATE 임계값 전부(전이 재현율 하한 0.80, 전이 창 10행 포함), '측정값이 없으면
  실패' 원칙, `gate()`, `select_checkpoint` 선택 규칙 — 전부 동결 하네스 안에
  그대로 있다.
- 학습 샘플러 `transition_row_weights`도 손대지 않았다.

## 검증

- 단위 테스트: `tests/test_pairact_r1.py`(동결본 그대로) +
  `tests/test_pairact_r1_offline.py`(신규 회귀 2건) = 14 passed, 2 skipped(기존
  skip). 회귀 테스트는 (1) 1행 ready + segment 분리 + 동일 에피소드에서 전이가
  세어지고, 동결 하네스 함수로는 total=0이며, 에피소드 경계에서는 세지 않는 것,
  (2) 같은 segment id라도 에피소드가 다르면 세지 않는 것을 확인한다.
- 실데이터 감사(완벽 예측으로 GT를 대입): segment id 범위는 샤드 간 겹치지
  않고(실행기가 샤드별 offset을 부여), 24개 샤드는 전부 approach로 시작해
  complete로 끝난다(샤드=에피소드). 전이 total은 기존/개정 계측이
  alignment→ready 25, carry→place 24, place→complete 24로 동일하고,
  ready→execute만 0→24로 달라진다.
- 리뷰 파이프라인: Codex 검토 2회 모두 `PASS_WITH_NOTES` (2026-10-25; 1차는
  하네스 내 구현, 2차는 실행기로 옮긴 최종 구현). 2차 지적 반영 — hit 창의
  기존 의미(0–10 오프셋·도착 segment 제한)를 이 문서에 명시했고, 선택은
  재평가한 7개 안에서의 선택이며 나머지 13개는 개정 계측으로 측정되지
  않았음을 적용 범위에 명시했다.

## 적용 범위

- 재평가는 보존된 체크포인트 7개(step 7000·9000·11000·13000·15000·17000·19000)에만
  적용한다. 나머지 13개의 가중치는 2026-10-25 승인된 gcp6 디스크 정리로 삭제돼
  개정 계측으로 다시 잴 수 없다. 따라서 선택이 일어나도 그것은 7개 안에서의
  선택이며, 원래의 20개 전체 선택 절차를 완결하는 것은 아니다.
- 개정 전 결과(`offline-gate/selection.json`, NOT_READY)는 그대로 보존하고,
  개정 후 결과는 별도 출력 디렉토리 `offline-gate-amended-20261025`에 기록한다.
  실행기 sha256은 실행마다 `selection.json` provenance에 기록된다(개정 전
  `08c2b874…` → 개정 후 실행기 해시로 교체 기록).
